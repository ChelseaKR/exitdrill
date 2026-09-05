"""Shared closed-key contracts for the project's parsers.

Closed-key rejection is how every parser here refuses input it does not
understand: a mapping whose key set is not exactly the expected set is
rejected outright rather than silently ignored or defaulted. Six modules
each carried their own copy of that check, so a wording or ordering change
had to land in six places and any one copy could quietly diverge from the
rest.

Two variants live here because the six copies were not identical, and the
difference is load-bearing rather than drift:

- `require_exact_keys` names the offending fields. Its callers parse
  documents whose key names are part of the contract the operator wrote
  against, so saying which field is unknown or missing is most of the value
  of the message. Several tests assert that wording.
- `require_exact_key_set` names none of them. Its callers are the two
  canaries, which verify captures taken from a deployment they do not
  control; their messages consistently avoid echoing input-derived text, the
  same constraint `strict_json.load_strict_json` documents for its
  caller-supplied `document_label`. Their tests assert the terse wording.

Collapsing the two would either drop detail the first group asserts on or
push capture-derived text into canary messages, so the split is kept and
stated here instead of being left to drift.

Both take the exception type as a parameter so each module keeps raising its
own error class; each module binds that with a small module-local alias, and
call sites are unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Set as AbstractSet


def require_exact_keys(
    value: Mapping[str, object],
    expected: AbstractSet[str],
    context: str,
    error: type[Exception],
) -> None:
    """Reject `value` unless its keys are exactly `expected`, naming what differs.

    Unknown fields are reported before missing ones, each sorted, so the same
    malformed document always produces the same message.
    """
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise error(f"{context} has unknown field(s): {', '.join(unknown)}")
    if missing:
        raise error(f"{context} is missing field(s): {', '.join(missing)}")


def require_exact_key_set(
    value: Mapping[str, object],
    expected: AbstractSet[str],
    where: str,
    error: type[Exception],
) -> None:
    """Reject `value` unless its keys are exactly `expected`, naming no field.

    For callers whose keys come from a captured remote response and so must
    not be echoed back into a message; see the module docstring.
    """
    if set(value) != set(expected):
        raise error(f"{where} has an invalid field set")
