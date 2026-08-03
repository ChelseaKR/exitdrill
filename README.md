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
The candidate-release workflow builds and inspects a wheel but publishes no
package.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Architecture decision index](docs/adr/0000-record-architecture-decisions.md)
- [Data governance](docs/DATA-GOVERNANCE.md)
- [Threat model](docs/THREAT-MODEL.md)
- [Responsible-technology audit](docs/RESPONSIBLE-TECH-AUDITS.md)

Detailed source and target evidence stays with the corresponding example rather
than being duplicated here.

## License

ExitDrill is available under the [Apache License 2.0](LICENSE).
