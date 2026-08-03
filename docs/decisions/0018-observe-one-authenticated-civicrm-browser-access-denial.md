# ADR-0018: Observe one authenticated CiviCRM browser access denial

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

The target-interface result already proves one permission-enforced APIv4 deny
query, but it does not show how the corresponding authenticated browser request
behaves. A live prototype found no explicit denial page: the deny principal's
direct Contact Summary request redirects to the CiviCRM landing page and does
not expose the protected contact page or name.

## Decision

Run one separate isolated Chromium probe as the distinct deny principal against
the same protected synthetic contact. Require the exact 302-to-200 redirect
chain, final `/civicrm` route, absence of the contact page and protected name,
no failed or off-origin requests, and only the single known sanitized
`jquery_notify_unavailable` error.

Publish a minimized
`exitdrill/civicrm-browser-access-denial-result/v0.1` result with decision scope
`pinned_synthetic_browser_access_denial_only`. Advance the non-composite index to
v0.5 and its verification result to v0.4 without rewriting historical schemas.

## Consequences

- The result records redirect and protected-content absence, not an explicit
  access-denied page.
- No URLs with identifiers, HTML, screenshots, traces, downloads, credentials,
  cookies, record IDs, or protected names are retained.
- The observation does not prove all UI/API authorization, permission-principal
  equivalence, operational equivalence, or behavior for another object or route.
- The structural evaluator and five target-interface probes remain unchanged.

## Action Items

1. [x] Prototype the deny-principal browser request in a fresh isolated lab.
2. [x] Fail closed on redirect, content, runtime-error, or network drift.
3. [x] Publish a separate result schema and advance index contracts.
4. [x] Add exact positive/adversarial tests and update claim boundaries.
