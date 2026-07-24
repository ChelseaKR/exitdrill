# Changelog

All notable changes will be documented here.

## [Unreleased]

### Changed

- Advanced the independent baseline to `v0.2`, binding audit action and
  occurrence time as well as event identity.
- Renamed the aggregate remediation field to `observed_remediation_signals`;
  it no longer implies a minimum task count.
- Advanced result and receipt contracts to `v0.2` for the closed semantic
  payload.

### Added

- Canonical `docs/adr/` decision index linking the two existing accepted ADRs
  without moving or rewriting their history; new decisions continue there.
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
