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

## Consequences

- The standard discovery path now resolves without breaking existing links.
- Old records remain where their history was established.
- New decisions remain in the established `docs/decisions/` sequence.
- A future consolidation may add redirects, but must not silently move or
  rewrite accepted decisions.
