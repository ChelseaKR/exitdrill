# ExitDrill

[![CI](https://github.com/ChelseaKR/exitdrill/actions/workflows/ci.yml/badge.svg)](https://github.com/ChelseaKR/exitdrill/actions/workflows/ci.yml)

Run structural recovery drills for leaving SaaS systems.

**Status:** technical alpha · synthetic data only · offline verifier

A vendor export can contain every row and still lose the structure an
organization needs: relationships, attachment bytes, permissions, or audit
history. ExitDrill compares a separately captured baseline with a normalized
export and keeps those dimensions visible instead of collapsing them into one
portability score.

The current release proves a narrower claim: declared structural losses can be
detected and summarized in a replayable aggregate receipt. It does not prove a
completed migration or an operational exit.

## Three-minute demo

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
make install
make demo-compare
```

The command runs the same baseline against two invented CRM exports:

- the clean fixture returns `structurally_restorable`;
- the adversarial fixture keeps the entity row count unchanged while changing
  identity, relationship, attachment, permission, and audit evidence;
- that second fixture returns `not_structurally_restorable`; and
- the final comparison reports the observed increase in missing or invalid
  evidence without inventing an overall score.

The command ends with a four-line human summary. The clean and lossy aggregate
reports are written to `examples/synthetic-crm/out/report.html` and
`examples/synthetic-crm-lossy/out/report.html`. Receipts, comparisons, and
generated reports are ignored by version control.

## What it checks

| Dimension | Question |
|---|---|
| Entities | Are the expected identities and declared critical values present? |
| Relationships | Can the expected links still be reconstructed? |
| Attachment bytes | Are the referenced bytes present and unchanged? |
| Permissions | Are the declared grants represented? |
| Audit history | Are the expected events represented? |

Each dimension has its own coverage declaration and result. Missing evidence is
not averaged away.

## How the evidence flows

1. An operator records a baseline before requesting the export.
2. A source-specific process normalizes the export into ExitDrill's fixed input
   contract.
3. The evaluator compares the two inputs and loads the normalized graph into a
   foreign-key-enforced SQLite reference model.
4. ExitDrill writes an aggregate receipt that can be validated, replayed, and
   rendered offline.

The neutral SQLite load tests representability, not whether people can work in
another production system.

## Run the CLI directly

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

To compare two same-scope receipts:

```sh
exitdrill compare reference-receipt.json candidate-receipt.json
```

The caller supplies the order. ExitDrill rejects comparisons whose drill,
baseline, contract, coverage, or expected counts differ.

## Receipts and trust

- Receipts contain aggregates and input digests, not record fields or attachment
  contents.
- Replay verification recomputes the result from the baseline, export, and
  attachment bytes.
- Receipts are unsigned and contain no trusted time. A checksum detects internal
  inconsistency; it does not authenticate the operator or inputs.
- The evaluator does not execute mapping commands, SQL, JQ, plugins, URLs, or
  model-generated transforms.

## Real-process synthetic canaries

The repository contains two deliberately narrow integration exercises:

- [Directus 11.17.4 source canary](examples/directus-11.17.4-civic-case/README.md)
  verifies and normalizes one local synthetic API-response capture profile. Its
  equal-count adversarial derivative produces six declared loss signals.
- [CiviCRM 6.16.2 target canary](examples/civicrm-6.16.2-target-roundtrip/README.md)
  loads that fixed source profile into an isolated local target and performs
  independent read-back. Five target-interface probes pass, while the structural
  evaluation still reports six source-to-target gaps.

These are exact-profile observations. They do not establish a general Directus
export, a Directus-to-CiviCRM connector, vendor-wide portability, UI usability,
accessibility conformance, or production readiness. The example READMEs contain
the setup, evidence inventory, known failures, and claim limits.

Run their committed offline acceptance checks with:

```sh
make demo-directus-canary
make demo-civicrm-target-canary
```

## Result states

| State | Meaning |
|---|---|
| `structurally_restorable` | Complete declared coverage with no observed structural loss |
| `structurally_restorable_with_findings` | No observed loss, with additional exported items |
| `not_structurally_restorable` | Expected evidence is missing, invalid, corrupt, or cannot be loaded |
| `indeterminate` | Baseline coverage is partial or unavailable |

None of these states means portable, exit-ready, operationally equivalent, or
legally compliant.

## Current boundary and next milestone

ExitDrill is ready for outside technical evaluation using its invented fixtures.
It is not ready for production or sensitive data.

Feature scope is paused at this boundary. The next milestone is an outside person
running the synthetic demo without help and explaining whether the receipt
answers their exit question. Until that happens, the project will not add another
connector, evidence family, or data category.

Real, production-derived, or merely deidentified exports remain prohibited until
the [data-governance gate](docs/DATA-GOVERNANCE.md) is satisfied.

## Development

```sh
make verify
make package
```

The merge gate runs Ruff, strict mypy, pytest, and at least 90% branch coverage.
The release workflow is dispatch-only: it verifies a signed annotated tag
against trusted main, rebuilds and re-verifies at that exact commit, and can
publish a GitHub Release. No tag or release exists yet, and no package-registry
publication is configured.

ExitDrill is built AI-assisted, within a portfolio that shares a common quality
standard: merge-blocking gates guard the core safety properties, audit
artifacts are committed rather than claimed, and the accountable maintainer
reviews and owns every change.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Architecture decision index](docs/adr/0000-record-architecture-decisions.md)
- [Data governance](docs/DATA-GOVERNANCE.md)
- [Threat model](docs/THREAT-MODEL.md)
- [Responsible-technology audit](docs/RESPONSIBLE-TECH-AUDITS.md)
- [Roadmap and metrics ledger](docs/ROADMAP.md)
- [Internationalization declaration](docs/I18N.md)

Detailed source and target evidence stays with the corresponding example rather
than being duplicated here.

## Standards Conformance

Declared per the portfolio standards set. Every standard is either applied or
recorded as N/A with a reason; there are no silent skips.

| Standard | State |
|---|---|
| Code Quality | Applies: Single root `pyproject.toml`, `uv.lock`, Ruff lint and format, strict mypy over `src`, `tests`, and `scripts`, pytest with at least 90% branch coverage, pre-commit hooks, and `make verify` as the merge gate. |
| Security & Supply-Chain | Applies: SHA-pinned actions, scoped workflow permissions, Semgrep, gitleaks, strict pip-audit plus npm audit, zizmor, Dependabot, and private vulnerability reporting per [SECURITY.md](SECURITY.md). |
| CI/CD | Applies: `ci.yml` runs the same `make` targets a contributor runs locally; the release workflow is dispatch-only, verifies a signed annotated tag against trusted main, and separates verification from publication authority. No tag or release exists yet. |
| Release & Versioning | Applies: `.github/workflows/release.yml` runs only on maintainer dispatch, verifies an SSH-signed annotated tag against trusted main, and hands publication to a separate job that never checks out code. No tag or release exists yet and no package registry is configured. |
| Observability | Applies (Tier C scope). Offline single-run CLI; evidence is deterministic exit codes, replayable receipts, and rendered reports. The out-of-scope decision for tracing and SLO surfaces is recorded in [docs/ROADMAP.md](docs/ROADMAP.md). |
| Performance | N/A (offline single-run CLI with no hosted route and no served page; the HTML report is written to a local path on demand and pulls no subresources, so there is no delivery surface to budget). |
| Accessibility | Applies (scoped). The offline HTML report is static, script-free, and escaped. The CiviCRM canary records one sanitized automated accessibility scan and one keyboard observation without claiming WCAG conformance; human assistive-technology review remains open. |
| Internationalization | N/A (single-operator, English-only CLI with no public or bilingual delivery obligation; declared in [docs/I18N.md](docs/I18N.md)). |
| AI Evaluation | N/A (no LLM or model component in the evaluator or its trust path; excluding model-generated transforms is a load-bearing invariant in `AGENTS.md`). |
| Documentation | Applies: README, architecture, ADR log, CHANGELOG, SECURITY.md, CONTRIBUTING.md, CITATION.cff, threat model, data governance, and responsible-tech audit are committed and current. |
| Quality & Metrics | Applies: The metrics ledger and milestone gates live in [docs/ROADMAP.md](docs/ROADMAP.md); `make verify` is the single merge gate locally and in CI. |
| AI Development Measurement | Applies: No tool-usage counter is collected and none gates a merge. The committed ledger in [docs/ROADMAP.md](docs/ROADMAP.md) is the record, and its gates are what a change must clear regardless of how it was authored. |
| Incident Response | Applies: No incident has occurred. Reports go through GitHub private vulnerability reporting per [SECURITY.md](SECURITY.md), and a postmortem will be committed under `docs/incidents/` when there is one to write. |
| Data Governance | Applies: [docs/DATA-GOVERNANCE.md](docs/DATA-GOVERNANCE.md) permits invented synthetic fixtures only; any non-synthetic input stays prohibited until an explicit gate is satisfied, and that gate is recorded as open in [docs/ROADMAP.md](docs/ROADMAP.md). |
| Responsible-Tech Framework | Applies: [docs/RESPONSIBLE-TECH-AUDITS.md](docs/RESPONSIBLE-TECH-AUDITS.md) covers public-interest value, privacy, equity, transparency, and accountability; the synthetic-only boundary is enforced through [docs/DATA-GOVERNANCE.md](docs/DATA-GOVERNANCE.md). |

## License

ExitDrill is available under the [Apache License 2.0](LICENSE).

## Support

This is independent work, published so it can be read and checked rather than taken on
trust. If your organization is planning a platform migration or an exit and wants help
running one, see [consulting and workshops](https://chelseakr.com/consulting/).
