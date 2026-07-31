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
- `comparison.py` reduces two verified receipts to aggregate snapshots, gates
  exact input-scope comparability, and emits deterministic per-dimension deltas.
- `cli.py` exposes validation, drill, verification/replay, and comparison.

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
