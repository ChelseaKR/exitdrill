# ADR 0003: Compare only same-scope aggregate receipts

**Status:** Accepted
**Date:** 2026-07-22
**Decider:** Chelsea Kelly-Reif

## Context

Recurring drills need to reveal whether observed structural loss signals changed.
Receipts contain only aggregate counts and unsigned, untrusted envelope times.
They contain no stable series identifier, authenticated chronology, or record
identities. Treating statuses as an ordered score or comparing changed
denominators would create unsupported trend claims.

## Decision

Add deterministic offline comparison with these boundaries:

1. Both receipt files must independently pass bounded parsing, closed semantic
   validation, and checksum verification.
2. The caller supplies reference and candidate order. Envelope time is ignored.
3. Drill ID, source, exact baseline digest, contract versions, decision scope,
   trust limitations, coverage, and expected counts must match.
4. A scope mismatch returns `incomparable` with reason codes and no deltas.
5. Comparable output reports signed candidate-minus-reference deltas separately
   for every dimension and count.
6. Only missing/invalid changes feed observed loss-signal direction. Extra
   records and statuses are factual transitions, not quality ranks.
7. Partial or unavailable coverage forces uncertain assessment.
8. The unsigned output carries fixed limitations, no paths, no score, and no
   operational restoration claim.
9. The output explicitly states that the receipts do not bind the
   export-generation method or evaluator version, so deltas have no causal
   attribution.

## Options considered

- **Rank statuses:** rejected because fail-to-indeterminate and
  pass-to-finding transitions are not safely ordinal.
- **Compare any two valid receipts:** rejected because denominator or contract
  changes can masquerade as improvement.
- **Infer order from envelope time:** rejected because receipt time is explicitly
  claimed and untrusted.
- **Compare record identities:** deferred because receipts intentionally contain
  no record-level identifiers.

## Consequences

- Same-scope increases and decreases in observed aggregate loss signals are
  visible without a hosted service.
- Mixed missing/invalid movement stays mixed rather than being netted into a
  score.
- Identical payloads are recognized as duplicate measurements.
- Equal aggregates from distinct payloads remain only
  `no_observed_loss_signal_change`; record churn may be invisible.
- Changed aggregates may reflect export preparation or evaluator changes rather
  than source-system change.
