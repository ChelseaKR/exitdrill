# ExitDrill portfolio case study

## Defensible case study

ExitDrill is Chelsea Kelly-Reif's independently built, post-separation personal
technical alpha for testing whether a SaaS export preserves structure beyond row
counts. Using invented CRM data only, it compares an independently captured
baseline with a normalized export across entities, relationships, attachment
bytes, permissions, and audit history; restores the normalized graph into a
neutral SQLite reference model; and emits replayable aggregate receipts. Its
adversarial fixture keeps the entity row count unchanged while introducing
structural losses, and the evaluator detects those losses. This is a synthetic
engineering case study—not a client engagement, employer deliverable, corporate
past-performance claim, or proof of an operational migration.

The next evidence slice uses a pinned, local Directus 11.17.4 process with an
invented civic-case schema. A reviewed capture script collected documented
first-party API responses and attachment bytes; a closed source-specific
normalizer verifies that manifest and maps it into the existing evaluator
contract. A deterministic equal-row-and-file-count derivative introduces six
different mutations, and the drill reports exactly six observed missing/invalid
signals. This remains a personal synthetic lab, not Directus-wide or
nonprofit-CRM validation.

A second evidence slice loads that fixed source profile into a fresh, isolated
CiviCRM Standalone 6.16.2 lab through supported target interfaces. Four distinct
synthetic principals separate writes, independent read-back, allowed access, and
denied access. The clean capture passes five target-interface probes while the
unchanged structural evaluator still reports six explicit source-to-target gaps.
The independent reader also observes one authenticated server-rendered Contact
Summary surface containing the exact synthetic contact and Cases tab, then
completes one isolated Chromium workflow from the all-cases dashboard into
Manage Case and observes the exact case controls. The workflow reports two known
non-fatal CiviCRM `jquery_notify_unavailable` errors and retains no browser
artifacts. Separate artifacts record one automated accessibility scan, one
bounded keyboard interaction, and one read-only Activity View observation. A
machine-readable evidence index catalogs the normalized export and six result
families without composing their scopes or adding a verdict. Byte lengths and
SHA-256 digests bind the exact generated set for internal consistency without
claiming authenticity. This is a bounded target-process experiment, not a
completed migration, accessibility-conformance assessment, customer result,
employer deliverable, or claim of CiviCRM-wide portability.

## Evidence in the repository

- Five-dimension evaluation, exact comparisons for baseline-declared critical
  field values, and neutral SQLite restoration are implemented in
  [`src/exitdrill/evaluator.py`](../src/exitdrill/evaluator.py) and bounded by the
  design in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).
- The equal-row-count adversarial scenario is encoded in
  [`examples/synthetic-crm-lossy/`](../examples/synthetic-crm-lossy/) and asserted
  in [`tests/test_lossy_demo.py`](../tests/test_lossy_demo.py).
- The real-process synthetic source fixture, independent baseline, capture
  boundary, and claim limits are documented in
  [`examples/directus-11.17.4-civic-case/`](../examples/directus-11.17.4-civic-case/).
- The closed Directus capture normalization seam is implemented in
  [`src/exitdrill/directus_canary.py`](../src/exitdrill/directus_canary.py). The
  one-command clean-vs-lossy acceptance demonstration is
  [`scripts/check_directus_canary_demo.py`](../scripts/check_directus_canary_demo.py)
  and is enforced by [`tests/test_directus_demo.py`](../tests/test_directus_demo.py).
- The closed CiviCRM target read-back verifier is implemented in
  [`src/exitdrill/civicrm_target_canary.py`](../src/exitdrill/civicrm_target_canary.py).
  The digest-pinned local harness lives in
  [`scripts/civicrm_target_roundtrip_lab.mjs`](../scripts/civicrm_target_roundtrip_lab.mjs),
  and its closed browser task is
  [`scripts/civicrm_browser_workflow.mjs`](../scripts/civicrm_browser_workflow.mjs),
  which also emits the sanitized automated-accessibility observation, while
  [`scripts/check_civicrm_target_roundtrip_demo.py`](../scripts/check_civicrm_target_roundtrip_demo.py)
  verifies the frozen clean capture, intentional structural failure, and five
  adversarial controls offline. The normalizer also emits a closed
  digest-bound `evidence-index.json` catalog with no composite status or score.
- Aggregate-only receipts, semantic verification, and offline replay are covered
  by [`src/exitdrill/receipt.py`](../src/exitdrill/receipt.py),
  [`tests/test_receipt.py`](../tests/test_receipt.py), and the end-to-end CLI tests
  in [`tests/test_cli.py`](../tests/test_cli.py).
