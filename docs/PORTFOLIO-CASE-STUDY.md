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

## Evidence in the repository

- Five-dimension evaluation, exact comparisons for baseline-declared critical
  field values, and neutral SQLite restoration are implemented in
  [`src/exitdrill/evaluator.py`](../src/exitdrill/evaluator.py) and bounded by the
  design in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).
- The equal-row-count adversarial scenario is encoded in
  [`examples/synthetic-crm-lossy/`](../examples/synthetic-crm-lossy/) and asserted
  in [`tests/test_lossy_demo.py`](../tests/test_lossy_demo.py).
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
cutover to another SaaS product. It currently has no live source connector,
native-export proof, production-capable target adapter, or workflow read-back.

## Resume bullet

- Built ExitDrill, an offline Python technical alpha that tests synthetic SaaS
  exports across five structural dimensions, verifies baseline-declared critical
  field values, and detects adversarial data loss hidden by unchanged row counts,
  with replayable aggregate receipts and a standalone evidence report.

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
test, not a production migration or operational exit readiness. The next
credible milestone is one lawful native-format export generated from an isolated
synthetic sandbox, followed by target read-back and workflow probes.
