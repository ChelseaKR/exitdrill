# Architecture

## Claims boundary

```text
independent baseline ─┐
                      ├─ strict normalization ── neutral graph ── SQLite restore
vendor export ────────┘             │                   │
attachment bytes ───────────────────┘                   ▼
                                            structural reconciliation
                                                        │
                                                        ▼
                                        aggregate receipt + offline replay

Future operational exercise:
neutral graph → real target load → target read-back → workflow probes
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
- `paths.py` is the single attachment-root boundary. Attachment size checks and
  hashing share one open descriptor, so a path replacement after open cannot
  change the bytes being measured.
- `evaluator.py` compares independent denominators, validates field shapes and
  attachment bytes, and loads a foreign-key-enforced reference model.
- `models.py` defines dimension and overall result algebra.
- `receipt.py` builds aggregate-only deterministic payloads through
  collision-resistant temporary files and verifies exact, closed
  receipt/envelope shapes plus their self-contained checksums.
- `receipt_validation.py` closes nested result fields and verifies dimension
  presence, counts, arithmetic, limitations, and shared result algebra.
- `cli.py` exposes validation, drill, and verification/replay.

## Architecture decision

Three options were considered:

| Option | Decision | Reason |
|---|---|---|
| General connector platform | Reject for the current scope | Tests abstractions before customer value; high treadmill risk |
| Export-to-neutral-model only | Implement with restricted label | Cheapest way to test denominator, loss algebra, privacy, and replay |
| One native source → real target → read-back → workflows | Required for an operational claim | Smallest credible operational exit claim |

The canonical model is an adapter boundary, not proof of successful exit.

## Data contracts

The baseline records expected identities, required field shapes, and exact
audit action/time tuples. It is an operator assertion, not ground truth. The
normalized export records:

- entities with scalar fields;
- directed typed relationships;
- attachments with owner, bounded relative path, and content digest;
- semantic permission grants; and
- audit events with referenced objects.

The receipt emits none of those record-level identifiers or values. It emits
aggregate counts, dimension statuses, source-document hashes, and limitations.
`observed_remediation_signals` sums observed missing and invalid conditions; it
is deliberately not called a minimum task count, cost, or RTO estimate.

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

## Trust claims

The current evaluator records:

- exact baseline and normalized-export digests;
- observed attachment-byte fidelity;
- dimension numerators and denominators;
- reference restore success; and
- deterministic replay equivalence.

It does not prove:

- the baseline or export is authentic or complete;
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
