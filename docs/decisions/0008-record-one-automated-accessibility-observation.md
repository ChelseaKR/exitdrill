# ADR-0008: Record one automated CiviCRM accessibility observation

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

ADR-0007 proved one Dashboard → Manage Case browser task but explicitly left
accessibility unobserved. The same rendered document can support a bounded
automated check, provided that the result is not presented as a WCAG conformance
assessment and does not retain DOM selectors, HTML, screenshots, or traces.

Automated rules cover only a subset of accessibility requirements. Keyboard
operation, focus behavior, screen-reader output, zoom and reflow, meaningful
reading order, and contextual usability require separate manual work.

## Decision

Pin `axe-core` 4.12.1 and run its WCAG 2.0 A/AA and WCAG 2.1 A/AA tagged rules
against the full Manage Case document after the existing workflow controls are
visible. The scanner runs inside the same read-only, capability-dropped,
internal-network-only Chromium container as the workflow.

Retain only the engine and version, rule tags, page-scope key, aggregate rule
counts, and for each violation its rule ID, impact, and affected-node count.
Discard selectors, HTML snippets, failure summaries, help text, URLs, and all
other node-level data. Retain no browser artifact.

The pinned observation records 32 passing rules, 0 incomplete rules, 29
inapplicable rules, and two serious violations: `color-contrast` affecting four
nodes and `link-in-text-block` affecting two nodes. Any drift in those exact
values fails the closed profile; a changed result requires review and a new
capture.

The offline verifier emits a fourth, separate aggregate
`accessibility-result.json`. It does not change the structural evaluator, the
five target-interface probes, the UI-surface result, or the browser-workflow
result. Its fixed limitations state that it does not establish WCAG conformance.

## Options Considered

### Option A: Store a sanitized exact automated observation

**Pros:** Makes current defects visible, reproducible, and tamper-evident while
keeping the artifact boundary aggregate-only.

**Cons:** Adds a pinned dependency and live-run time; exact results may require
review when upstream rendering changes.

### Option B: Fail the workflow whenever axe reports any violation

**Pros:** Creates a simple zero-violation gate.

**Cons:** Would prevent honest publication of a restoration target that is
functionally observable but has accessibility defects, and could invite hiding
the scan. Findings remain explicit evidence instead of being mislabeled as a
workflow failure.

### Option C: Claim accessibility from an automated pass

**Pros:** Simple headline.

**Cons:** False. Automated rules cannot evaluate the complete WCAG standard or
real assistive-technology behavior.

### Option D: Retain complete axe node results

**Pros:** Easier remediation debugging.

**Cons:** Stores selectors and HTML snippets that expand the evidence and
potential data-disclosure surface. Detailed debugging stays ephemeral inside the
synthetic lab.

## Consequences

- The native bundle adds `browser-accessibility.json`; the normalizer emits
  `accessibility-result.json` under a closed JSON Schema.
- The browser dependency tree adds exact `axe-core` 4.12.1.
- The two serious findings remain visible and are not converted into a pass.
- The aggregate supports comparison only to this exact pinned observation; it
  is not a general accessibility score or certification.
- Keyboard-only, screen-reader, focus, zoom/reflow, and contextual contrast
  review remain unperformed and explicitly out of scope.
- The structural result remains `not_structurally_restorable`, and all existing
  target, UI, and workflow observations remain unchanged.

## Action Items

1. [x] Pin the scanner version and WCAG tag set.
2. [x] Run it inside the existing isolated browser boundary.
3. [x] Strip all node-level selectors and HTML from retained evidence.
4. [x] Pin the exact findings and fail closed on drift.
5. [x] Add a separate aggregate schema and offline verifier output.
6. [x] Add negative controls for version, counts, artifacts, and findings.
7. [ ] Perform keyboard-only and VoiceOver testing before making any broader
   accessibility claim.
