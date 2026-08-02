# Architecture

## Claims boundary

```text
Directus API capture ── closed source normalizer ── source export ── fixed load ─┐
                                                                               ▼
independent baseline ──────────────────────────────────────────────── CiviCRM sandbox
        │                                                                      │
        │                                             independent API/file read-back
        │                                                                      │
        │                                                                      ▼
        └────────────── closed target verifier ◀── target capture bundle ───────┘
                               │                         │
                     target normalized export           └── five-probe target result
                               │                                  (separate evidence)
                               ▼
                    unchanged structural evaluator
                               │
                               ▼
                    failing structural result
```

The current evaluator establishes structural representability and reference
integrity. It cannot establish operational substitutability because SQLite has
no equivalent user interface, workflow engine, automation, reporting, or
permission model.

## Components

- `strict_json.py` rejects duplicate keys, non-finite numbers, excessive
  nesting, invalid UTF-8, and documents beyond their byte budgets.
- `loader.py` enforces strict versioned baseline and export contracts.
- `exercise.py` validates a synthetic-only safety/evidence plan for a future
  target exercise; it contains no connector, transform, credential, or target
  execution path.
- `directus_canary.py` is a source-specific, fail-closed verifier and normalizer
  for exactly the Directus 11.17.4 synthetic civic-case canary profile. It
  verifies the capture manifest and declared bytes before mapping them into the
  existing normalized contract and atomically creating a new output directory.
  It is not a connector registry, arbitrary transform runner, or evaluator.
- `civicrm_target_canary.py` is a separate target-specific, fail-closed verifier
  for exactly one Directus-to-CiviCRM Standalone 6.16.2 read-back profile. It
  checks a closed native inventory, sandbox and identity assertions, target API
  envelopes, private attachment bytes, and allow/deny outcomes before atomically
  emitting the existing export contract plus a separate aggregate target result.
  It does not load a target, execute a mapping, or alter evaluator result algebra.
- `paths.py` is the single attachment-root boundary. Attachment size checks and
  hashing share one open descriptor, so a path replacement after open cannot
  change the bytes being measured.
- `evaluator.py` compares independent denominators, validates declared critical
  field values and attachment bytes, and loads a foreign-key-enforced reference
  model.
- `models.py` defines dimension and overall result algebra.
- `receipt.py` builds aggregate-only deterministic payloads through
  collision-resistant temporary files and verifies exact, closed
  receipt/envelope shapes plus their self-contained checksums.
- `receipt_validation.py` closes nested result fields and verifies dimension
  presence, counts, arithmetic, limitations, and shared result algebra.
- `comparison.py` reduces two verified receipts to aggregate snapshots, gates
  exact input-scope comparability, and emits deterministic per-dimension deltas.
- `report.py` renders one semantically verified aggregate receipt as a
  deterministic, accessible, script-free offline HTML report with the complete
  claims boundary intact.
- `cli.py` exposes the bounded Directus source and CiviCRM target normalizers
  plus validation, drill, verification/replay, comparison, and offline reporting.

## Architecture decision

Three options were considered:

| Option | Decision | Reason |
|---|---|---|
| General connector platform | Reject for the current scope | Tests abstractions before customer value; high treadmill risk |
| Export-to-neutral-model only | Implement with restricted label | Cheapest way to test denominator, loss algebra, privacy, and replay |
| One real source capture → real target → read-back → workflows | Required for an operational claim | Smallest credible operational exit claim |

The canonical model is an adapter boundary, not proof of successful exit.

## API-response capture boundary

The custom ExitDrill bundle was assembled from API responses and attachment
bytes captured from a pinned local Directus 11.17.4 process using documented
first-party surfaces and invented data. Capture and normalization are separate
phases:

1. the reviewed lab script creates and captures a fixed synthetic profile;
2. the committed manifest declares an exact file set, byte sizes, SHA-256 values,
   aggregate bundle digest, source version, profile, and limitations;
3. `normalize-directus-canary` verifies the closed profile and captured bytes,
   then writes the normal export and attachment contracts; and
4. the unchanged evaluator consumes only those normal contracts.

The normalizer never changes evaluator result algebra or receipt semantics. Its
`normalization-manifest.json` is aggregate, path-free evidence about the staging
operation and remains outside the receipt. This separation prevents a
source-specific adapter from silently strengthening the evaluator's claims. It
also means the receipt does not bind or authenticate the acquisition process.

Directus permission records are represented as grants to policy principals over
explicit collection-scope entities. The role value binds a SHA-256 digest of the
canonical captured Directus `action`, `fields`, `permissions`, `presets`, and
`validation`
semantics. That detects changes in the declared record; it does not prove user
identity, effective authorization, deny precedence, or cross-product permission
equivalence.

## CiviCRM target-roundtrip boundary

