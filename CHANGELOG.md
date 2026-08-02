# Changelog

All notable changes will be documented here.

## [Unreleased]

### Changed

- Advanced the CiviCRM evidence index to `v0.2`, binding each catalog entry to
  the exact emitted artifact bytes and length while explicitly withholding any
  authenticity claim.
- Advanced the independent baseline to `v0.3`; every declared required entity
  field now binds an exact expected scalar value as well as its type.
- Advanced drill-result and receipt contracts to `v0.3` so their limitations
  accurately state that field-value equivalence is bounded to declared required
  fields.
- Advanced the independent baseline to `v0.2`, binding audit action and
  occurrence time as well as event identity.
- Renamed the aggregate remediation field to `observed_remediation_signals`;
  it no longer implies a minimum task count.
- Advanced result and receipt contracts to `v0.2` for the closed semantic
  payload.

### Added

- A fail-closed `verify-civicrm-evidence-index` command that checks the exact
  v0.2 catalog, bounded artifact bytes, packaged result schemas, normalized
  export contract, and declared attachment bytes without producing a composite
  or structural verdict.
- A closed `evidence-index.json` catalog for the normalized CiviCRM export and
  six independent result artifacts, with per-entry schemas and decision scopes
  but no composite status, score, pass count, or inferred conclusion.
- A sixth CiviCRM evidence family that follows a supported read-only activity
  View action, verifies one generated `Open Case` activity's exact bounded
  markers, and records its additional known runtime error without relabeling
  target scaffolding as restored source history.
- A fifth CiviCRM evidence family that records one bounded keyboard interaction:
  the Roles disclosure is reached after 69 Tab presses, closes with Enter, and
  reopens with Space, without claiming complete keyboard accessibility.
- A fourth CiviCRM evidence family: pinned axe-core 4.12.1 scans the isolated
  synthetic Manage Case document, retains only aggregate rule counts and
  sanitized violation IDs/impacts/node counts, reports two serious findings,
  and explicitly does not establish WCAG conformance.
- Canonical `docs/adr/` compatibility index linking all accepted ADRs without
  moving or rewriting their durable `docs/decisions/` history.
- A real-process, synthetic-only Directus 11.17.4 API-response canary captured
  from a pinned local sandbox, with schema, content, relationships, attachment
  bytes, permissions, activity, and a closed hash manifest.
- A bounded source-specific Directus normalizer that verifies the custom capture
  bundle and atomically emits the existing normalized export and attachment
  contracts without entering the evaluator's trust algebra.
- A one-command Directus-canary acceptance demonstration: deterministic
  normalization, clean replay, an equal-row-and-file-count six-mutation
  derivative, exact five-dimension loss assertions, aggregate-only reports,
  receipt comparison, and comparison-policy exit verification.
- Fail-closed detection and replay evidence for same-type critical-field value
  loss without placing raw field values in aggregate receipts.
- Strict independent baseline and normalized-export contracts.
- Structural comparison across entities, relationships, attachments,
  permissions, and audit history.
- Neutral foreign-key-enforced reference restore.
- Aggregate deterministic receipt and offline replay.
- Synthetic CRM/case-management demonstration and adversarial fault suite.
- Shared bounded JSON decoder with duplicate-key, non-finite-number, invalid
  UTF-8, and excessive-nesting rejection.
- Exact closed receipt and untrusted-envelope field validation.
- Descriptor-stable attachment size checks and hashing.
- Pinned CI, security, packaging, and build-only release-candidate workflows.
- Project conformance, data-governance, incident-response, observability,
  release, and internationalization declarations.
- Cumulative 128 MiB attachment hashing budget.
- Per-row SQLite restore with read-back counts and foreign-key check.
- Offset-aware timestamp and chronology validation.
- Closed receipt payload/dimension arithmetic and result-algebra validation.
- Collision-resistant atomic receipt writing.
- Synthetic-only target-exercise preflight plan and five-probe validator.
- PEP 561 typing marker and local wheel-content gate.
- Deterministic offline comparison of two validated receipts with exact scope
  comparability gates, per-dimension signed count deltas, nonordinal status and
  extra-record transitions, and separate observed loss-signal directions.
- Closed JSON Schema for receipt-comparison output and explicit duplicate,
  incomparable, uncertain, mixed, and no-observed-loss-signal states.
- Wheel-packaged comparison schema with Draft 2020-12 semantic consistency
  tests and explicit export-generation/evaluator-version limitation.
- Opt-in comparison CI policy exit 3 for directly observed missing/invalid
  increases, without changing JSON or ranking statuses, extras, or totals.
- JSON regular-file and 200,000-node bounds, attachment size-change detection,
  and descriptor-relative parent traversal on supported platforms.
- Stronger comparison-schema consistency for scope reasons, observed signal
  direction, assessments, status transitions, and extra-count transitions.
- CI demonstration of ordinary comparison and the expected opt-in policy exit.
- Pre-write semantic verification and encoded 2 MiB receipt bound before any
  output-directory or temporary-file mutation.
- Installed source-bound comparison verifier that recomputes every derived field
  from two fully verified receipts; JSON Schema remains the structural and
  locally expressible contract.
- Deterministic, accessible, script-free offline HTML evidence reports generated
  only from semantically verified aggregate receipts, with mandatory trust
  limitations and no operational-equivalence claim.
