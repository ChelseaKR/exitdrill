# ADR-0017: Observe one target-generated CiviCRM case-client workflow

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

The source-mapped Alpha contact is the coordinator for the first synthetic case,
not its CiviCRM case client. Its Contact Summary therefore exposes the Cases
affordance but correctly lists no case. A live prototype detected this boundary;
claiming that Alpha could navigate into the case would misrepresent both the
source relationship and the target model.

CiviCRM requires a case client, so the fixed target profile creates one helper
contact and counts it as target-generated scaffolding. The dashboard and Manage
Case observations prove portions of casework, but no existing result proves the
contact-scoped path through that actual case client.

## Decision

Add a separate read-only browser workflow that reopens the case dashboard,
follows the exact target-generated case-client helper, observes Contact Summary,
activates Cases, requires the exact synthetic case subject, follows the row's
supported `Manage` action, and reobserves the subject in Manage Case.

Publish only minimized semantic steps, browser engine, an empty retained-artifact
list, and the sanitized known-error key/count. Emit a separate
`exitdrill/civicrm-case-client-workflow-result/v0.1` result with the decision
scope `pinned_synthetic_target_generated_case_client_browser_workflow_only`.
Advance the non-composite evidence index to v0.4 and its verification result to
v0.3 without rewriting historical schemas.

## Options Considered

### Option A: Observe the target-generated case-client path honestly

**Pros:** Proves a real contact-scoped task while preserving the distinction
between target scaffolding and restored source data.

**Cons:** The result is operationally useful but cannot support source
case-client equivalence.

### Option B: Force the coordinator's empty Cases view to count as navigation

**Pros:** Produces a simpler source-contact story.

**Cons:** Falsifies the observed target model and converts a visible affordance
into evidence of content that is not there.

### Option C: Remap the source coordinator as the CiviCRM case client

**Pros:** Makes the source contact's Cases table nonempty.

**Cons:** Changes the semantic mapping merely to improve the demo and conflates
an `assigned_to` relationship with case-client identity.

## Consequences

- The new workflow records three exact `jquery_notify_unavailable` errors at
  dashboard, Contact Summary, and Manage Case loads; activating Cases itself is
  clean.
- The target helper remains in `target_generated_counts` and is never emitted as
  a source-mapped entity.
- No screenshots, traces, HTML, downloads, cookies, credentials, record IDs,
  route parameters, helper name, or case subject are retained in aggregate
  evidence.
- The result does not prove source case-client equivalence, contact or case
  editing, accessibility, broader usability, or operational equivalence.
- The structural evaluator and five target-interface probes remain unchanged.

## Action Items

1. [x] Prototype the coordinator path and fail closed when its Cases view is empty.
2. [x] Observe the target-generated case-client path in a fresh isolated lab.
3. [x] Publish a separate result schema and advance index contracts.
4. [x] Add exact positive/adversarial tests and update public claim boundaries.
