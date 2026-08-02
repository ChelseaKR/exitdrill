# ADR-0005: Exercise one closed CiviCRM target-roundtrip canary

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-01

**Deciders:** Chelsea Kelly-Reif

## Context

ExitDrill now verifies one pinned Directus API-response capture, normalizes it
into the existing five-dimension export contract, and proves structural
representability in a neutral SQLite model. That does not show whether the
declared structure can be loaded through a supported interface into a real
alternate application, read back independently, or used for the five
target-interface probes required by ADR-0002.

CiviCRM Standalone 6.16.2 is a nonprofit-relevant, production-capable
application with an official local-testing container image and supported API
surfaces. One pinned synthetic exercise can test the next product assumption
without introducing a generic migration or connector abstraction. CiviCRM's
official Docker quickstart is not a hardened production deployment, so the
exercise must add its own isolation and fail-closed preconditions.

The source fixture remains the custom Directus canary capture rather than a
vendor-native export. Its existing structural receipt explicitly disclaims
operational equivalence and therefore cannot serve as target evidence.

## Decision

Discover, and implement only if discovery passes, one closed target profile:
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1`.

The profile accepts only the verified normalized output of
`directus-11.17.4-civic-case/v0.1`. It loads a fixed allowlist of synthetic
fields through pinned, supported CiviCRM interfaces into a harness-created
fresh sandbox. It cannot accept a caller URL, mapping expression, command,
plugin, SQL statement, template, or arbitrary target configuration.

The target manifest binds the verified source normalization with the exact
adapter profile and normalization schema plus the source-bundle,
normalized-export, and normalized-attachment digests. That binding rejects a
target capture produced from any other source bundle or normalized output; it
does not authenticate either bundle's author or execution context.

The sandbox must use these multi-platform image digests:

- `civicrm/civicrm:6.16.2-php8.5@sha256:cdf062708b054670cc0f9b452e0b883840af71ce6db21615304f9e7ffe44b93f`;
- `mariadb:10.11.18@sha256:be981e4113326ada8d6004174dd09eeaefc03094037f811182a52d4f2e737350`.

Before the first fixture write, the harness must verify the exact image and
application versions, a run-owned sandbox marker, no public ingress, blocked
egress, outbound mail explicitly set to CiviCRM's disabled value, every
scheduled job inactive, an empty external-password-lookup URL, an
application-empty seed state, absent fixed-identity collisions, and distinct
least-privilege writer, reader, allowed, and denied principals. A failed
precondition makes no target mutation.

Writer mutation responses and in-memory ID maps are not business-state read-back
evidence. A separate reader process using no writer credential must reconstruct
the declared target state through target interfaces. A separate writer AuthX
envelope records identity separation but is not business-state evidence. The
five required target-interface probes are exact lookup, relationship traversal,
attachment-byte retrieval, authorized access, and authenticated unauthorized
denial. The deny probe must address the same object whose existence the reader
already proved.

Attachment support is a discovery gate. The pinned target must expose a
supported upload, association, and byte-retrieval path. If it does not, the
profile is rejected rather than omitting the attachment probe or treating
metadata as content evidence.

Discovery established that private file bytes can be retrieved by following a
reader-generated signed target URL. CiviCRM's `access uploaded files`
permission is broad and does not enforce the attached Case's row-level ACL.
Attachment retrieval therefore proves byte fidelity in this controlled lab; it
is not used as the allow/deny authorization proof. That proof uses an explicit
allow ACL and an explicit deny ACL over the same Contact record and submits the
same permission-enforced APIv4 query with the allowed and denied principals.

The public `target-result.json` and offline acceptance summary use new closed,
aggregate-only contracts. The native capture bundle remains record-level local
fixture evidence. Neither aggregate contract can change a structural receipt's
result algebra or limitations, and the target result has no composite
restoration label. The offline acceptance summary may emit
`civicrm_target_roundtrip_canary_verified` only after the clean run, the
intentionally failing structural replay, and every required negative control
succeeds.

## Options Considered

### Option A: One closed target profile outside the evaluator

| Dimension | Assessment |
|---|---|
| Complexity | Medium-high; real sandbox lifecycle, fixed load, independent read-back, and behavioral probes |
| Cost | Bounded to one pinned source-target fixture |
| Scalability | Intentionally low until a second target exercise supplies evidence |
| Team familiarity | Medium; existing contracts are reusable but CiviCRM semantics require discovery |

**Pros:** Tests the missing target boundary, preserves the evaluator's claims,
and can falsify unsupported attachment and authorization assumptions.

**Cons:** Slow container acceptance path, profile-specific maintenance, and no
claim beyond the exact synthetic configuration.

### Option B: Add CiviCRM output directly to the structural evaluator

| Dimension | Assessment |
|---|---|
| Complexity | High; vendor behavior enters the core trust path |
| Cost | Ongoing vendor-specific evaluator churn |
| Scalability | Superficially broad but untested |
| Team familiarity | Low; structural and operational result algebras would be conflated |

**Pros:** One command and one apparent result surface.

**Cons:** A neutral structural pass could be mislabeled as target success, and
target infrastructure failures could be mislabeled as data loss.

### Option C: Add a generic target adapter protocol first

| Dimension | Assessment |
|---|---|
| Complexity | High; credentials, retries, mappings, and error semantics before evidence |
| Cost | Connector treadmill risk |
| Scalability | Unknown after zero completed target exercises |
| Team familiarity | Medium technically, low empirically |

**Pros:** Could reduce later duplication if several targets share real seams.

**Cons:** Freezes speculative abstractions and expands the execution surface
before one source-target pair demonstrates customer value.

## Consequences

- A verified result will apply only to one pinned synthetic Directus-to-CiviCRM
  profile, not to general CRM portability or production migration.
- Target infrastructure, load, read-back, and probe failures remain distinct;
  none becomes a structural evaluator result.
- Source permission tuples are not mapped as equivalent CiviCRM permissions.
  The target claim is limited to observed allow and deny behavior of fixed
  synthetic principals.
- The unchanged structural evaluator is expected to report
  `not_structurally_restorable`: five of seven source entities, both
  relationships, and both attachments are represented, while two Directus
  collection-scope entities, two Directus policy grants, and two Directus audit
  events remain missing. Six observed missing signals are not hidden by the
  successful target-interface probes.
- Fresh run-owned databases and volumes are mandatory. The harness never cleans
  or reuses an operator-supplied target.
- The exact target-generated scaffolding counts include two case activities, two
  case contacts, one case type, two custom-field groups, seven custom fields,
  three ACL groups, four ACL group memberships, two ACL roles, two ACL
  entity-role assignments, two ACL rules, one helper contact, four principals,
  four application roles, zero created relationship types, and one referenced
  built-in relationship type. None is relabeled as source data.
- Raw synthetic fixture values and attachment bytes may exist inside the
  disposable lab and committed native bundle, but not in `target-result.json`,
  the offline acceptance summary, structural receipts, or reports.
- A second real target exercise is required before extracting a target SDK or
  common adapter interface.

## Acceptance Gates

### Live capture gate

The live harness may publish a target bundle only when:

1. the exact Directus source bundle passes the closed normalizer and the target
   manifest binds its adapter profile, normalization schema, and three aggregate
   digests;
2. every pre-write sandbox, version, empty-state, automation, egress, and
   credential-separation check passes;
3. the fixed source fixture loads only through the supported target surface; and
4. a separate reader reconstructs exact declared scalar values, relationships,
   attachment bytes, and allow/deny behavior.

The published execution assertions and hashes remain unsigned. They make the
frozen bundle internally checkable but do not authenticate the historical live
run.

### Offline frozen-bundle gate

`make demo-civicrm-target-canary` may pass only when it verifies that:

1. the closed committed manifest, source-normalization binding, file inventory,
   response shapes, exact counts, safety assertions, and limitations are intact;
2. two clean normalizations are byte-exact and all five target-interface probes
   pass in the clean frozen capture;
3. the unchanged structural evaluator reports the intentional six-gap
   `not_structurally_restorable` result;
4. same-count scalar substitution, relationship rewiring, same-length
   attachment corruption, permission escalation, and a nonempty target are all
   detected; and
5. deterministic aggregate evidence contains fixed limitations and no raw IDs,
   values, attachment content, credentials, target paths, or HTTP bodies.

This offline command does not create a sandbox or re-prove the historical live
execution assertions.

## Action Items

1. [x] Verify the pinned target's supported contact, case, relationship,
   attachment, authentication, and authorization surfaces in an isolated lab.
2. [x] Freeze the exact fresh-install seed state and pre-write safety checks.
3. [x] Implement the closed writer, independent reader, probes, and separate
   target evidence contract without changing the evaluator.
4. [x] Add every negative control named in the acceptance gates.
5. [x] Change this decision to accepted only after both gates pass.
