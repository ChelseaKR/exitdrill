# ADR-0019: Observe one authenticated CiviCRM browser allow control

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

The deny-principal browser probe records a redirect and protected-content
absence. A positive control on the same route and object is needed to distinguish
that observation from a generally unavailable Contact Summary page.

## Decision

Authenticate the distinct allow principal in a separate isolated Chromium run
and request the same protected contact. Require HTTP 200, the Contact Summary
page and protected name, no redirect, failed request, or off-origin traffic, and
only the one known sanitized runtime error. Retain neither the name nor contact
identifier. Publish an independent allow-control result, advance the index to
v0.6, and advance verification output to v0.5.

## Consequences

- The paired route and object strengthen interpretation of the denial result.
- The artifacts remain non-composite and prove neither every authorization path
  nor permission-principal or operational equivalence.
- The structural evaluator and target-interface probe algebra remain unchanged.
