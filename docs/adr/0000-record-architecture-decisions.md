# ADR 0000: Record architecture decisions

**Status:** Accepted

**Date:** 2026-07-23

**Decider:** Chelsea Kelly-Reif

## Context

ExitDrill already records load-bearing decisions as ADRs under
[`docs/decisions/`](../decisions/), but the portfolio's canonical discovery
path is `docs/adr/`. Moving accepted records would break durable links and
obscure their history; leaving no canonical index makes both people and
automation miss decisions that do exist.

## Decision

Keep accepted records immutable at their existing paths and use this directory
as the compatibility ADR entry point. New decisions continue under
`docs/decisions/NNNN-title.md`. Superseding a decision creates a new ADR and
links both records; accepted history is never rewritten to make the current
design look inevitable.

Existing accepted records:

1. [ADR 0001: Structural evaluation before a target adapter](../decisions/0001-structural-evaluation-before-target-adapter.md)
2. [ADR 0002: Validate synthetic exercise preflight without a connector seam](../decisions/0002-synthetic-exercise-preflight.md)
3. [ADR 0003: Compare only same-scope aggregate receipts](../decisions/0003-compare-only-same-scope-aggregates.md)
4. [ADR 0004: Normalize one Directus canary outside the evaluator](../decisions/0004-normalize-one-directus-canary-outside-evaluator.md)
5. [ADR 0005: Exercise one CiviCRM target-roundtrip canary](../decisions/0005-exercise-one-civicrm-target-roundtrip-canary.md)
6. [ADR 0006: Observe one authenticated CiviCRM UI surface](../decisions/0006-observe-one-authenticated-civicrm-ui-surface.md)
7. [ADR 0007: Observe one CiviCRM browser workflow](../decisions/0007-observe-one-civicrm-browser-workflow.md)
8. [ADR 0008: Record one automated CiviCRM accessibility observation](../decisions/0008-record-one-automated-accessibility-observation.md)
9. [ADR 0009: Record one CiviCRM keyboard interaction observation](../decisions/0009-record-one-keyboard-interaction-observation.md)
10. [ADR 0010: Observe one CiviCRM activity-view workflow](../decisions/0010-observe-one-civicrm-activity-view-workflow.md)
11. [ADR 0011: Index CiviCRM evidence without composing it](../decisions/0011-index-civicrm-evidence-without-composing-it.md)
12. [ADR 0012: Bind indexed CiviCRM artifacts by digest](../decisions/0012-bind-civicrm-indexed-artifacts-by-digest.md)
13. [ADR 0013: Verify CiviCRM index bindings without composing results](../decisions/0013-verify-civicrm-index-bindings-without-composing-results.md)
14. [ADR 0014: Validate indexed CiviCRM artifact contracts](../decisions/0014-validate-indexed-civicrm-artifact-contracts.md)
15. [ADR 0015: Publish a closed CiviCRM verification result](../decisions/0015-publish-a-closed-civicrm-verification-result.md)
16. [ADR 0016: Observe one CiviCRM contact-summary browser workflow](../decisions/0016-observe-one-civicrm-contact-summary-workflow.md)
17. [ADR 0017: Observe one target-generated CiviCRM case-client workflow](../decisions/0017-observe-one-target-generated-civicrm-case-client-workflow.md)
18. [ADR 0018: Observe one authenticated CiviCRM browser access denial](../decisions/0018-observe-one-authenticated-civicrm-browser-access-denial.md)
19. [ADR 0019: Observe one authenticated CiviCRM browser allow control](../decisions/0019-observe-one-authenticated-civicrm-browser-allow-control.md)
20. [ADR 0020: Record one CiviCRM case-search failure](../decisions/0020-record-one-civicrm-case-search-failure.md)
21. [ADR 0021: Gate record-value disclosure on the synthetic demo](../decisions/0021-gate-record-value-disclosure-on-the-synthetic-demo.md)
22. [ADR 0022: Bind the canary disclosure checks to their fixtures](../decisions/0022-bind-canary-disclosure-checks-to-their-fixtures.md)
23. [ADR 0023: Keep and exercise the report dimension guard](../decisions/0023-keep-and-exercise-the-report-dimension-guard.md)

## Consequences

- The standard discovery path now resolves without breaking existing links.
- Old records remain where their history was established.
- New decisions remain in the established `docs/decisions/` sequence.
- A future consolidation may add redirects, but must not silently move or
  rewrite accepted decisions.
