# ADR-0021: Gate record-value disclosure on the synthetic demo

**Status:** Accepted

**Date:** 2026-08-27

**Deciders:** Chelsea Kelly-Reif

## Context

Invariant 7 in `AGENTS.md` says receipts contain aggregates and hashes, never
record fields or attachment contents. The README repeats it under "Receipts and
trust", and ADR 0003 relies on it: comparison deferred record-identity matching
"because receipts intentionally contain no record-level identifiers". It is one
of the few properties this project asserts about what its output does *not*
contain, so nothing downstream re-derives it.

Both real-process canaries enforce it for themselves.
`scripts/check_directus_canary_demo.py` and
`scripts/check_civicrm_target_roundtrip_demo.py` each scan their aggregate
output for a hand-written `_RAW_SENTINELS` tuple.

The flagship `examples/synthetic-crm` path had no equivalent. That is the path
the README leads with, that `make demo-compare` produces, and whose rendered
report the usability gate in issue #51 asks outside testers to open in a
browser. The closest thing was three string literals inside one report test:
`"Synthetic Person"`, `"person-001"`, and one timestamp, asserted absent from
the rendered HTML only, with the receipt and comparison documents unchecked.

Two weaknesses follow from a hand-written needle list, and they compound:

1. Nothing binds the literals to the fixtures. Rename a fixture value and the
   assertions stay green while searching for a string that exists nowhere. The
   check does not fail; it stops being a check, and reports success either way.
2. Three literals out of the fixtures' twenty-four record values leaves most of
   the invariant ungated. Measured directly: leaking the permission principal
   `worker-001` into every receipt, report, and comparison document left all
   492 pre-existing tests passing.

## Decision

Add `tests/test_disclosure.py`, a merge-gating check that no aggregate artifact
republishes a record-level value, built so that it cannot quietly stop
checking.

1. The corpus is derived from the committed fixture files, not written down.
   `record_values` reads `baseline.json`, `export.json`, and the attachment
   bytes, and returns each value mapped to its provenance.
2. The corpus is proved real before it is trusted. Every derived value must
   occur verbatim in the input bytes, so a fixture rename fails the gate loudly
   instead of emptying it.
3. The five artifacts `make demo-compare` produces are all covered: both
   receipts, both HTML reports, and the comparison document.
4. Values are searched for in literal and HTML-escaped form, so `report.py`'s
   escaping cannot act as a bypass for exactly the characters that make a value
   dangerous.
5. Values that ExitDrill's own vocabulary already contains are computed, not
   hardcoded. A control receipt with placeholders in both free-text payload
   fields is rendered through the same path; anything appearing in that output
   came from the format rather than from a fixture. Two values qualify today,
   `case` (inside the stylesheet's `uppercase`) and `exported` (inside
   `exported_count`), and the set is pinned so a change is reviewed.
6. The gate is shown to fire. Injecting real record values into the receipt,
   the report, and the comparison document must produce a finding in each.

## Options considered

- **Extend the three literals:** rejected. It scales the coverage problem
  without touching the vacuity problem, which is the more dangerous of the two.
- **Reuse the canaries' `_RAW_SENTINELS` shape:** rejected for the same reason.
  Those tuples have the same defect; they are acceptable there only because a
  canary's fixtures are pinned to one captured profile. This decision does not
  change them, and they remain worth revisiting.
- **Scan for every token rather than whole values:** rejected. It would catch a
  fragment of a leaked value, but it drags common English words into the
  indistinguishable set and weakens the exact pin that makes the exclusion
  reviewable. Whole-value republication is what the invariant is about.
- **Make it a runtime CLI check:** rejected. Feature scope is paused per
  `docs/ROADMAP.md` until the usability gate closes. A regression gate is not a
  feature and does not reopen that boundary.
- **A length threshold instead of a control:** rejected. It would have excluded
  `case` and `open` for being short while `person`, equally short, is genuinely
  checkable. Length is a proxy; presence in the control is the actual property.

## Consequences

- The invariant the README states publicly is now enforced on the path the
  README leads with, and enforced by `make verify` rather than by review.
- A change that starts putting record identifiers into a receipt, a report, or
  a comparison document fails the merge gate with the value and its provenance
  named.
- The gate covers whole record values only. A leak of a fragment of one value,
  such as the first half of the attachment text, would not be caught. This is
  a stated boundary, not an oversight.
- The gate reads the fixture documents directly rather than through
  `load_baseline` and `load_export`, so narrowing the loaders cannot narrow
  what counts as record data.
- The two canaries keep their hand-written sentinel tuples. This decision does
  not claim to have fixed them.
- Adding record data to a fixture may require raising the pinned corpus floor
  or reviewing the indistinguishable set. Both are deliberate review points.
