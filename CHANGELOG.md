# Changelog

All notable changes will be documented here.

## [Unreleased]

### Added

- Portfolio standards conformance documentation: a Standards Conformance
  table and an AI-assisted development disclosure in the README, a roadmap
  with the milestone gates and the Quality & Metrics ledger
  (`docs/ROADMAP.md`), and a reasoned internationalization N/A declaration
  (`docs/I18N.md`).
- `.github/allowed_signers`, the SSH allowed-signers file the release
  workflow uses to verify a signed annotated release tag.

### Changed

- The release workflow is now dispatch-only and split-authority: a shared
  read-only authorization job verifies a signed annotated tag against trusted
  main, the build job re-runs `make verify` and both declared demo outcomes at
  the verified commit before packaging, and a checkout-free publish job
  rechecks the immutable tag object before creating the GitHub Release. It
  replaces the tag-push candidate build, which had never run because no tag
  exists; there is still no tag, no release, and no package-registry
  publication.
- The wheel-content gate now derives its expected schema set from the committed
  `schemas/` directory instead of a hand-maintained constant list. It requires
  the wheel to carry exactly that set, byte for byte, and rejects an unexpected
  packaged schema. Each schema stays pinned to exactly one `$id`, as before:
  the two schemas published under the repository URL keep that form, and every
  other schema must use `https://exitdrill.example/schemas/<name>`, so a schema
  added later is `$id`-pinned without editing the gate.
- Strict mypy now covers `scripts/` as well as `src/` and `tests/`, so the
  offline acceptance gates, fixture builders, and the wheel checker are type
  checked like the package.
- CI syntax-checks every committed browser-lab script through a new
  `make lint-lab` target instead of two individually named files.
- Advanced the CiviCRM evidence index to `v0.7` and verification result to
  `v0.6` for a twelfth indexed artifact: a bounded case-search failure result.
- Advanced the CiviCRM evidence index to `v0.6` and verification result to
  `v0.5` for an eleventh indexed artifact: a same-object browser allow control.
- Advanced the CiviCRM evidence index to `v0.5` and the closed verification
  result to `v0.4` for a tenth indexed artifact: a separate authenticated
  browser access-denial result.
- Advanced the CiviCRM evidence index to `v0.4` and the closed verification
  result to `v0.3` for a ninth indexed artifact: a separate target-generated
  case-client browser-workflow result.
- Advanced the CiviCRM evidence index to `v0.3` and the closed verification
  result to `v0.2` for an eighth indexed artifact: a separate bounded
  contact-summary browser-workflow result.
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

- A top-level `--version` flag that reports the installed `exitdrill` package
  version and exits before any subcommand is required, so an operator can
  confirm what they installed without running a drill.
- Gate-completeness regression tests: the merge gate now fails when a committed
  schema is missing from the wheel force-include map, when a committed schema
  departs from its pinned `$id`, including by adopting the other published form,
  when a packaged schema is not a JSON object, when a committed browser-lab
  script escapes the syntax gate or fails `node --check`, and when the lab or
  type gates go back to naming individual files.
- A negative test for the synthetic-demo summary parser, which now rejects a
  receipt that parses as JSON but is not an object.
- A `make lint-lab` target that syntax-checks every committed browser-lab
  script and fails when none is found.
- An eleventh CiviCRM evidence family that observes both synthetic cases through
  Case Summary, then records HTTP 500 from one exact-subject filter submission
  without claiming root cause or general search behavior.
- A tenth CiviCRM evidence family that confirms the allow principal can render
  the same protected Contact Summary used by the browser denial probe.
- A ninth CiviCRM evidence family that records one deny-principal browser
  redirect and protected-content absence while withholding universal UI/API
  authorization and principal-equivalence claims.
- An eighth CiviCRM evidence family that follows the target-generated case
  client through Contact Summary and Cases back into Manage Case, while
  explicitly withholding source case-client equivalence, editing,
  accessibility, and operational-equivalence claims.
- A seventh CiviCRM evidence family that reopens the case dashboard, follows
  the exact synthetic contact into Contact Summary, verifies the contact-page
  region and Cases affordance, and explicitly withholds contact-editing,
  case-navigation, accessibility, and operational-equivalence claims.
- A fail-closed `verify-civicrm-evidence-index` command that checks the exact
  v0.2 catalog, bounded artifact bytes, packaged result schemas, normalized
  export contract, and declared attachment bytes without producing a composite
  or structural verdict, then emits a separate closed v0.1 verification result
  with machine-readable limitations.
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
