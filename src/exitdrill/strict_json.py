"""Shared fail-closed JSON decoding and shape validation."""

from __future__ import annotations

import json
import math
import os
import stat
from pathlib import Path

from exitdrill.canonical import sha256_bytes

_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 200_000


class StrictJsonError(ValueError):
    """Raised when JSON is ambiguous, unsafe, or outside declared bounds."""


def _reject_constant(value: str) -> object:
    raise StrictJsonError(f"non-finite number is not permitted: {value}")


def _object_from_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError("duplicate object key is not permitted")
        result[key] = value
    return result


def validate_json_value(
    value: object,
    *,
    max_depth: int = _MAX_JSON_DEPTH,
    max_nodes: int = _MAX_JSON_NODES,
) -> None:
    """Reject non-finite floats and JSON beyond declared depth/node bounds."""
    stack: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise StrictJsonError(f"JSON exceeds the node limit of {max_nodes}")
        if isinstance(current, float) and not math.isfinite(current):
            raise StrictJsonError("non-finite number is not permitted")
        if isinstance(current, dict):
            if depth >= max_depth:
                raise StrictJsonError(f"JSON nesting exceeds the depth limit of {max_depth}")
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            if depth >= max_depth:
                raise StrictJsonError(f"JSON nesting exceeds the depth limit of {max_depth}")
            stack.extend((item, depth + 1) for item in current)


def load_strict_json(
    path: Path,
    *,
    max_bytes: int,
    size_label: str,
) -> tuple[object, str]:
    """Read and decode one bounded JSON document from a single byte snapshot."""
    try:
        resolved = path.resolve(strict=True)
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved, flags)
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise StrictJsonError("document path is not a regular file")
            document = handle.read(max_bytes + 1)
    except OSError:
        raise
    if len(document) > max_bytes:
        raise StrictJsonError(f"document exceeds the {size_label} limit")
    try:
        text = document.decode("utf-8")
        raw = json.loads(
            text,
            object_pairs_hook=_object_from_pairs,
            parse_constant=_reject_constant,
        )
        validate_json_value(raw)
    except UnicodeDecodeError as exc:
        raise StrictJsonError("document is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise StrictJsonError(f"document is not valid JSON: {exc}") from exc
    except RecursionError as exc:
        raise StrictJsonError("JSON nesting exceeds the parser limit") from exc
    except ValueError as exc:
        if isinstance(exc, StrictJsonError):
            raise
        raise StrictJsonError(f"document is not valid JSON: {exc}") from exc
    return raw, sha256_bytes(document)
