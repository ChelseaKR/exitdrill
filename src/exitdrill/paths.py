"""Bounded attachment access."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class BoundedPathError(ValueError):
    """Raised when an attachment path escapes the declared root."""


@dataclass(slots=True)
class ByteBudget:
    """Track cumulative attachment bytes before any bounded read."""

    limit: int
    consumed: int = 0

    def consume(self, size: int) -> None:
        if size < 0 or self.consumed + size > self.limit:
            raise BoundedPathError("attachments exceed the total byte limit")
        self.consumed += size


def resolve_bounded_file(root: Path, relative_path: str) -> Path:
    """Resolve an existing regular file beneath a strict root."""
    requested = Path(relative_path)
    if requested.is_absolute():
        raise BoundedPathError("attachment path must be relative")
    resolved_root = root.resolve(strict=True)
    candidate = (resolved_root / requested).resolve(strict=True)
    if not candidate.is_relative_to(resolved_root):
        raise BoundedPathError("attachment path escapes its declared root")
    if not candidate.is_file():
        raise BoundedPathError("attachment path is not a regular file")
    return candidate


def _sha256_stream(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(64 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_bounded_file(
    root: Path,
    relative_path: str,
    *,
    max_bytes: int,
    total_budget: ByteBudget | None = None,
) -> str:
    """Hash one bounded file through the same descriptor used for size checks."""
    path = resolve_bounded_file(root, relative_path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BoundedPathError("attachment could not be opened safely") from exc
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise BoundedPathError("attachment path is not a regular file")
        if metadata.st_size > max_bytes:
            raise BoundedPathError("attachment exceeds size limit")
        if total_budget is not None:
            total_budget.consume(metadata.st_size)
        return _sha256_stream(handle)
