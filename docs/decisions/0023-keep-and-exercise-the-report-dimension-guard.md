# ADR-0023: Keep and exercise the report dimension guard

**Status:** Accepted

**Date:** 2026-08-27

**Deciders:** Chelsea Kelly-Reif

## Context

Issue #55 asked whether the malformed-dimension guard in `report.py`'s
`_dimension_rows` is reachable, and framed it as an investigate-then-decide
task rather than a test to write.

The reachability finding is confirmed, by reading and by measurement.
`_dimension_rows` has exactly one caller, `render_receipt_report`, which is
also the only thing `render_receipt_file` calls. `render_receipt_report` runs
`verify_receipt(receipt)` as its first statement. That reaches
`validate_payload`, which routes every entry of `payload["dimensions"]` through
`_validate_dimension` and then `_object`, and `_object` rejects a non-dict
entry. `render_receipt_report` then reads that same already-validated list.

Measured directly against the committed fixtures, replacing a dimension with a
string, a list, or `None`, and appending a bare integer as a sixth entry, all
four attempts were stopped by `verify_receipt`:

```
dimension replaced by a string     -> ReceiptError: receipt payload dimensions[0] must be an object
dimension replaced by a list       -> ReceiptError: receipt payload dimensions[0] must be an object
dimension replaced by None         -> ReceiptError: receipt payload dimensions[0] must be an object
extra non-dict appended            -> ReceiptError: receipt payload dimensions[5] must be an object
```

The issue offered two resolutions: delete the guard, or keep it and mark it
`# pragma: no cover` with an explanation.

## Decision

Keep the guard, and take neither of the two offered options. Instead:

1. **Comment it** with the chain that makes it unreachable today, so the next
   reader does not have to re-derive it.
2. **Exercise it directly** with unit tests that call `_dimension_rows` with a
   non-dict entry, alongside a positive-path test so the guard tests cannot
   pass against a function that raised for everything.
3. **Pin the ordering the finding depends on.** A separate test requires
   `render_receipt_report` to raise `ReceiptError` rather than `ReportError`
   for a malformed dimension, at position 0 and at an appended position 5. If
   verification ever stops running first, the guard becomes reachable and that
   test says so, instead of the finding in this ADR silently going stale.

## Options considered

- **Delete the guard:** rejected. `_dimension_rows` declares
  `list[JsonValue]`, and `JsonValue` includes non-dict members, so the guard is
  the contract that parameter type states. Deleting it does not remove the
  possibility of a bad entry; it converts a named `ReportError` into a
  `KeyError`, or worse into a silently malformed table, for any future caller
  that renders rows from a list this module did not verify.
- **Keep it and mark it `# pragma: no cover`:** rejected, and this is the
  substantive part of the decision. A pragma leaves a guard in the tree that
  has never been observed to fire, which is exactly the defect ADR 0021 and ADR
  0022 exist to remove, arriving by a different route. Coverage would report
  100% for a line nothing has ever executed. Exercising the function directly
  costs five parametrized cases and produces a check that has been shown to
  work.
- **Reach it through the public path by weakening verification:** rejected.
  That would make the guard reachable by making the product worse.

## Consequences

- `report.py` reaches 100% branch coverage without a pragma.
- The precedent this follows is already in the tree.
  `civicrm_target_canary._target_result` carries a comment saying its `fail`
  branches are unreachable through the public entry point and are exercised
  directly by unit tests with fabricated inputs. This decision applies the same
  answer to the same question, so the codebase has one rule for it rather than
  two.
- The reachability claim is now enforced rather than asserted. A change that
  reorders `render_receipt_report` fails the merge gate.
- `cli.py`'s trailing `return 2`, after argparse has already rejected every
  unknown command, is the one remaining branch of this shape. It is left
  uncovered and unclaimed rather than pragma'd, because it is unreachable for a
  different reason (argparse, not a call ordering inside this codebase) and has
  no function-level contract of its own to exercise. Recorded here so it is a
  known open item and not an oversight.
