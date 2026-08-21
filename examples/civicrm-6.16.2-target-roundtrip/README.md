# CiviCRM 6.16.2 synthetic target-roundtrip canary

This directory describes one pinned, synthetic-only target read-back from a
local CiviCRM Standalone 6.16.2 sandbox. The source is the committed Directus
11.17.4 civic-case profile. That source is a custom ExitDrill bundle assembled
from documented API responses and attachment bytes; it is **not** a
vendor-native Directus export.

The accepted profile is
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1`. It is a closed
source-to-target lab, not a generic CiviCRM adapter. Its `native/` bundle
contains fixed API read-back envelopes, identity-separation evidence,
permission-probe outcomes, and attachment bytes from the disposable target.
It also contains separate sanitized browser-workflow, automated-accessibility,
keyboard-interaction, activity-view, contact-summary workflow, and
target-generated case-client workflow observations, plus one browser
access-denial observation.
The same route and protected contact also have a separate allow-control
observation under the distinct authorized principal.
The profile verifier must reject any other version, file inventory, sandbox
posture, identity shape, or response shape rather than infer a mapping.

## Evidence boundary

The lab uses four distinct synthetic target identities:

- a writer that creates the fixed target records;
- a read-only reader used for independent data read-back;
- an allowed user for the positive permission probe; and
- a denied user for the negative permission probe.

The native JSON files are deterministic, closed capture projections of real
supported APIv4 and AuthX responses. They preserve the selected values used by
this profile while omitting unrelated transport metadata. They are not
byte-raw HTTP response bodies.

`ui-contact-summary.json` is a sanitized projection of one authenticated,
server-rendered Contact Summary response. The live harness publishes it only
when the independent reader sees the exact synthetic contact, the contact-page
container, and the Cases tab.

`browser-workflow.json` is a separate sanitized projection of one real Chromium
task. The same independent reader opens the all-cases dashboard, locates the
first synthetic case, opens Manage Case, and observes the exact summary, status,
type, coordinator, Roles, and Activities controls. The read-only,
capability-dropped browser container uses the internal Docker network and an
exact digest-pinned Playwright image. It retains no screenshots, traces,
downloads, HTML, cookies, or credentials and blocks requests outside the local
application origin.

The pinned CiviCRM Standalone UI raises two exact, non-fatal
`jquery_notify_unavailable` page errors during this task. The workflow records
their sanitized key and count and rejects any other page error, failed request,
or off-origin request. This defect remains part of the evidence, not a hidden
exception.

`browser-accessibility.json` is a separate sanitized axe-core 4.12.1 scan of
the full Manage Case document after those controls are visible. It retains only
rule counts and each violation's rule ID, impact, and affected-node count—never
selectors, HTML snippets, screenshots, or traces. The fixed scan reports 32
passing rules, 0 incomplete, 29 inapplicable, and two serious violations:
`color-contrast` on four nodes and `link-in-text-block` on two nodes. Automated
coverage is partial and does not establish WCAG conformance; keyboard,
screen-reader, focus, and zoom/reflow testing remain unperformed.

`browser-keyboard.json` separately records one programmatic keyboard path from
the document start. The Roles disclosure receives focus after 69 Tab presses,
closes with Enter, and reopens with Space. The projection retains no focused
element labels, selectors, DOM paths, screenshots, or HTML. This is not a
complete tab-order, visible-focus, keyboard-accessibility, screen-reader, or
WCAG-conformance result.

`browser-activity-view.json` records a second read-only browser task. From
Manage Case, the reader follows the generated activity's supported `View`
action and observes the Activity View heading, exact synthetic case subject,
`Open Case` type, and `Completed` status. The route raises one additional exact
`jquery_notify_unavailable` error. The projection retains no route parameters,
target IDs, HTML, screenshots, traces, or credentials.

`browser-contact-summary-workflow.json` records a third read-only browser task.
The reader reopens the all-cases dashboard, follows the exact synthetic contact
link into Contact Summary, and observes the contact-page region, exact contact
name, and Cases affordance. The two exact page-load
`jquery_notify_unavailable` errors are recorded. The projection retains no
route parameters, target IDs, HTML, screenshots, traces, or credentials.

`browser-case-client-workflow.json` records a fourth read-only browser task.
The reader reopens the dashboard, follows the target-generated helper that
CiviCRM uses as the case client, opens its Contact Summary, activates Cases,
observes the exact synthetic case, and follows the row's `Manage` action back
to Manage Case. Three exact page-load `jquery_notify_unavailable` errors are
recorded. The helper is target scaffolding, not restored source data, and the
projection retains no route parameters, target IDs, HTML, screenshots, traces,
or credentials.

`browser-access-denial.json` records a fifth browser task under the distinct
deny principal. A direct request for the protected Alpha contact redirects from
Contact Summary to `/civicrm`, and neither the contact page nor protected name
is present. The projection retains only route names and statuses, semantic
steps, a sanitized single known-error key/count, and an empty artifact list.
This one observation does not prove all UI or API authorization behavior.

`browser-access-allow-control.json` records the paired positive control. The
distinct allow principal receives HTTP 200 and the protected Contact Summary
page and name are present. The minimized projection retains neither the name nor
contact ID and does not establish authorization behavior beyond this one route.

`browser-case-search-workflow.json` records a seventh browser task. The reader
opens the Case Summary drilldown and observes both exact synthetic cases, then
opens Edit Search Criteria and submits the exact visible Alpha subject. The
pinned target returns HTTP 500 and an Error page. The minimized projection
retains no subject, case ID, route parameters, response body, HTML, screenshot,
or trace. It does not establish root cause, behavior of other filters or
configurations, or general search usability.

Source-mapped business-state read-back never uses the writer credential or its
in-memory mutation responses. A separate AuthX identity envelope records writer
authentication for identity-separation evidence; it is not business-state
read-back. Fresh authenticated HTTP client processes access the application only
on the internal, run-owned Docker network, and no service publishes a host port.
The target is checked for the pinned empty-business-data precondition before
writing, has no external network route, has outbound email disabled, and has no
cron runner.
Production-derived data and production credentials are prohibited.

Before loading the target, the live harness verifies the closed Directus
normalization and binds this exact aggregate source seam in the target manifest:

```json
{
  "adapter_profile": "directus-11.17.4-civic-case/v0.1",
  "attachment_bundle_sha256": "b1e24857570523f2d1606bb3ef0d32708680b369b631c623df83db95f16c177d",
  "export_sha256": "2e2a4280c7e9b2249b443a861e3eb8498a379bd462b2b4ad5637208d9698a51b",
  "schema_version": "exitdrill/directus-normalization/v0.1",
  "source_bundle_sha256": "a67048bf25c07b73aa0bff26372090c0a7e5ce77871b49259d0a96110998be49"
}
```

The five observed target-interface probes are:

| Probe | Clean captured outcome |
|---|---|
| Find a declared record | pass |
| Traverse a declared relationship | pass |
| Retrieve and hash declared attachment bytes | pass |
| Read a protected record as the allowed identity | pass |
| Fail to return that same record as the denied identity | pass |

The allow and deny probes execute the same permission-enforced `Contact.get`
query. The authenticated allowed identity receives exactly one matching record;
the authenticated denied identity receives the documented APIv4 filtered result
with HTTP 200 and zero values. The separately captured identity responses record
successful authentication for both credentials in those requests. No probe
disables API permission checks.

The attachment-byte probe is not an attachment-ACL claim. It proves that the
allowed reader retrieved the expected target-associated bytes in this exact
sandbox. The deny probe covers the protected `Contact.get` query, not the file
download surface. ExitDrill therefore makes no claim that CiviCRM attachment
authorization is equivalent to the source permission model or inherits the
same case-level access rules.

## Intentionally incomplete structural read-back

The unchanged ExitDrill evaluator compares the normalized target read-back with
the original independent Directus baseline. The clean target result is
intentionally `not_structurally_restorable`:

| Dimension | Expected | Exported | Restored | Missing | Invalid | Status |
|---|---:|---:|---:|---:|---:|---|
| Entities | 7 | 5 | 5 | 2 | 0 | fail |
| Relationships | 2 | 2 | 2 | 0 | 0 | pass |
| Attachments | 2 | 2 | 2 | 0 | 0 | pass |
| Permissions | 2 | 0 | 0 | 2 | 0 | fail |
| Audit events | 2 | 0 | 0 | 2 | 0 | fail |

The six observed remediation signals are deliberate and explicit: two Directus
collection-scope technical entities, two Directus policy grants, and two source
audit events have no semantics-preserving representation in this fixed CiviCRM
target profile. Recreating similarly named target configuration or events would
be fabricated equivalence, so the target export omits them and the evaluator
fails closed.

The profile also records target-generated scaffolding separately from source
data: two case activities, two case contacts, one case type, two custom-field
groups, seven custom fields, three ACL groups, four ACL group memberships, two
ACL roles, two ACL entity-role assignments, two ACL rules, one helper contact,
four principals, four application roles, zero created relationship types, and
one referenced built-in relationship type.

Passing all five target-interface probes does not override that structural
result. The generated `target-result.json` records only bounded probe
observations and represented, unmapped, or target-generated counts; it has no
composite restoration status.

The generated `ui-surface-result.json`, `browser-workflow-result.json`,
`accessibility-result.json`, `keyboard-result.json`,
`activity-view-result.json`, `contact-summary-workflow-result.json`, and
`case-client-workflow-result.json`, `browser-access-denial-result.json`, and
`browser-access-allow-control-result.json`, and `case-search-workflow-result.json`
are separate evidence families. The browser results support only the seven
read-only tasks described above. The accessibility and
keyboard results report only their bounded observations and are not conformance
verdicts. None modifies the target probe algebra or structural result.

`evidence-index.json` is a twelfth, non-evaluative artifact: a closed catalog of
`export.json` and the eleven result files. It records only each artifact's fixed
identifier, filename, schema, independent decision scope, byte length, and
SHA-256 digest. It contains no status, score, pass count, priority, or inferred
conclusion, and it does not replace schema validation or the structural
evaluator. The unsigned digests detect internal inconsistency but do not
authenticate who produced the files or whether the lab assertions are true.

After normalization, verify the index contract and exact artifact bindings:

```sh
exitdrill verify-civicrm-evidence-index out/evidence-index.json
```

The command's success scope is
`catalog_bindings_artifact_schemas_and_export_attachments_only`. It validates
the packaged index and result schemas, the normalized export contract, and its
declared attachment bytes. It does not interpret any finding, run the structural
evaluator, authenticate the files, or prove live execution.
Its stdout uses the separate closed
`exitdrill/civicrm-evidence-verification/v0.6` schema, identifies the verified
v0.7 index in `index_schema_version`, and carries fixed limitations with the
success status.

The live capture gate and offline acceptance gate are distinct. The live harness
may publish a bundle only after its fresh sandbox, source normalization, target
load, independent business-state read-back, and target-interface probes pass.
Those execution assertions remain unsigned. The command below verifies the
committed bundle and adversarial controls; it does not rerun or authenticate the
historical Docker execution.

A third, narrower gate closes part of that remaining distance:
[`scripts/check_browser_capture_bindings.mjs`](../../scripts/check_browser_capture_bindings.mjs)
statically extracts the literal each of the four `civicrm_browser_*.mjs`
capture scripts declares as its output on a successful run and requires it to
canonically equal the corresponding committed `browser-*.json`, offline, with
no CiviCRM, Playwright, or Docker involved. Editing a script's declared output
without a matching update to the committed file -- or the reverse -- now fails
this gate. It is bound into `make demo-civicrm-target-canary` and runs on
every PR. It cannot verify the handful of fields only a live page produces
(axe-core's rule counts, its version, and the measured keyboard tab-count to
reach a target); those stay unverified between live recaptures, and the
script documents exactly which fields those are. It does not, on its own,
prove a script's live *behavior* is unchanged -- only that its *declared*
output still matches what is committed. Nothing today re-executes the full
live capture in CI: a real attempt to do so brought up the compose stack and
provisioned CiviCRM successfully but failed during the first browser
automation step on a tight visibility-wait timeout, which is a fixable
reliability gap in the harness, not evidence against determinism -- every
observation asserted above (`requireExact`-style checks throughout the
scripts) makes each script's real output deterministic *given* a completed
run.

## Recapturing this profile

Nothing in CI re-runs the live capture; it is a documented manual procedure,
not an automated or scheduled one, matching the project's paused feature
scope. The entry point is the orchestrator itself:

```sh
uv sync --locked
npm ci --ignore-scripts
node scripts/civicrm_target_roundtrip_lab.mjs --output <a-fresh-empty-directory>
```

No environment variables are required; database and admin credentials are
generated per run and never printed. The orchestrator brings up
`lab/civicrm-6.16.2-standalone/compose.yaml` (pinned MariaDB and CiviCRM
images, `pull_policy: never` -- pull them first if they are not already
local), provisions CiviCRM's business data, roles, and ACLs, then invokes
each of the four `civicrm_browser_*.mjs` scripts in a separate, digest-pinned,
read-only, network-isolated Playwright container. Every observation is
asserted exactly against a fixed expectation before it is written, so a
successful run reproduces the committed bundle by construction, not by
chance.

A real attempt at this procedure, while working on issue #31, brought the
compose stack up healthy and completed CiviCRM provisioning, then failed
inside the first browser script (`civicrm_browser_workflow.mjs`, at the
`case_locator` step) on a 15-second visibility-wait timeout for the "Manage
Case" link, roughly four minutes in. That is a specific, fixable harness
reliability question -- whether the wait budget is tight for a resource-
constrained host, not a question about whether the scripts' declared output
is trustworthy once a run completes. It has not yet been re-run to
confirm a full success.

## Offline acceptance

The offline acceptance command normalizes the committed Directus source,
normalizes the clean target bundle twice, and runs the clean target export
through the unchanged evaluator. It then creates disposable derivatives in a
fresh temporary directory and proves detection of:

- a same-count critical scalar substitution;
- a same-count relationship rewire;
- same-length attachment-byte corruption;
- permission escalation that makes the denied query return the protected
  record; and
- a nonempty-target precondition that is rejected before an output directory is
  created.

The committed bundle is never modified. Each derivative refreshes its declared
byte sizes, SHA-256 values, and aggregate bundle digest before verification.
Aggregate acceptance output must contain no fixture values, attachment content,
credentials, filesystem paths, or raw API responses.

## Claim limits

This evidence supports only the statement that one pinned synthetic Directus
API-response profile was mapped into one pinned CiviCRM 6.16.2 sandbox, five
declared target-interface probes and one Dashboard → Manage Case browser task
were observed, one bounded automated accessibility scan reported the exact
findings above, one disclosure's programmatic keyboard behavior was observed,
one target-generated activity was viewed read-only, one dashboard-to-contact
summary browser path and one target-generated case-client-to-Manage-Case path
were observed read-only, and the unchanged structural
evaluator reported the six known source-to-target gaps.

It does **not** establish:

- operational equivalence, portability, exit readiness, or a successful
  migration;
- general Directus or CiviCRM support;
- preservation of source permission principals, effective authorization, or
  audit history;
- attachment authorization equivalence;
- WCAG conformance, general CiviCRM UI usability, or any unobserved workflow;
- activity editing, creation, or restoration of source audit history;
- contact or case editing, source case-client equivalence, or other contact
  workflows;
- production safety, customer use, vendor deletion, or legal compliance; or
- completeness or authenticity of the source capture, target capture, or
  separately authored baseline.

The fixture and its hashes are unsigned. All records, identities, cases,
relationships, permission probes, and attachment content are invented for this
local lab.
