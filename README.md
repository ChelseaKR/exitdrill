# ExitDrill

[![CI](https://github.com/ChelseaKR/exitdrill/actions/workflows/ci.yml/badge.svg)](https://github.com/ChelseaKR/exitdrill/actions/workflows/ci.yml)

Run structural recovery drills for leaving SaaS systems.

**Status:** technical alpha · synthetic data only · offline CLI · zero runtime
dependencies

ExitDrill asks a question that ordinary backup and native export checks do not:

> Could this organization reconstruct enough structure to keep operating if its
> SaaS vendor disappeared or became unacceptable?

The current evaluator compares an independently captured baseline with a
normalized export, validates entities, relationships, attachment bytes,
permission grants, and audit events, then loads the package into an in-memory
neutral SQLite reference model. It emits an aggregate receipt that can be
checked and replayed offline.

This is a structural normalization experiment, not yet the complete product.
A neutral SQLite restore does **not** prove that people can operate in an
alternate production system. A future operational exercise must restore through
a supported interface into one production-capable target, read it back, and run
declared workflows before using a stronger restoration label.

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
```

Checksum-only verification reports `checksum_self_consistent`; it does not
authenticate the receipt. Supplying all replay inputs reports `replay_verified`.
The receipt payload is a closed contract: recomputing a checksum cannot make
missing dimensions, impossible counts, or contradictory statuses valid.

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

## Synthetic target-exercise preflight

The future target-exercise protocol can be checked without connecting to a
source or target:

```sh
exitdrill validate-exercise examples/synthetic-exercise/plan.json
```

This validates only a synthetic plan: separate baseline coverage, an empty and
isolated egress-blocked target, disabled automations, read-back evidence, and
the five required workflow probes. It executes nothing and cannot produce a
restoration result.

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
- No claim that an export proves its own completeness.
- No claim that file presence proves semantic usability.
- No claim that a successful neutral import proves operational recovery.
- Required field values beyond shape and permission-principal identity remain
  explicitly outside the current evaluator's denominator.
- No raw record fields or attachment content in receipts.
- No signature or trusted-time claim; the self-contained hash is a checksum, not
  authentication.
- No ambiguous JSON: duplicate keys, non-finite numbers, excessive nesting, and
  undeclared receipt/envelope fields fail closed.
- No single portability score that can hide a failed dimension.

## Why the baseline is separate

A vendor export cannot establish its own denominator. The baseline represents
what an operator could observe before requesting the export. Its coverage must
be declared separately for entities, relationships, attachments, permissions,
and audit history. Partial or unavailable coverage yields `indeterminate`; it
never silently becomes a pass.

## Product direction

The intended wedge is recurring CRM/case-management exit drills for nonprofits
and local government. The strongest future slice is one lawful native export,
one real alternate target such as an isolated CiviCRM sandbox, target read-back,
and operational scenario probes.

## Project documents

- [Architecture](docs/ARCHITECTURE.md)
- [Architecture decision](docs/decisions/0001-structural-evaluation-before-target-adapter.md)
- [Synthetic preflight decision](docs/decisions/0002-synthetic-exercise-preflight.md)
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
| Release/versioning | Applies; build-only candidate workflow, no public or registry publication |
| Accessibility | N/A — no HTML or graphical interface |
| Observability | Tier C; service telemetry is out of scope because the CLI is offline and emits no operational logs |
| Performance | N/A — offline CLI with no latency contract; input and attachment work remain bounded |
| Internationalization | N/A — English-only expert operator workflow |
| AI evaluation | N/A — deterministic evaluator with no model or AI SDK |
| Documentation | Applies; the canonical [ADR index](docs/adr/0000-record-architecture-decisions.md) links accepted history without breaking its original paths |
| Responsible-Tech Framework | Applies; see the current responsible-technology audit |
| Incident response and data governance | Applies; synthetic-only data gate remains mandatory |
