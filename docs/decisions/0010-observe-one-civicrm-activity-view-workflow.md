# ADR-0010: Observe one CiviCRM activity-view workflow

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

ADR-0007 observes Dashboard → Manage Case and verifies that an Activities region
exists, but does not exercise an activity. The target creates one `Open Case`
activity as scaffolding when the synthetic case is loaded. Its supported `View`
action provides a second, read-only user task without creating or editing data.

The Activity View route raises the same non-fatal jQuery-notify TypeError already
observed on the dashboard and Manage Case pages. Ignoring it generically would
weaken the runtime boundary; hiding it would misstate target behavior.

## Decision

From the already verified Manage Case page, select the first generated
activity's supported `View` action. Require navigation to the fixed Activity
View route and visible exact markers for the synthetic case subject, activity
type `Open Case`, status `Completed`, and `Activity View` heading.

Accept exactly one additional `jquery_notify_unavailable` error during that
navigation. Any other page error, failed request, off-origin request, route
change, or marker mismatch fails the browser run. Retain no HTML, route
parameters, target IDs, screenshots, traces, downloads, or credentials.

Store a separate sanitized `browser-activity-view.json` projection and emit a
sixth aggregate `activity-view-result.json`. Do not change the earlier workflow,
accessibility, keyboard, target-interface, or structural result contracts.

## Options Considered

### Option A: View one generated activity

**Pros:** Exercises a distinct supported read-only task and verifies meaningful
activity details without mutating the target.

**Cons:** Covers target-generated scaffolding rather than preserved source
history and adds a third known runtime-error occurrence.

### Option B: Edit or create an activity

**Pros:** Exercises a deeper operational workflow.

**Cons:** Mutates the evidence target, requires rollback semantics, and risks
confusing newly created target data with source restoration.

### Option C: Treat the Activities region marker as sufficient

**Pros:** No additional runtime or artifact.

**Cons:** Presence of a region does not prove that a user can inspect an
activity or that its details render.

## Consequences

- The native bundle adds `browser-activity-view.json`; the normalizer emits
  `activity-view-result.json` under a closed JSON Schema.
- One target-generated `Open Case` activity is viewable with its subject, type,
  and completed status in the pinned synthetic sandbox.
- The third exact jQuery-notify error remains visible and narrowly allowlisted.
- Activity editing, creation, filtering, attachments, source-history
  equivalence, and other activity types remain unobserved.
- Target-generated activity evidence does not reduce the two missing source
  audit-history signals or change `not_structurally_restorable`.

## Action Items

1. [x] Use the supported read-only `View` action from Manage Case.
2. [x] Verify the exact route and fixed synthetic activity markers.
3. [x] Record and narrowly allowlist the additional known runtime error.
4. [x] Retain only a sanitized step projection with no target IDs or HTML.
5. [x] Add a separate aggregate schema and negative controls.
6. [ ] Exercise a source-history-bearing activity only after a semantics-preserving
   mapping is designed.