The target exercise is a second closed profile, not a generic adapter. A reviewed
Node.js harness creates a fresh run-owned CiviCRM Standalone 6.16.2 and MariaDB
10.11.18 sandbox from digest-pinned images. Before loading it, the harness runs
the closed Directus normalizer and binds the exact adapter profile,
normalization schema, source-bundle, normalized-export, and
normalized-attachment digests into the target manifest. The Compose topology
publishes no host port and uses an internal network. Before fixture writes, the
harness checks the pinned versions and fixed seed state, absent source-identity
collisions, private attachment posture, blocked egress, disabled scheduled jobs,
outbound mail set to CiviCRM's disabled value, and an empty
external-password-lookup URL.

Four distinct synthetic identities separate write, independent read-back,
authorized access, and denied access. Writer mutation responses and in-memory
IDs are not business-state read-back evidence. A separate AuthX writer envelope
records identity separation without serving as business-state evidence. The
reader reconstructs three source contacts, two cases, two case-scoped
relationships, two private file associations, and both attachment byte streams
through authenticated target surfaces. The allow and deny identities run the
same permission-enforced Contact query over the same protected record. The
expected denial is an authenticated APIv4 response with zero values, not an
invented HTTP error.

The native bundle contains synthetic API response projections and attachment
bytes, so it is local fixture evidence rather than a public receipt. The harness
preserves selected response values but removes unrelated APIv4 transport metadata
into a closed `{values, count, countFetched[, countMatched]}` envelope. Its
manifest binds an exact file inventory, source normalization, and aggregate
execution assertions but remains unsigned and operator asserted.
The offline verifier `normalize-civicrm-target-canary` checks that closed bundle,
creates a five-entity normalized target export, and emits a separate aggregate
`target-result.json` with the five target-interface probe observations.

The live capture and offline acceptance gates are separate. The live harness may
publish only after the source binding, fresh sandbox, target load, independent
business-state read-back, and five target-interface probes succeed. The offline
`make demo-civicrm-target-canary` command verifies the frozen unsigned bundle,
deterministic outputs, structural result, and adversarial controls; it does not
rerun or authenticate the historical Docker execution.

The target result has no composite restoration state. CiviCRM-generated case
activities, case contacts, application roles, custom fields, ACL groups, ACL
group memberships, ACL roles, ACL entity-role assignments, ACL rules, helper
contact, and principals are counted as target scaffolding, not source
restoration. Source collection scopes, permission grants, and audit events
remain unmapped. The unchanged structural evaluator therefore reports six
missing signals and `not_structurally_restorable` even though all five clean
target-interface probes pass.

The fixed scaffolding counts are two case activities, two case contacts, one
case type, two custom-field groups, seven custom fields, three ACL groups, four
ACL group memberships, two ACL roles, two ACL entity-role assignments, two ACL
rules, one helper contact, four principals, four application roles, zero
created relationship types, and one referenced built-in relationship type.

CiviCRM's broad uploaded-file permission does not establish that a private file
inherits the attached case's row-level ACL. Attachment retrieval proves only byte
fidelity in this profile; the Contact ACL query supplies the separate allow/deny
observation. Neither probe proves UI usability or source-permission equivalence.

## CiviCRM UI-surface boundary

A separate closed observation requests one fixed local Contact Summary route
with the independent reader. The live harness checks HTTP 200, the exact
synthetic contact label, the contact-page container, and the Cases tab, then
stores only a sanitized projection. The offline verifier emits a separate
aggregate `ui-surface-result.json`; it never changes the structural evaluator or
the five target-interface probes.

This server-rendered observation does not by itself prove Manage Case, browser
interaction, JavaScript behavior, accessibility, or end-to-end task completion.
It remains a separate evidence family from the later browser workflow.

## CiviCRM browser-workflow boundary

A third closed observation runs Playwright 1.62.0 with Chromium from an exact
digest-pinned image on the same internal Docker network. The browser container
is read-only, drops all capabilities, gains no new privileges, mounts only the
fixed workflow and pinned `playwright-core` dependency read-only, and retains no
screenshots, traces, downloads, HTML, cookies, or credentials. Requests outside
the local application origin are blocked.

The independent reader opens the all-cases dashboard, locates the first
synthetic case, follows CiviCRM's supported Manage Case action, verifies the
exact subject, case type, displayed status, coordinator, Roles region, and
Activities region, and emits only a fixed JSON projection. The offline verifier
emits a separate aggregate `browser-workflow-result.json`; it does not change
`target-result.json`, the five target probes, or the structural evaluator.

The pinned CiviCRM Standalone build raises the same non-fatal
`jquery_notify_unavailable` TypeError on dashboard and Manage Case load. The
canary accepts only those two exact occurrences and records their sanitized key
and count; any other page error, failed request, or off-origin request fails the
workflow. This proves one bounded synthetic browser task despite that known
runtime defect. It does not prove accessibility, general UI usability,
production readiness, or any other case-management workflow.

