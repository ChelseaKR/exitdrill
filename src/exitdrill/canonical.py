"""Canonical JSON and content hashing."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

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
    """Return whether `value` is a lowercase hex SHA-256 digest.

    This recognises exactly what `sha256_bytes` and `sha256_file` emit, which
    is why it lives beside them. Three modules previously each answered this
    question their own way -- two byte-identical anchored regexes and one
    hand-rolled length-plus-character-membership check -- so a change to what
    counts as a digest had three places to land.

    The pattern is unanchored and matched with `fullmatch`, rather than
    anchored *and* matched with `fullmatch`, so there is only one thing making
    the match total.
    """
    return _SHA256_HEX_PATTERN.fullmatch(value) is not None
