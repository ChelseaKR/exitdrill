# ADR 0002: Validate synthetic exercise preflight without a connector seam

**Status:** Accepted  
**Date:** 2026-07-22  
**Decider:** Chelsea Kelly-Reif

## Context

A credible operational exercise needs an empty isolated target, read-back,
evidence matrices, and five operational probes. No lawful native export, source
profile, or real target has passed discovery. A generic adapter or simulated
restoration would freeze an untested abstraction and invite an unsupported
success claim.

## Decision

Add one strict, synthetic-only exercise-plan contract. It may validate:

- a separately captured baseline and declared per-dimension coverage;
- a customer-obtainable synthetic export mechanism;
- an empty, isolated, egress-blocked target with automations disabled;
- prohibition of production data;
- target read-back and raw evidence requirements; and
- exactly five lookup, relationship, attachment, allow, and deny probes.

The validator contains no URL, credential, command, mapping, load, read-back, or
result interface. Its CLI status is `synthetic_protocol_valid` with decision
scope `plan_only_no_target_execution`.

## Options considered

- **Build a generic target protocol:** rejected until one real source-target
  pair tests the abstraction.
- **Build a simulated target:** rejected because a simulator can only prove
  behavior it invents.
- **Keep the protocol prose-only:** rejected because omitted sandbox and
  evidence controls are cheaply detectable before a real exercise.

## Consequences

- Teams can prepare a complete safety/evidence checklist offline.
- A valid plan makes no claim that declared controls exist.
- Source profiles, target interfaces, read-back, and result assurance remain
  blocked on discovery and a real sandbox.