## CiviCRM automated-accessibility boundary

A fourth closed observation injects pinned axe-core 4.12.1 into the already
isolated Chromium page after the Manage Case controls are visible. It runs only
the WCAG 2.0 A/AA and WCAG 2.1 A/AA tagged automated rules against that full
document. The native projection retains the engine/version, rule tags, aggregate
pass/incomplete/inapplicable counts, and each violation's rule ID, impact, and
affected-node count. Selectors, HTML snippets, help URLs, screenshots, traces,
and other node-level results are discarded.

The fixed observation reports 32 passing rules, 0 incomplete, 29 inapplicable,
and two serious violations: `color-contrast` affecting four nodes and
`link-in-text-block` affecting two. The offline verifier emits these findings in
a separate `accessibility-result.json`; it does not turn them into a composite
pass/fail or alter any prior evidence family.

This automated observation does not establish WCAG conformance and does not
cover keyboard operation, focus order or visibility, screen-reader behavior,
zoom/reflow, or contextual review of contrast and semantics. Those require
manual and assistive-technology testing.

## CiviCRM keyboard-interaction boundary

A fifth closed observation clears focus after the Manage Case scan and sends at
most 80 Tab presses from the document start. In the pinned page, the Roles
disclosure summary receives focus on press 69; Enter closes it and Space reopens
it. The native projection retains only those semantic steps, the Tab count, the
browser engine, and an empty artifact list. The offline verifier emits separate
`keyboard-result.json` evidence and does not convert the observation into a
pass/fail score.

This programmatic interaction covers one control only. It does not evaluate the
meaning or efficiency of the preceding focus sequence, visible focus styling,
focus traps elsewhere, complete keyboard operation, or screen-reader behavior.
It therefore establishes neither keyboard accessibility nor WCAG conformance.

## CiviCRM activity-view boundary

A sixth closed observation follows the first generated activity's supported
read-only `View` action from Manage Case. It requires the fixed Activity View
route and exact markers for the synthetic case subject, `Open Case` activity
type, `Completed` status, and page heading. The route raises one additional
`jquery_notify_unavailable` TypeError; only that exact error at the activity-view
navigation step is accepted.

The native projection retains semantic step keys, the sanitized error key/count,
browser engine, and an empty artifact list. The verifier emits separate
`activity-view-result.json` evidence. This proves only that one target-generated
activity can be viewed. It does not prove editing, creation, filtering,
attachment behavior, other activity types, or restoration of the two missing
source audit events.

## CiviCRM contact-summary browser-workflow boundary

A seventh closed observation reopens the all-cases dashboard after the
activity-view task, locates the exact synthetic contact link, and follows it to
the fixed Contact Summary route. It requires the contact-page region, exact
synthetic contact name, and Cases affordance. Dashboard and Contact Summary
navigation each raise the same bounded `jquery_notify_unavailable` TypeError;
only those two exact occurrences at those steps are accepted.

The native projection retains semantic step keys, browser engine, the sanitized
error key/count, and an empty artifact list. The verifier emits separate
`contact-summary-workflow-result.json` evidence. This proves only one read-only
dashboard-to-contact-summary path. It does not prove contact editing, navigation
into a case, accessibility, other contact workflows, or operational
equivalence.

## CiviCRM evidence-index boundary

The normalizer emits `evidence-index.json` as a closed catalog of the normalized
export and seven independent CiviCRM result artifacts. Each entry fixes only an
artifact identifier, filename, schema, decision scope, byte length, and SHA-256
digest. The binding is calculated from the exact byte string written for each
artifact. The index contains no status, score, pass count, priority, or inferred
conclusion and therefore cannot replace validation of an entry's schema or
interpretation of its own limitations.

In particular, listing `export.json` beside the target-interface and browser
evidence does not compose them. The export remains input to the separate
five-dimension structural evaluator, while each result remains bounded to its
own observation. The index is unsigned and authenticates neither the artifacts
nor the operator-asserted target execution. Its digests detect an internally
inconsistent artifact set but can be recomputed by a fabricator.

`verify-civicrm-evidence-index` provides a fail-closed consumer for this narrow
contract. It validates the exact v0.3 index, performs bounded regular-file reads
of the eight fixed sibling artifacts, checks their lengths and digests, validates
the index and seven result documents against packaged JSON Schemas, and validates
the normalized export through the existing strict loader. Its bounded export
attachment reads verify every declared content digest. It does not run the
structural evaluator or interpret the observations, and its success scope is
explicitly `catalog_bindings_artifact_schemas_and_export_attachments_only`.
The command emits a separate closed
`exitdrill/civicrm-evidence-verification/v0.2` document. Its own
`schema_version` is distinct from `index_schema_version`, and fixed limitations
prevent a binding/schema success from being represented as authenticated,
complete, interpreted, or structurally restorable evidence.

