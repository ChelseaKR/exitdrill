# ADR-0012: Bind indexed CiviCRM artifacts by digest

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

ADR-0011 introduced a non-composite catalog of the seven CiviCRM output
artifacts. That v0.1 index makes discovery deterministic but cannot detect when
an indexed file is missing, truncated, or replaced after normalization.

Content digests can bind the catalog to the exact emitted bytes. They cannot
authenticate the operator, establish trusted time, prove that a sandbox ran, or
make any underlying observation true.

## Decision

Emit evidence-index v0.2 with the byte length and lowercase SHA-256 digest of
each indexed artifact. Construct every artifact byte string first, write those
exact bytes, and derive the bindings from the same byte strings. Keep the index
itself outside its entries to avoid a circular digest.

Retain every independent artifact ID, filename, schema, and decision scope from
v0.1. Add a fixed limitation stating that digests prove internal consistency,
not authenticity. Do not add a composite status, score, pass count, ranking, or
inferred result.

## Options Considered

### Option A: Per-artifact byte length and SHA-256

**Pros:** Detects accidental or undisclosed artifact changes with a small,
deterministic contract extension.

**Cons:** A fabricator can replace an artifact and recompute the unsigned index.

### Option B: Sign the index now

**Pros:** Could authenticate control of a signing key and protect integrity.

**Cons:** Key ownership, rotation, revocation, trusted time, and issuer policy
are not designed; a signature still would not prove the observations true.

### Option C: Leave the discovery-only v0.1 index unchanged

**Pros:** No contract revision.

**Cons:** Consumers cannot distinguish the original generated set from a set
with missing or altered artifacts.

## Consequences

- New normalization emits evidence-index v0.2; the v0.1 schema remains packaged
  for interpretation of already produced indexes.
- Each entry binds its artifact's exact bytes and length.
- Reformatting an artifact changes its digest even when parsed JSON is equal.
- The index remains unsigned, unauthenticated, non-composite, and subordinate to
  each artifact's decision scope and limitations.

## Action Items

1. [x] Derive all bindings from the exact byte strings written to disk.
2. [x] Close and package the v0.2 JSON Schema.
3. [x] Verify every binding in unit and offline acceptance tests.
4. [x] Preserve the no-score and independent-scope constraints.
