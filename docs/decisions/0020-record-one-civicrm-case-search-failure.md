# ADR-0020: Record one CiviCRM case-search failure

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

The existing browser evidence proves several narrow read-only paths but does
not exercise case-search criteria. The pinned target can show the two synthetic
cases from Case Summary while still failing a more specific search operation.

## Decision

In isolated Chromium, open the Case Summary drilldown, require both exact
synthetic cases in the unfiltered results, open Edit Search Criteria, enter the
exact visible Alpha case subject, and submit Search. Record the observed HTTP
500 Error response as a distinct closed result. Retain no subject, case ID,
route parameters, response body, HTML, screenshot, or trace. Advance the
evidence index to v0.7 and verification output to v0.6.

## Consequences

- The artifact documents one reproducible defect on the pinned profile.
- It does not prove root cause, behavior of other filters or configurations,
  general search usability, or operational equivalence.
- The structural evaluator and all earlier evidence-family results remain
  unchanged.