## Data contracts

The baseline records expected identities, exact scalar values for its declared
required fields, and exact audit action/time tuples. It is an operator
assertion, not ground truth. The normalized export records:

- entities with scalar fields;
- directed typed relationships;
- attachments with owner, bounded relative path, and content digest;
- semantic permission grants; and
- audit events with referenced objects.

The receipt emits none of those record-level identifiers or values. It emits
aggregate counts, dimension statuses, source-document hashes, and limitations.
`observed_remediation_signals` sums observed missing and invalid conditions; it
is deliberately not called a minimum task count, cost, or RTO estimate.

The CiviCRM target result is a different public contract. It records the pinned
source and target profiles, five bounded target-interface probe states,
represented/unmapped counts, target-generated counts, and fixed limitations. It
contains no record IDs, field values, attachment bytes, credentials, paths, HTTP
bodies, score, or structural-restoration label. It never replaces or overrides
a receipt.

Entity value comparison is exact and bounded to the baseline's required-field
assertions. Each entity contributes at most one invalid count even if several
declared fields are missing, mistyped, or unequal. Undeclared fields remain
outside the denominator.

## Result algebra

Per dimension:

1. missing expected or invalid/restoration loss → `fail`;
2. partial/unavailable denominator → `indeterminate`;
3. extra exported items → `finding`;
4. complete exact reconstruction → `pass`.

Overall:

1. any failure → `not_structurally_restorable`;
2. otherwise any indeterminate → `indeterminate`;
3. otherwise any finding → `structurally_restorable_with_findings`;
4. every dimension passes → `structurally_restorable`.

These are structural states only.

## Receipt comparison

Comparison treats its first and second operands as caller-supplied reference
and candidate inputs. It never reads envelope timestamps and never serializes
input paths. Before producing deltas it requires equality of:

- drill ID and source system;
- baseline SHA-256;
- receipt and result schema versions;
- decision scope and trust limitations; and
- coverage and expected count for every dimension.

A failed check produces a closed `incomparable` result with reason codes and no
dimension comparison. Comparable dimensions report every signed count delta,
but only missing/invalid movement feeds observed loss-signal direction. Extras
and status transitions remain factual context. Statuses are not ordinal, and
partial or unavailable coverage makes assessment uncertain.

The output has no aggregate score. `duplicate_payload` means the deterministic
payloads are identical; `no_observed_loss_signal_change` means only that the
available aggregate missing/invalid signals did not move. Neither can detect
same-count record substitution. The receipt contract does not bind the
export-generation method or evaluator version, so comparison cannot causally
attribute a change.

The optional CLI policy `--fail-on-loss-signal-increase` is applied after the
comparison document is complete and does not modify it. Invalid receipts,
incomparable inputs, or command-usage errors exit 2. A comparable result exits 3
only when a dimension's explicit missing/invalid increase array is nonempty;
otherwise it exits 0. Without the flag every comparable result exits 0. This
includes mixed movement and directly observed increases under partial coverage,
although partial coverage keeps the document's assessment `uncertain`. Status
transitions, extras, and other count deltas never feed the policy. Exit 3 names
only this observed aggregate condition; it does not classify overall direction,
certainty, or readiness.

The public JSON Schema validates closed structure and every locally expressible
invariant. Cross-object equality is not expressible in standard Draft 2020-12.
`verify_comparison_document` therefore verifies both original receipts,
recomputes the complete deterministic comparison, and requires canonical byte
equality. This is the source-bound semantic verification path for summaries,
measurement relationship, scope checks and reasons, deltas, transitions,
signals, and assessments.

## Trust claims

The current evaluator records:

- exact baseline and normalized-export digests;
- exact equality for baseline-declared required entity fields;
- observed attachment-byte fidelity;
- dimension numerators and denominators;
- reference restore success; and
- deterministic replay equivalence.

For the one target canary, separate evidence additionally records that the
closed captured API and file responses satisfied the five pinned
target-interface probes. That evidence is an unsigned observation of one
synthetic lab, not an evaluator claim or a general connector guarantee.

It does not prove:

- the baseline or export is authentic or complete;
- the capture manifest authenticates its author or acquisition context;
- a vendor exported everything it holds;
- semantic or operational equivalence;
- successful cutover into another product;
- vendor deletion;
- trusted authorship or time; or
- legal compliance.

The unsigned self-contained payload checksum detects accidental or incomplete
modification. An attacker able to rewrite the receipt can recompute it.
Recomputed payloads still have to satisfy the closed semantic result contract,
but that validation does not authenticate who produced the data.
