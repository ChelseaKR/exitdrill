"""Canonical JSON and content hashing."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

# Unanchored, and always applied with `fullmatch`. Anchoring as well would put
# two mechanisms on one bound and leave a reader guessing which is load-bearing.
_SHA256_HEX_PATTERN = re.compile(r"[0-9a-f]{64}")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize JSON-shaped data deterministically."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a file without retaining its content."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_sha256_hex(value: str) -> bool:
    """Report whether a string is a lowercase SHA-256 digest.

    The predicate that recognises the two functions above lives beside them so
    that "digest shape" has one answer. Callers state their own rejection
    message; this reports only the shape.
    """
    return _SHA256_HEX_PATTERN.fullmatch(value) is not None
