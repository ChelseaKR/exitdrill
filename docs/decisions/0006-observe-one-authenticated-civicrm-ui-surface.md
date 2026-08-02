# ADR-0006: Observe one authenticated CiviCRM UI surface

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

ADR-0005 proves five target-interface behaviors through APIv4, AuthX, and
private-file read-back. It explicitly does not prove that a person can find the
restored records in CiviCRM's user interface. The next useful increment is a
small UI observation that does not introduce browser automation, alter the five
probe result algebra, or overstate a server-rendered response as a usable
workflow.

The pinned CiviCRM image exposes a Contact Summary route and a Cases tab. Its
Manage Case experience crosses redirect, tab-fragment, and JavaScript seams.
Discovery did not establish a bounded Manage Case request in this harness: the
full route returned the contact shell, while attempted fragment requests failed.
That failure is evidence against claiming a complete case workflow.

## Decision

Add one separate, closed UI-surface observation to the existing target canary.
The independent reader requests only the exact local Contact Summary route for
the first synthetic person. The live harness publishes a sanitized JSON
projection only when the response is HTTP 200 and contains the exact synthetic
contact label, the Contact Summary container, and the Cases tab.

The native projection is record-level synthetic fixture evidence. The offline
verifier requires its exact identity, route, status, labels, and region, then
emits a separate aggregate `ui-surface-result.json`. That result contains no raw
record value, target ID, URL parameter, HTML, credential, cookie, token, or
filesystem path. It does not modify `target-result.json`, add a restoration
probe, or change the structural evaluator.

The accepted claim is only that one authenticated server-rendered Contact
Summary surface exposed the exact synthetic contact and a Cases-tab affordance
in the pinned sandbox. Manage Case, browser interaction, JavaScript behavior,
accessibility, and end-to-end casework remain unobserved limitations.

## Options Considered

### Option A: Separate closed server-rendered UI observation

**Pros:** Adds real user-surface evidence with the existing independent reader,
no public port, no new runtime dependency, and an aggregate result isolated from
restoration claims.

**Cons:** Observes markup rather than a browser task and covers only Contact
Summary plus the Cases-tab affordance.

### Option B: Add a sixth target restoration probe

**Pros:** Would place all target observations in one result file.

**Cons:** Conflates UI presence with data restoration and changes the fixed
five-probe contract without a new structural dimension.

### Option C: Add Playwright browser automation now

**Pros:** Could test JavaScript behavior, navigation, and user tasks.

**Cons:** Adds a browser/runtime trust boundary and substantial lab complexity
before the server-rendered route is stable. It would require its own interaction,
accessibility, screenshot, and secret-handling design.

### Option D: Claim the Manage Case surface from route or template inspection

**Pros:** Would produce a stronger-looking workflow story quickly.

**Cons:** Discovery falsified the direct-request assumption. Static templates do
not prove that the independent reader receives the rendered case workflow.

## Tradeoffs

This decision favors a small falsifiable claim over a polished workflow demo.
It makes the portfolio evidence incrementally stronger while keeping the known
UI gap visible. A later browser exercise may supersede this observation, but it
must remain a separate evidence family and cannot retroactively strengthen this
capture.

## Consequences

- The target bundle adds one sanitized UI projection and two explicit UI
  limitations.
- The live lab follows no redirects for the fixed local UI route, API probes, or
  file probes.
- The offline verifier rejects changed identity, status, route, labels, regions,
  inventory, hashes, or limitations.
- The existing `api_probes_do_not_prove_ui_usability` limitation remains true.
- Manage Case and the case workflow remain unobserved and must not appear in a
  capability claim.

## Action Items

1. [x] Exercise the Contact Summary route with the independent reader.
2. [x] Reject unsupported Manage Case claims discovered during the live run.
3. [x] Add a closed native projection and aggregate-only UI result schema.
4. [x] Add negative tests for identity and region drift.
5. [x] Run the full repository verification and packaging gates, then mark this
   decision accepted for the pinned profile only.
