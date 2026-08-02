# ExitDrill

[![CI](https://github.com/ChelseaKR/exitdrill/actions/workflows/ci.yml/badge.svg)](https://github.com/ChelseaKR/exitdrill/actions/workflows/ci.yml)

Run structural recovery drills for leaving SaaS systems.

**Status:** technical alpha · synthetic data only · offline verifier with an
optional isolated local capture lab · zero runtime dependencies

ExitDrill asks a question that ordinary backup and native export checks do not:

> Could this organization reconstruct enough structure to keep operating if its
> SaaS vendor disappeared or became unacceptable?

The current evaluator compares an independently captured baseline with a
normalized export, validates entity identities and declared critical field
values, relationships, attachment bytes, permission grants, and audit events,
then loads the package into an in-memory neutral SQLite reference model. It
emits an aggregate receipt that can be checked and replayed offline.

This is a structural normalization experiment, not yet the complete product.
A neutral SQLite restore does **not** prove that people can operate in an
alternate production system. The repository now also exercises one closed,
synthetic Directus-to-CiviCRM target profile through supported target interfaces,
independent read-back, and five target-interface probes. That canary
intentionally retains a failing structural result and does not establish
operational equivalence, production readiness, or a stronger restoration label.

## Five-minute synthetic drill

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
make install
make verify
make demo
make package
```

Or run the public flow directly:

```sh
exitdrill validate \
  examples/synthetic-crm/baseline.json \
  examples/synthetic-crm/export.json

exitdrill drill \
  examples/synthetic-crm/baseline.json \
  examples/synthetic-crm/export.json \
  --attachment-root examples/synthetic-crm/export-files \
  --out receipt.json

exitdrill verify receipt.json \
  --baseline examples/synthetic-crm/baseline.json \
  --export examples/synthetic-crm/export.json \
  --attachment-root examples/synthetic-crm/export-files

exitdrill report receipt.json --out report.html
```

Checksum-only verification reports `checksum_self_consistent`; it does not
authenticate the receipt. Supplying all replay inputs reports `replay_verified`.
The receipt payload is a closed contract: recomputing a checksum cannot make
missing dimensions, impossible counts, or contradictory statuses valid.

The `report` command strict-loads and semantically verifies the receipt before
writing a deterministic, accessible, standalone HTML summary. The report has no
scripts or external assets, contains only the aggregate receipt evidence, and
states the same trust limitations in plain language. It does not turn an
unsigned checksum into authentication or a structural result into operational
exit readiness.

The fixture uses only invented people, cases, relationships, roles, events, and
attachment content.

The adversarial demonstration keeps the same entity row count while replacing
one person, rewiring a relationship, corrupting attachment content, collapsing a
permission role, and replacing an audit event:

```sh
make demo-lossy
```

ExitDrill returns `not_structurally_restorable`. This is the core product claim
under test: “100% of the rows exported” can still conceal an unsafe exit.
The receipt reports `observed_remediation_signals`, not a cost, task count, or
minimum remediation estimate.

## Directus API-response capture canary

The repository also contains a source-specific canary captured from a real,
local Directus 11.17.4 process. The sandbox used SQLite, an invented civic-case
schema, fixed synthetic records, local attachment bytes, and documented
first-party API surfaces for content, file metadata and bytes, permissions, and
activity. The artifact is a custom ExitDrill capture bundle assembled from those
responses, not a vendor-native Directus export format. It contains no production
or customer data. Directus is Business Source License software; this local
nonproduction experiment does not describe it as open source.

The capture boundary follows Directus's official documentation for
[self-hosting](https://directus.com/docs/self-hosting/deploying),
[files and assets](https://directus.com/docs/api/files),
[permissions](https://directus.com/docs/api/permissions), and
[activity](https://directus.com/docs/api/activity). The fixture
README pins the exact release, image digest, API surfaces, and license text.

Run the complete synthetic acceptance demonstration without Docker or network
access:

```sh
make demo-directus-canary
```

The command verifies the capture manifest, checks byte-identical
normalization output across two runs, runs and replays a clean drill, builds an
equal-row-and-file-count adversarial derivative, runs and replays its failing
drill, renders both aggregate-only reports, compares the receipts, and checks
the opt-in comparison policy exit. The clean canary passes all five declared
dimensions. The derivative produces exactly six observed missing/invalid
signals after changing a declared critical value, an unreferenced identity, a
relationship, same-length attachment bytes, permission semantics, and an audit
action.

The source adapter is deliberately outside the evaluator's trust algebra:

```sh
exitdrill normalize-directus-canary \
  examples/directus-11.17.4-civic-case/native/capture-manifest.json \
  --out-dir normalized-directus-canary
```

The normalizer accepts only this bounded canary profile, verifies every declared
captured response or attachment before semantically parsing it, and atomically
writes the existing ExitDrill `export.json` plus attachment layout. Its aggregate
normalization manifest is out of band. The receipt continues to bind the
normalized export, not the operator-asserted acquisition process. Neither the
manifest hash nor the receipt checksum authenticates who produced the custom
capture bundle or proves that the capture includes everything Directus held.

The defensible claim is limited to the exact synthetic lab configuration: a
pinned Directus 11.17.4 API-response capture bundle can be reproducibly
normalized and the declared equal-count losses are detected. This is not
evidence of a production migration, operational equivalence, vendor deletion,
general CRM portability, or nonprofit case-management behavior.

## CiviCRM target-roundtrip canary

One additional closed profile maps the same frozen Directus source fixture into
a fresh, local CiviCRM Standalone 6.16.2 sandbox. The reviewed lab pins the
application and database images by digest, exposes no host port, blocks target
egress, disables outbound mail, scheduled jobs, and the external password
lookup, and creates four distinct synthetic principals. A writer loads only the
fixed profile; an independent reader reconstructs target state through APIv4 and
authenticated private-file read-back.

The implementation follows CiviCRM's official documentation for
[Standalone](https://docs.civicrm.org/installation/en/latest/standalone/),
[APIv4 REST](https://docs.civicrm.org/dev/en/latest/api/v4/rest/), and
[AuthX](https://docs.civicrm.org/dev/en/latest/framework/authx/). The upstream
[Docker project](https://github.com/civicrm/civicrm-docker) describes its
quickstart as a local testing environment, so this repository does not present
the container lab as a production deployment.

Run the committed target evidence and all offline negative controls without
Docker or network access:

```sh
make demo-civicrm-target-canary
```

Or invoke the closed verifier directly:

```sh
exitdrill normalize-civicrm-target-canary \
  examples/civicrm-6.16.2-target-roundtrip/native/capture-manifest.json \
  --out-dir normalized-civicrm-target-canary
```

The five observed target-interface probes cover record lookup, relationship
traversal, private attachment-byte retrieval, authorized access, and
authenticated denial over the same protected record. All five pass in the clean
frozen capture. The separate structural evaluation still reports
`not_structurally_restorable` with six known gaps: two Directus collection-scope
entities, two source permission grants, and two source audit events have no
semantics-preserving representation in this profile. Target scaffolding is
counted separately and never relabeled as source data.

The live capture harness first verifies the exact Directus normalization and
binds its adapter profile, normalization schema, source-bundle,
normalized-export, and normalized-attachment digests in the target manifest.
That live Docker capture gate is separate from the offline command above. The
offline command checks the frozen bundle, its unsigned execution assertions,
deterministic normalization, structural result, and negative controls; it does
not rerun or authenticate the historical sandbox.

The target result is aggregate, unsigned, and profile-specific. Successful
target-interface probes do not override the five-dimension structural result,
prove UI usability, preserve source principals or history, establish a completed
migration, or support a general Directus/CiviCRM connector claim.

The same live harness also exercises one authenticated server-rendered Contact
Summary surface with the independent reader. Its separate aggregate
`ui-surface-result.json` records that the exact synthetic contact and Cases-tab
affordance were observed. A third evidence family drives a digest-pinned,
isolated Chromium browser from the all-cases dashboard into Manage Case and
observes the exact synthetic case controls. That single browser task retains no
browser artifacts and reports two known non-fatal CiviCRM
`jquery_notify_unavailable` errors. It does not prove accessibility, general UI
usability, another casework task, or production readiness.

A fourth evidence family runs pinned axe-core WCAG 2.0/2.1 A/AA-tagged rules on
that Manage Case document. Its sanitized `accessibility-result.json` reports 32
passing rules, 0 incomplete rules, 29 inapplicable rules, and two serious
violations: `color-contrast` on four nodes and `link-in-text-block` on two. It
retains no selectors or HTML and does not establish WCAG conformance; keyboard,
screen-reader, focus, contrast-context, and zoom/reflow testing remain manual.

## Compare recurring receipts

After creating two receipts, compare their aggregate evidence offline:

```sh
exitdrill compare reference-receipt.json candidate-receipt.json
```

The operand order is supplied by the caller and is not inferred from either
receipt's untrusted envelope time. The command first performs full bounded
receipt and payload validation. Comparison is allowed only when the drill ID,
source system, exact baseline digest, contract versions, decision scope,
dimension coverage and expected counts, and trust limitations match.
Otherwise it emits `comparability: incomparable`, fixed reason codes, no
dimension deltas, and exits with status 2.

For comparable inputs, each dimension reports signed candidate-minus-reference
count deltas. Only increases or decreases in observed `missing_count` and
`invalid_count` become loss-signal assessments. Extra-record and status changes
remain separate factual transitions; statuses are never ranked. Partial or
unavailable coverage forces an `uncertain` assessment. Identical payload hashes
are labeled `duplicate_payload`, while unchanged aggregates from distinct
payloads mean only `no_observed_loss_signal_change`.

CI can opt into a policy exit without changing the JSON evidence:

```sh
exitdrill compare reference-receipt.json candidate-receipt.json \
  --fail-on-loss-signal-increase
```

Exit status 0 means the inputs are comparable and no directly observed
`missing_count` or `invalid_count` increase triggered the requested policy.
Status 3 means at least one comparable dimension directly observed such an
increase, including mixed increase/decrease movement. Status 2 retains
precedence for invalid receipts, incomparable inputs, and command-usage errors.
Without the flag, every comparable result exits 0. Status 3 says only that the
opt-in condition matched observed aggregate evidence; it is not a label for
overall direction, certainty, operational readiness, or any status rank.

The policy checks only each dimension's explicit missing/invalid increase
signals. It never ranks statuses, extras, restored/exported totals, or a
composite value. With partial or unavailable coverage, a directly observed
increase can therefore produce status 3 while the JSON assessment correctly
remains `uncertain`; the exit policy does not convert uncertainty into a
structural conclusion.

The comparison has no score and makes no claim about record identity churn,
chronology, authenticity, causal attribution, or operational exit readiness.
It does not bind the export-generation method or evaluator version, so even
same-scope movement cannot prove why a signal changed. Inputs and comparison
output remain unsigned and unauthenticated. Its closed machine-readable contract is
[receipt-comparison-v0.1.schema.json](schemas/receipt-comparison-v0.1.schema.json).
The JSON Schema closes structure and locally expressible invariants. Standard
Draft 2020-12 cannot compare arbitrary sibling values, so source-bound semantics
must also be verified against the two original receipts:

```python
from exitdrill import verify_comparison_document

verify_comparison_document(comparison, reference_receipt, candidate_receipt)
```

That verifier fully validates both receipts, recomputes the deterministic
comparison, and requires byte-exact canonical equality. It detects forged
summaries, scope checks/reasons, payload relationships, deltas, transitions,
signals, and assessments.

## Synthetic target-exercise preflight

The future target-exercise protocol can be checked without connecting to a
source or target:

```sh
exitdrill validate-exercise examples/synthetic-exercise/plan.json
```

This validates only a synthetic plan: separate baseline coverage, an empty and
isolated egress-blocked target, disabled automations, read-back evidence, and
the five required target-interface probes. It executes nothing and cannot
produce a restoration result.

## Result semantics

Each dimension reports:

- `pass`: complete baseline, no observed structural loss;
- `finding`: no observed loss, but the export contains additional items;
- `fail`: expected items are missing, invalid, corrupt, or cannot be restored;
- `indeterminate`: the baseline is partial or unavailable.

Overall states are deliberately bounded:

- `structurally_restorable`;
- `structurally_restorable_with_findings`;
- `not_structurally_restorable`; or
- `indeterminate`.

No state means “portable,” “exit ready,” “operationally equivalent,” or legally
compliant.

## Hard boundaries

- Synthetic data only.
- No live vendor credentials, APIs, destructive operations, or production writes.
- No arbitrary transforms, commands, plugins, SQL, JQ, or model-generated mapping.
- The profile-specific Directus normalizer accepts only the committed 11.17.4
  synthetic canary profile; it is not a generic connector or
  permission-equivalence engine.
- The profile-specific CiviCRM verifier accepts only the committed 6.16.2
  synthetic target read-back; its five target-interface probes are not a
  migration, UI, or source-permission-equivalence claim.
- No claim that an export proves its own completeness.
- No claim that file presence proves semantic usability.
- No claim that a successful neutral import proves operational recovery.
- Field-value equivalence is limited to baseline-declared required fields;
  undeclared field values and permission-principal identity remain explicitly
  outside the current evaluator's denominator.
- No raw record fields or attachment content in receipts.
- No receipt comparison based on paths, claimed timestamps, or a composite
  portability score.
- No CI comparison policy based on statuses, extra records, aggregate totals,
  or uncertain coverage being treated as a structural conclusion.
- No signature or trusted-time claim; the self-contained hash is a checksum, not
  authentication.
- No ambiguous or unbounded JSON: duplicate keys, non-finite numbers, excessive
  nesting or node count, non-regular document paths, and undeclared
  receipt/envelope fields fail closed.
- No single portability score that can hide a failed dimension.

## Why the baseline is separate

A vendor export cannot establish its own denominator. The baseline represents
what an operator could observe before requesting the export. Its coverage must
be declared separately for entities, relationships, attachments, permissions,
and audit history. Partial or unavailable coverage yields `indeterminate`; it
never silently becomes a pass.

Each required entity field also carries an independently captured expected
scalar value. A missing field, wrong scalar type, or unequal value is an invalid
entity. Fields absent from that declared set make no equivalence claim, and raw
field values never enter the receipt.

## Product direction

The intended wedge is recurring CRM/case-management exit drills for nonprofits
and local government. The Directus canary exercises one real source process, and
the CiviCRM canary exercises one real target process; neither is domain
validation. A second real source-target exercise is required before extracting a
connector SDK. Any production-derived design-partner work remains blocked on the
documented data-governance gate and would need user-visible operational scenarios
beyond these target-interface probes.

## Project documents

- [Architecture](docs/ARCHITECTURE.md)
- [Architecture decision](docs/decisions/0001-structural-evaluation-before-target-adapter.md)
- [Synthetic preflight decision](docs/decisions/0002-synthetic-exercise-preflight.md)
- [Directus canary boundary decision](docs/decisions/0004-normalize-one-directus-canary-outside-evaluator.md)
- [CiviCRM target-roundtrip decision](docs/decisions/0005-exercise-one-civicrm-target-roundtrip-canary.md)
- [CiviCRM UI-surface decision](docs/decisions/0006-observe-one-authenticated-civicrm-ui-surface.md)
- [CiviCRM browser-workflow decision](docs/decisions/0007-observe-one-civicrm-browser-workflow.md)
- [CiviCRM automated-accessibility decision](docs/decisions/0008-record-one-automated-accessibility-observation.md)
- [Threat model](docs/THREAT-MODEL.md)
- [Responsible-technology audit](docs/RESPONSIBLE-TECH-AUDITS.md)
- [Data governance](docs/DATA-GOVERNANCE.md)

## Standards Conformance

| Standard | Current disposition |
|---|---|
| Quality & Metrics | Applies; ≥90% branch coverage is merge-blocking |
| Code Quality | Applies; Python 3.12, strict mypy, Ruff, and pytest |
| Security & Supply-Chain | Applies; closed local inputs, zero runtime dependencies, pinned CI actions, SAST, secret and dependency scanning are committed |
| CI/CD | Applies; committed workflows mirror local verification and demo paths |
| Release/versioning | Applies; the build-only candidate workflow publishes no package or registry artifact |
| Accessibility | Applies; deterministic report tests cover the language declaration, skip link, table caption, aggregate-only content, escaping, and absence of scripts; the pinned CiviCRM page has a separate automated finding report that is explicitly not a conformance claim |
| Observability | Tier C; service telemetry is out of scope because the CLI is offline and emits no operational logs |
| Performance | N/A — offline CLI with no latency contract; input and attachment work remain bounded |
| Internationalization | N/A — English-only expert operator workflow |
| AI evaluation | N/A — deterministic evaluator with no model or AI SDK |
| Documentation | Applies; the canonical [ADR index](docs/adr/0000-record-architecture-decisions.md) links accepted history without breaking its original paths |
| Responsible-Tech Framework | Applies; see the current responsible-technology audit |
| Incident response and data governance | Applies; synthetic-only data gate remains mandatory |
