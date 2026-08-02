# ADR-0009: Record one CiviCRM keyboard interaction observation

**Status:** Accepted for
`directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1` only

**Date:** 2026-08-02

**Deciders:** Chelsea Kelly-Reif

## Context

ADR-0008 added automated accessibility findings while explicitly leaving
keyboard behavior untested. The Manage Case Roles disclosure is part of the
already observed workflow and provides one bounded control for a programmatic
keyboard interaction. A single control cannot establish general keyboard
accessibility, logical focus order, or visible focus quality.

## Decision

After the automated scan, clear the current focus and send Tab from the document
start until the Roles disclosure summary receives focus, with a hard ceiling of
80 presses. Send Enter and require the disclosure to close, then send Space and
require it to reopen. Any mismatch fails the live capture.

Retain only the Chromium engine key, three semantic step keys, the exact Tab
count, an empty artifact list, and the target profile. The pinned observation
requires 69 Tab presses to reach the Roles summary. That count is evidence, not
a pass, score, or assertion that the intervening focus order is logical.

The offline verifier emits a fifth separate `keyboard-result.json`. Fixed
limitations state that programmatic events on one disclosure do not cover the
complete tab order, visible focus indicator, screen-reader behavior, general
keyboard accessibility, or WCAG conformance.

## Options Considered

### Option A: Preserve one exact keyboard interaction

**Pros:** Adds falsifiable evidence beyond automated rules and makes the deep
Tab position visible without retaining DOM content.

**Cons:** Covers only one control and does not substitute for human review.

### Option B: Treat reachability and activation as a keyboard-accessibility pass

**Pros:** Simpler result.

**Cons:** False. Other controls, focus order, focus traps, and visible focus
remain untested.

### Option C: Store every focused element

**Pros:** Enables detailed order review.

**Cons:** Retains labels and DOM-derived information, expanding the evidence and
privacy boundary. Detailed inspection remains ephemeral and synthetic-only.

## Consequences

- The native bundle adds `browser-keyboard.json`; the normalizer emits
  `keyboard-result.json` under a closed JSON Schema.
- The observed 69-step path is explicit and should not be interpreted as an
  acceptable or unacceptable threshold without user research and manual review.
- Enter and Space activation are observed only for the Roles disclosure.
- The previous automated findings and all structural and target-interface
  results remain unchanged.
- Manual keyboard traversal, focus visibility review, VoiceOver/NVDA testing,
  zoom/reflow, and other workflows remain open work.

## Action Items

1. [x] Bound Tab traversal and fail closed when the control is not reached.
2. [x] Verify Enter closes and Space reopens the disclosure.
3. [x] Retain only semantic step keys and the aggregate Tab count.
4. [x] Add a separate result schema and negative controls.
5. [ ] Perform a human keyboard-only review of the complete Manage Case page.
6. [ ] Assess focus visibility and screen-reader output with assistive technology.
