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
as the canonical ADR entry point. New decisions use `docs/adr/NNNN-title.md`.
Superseding a decision creates a new ADR and links both records; accepted
history is never rewritten to make the current design look inevitable.

Existing accepted records:

1. [ADR 0001: Structural evaluation before a target adapter](../decisions/0001-structural-evaluation-before-target-adapter.md)
2. [ADR 0002: Validate synthetic exercise preflight without a connector seam](../decisions/0002-synthetic-exercise-preflight.md)
3. [ADR 0003: Compare only same-scope aggregate receipts](../decisions/0003-compare-only-same-scope-aggregates.md)

## Consequences

- The standard discovery path now resolves without breaking existing links.
- Old records remain where their history was established.
- Decision numbering continues from 0004 in this directory.
- A future consolidation may add redirects, but must not silently move or
  rewrite accepted decisions.
