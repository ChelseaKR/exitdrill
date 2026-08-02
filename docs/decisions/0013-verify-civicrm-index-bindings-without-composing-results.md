# ADR-0013: Verify CiviCRM index bindings without composing results

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

Evidence-index v0.2 binds seven generated artifacts by byte length and SHA-256,
but consumers otherwise must implement the same closed-profile checks. A shared
verifier reduces inconsistent path, JSON, and digest handling. Its success must
not be confused with validation of every artifact's full schema or a combined
restoration assessment.

## Decision

Add `exitdrill verify-civicrm-evidence-index INDEX`. The command fail-closed
validates the exact v0.2 index structure and limitations, reads only the seven
fixed sibling filenames with bounded regular-file reads, verifies each byte
length and SHA-256, strictly decodes each JSON artifact, and checks its declared
schema-version header against the index contract.

Successful output uses the explicit decision scope
`catalog_binding_and_declared_schema_headers_only`. It does not validate the
full contents of each artifact against its JSON Schema, run the structural
evaluator, interpret observations, aggregate states, or authenticate the index.

## Options Considered

### Option A: A closed-profile binding and header verifier

**Pros:** Makes the digest contract directly usable with no runtime dependency
and preserves the independently bounded evidence scopes.

**Cons:** Consumers still must perform artifact-specific schema and semantic
validation separately.

### Option B: Return one overall evidence verdict

**Pros:** A simpler headline for callers.

**Cons:** Conflates byte consistency with evidentiary meaning and would recreate
the composite-score problem the index is designed to avoid.

### Option C: Require every consumer to implement verification

**Pros:** No new command surface.

**Cons:** Encourages inconsistent security bounds and ambiguous success claims.

## Consequences

- The CLI detects missing, unreadable, oversized, changed, malformed, or
  wrong-schema-header artifacts in the fixed generated set.
- Verification output contains no paths, record data, score, or restoration
  conclusion.
- Full artifact schemas, semantic limitations, structural evaluation, and
  authenticity remain separate responsibilities.

## Action Items

1. [x] Reuse one canonical artifact definition for generation and verification.
2. [x] Bound index and artifact reads and reject non-regular files.
3. [x] Test valid, byte-tampered, and digest-rebound wrong-header cases.
4. [x] Expose only the limited verification scope in CLI output and docs.
