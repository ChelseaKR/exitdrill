"""Shared fail-closed JSON decoding and shape validation."""

from __future__ import annotations

import json
import math
import os
import stat
from collections.abc import Mapping
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


def require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    context: str,
    error: type[Exception],
) -> None:
    """Reject a mapping whose key set is not exactly `expected`.

    Closed-key rejection is how every document parser here refuses a field it
    does not understand, and it used to be copied into four modules that
    differed only in the exception they raised. `error` is the caller's own
    exception type, bound once by a module-local alias so call sites stay three
    arguments wide.

    Both messages are part of the contract: tests match "unknown field(s)" and
    "missing field(s)" by name, and unknown is reported before missing so that
    a document with both faults names the extra field first. Field names are
    safe to echo here because `expected` and the document's own keys are the
    only text either message can contain.

    The two canaries deliberately do not use this. `directus_canary._exact_keys`
    and `civicrm_target_canary._exact_keys` compare the key sets in one step and
    report "has an invalid field set", naming no field; their tests assert that
    wording, so they are a different check rather than a fifth copy of this one.
    """
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise error(f"{context} has unknown field(s): {', '.join(unknown)}")
    if missing:
        raise error(f"{context} is missing field(s): {', '.join(missing)}")


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
    document_label: str = "document",
) -> tuple[object, str]:
    """Read and decode one bounded JSON document from a single byte snapshot.

    An `OSError` from the resolve, open, or read below escapes unwrapped, and
    that split is load-bearing: callers separate "could not be read" from "was
    read and is not acceptable JSON". `loader._load_object` catches only
    `StrictJsonError`, `comparison.load_receipt_snapshot` catches `OSError`
    separately to give it its own non-disclosing message, and `cli.main`
    catches `OSError` at the top level.

    `document_label` names what the caller is loading, so a rejection reads
    "receipt exceeds the 2 MiB limit" rather than the generic noun. Callers
    used to patch that noun in afterwards with `str(exc).replace(...)`, a
    string-literal coupling across a module boundary that nothing bound
    (issue #85): rewording a message here matched nothing there and silently
    reverted the caller to the generic wording. Composing the message at the
    raise site is the same shape the two canaries' `where` parameter already
    uses. The label must stay a caller-supplied constant -- never a path or
    other input-derived text, which these messages deliberately withhold.
    """
    resolved = path.resolve(strict=True)
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(resolved, flags)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise StrictJsonError(f"{document_label} path is not a regular file")
        document = handle.read(max_bytes + 1)
    if len(document) > max_bytes:
        raise StrictJsonError(f"{document_label} exceeds the {size_label} limit")
    try:
        text = document.decode("utf-8")
        raw = json.loads(
            text,
            object_pairs_hook=_object_from_pairs,
            parse_constant=_reject_constant,
        )
        validate_json_value(raw)
    except UnicodeDecodeError as exc:
        raise StrictJsonError(f"{document_label} is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise StrictJsonError(f"{document_label} is not valid JSON: {exc}") from exc
    except RecursionError as exc:
        raise StrictJsonError("JSON nesting exceeds the parser limit") from exc
    except ValueError as exc:
        if isinstance(exc, StrictJsonError):
            raise
        raise StrictJsonError(f"{document_label} is not valid JSON: {exc}") from exc
    return raw, sha256_bytes(document)
