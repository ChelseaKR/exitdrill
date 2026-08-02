# ADR-0007: Observe one CiviCRM browser workflow

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

ADR-0006 added a server-rendered Contact Summary observation while explicitly
leaving browser interaction and Manage Case unproven. Browser discovery found
that the Contact Summary Cases tab does not initialize its case content in the
pinned Standalone build. Static route or template inspection cannot turn that
failure into workflow evidence.

The supported CiviCase dashboard provides another bounded user path. A reader
with `access all cases and activities` can open the all-cases dashboard, locate
the restored case, and follow the generated Manage Case action. Exercising that
path adds a browser runtime and new artifact, network, secret, and claim risks.

## Decision

Add one separate closed browser-workflow evidence family. Playwright Core
1.62.0 drives Chromium from the exact digest-pinned Playwright 1.62.0 Noble
image. The browser runs in a run-owned container on the existing internal
network with a read-only filesystem, bounded temporary filesystem, all
capabilities dropped, and `no-new-privileges`. Only the fixed workflow script
and pinned Node dependency tree are mounted read-only. The container receives
only the independent reader's generated credential through environment
variables and is removed before the lab is torn down.

The workflow permits requests only to the internal application origin, disables
service workers and downloads, and retains no screenshot, trace, video, HTML,
cookie, or credential artifact. It opens the all-cases dashboard, locates the
first synthetic case, follows Manage Case, and requires the exact subject, type,
displayed status, coordinator, Roles region, and Activities region.

The pinned Standalone build raises `TypeError: $(...).notify is not a function`
once during dashboard navigation and once when Manage Case loads. The observed
controls remain functional. The workflow accepts only those two exact error
messages at those exact steps. Any other page error, failed request, off-origin
request, control mismatch, or retained artifact fails closed. The native
projection records only the sanitized error key and occurrence count.

The offline verifier requires the exact native projection and emits a separate
aggregate `browser-workflow-result.json`. It does not change the five target
probes, `target-result.json`, the server-rendered UI result, or the structural
evaluator.

## Options Considered

### Option A: Dashboard to Manage Case in an isolated browser

**Pros:** Exercises a real supported user path, JavaScript, asynchronous case
rows, navigation, and case controls while keeping the evidence and runtime
boundary narrow.

**Cons:** Adds a large browser image, Node dependency, longer live run, and an
explicit known runtime defect.

### Option B: Continue through the Contact Summary Cases tab

**Pros:** Starts from the already observed contact surface.

**Cons:** The pinned build leaves the tab content uninitialized and raises a
TypeError. Treating the empty fragment as a workflow would falsify the evidence.

### Option C: Request the Manage Case URL directly

**Pros:** Simpler and faster.

**Cons:** Skips case discovery and the application's generated action, weakening
the user-task claim and increasing dependence on target IDs.

### Option D: Retain screenshots or traces as proof

**Pros:** Easier visual debugging and presentation.

**Cons:** Expands the sensitive artifact and retention surface without improving
the closed machine-verifiable claim. Debugging remains ephemeral and
synthetic-only.

## Tradeoffs

The decision favors one honest task over broad UI coverage. Recording the known
page errors makes the evidence less polished but more defensible. Exact error
matching prevents the exception from becoming a generic error suppression
policy. The additional runtime cost is confined to live recapture; offline
verification remains Python-only and deterministic.

## Consequences

- The native bundle adds `browser-workflow.json` and a browser image digest.
- The normalizer emits `browser-workflow-result.json` as a third evidence family.
- Manage Case is observed only for one synthetic case and one reader role.
- Accessibility, other browsers, mutations, forms, case activities, and other
  CiviCRM workflows remain unobserved.
- The two known jQuery-notify errors are part of the accepted evidence and claim
  limitations.
- The structural result remains `not_structurally_restorable` with six missing
  signals, and all five target-interface probes remain unchanged.

## Action Items

1. [x] Pin the browser package and image to the same Playwright version.
2. [x] Run the browser inside the existing internal, no-host-port lab.
3. [x] Prove Dashboard → Manage Case with exact controls and no retained artifacts.
4. [x] Record and narrowly allowlist the two known runtime errors.
5. [x] Add a separate native projection, aggregate schema, and verifier output.
6. [x] Add negative controls for browser engine, steps, artifacts, and error drift.
7. [x] Preserve the five-probe algebra and structural result unchanged.
