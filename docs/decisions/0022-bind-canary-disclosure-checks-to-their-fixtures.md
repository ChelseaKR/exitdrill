# ADR-0022: Bind the canary disclosure checks to their fixtures

**Status:** Accepted

**Date:** 2026-08-27

**Deciders:** Chelsea Kelly-Reif

## Context

ADR 0021 gated record-value disclosure on the `examples/synthetic-crm` demo
path and recorded one thing it deliberately did not fix:

> The two canaries keep their hand-written sentinel tuples. This decision does
> not claim to have fixed them.

Those tuples are `_RAW_SENTINELS` in `scripts/check_directus_canary_demo.py`
(five values) and in `scripts/check_civicrm_target_roundtrip_demo.py` (seven).
Each canary scans its aggregate output for them. Both have the two defects ADR
0021 named for the literals it replaced, and they compound the same way.

1. **Nothing binds a sentinel to a fixture.** Rename a captured value and the
   scan keeps running, searching for a string that exists nowhere, and reports
   success. Measured: changing one sentinel in each script to a value no longer
   present left all 510 pre-existing tests passing and both offline acceptance
   summaries byte-identical.
2. **Twelve literals do not cover the captures.** The Directus bundle carries
   22 distinct record values and the CiviCRM bundle 23. Case subjects,
   relationship descriptions, target file names, and the rendered contact label
   in `ui-contact-summary.json` are all outside both tuples. Measured: leaking
   the relationship type `assigned_to` into the Directus normalization manifest
   left all 510 pre-existing tests passing, and both
   `make demo-directus-canary` and `make demo-civicrm-target-canary` exiting 0
   with unchanged summaries.

This is the same class of defect the disclosure gate was built to remove, one
level up: a check that reports a clean result whether or not it is still
checking anything.

## Decision

Add `tests/test_canary_disclosure.py`, applying ADR 0021's method to both
real-process canaries and adding the binding those tuples never had.

1. **The corpus is derived, not written down.** A declared field table per
   canary names which fields of which captured file carry record data.
   `directus_record_values` and `civicrm_record_values` read the committed
   native bundles through it and return each value mapped to its provenance.
2. **The corpus is proved real before it is trusted.** Every derived value must
   occur verbatim in the capture bytes, so a fixture rename fails the gate
   loudly instead of emptying it.
3. **The field table is proved complete.** Every file in each native bundle is
   either in the record-field table or in an explicit non-record table with a
   stated reason, so a capture file added later cannot be skipped in silence.
4. **Every aggregate artifact is covered.** For Directus: the returned
   normalization aggregate, `normalization-manifest.json`, the receipt, the
   rendered report, and a comparison document. For CiviCRM: the returned
   aggregate, the twelve documents written beside the normalized export, the
   evidence-index verification document, and the structural payload the
   unchanged evaluator produces. The normalized `export.json` and its
   attachment files are excluded on purpose and the exclusion is proved to be
   about the right file.
5. **Values are searched in literal and HTML-escaped form**, so escaping cannot
   act as a bypass for exactly the characters that make a value dangerous.
6. **The undecidable values are computed, not hardcoded.** A control is built
   from two derived parts: the packaged schemas' declared vocabulary (property
   names, `const`, `enum`, `required`, titles, ids, formats, patterns, with
   prose descriptions left out) and the aggregates' own counts and SHA-256
   digests. A record value found in either cannot be attributed to the fixture.
   Five values qualify for Directus and four for CiviCRM; both sets are pinned
   so a change is reviewed.
7. **The hand-written tuples are bound.** Every sentinel in both scripts must
   appear in a corpus that was itself proved against the capture bytes. A
   fixture rename now breaks the tuple loudly.
8. **The gate is shown to fire**, for every artifact and for every checkable
   corpus value, not for one representative needle.

## Options considered

- **Rewrite the scripts to derive their own sentinels:** rejected for now. The
  scripts are the `make demo-*-canary` acceptance path and their summaries are
  pinned byte for byte by `tests/test_directus_demo.py` and
  `tests/test_civicrm_target_demo.py`. Binding the tuples from the merge gate
  gets the anti-vacuity property without touching an acceptance path, and
  leaves the scripts' own scans in place as a second, independent check.
- **Add the missing values to the two tuples:** rejected, for the reason ADR
  0021 gave. It scales the coverage problem without touching the vacuity
  problem, which is the more dangerous of the two.
- **Scan the normalized `export.json` too:** rejected. It is the evaluator's
  record-level input contract; carrying record data is what it is for. A gate
  that flagged it would be reporting the design as a defect.
- **Extend the Directus script to scan `normalization-manifest.json`:**
  rejected as unnecessary. `normalize-directus-canary` prints the aggregate,
  the printed aggregate equals the written manifest (pinned by
  `test_printable_result_and_written_manifest_are_aggregate_hash_only`), and
  the script already scans command output. The manifest was already in scope;
  what it lacked was needles, not reach.
- **A length or shape heuristic for undecidable values:** rejected, as in ADR
  0021. `Cases` and `Open` are short, ordinary English words that stay inside
  the gate because the control does not contain them. Presence in a derived
  control is the actual property; length is a proxy for it.
- **Share `search_forms` and `_found_in` with `tests/test_disclosure.py`:**
  rejected. Pytest's `--import-mode=importlib` puts no shared `tests/` helper
  module on the import path, so this would need a `pythonpath` entry plus an
  `mypy_path` entry to stay type-checked under strict mypy. Two four-line
  helpers restated with a cross-reference costs less than repackaging the test
  suite. Recorded here so the duplication is a decision rather than drift.

## Consequences

- Invariant 7 is now enforced by `make verify` on all three paths the project
  publishes: the synthetic demo, the Directus source canary, and the CiviCRM
  target canary.
- A fixture rename that is not propagated to a canary's sentinel tuple now
  fails the merge gate naming the stale sentinel, instead of silently
  converting the scan into a no-op.
- The CiviCRM aggregate documents turned out to be closed by `const` in their
  packaged schemas, so most of that canary's residual leak surface is the
  structural payload and the evidence-index verification document. Both are now
  scanned against 23 derived values rather than 7 literals.
- The gate compares whole values in literal and HTML-escaped form. A leaked
  fragment of one value is still not caught. ADR 0021 stated that boundary and
  this decision does not change it; scanning tokens would drag common English
  words into the undecidable set and weaken the exact pin that makes the
  exclusion reviewable.
- The two scripts keep their tuples and keep scanning for them. This decision
  makes those scans non-vacuous; it does not make them sufficient, and the
  merge gate rather than the acceptance script is now the authority on
  coverage.
- Adding record data to a capture may require raising a pinned corpus floor or
  reviewing an undecidable set. Both are deliberate review points.
- This is a regression gate, not a feature. It adds no connector, evidence
  family, or data category, so it does not reopen the boundary
  `docs/ROADMAP.md` holds until the usability gate in issue #51 closes.
