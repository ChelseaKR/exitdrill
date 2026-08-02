# ADR-0011: Index CiviCRM evidence without composing it

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

The CiviCRM normalizer now emits one normalized target read-back plus six
aggregate evidence results. Their separation prevents a successful narrow probe
from concealing the intentionally failed structural assessment, but consumers
must otherwise discover filenames and schemas from prose or implementation.

A convenience index can improve automation while creating a new risk: readers
may treat it as a composite score or assume that listed artifacts share one
decision scope.

## Decision

Emit deterministic `evidence-index.json` with one ordered entry for each output
artifact. Each entry contains only an artifact ID, filename, schema version, and
its independent decision scope. Include the normalized `export.json` as an input
requiring separate baseline evaluation, followed by the target-interface,
UI-surface, browser-workflow, automated-accessibility, keyboard-interaction, and
activity-view results.

The index contains no state, status, count, score, pass total, assessment,
ranking, or inferred overall outcome. Fixed limitations state that it is
unsigned, non-composite, and cannot replace each result's own limitations or the
separate structural evaluation.

## Options Considered

### Option A: A non-composite artifact catalog

**Pros:** Gives humans and automation one stable discovery point while
preserving the denominator and independent claim scopes.

**Cons:** Adds another schema and output that can still be quoted without its
limitations.

### Option B: One combined restoration score

**Pros:** Easy to display and compare.

**Cons:** Violates ExitDrill's central invariant by allowing successful narrow
observations to conceal missing permissions, history, or entities.

### Option C: Keep discovery in prose only

**Pros:** No new contract.

**Cons:** Fragile for automation and increasingly difficult to navigate as
bounded evidence families grow.

## Consequences

- Every normalization emits `evidence-index.json` under a packaged closed JSON
  Schema.
- The index lists seven artifacts and their exact independent scopes.
- Consumers still must run the normalized export against a separate baseline and
  interpret every result with its own limitations.
- No existing artifact, claim, probe algebra, or structural outcome changes.
- Adding or removing an evidence family requires an explicit index-contract
  update and review.

## Action Items

1. [x] List every current output artifact in deterministic order.
2. [x] Include filename, schema version, artifact ID, and decision scope only.
3. [x] Prohibit composite status and score fields in the closed schema.
4. [x] Add semantic validation, privacy checks, and write-failure cleanup tests.
5. [x] Package the schema with the wheel.
