# ADR-0016: Observe one CiviCRM contact-summary browser workflow

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

The target canary already retains a server-rendered Contact Summary marker
projection. That proves the response contained fixed markers, but it does not
prove that a reader can reach the page through the rendered CiviCRM interface.
The existing browser evidence covers Manage Case and one generated Activity
View, leaving this navigation seam unobserved.

## Decision

Extend the isolated Chromium run with one read-only path from the all-cases
dashboard through the exact synthetic contact link to Contact Summary. Require
the fixed Contact Summary route, contact-page region, exact synthetic contact
name, and Cases affordance. Retain only semantic step keys, browser engine, an
empty artifact list, and the sanitized known-error key/count.

Publish the observation as a separate
`exitdrill/civicrm-contact-summary-workflow-result/v0.1` result with the narrow
decision scope `pinned_synthetic_contact_summary_browser_workflow_only`. Advance
the non-composite evidence index to v0.3 and its closed verification result to
v0.2 rather than changing the historical v0.2 and v0.1 contracts.

## Options Considered

### Option A: Add one separate read-only browser result

**Pros:** Closes a real navigation gap while keeping its evidence and
limitations independently interpretable.

**Cons:** Adds another observation, schema, index entry, and versioned contract.

### Option B: Treat the existing server-rendered markers as browser proof

**Pros:** No additional capture work.

**Cons:** Confuses markup presence with a user interaction and hides navigation
failures.

### Option C: Fold the path into the existing Manage Case result

**Pros:** Fewer output files.

**Cons:** Composes two task scopes and makes it harder to state which runtime
errors and limitations belong to each observation.

## Consequences

- The live harness now performs three bounded read-only browser tasks in one
  isolated run.
- The new task accepts exactly two additional
  `jquery_notify_unavailable` errors at its fixed navigation steps; any other
  page error, failed request, or off-origin request still fails closed.
- No screenshots, traces, HTML, downloads, cookies, credentials, route
  parameters, or target identifiers are retained.
- The result does not prove contact editing, navigation into a case,
  accessibility, broader usability, operational equivalence, or production
  readiness.
- The structural evaluator and target-interface probe algebra are unchanged.

## Action Items

1. [x] Add and freshly execute the bounded browser path.
2. [x] Publish the minimized native observation and closed result schema.
3. [x] Advance the evidence index and verification-result contracts.
4. [x] Add exact positive and adversarial tests and update claim boundaries.
