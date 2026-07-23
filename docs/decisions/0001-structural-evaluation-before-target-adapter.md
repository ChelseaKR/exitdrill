# ADR 0001: Structural evaluation before a target adapter

**Status:** Accepted  
**Date:** 2026-07-22  
**Decider:** Chelsea Kelly-Reif

## Context

The product hypothesis requires actual alternate-system recovery, but no lawful
design-partner export or target has yet been selected. Inventing a vendor-shaped
connector would create misleading confidence and make an unvalidated abstraction
look permanent.

## Decision

Implement the denominator, normalization, integrity, neutral-restore, result,
privacy, and receipt seams using invented synthetic contracts. Label every
successful outcome as structural only.

A future strong restoration result requires:

1. one documented native export;
2. a separately captured baseline;
3. load through a supported interface into an empty production-capable sandbox;
4. independent target read-back; and
5. declared workflow and allow/deny permission probes.

## Options considered

- **Build generic connectors now:** rejected because connector maintenance may be
  the reason to kill the product.
- **Call SQLite a target system:** rejected because storage representability is
  not operational recovery.
- **Wait for a design partner before any code:** rejected because the strict
  baseline, loss algebra, receipt privacy, and fail-closed boundaries are cheap
  technical risks worth testing independently.

## Consequences

- Structural evaluation alone cannot demonstrate the full product promise.
- Schemas may be replaced after the first native export.
- Product discovery remains the critical path.
- The implementation provides a safe test harness for silent-loss fixtures.
