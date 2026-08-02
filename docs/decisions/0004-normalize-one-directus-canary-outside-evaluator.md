# ADR-0004: Normalize one Directus canary outside the evaluator

**Status:** Accepted for `directus-11.17.4-civic-case/v0.1` only

**Date:** 2026-08-01

**Deciders:** Chelsea Kelly-Reif

## Context

ExitDrill's synthetic contract fixtures prove the evaluator's loss algebra but
begin after vendor data has already been normalized. The product thesis needs
evidence from a documented, customer-obtainable source surface. At the same
time, the evaluator's trust boundary prohibits dynamic mappings, arbitrary
commands, URLs, and vendor-specific behavior.

One fresh, no-egress Directus 11.17.4 SQLite sandbox now supplies a frozen native
bundle. It contains invented records only and is pinned to one official image
digest, schema, set of REST responses, and permission shape. This evidence is
too narrow to justify either a generic connector SDK or a claim of Directus-wide
portability.

## Decision

Implement one closed normalizer for adapter profile
`directus-11.17.4-civic-case/v0.1` outside the evaluator. The normalizer may read
only the manifest-declared relative files in the frozen bundle, must verify byte
counts and SHA-256 digests before semantic parsing, and must emit the existing
`exitdrill/export/v0.1` normalized contract.

The profile fixes all collection names, fields, relationships, attachment
locations, permission canonicalization, and audit mapping. It cannot accept
mapping expressions, commands, URLs, plugins, or configuration that changes
semantics. The exact captured schema snapshot is bound to this profile by its
SHA-256, so a hash-refreshed manifest cannot authorize schema drift. The
independent baseline remains a separate evaluator input. The
vendor-agnostic evaluator remains unchanged.

Acceptance is profile-scoped: no other Directus version, database, schema,
permission shape, or export route is covered by this decision.

## Options Considered

### Option A: One closed profile normalizer outside the evaluator

| Dimension | Assessment |
|---|---|
| Complexity | Medium; one strict parser and fixed mapping |
| Cost | Small, bounded implementation and test surface |
| Scalability | Intentionally low until a second real profile exists |
| Team familiarity | High; JSON, hashes, and existing ExitDrill contracts |

**Pros:** Exercises a real first-party source surface, preserves the evaluator's
vendor-neutral trust boundary, and makes every supported semantic explicit.

**Cons:** Supports only one fixture profile and requires replacement or a new
profile when vendor output changes.

### Option B: Put Directus parsing or configurable mappings in the evaluator

| Dimension | Assessment |
|---|---|
| Complexity | High; expands the core trust path |
| Cost | Ongoing vendor and configuration maintenance |
| Scalability | Superficially high but untested across real sources |
| Team familiarity | Medium; abstraction behavior would be speculative |

**Pros:** Offers one command path and could appear easier to extend.

**Cons:** Violates the no-arbitrary-mapping invariant, couples vendor churn to
the evaluator, and makes a single canary look like a supported connector model.

### Option C: Commit only a hand-authored normalized export

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Low |
| Scalability | None; it bypasses the acquisition seam |
| Team familiarity | High |

**Pros:** Cheap and directly consumable by the current evaluator.

**Cons:** Repeats the existing synthetic evidence gap because no executable,
source-bound transformation connects native bytes to the normalized contract.

## Trade-off Analysis

Option A adds the smallest code seam that can falsify assumptions about an
actual vendor-shaped capture. Its deliberate lack of configurability is a
feature at this stage: malformed or changed native input fails closed instead
of being interpreted through operator-supplied logic. The cost is explicit
profile churn and duplicated code if later evidence reveals no stable
abstraction. That cost is preferable to freezing a generic connector API after
one source.

## Consequences

- Native manifest integrity and profile semantics become independently
  testable before evaluation.
- The evaluator remains vendor-neutral and retains its existing input contract.
- Permission changes can fail the permission dimension without also changing
  collection-scope entity validity.
- This profile must reject unknown files, fields, source versions, and semantic
  shapes rather than guessing.
- The resulting drill still proves structural normalization and neutral
  representability only—not a target load or operational exit.
- A second real source/profile is required before extracting a connector
  abstraction.

## Action Items

1. [x] Freeze the synthetic native bundle, independent baseline, capture notes,
   and permission canonicalization for this profile.
2. [x] Implement a bounded, closed profile normalizer outside the evaluator.
3. [x] Add negative tests for manifest tampering, traversal, unknown fields,
   type drift, relation loss, attachment mismatch, permission-semantic changes,
   and audit changes.
4. [x] Run the normalized good fixture through the existing five-dimension
   evaluator and preserve aggregate-only receipts.
5. [ ] Revisit the architecture only after evidence from another real native
   profile or a production-capable target exercise.
