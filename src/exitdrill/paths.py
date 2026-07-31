"""Bounded attachment access."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import BinaryIO

_OPEN_SUPPORTS_DIR_FD = os.open in os.supports_dir_fd


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
    windows_requested = PureWindowsPath(relative_path)
    if requested.is_absolute() or windows_requested.is_absolute() or windows_requested.drive:
        raise BoundedPathError("attachment path must be relative")
    resolved_root = root.resolve(strict=True)
    candidate = (resolved_root / requested).resolve(strict=True)
    if not candidate.is_relative_to(resolved_root):
        raise BoundedPathError("attachment path escapes its declared root")
    if not candidate.is_file():
        raise BoundedPathError("attachment path is not a regular file")
    return candidate


def _sha256_stream(handle: BinaryIO, *, expected_size: int) -> str:
    digest = hashlib.sha256()
    remaining = expected_size
    while remaining:
        chunk = handle.read(min(64 * 1024, remaining))
        if not chunk:
            raise BoundedPathError("attachment changed size while being read")
        digest.update(chunk)
        remaining -= len(chunk)
    if handle.read(1):
        raise BoundedPathError("attachment changed size while being read")
    return digest.hexdigest()


def _open_beneath(root: Path, path: Path) -> int:
    """Open a resolved child without following swapped parent components where supported."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not _OPEN_SUPPORTS_DIR_FD or not nofollow or not directory:
        return os.open(path, os.O_RDONLY | nofollow)
    resolved_root = root.resolve(strict=True)
    try:
        parts = path.relative_to(resolved_root).parts
    except ValueError as exc:
        raise BoundedPathError("attachment path escapes its declared root") from exc
    if not parts:
        raise BoundedPathError("attachment path is not a regular file")
    parent = os.open(resolved_root, os.O_RDONLY | directory | nofollow)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | directory | nofollow, dir_fd=parent)
            os.close(parent)
            parent = child
        return os.open(parts[-1], os.O_RDONLY | nofollow, dir_fd=parent)
    finally:
        os.close(parent)


def sha256_bounded_file(
    root: Path,
    relative_path: str,
    *,
    max_bytes: int,
    total_budget: ByteBudget | None = None,
) -> str:
    """Hash one bounded file through the same descriptor used for size checks."""
    path = resolve_bounded_file(root, relative_path)
    try:
        descriptor = _open_beneath(root, path)
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
        return _sha256_stream(handle, expected_size=metadata.st_size)