- The standalone, script-free HTML evidence report is implemented in
  [`src/exitdrill/report.py`](../src/exitdrill/report.py) and tested for
  deterministic output, aggregate-only content, escaping, bounded writes, and
  basic accessibility structure in
  [`tests/test_report.py`](../tests/test_report.py).
- The verification gate runs Ruff, strict mypy, pytest, and branch coverage with
  a 90% minimum; see [`Makefile`](../Makefile) and
  [`pyproject.toml`](../pyproject.toml).

## Claims boundary

The evidence supports saying that ExitDrill is a personal, synthetic-only
technical alpha that detects declared structural losses, restores normalized
data into a neutral reference model, and produces replayable aggregate evidence.
It does **not** support claims of production use, customer adoption, client
delivery, a completed migration, portability, exit readiness, operational
equivalence, authenticated evidence, legal compliance, savings, or successful
cutover to another SaaS product. The Directus evidence supports only one frozen
11.17.4 synthetic source profile captured through documented APIs. The CiviCRM
evidence supports only one frozen 6.16.2 target profile and five target-interface
probe observations plus six separately bounded result families: target
interface, Contact Summary UI surface, Dashboard → Manage Case browser workflow,
automated accessibility, keyboard interaction, and Activity View. A separate
index catalogs those results and the normalized export without composing them.
It still has no supported production connector, production data path, WCAG
conformance evidence, general UI-workflow coverage, or cutover evidence.

## Resume bullet

- Built ExitDrill, an offline Python technical alpha that tests synthetic SaaS
  exports across five structural dimensions; added pinned Directus 11.17.4 source
  and CiviCRM 6.16.2 target canaries with independent API read-back, five bounded
  target-interface probes, one authenticated Contact Summary observation,
  one isolated Dashboard → Manage Case browser task, three further bounded
  accessibility/keyboard/activity observations, adversarial controls, and a
  non-composite evidence catalog that keeps six known source-to-target gaps and
  three known UI runtime errors explicit.

## 60-second interview version

I built ExitDrill as a personal post-separation technical alpha to test a narrow
but important idea: getting every row out of a SaaS product does not mean an
organization can reconstruct the structure it depends on. I created an
independent synthetic baseline, a normalized export contract, and an evaluator
covering entities, relationships, attachment bytes, permissions, and audit
history. The evaluator also loads the graph into a foreign-key-enforced SQLite
reference model and produces aggregate receipts that can be replayed offline.
Baseline-declared critical fields use typed exact-value assertions, while
undeclared values remain explicitly outside the claim. To make the result
falsifiable, I built an adversarial fixture that preserves the entity row count
while replacing an entity, rewiring a relationship, corrupting an attachment,
collapsing a permission, and replacing an audit event; the drill surfaces the
losses. I also added a deterministic, script-free HTML evidence report and strict
quality gates. The boundary matters: this demonstrates a synthetic structural
test, not a production migration or operational exit readiness. I then moved one
seam closer to a real source: a capture program collected documented first-party
API responses and attachment bytes from a pinned local Directus 11.17.4 sandbox
and assembled the committed custom capture bundle. A closed normalizer verifies
those bytes and an equal-count derivative creates six exact loss signals without
changing the evaluator. That evidence is limited to the frozen synthetic
profile. I then loaded that one fixed profile into a digest-pinned, no-egress
CiviCRM Standalone 6.16.2 lab. Separate writer, reader, allowed, and denied
identities produced five target-interface observations, including private attachment
byte retrieval and a real permission-filtered denial. The same reader observed
one authenticated Contact Summary surface with the exact synthetic contact and
Cases tab. In a separate digest-pinned Chromium container, it then opened the
all-cases dashboard, located the synthetic case, followed Manage Case, and
observed its summary, type, displayed status, coordinator, Roles, and Activities
controls. The browser retained no artifacts and the evidence explicitly records
two known non-fatal jQuery-notify errors in the pinned Standalone build. That is
one bounded task, not general UI proof. A separate axe-core observation reports
32 passing automated rules and two serious findings—color contrast and links
distinguished only by color—without retaining selectors or HTML. It is not a
WCAG conformance claim, and keyboard, screen-reader, focus, and zoom/reflow
testing remain undone. A following bounded check reaches the Roles disclosure
after 69 Tab presses and activates it with Enter and Space; the unusually deep
position is evidence, not a keyboard-accessibility pass. Crucially, those
observations are followed by one distinct read-only task that opens a generated
`Open Case` activity and verifies its subject, type, and completed status. That
target scaffolding is not relabeled as restored history. Crucially, the browser
observations do not hide the result: the unchanged evaluator still reports six
source permission, audit, and collection-scope gaps and remains
`not_structurally_restorable`. The next credible milestone is a second real
source-target pair and a different user-critical browser workflow, not a generic
connector SDK inferred from one lab.
