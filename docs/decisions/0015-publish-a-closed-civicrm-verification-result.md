# ADR-0015: Publish a closed CiviCRM verification result

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

The CiviCRM evidence verifier now checks index bindings, packaged result
schemas, the normalized export contract, and attachment bytes. Its stdout is
covered by exact tests but has no independently published contract, and the
existing `schema_version` field names the input index rather than the output
document itself.

That ambiguity makes automation brittle and makes it easier to quote a success
status without its narrow decision scope and limitations.

## Decision

Publish `exitdrill/civicrm-evidence-verification/v0.1` as a closed packaged JSON
Schema. The result identifies its own schema and separately records
`index_schema_version`. It includes exact artifact and attachment counts, the
fixed target profile, narrow decision scope, status, and five ordered
limitations.

The limitations state that verification is unsigned and unauthenticated, does
not interpret or compose artifact results, does not run the structural
evaluator, does not prove live execution or completeness, and provides internal
digest consistency rather than authenticity.

## Options Considered

### Option A: A separate closed verification-result contract

**Pros:** Gives consumers a stable machine-readable surface and makes the input
and output schema versions unambiguous.

**Cons:** Adds another versioned schema that must evolve explicitly.

### Option B: Continue relying on exact tests only

**Pros:** No additional public file.

**Cons:** External consumers must infer the contract from implementation and
can silently ignore limitations.

### Option C: Reuse the evidence-index schema identifier

**Pros:** Avoids another identifier.

**Cons:** Incorrectly claims two different documents share one contract and
obscures which schema was verified.

## Consequences

- Verifier stdout is independently schema-versioned and packaged in the wheel.
- `index_schema_version` identifies the verified input contract.
- The result remains aggregate-only and contains no artifact paths, record
  values, findings, scores, or composite restoration state.
- Any future output-field or limitation change requires a contract version
  decision.

## Action Items

1. [x] Add the closed verification-result schema.
2. [x] Distinguish output and input-index schema versions.
3. [x] Include fixed non-composite and unauthenticated limitations.
4. [x] Validate the result in tests and package the schema in the wheel.
