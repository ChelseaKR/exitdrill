# ADR-0014: Validate indexed CiviCRM artifact contracts

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

ADR-0013 added a fail-closed verifier for evidence-index v0.2 bindings and each
artifact's declared schema-version header. That detects changed bytes and
misidentified artifacts, but a caller can recompute the unsigned binding around
a structurally invalid result that retains the expected header.

The normalized export also references attachment files outside the seven JSON
artifacts. Binding `export.json` protects its declared attachment hashes, but
the existing verifier does not read the attachment bytes.

## Decision

Extend `verify-civicrm-evidence-index` to validate the full packaged JSON Schema
for the index and each of the six aggregate result artifacts. Validate the
normalized export with the existing strict loader, require that loader's exact
source digest to match the index binding, and verify every declared attachment
through bounded path and byte-budget controls.

Promote `jsonschema` from a development-only dependency to a runtime dependency.
Load schemas from installed package resources, with a source-tree fallback for
editable development, and keep all validation failures free of artifact values
and filesystem paths. The isolated wheel smoke test must normalize and verify
the committed synthetic fixture using only the built wheel and its declared
dependencies.

Successful output uses
`catalog_bindings_artifact_schemas_and_export_attachments_only`. It remains a
contract-and-integrity statement, not an interpretation, composite score,
restoration result, authenticity claim, or proof of live execution.

## Options Considered

### Option A: Validate packaged schemas and normalized attachments

**Pros:** Closes the gap between a correct header and a structurally valid
artifact while exercising the actual installed package.

**Cons:** Adds one runtime dependency and still cannot prove evidence truth.

### Option B: Continue checking headers only

**Pros:** Keeps the runtime dependency list empty.

**Cons:** A digest-rebound artifact can retain its expected header while
violating the published contract.

### Option C: Duplicate every JSON Schema as handwritten Python validation

**Pros:** Avoids the dependency.

**Cons:** Creates two contract implementations likely to drift and makes review
substantially harder.

## Consequences

- The verifier rejects structurally invalid indexed results even after their
  byte bindings are recomputed.
- The normalized export and its referenced attachment bytes are validated
  without requiring a baseline or running the evaluator.
- Wheel verification proves the schemas and runtime validator work from the
  installed artifact, not only from the repository checkout.
- Passing validation still says nothing about evidence authenticity,
  completeness, operational equivalence, or structural restorability.

## Action Items

1. [x] Validate the v0.2 index and six result artifacts with packaged schemas.
2. [x] Validate the normalized export and bounded attachment bytes.
3. [x] Add rebound-invalid-result, invalid-export, and attachment-mutation tests.
4. [x] Exercise normalization and verification from the isolated built wheel.
