# Changelog

All notable changes will be documented here.

## [Unreleased]

### Fixed

- The improvement plan published two limits the tree had already closed.
  `docs/plans/improvement-plan.md` still listed "Coverage does not measure
  `scripts/`" after #125 put `scripts` in `[tool.coverage.run] source` with
  `COVERAGE_PROCESS_START` following the gate scripts into their subprocesses,
  and still listed the `pageErrors` stub as unpinned after
  `scripts/check_browser_capture_bindings.mjs` gained the guard that fails when
  another script's declared literal reads `pageErrors`, when the owning
  script's literal stops reading it, or when that script stops proving
  `pageErrors.length === 2` first. Nothing noticed, because nothing read the
  plan against the code. That is this plan's own subject matter pointed at the
  plan: a statement about what is enforced, outliving the enforcement. It
  understated the project rather than overstating it, which is the safer
  direction and still not a true one.

  Both entries now record what closed them, and
  `test_the_plan_publishes_no_limit_the_code_has_closed` binds the section to
  the two facts in the tree that decide it, in both directions: a closure that
  is reverted must be republished as a limit, and a limit that is republished
  must have its closure gone. The section itself is asserted present, so the
  check cannot pass by finding nothing to read.

### Added

- `exitdrill explain RECEIPT` narrates one verified receipt in plain language,
  for the reader issue #51's usability gate is about: someone who has never seen
  the tool, deciding whether a receipt answers their exit question. It states
  what a baseline and an export are here; per dimension the question asked, the
  denominator the baseline declared with its coverage, what the export carried
  and what became of it, and one conclusion sentence; what the overall state
  means; the full list of things it does not mean, quoted verbatim from the
  contract; and what the reader can do next. `--json` emits the same narration
  as a canonical `exitdrill/receipt-narration/v0.1` document.

  It cannot say more than the receipt does. Verification runs before any
  sentence is built, so an invalid receipt exits 2 with the validation error and
  no partial narration. Nothing reads the envelope's claimed time, attributes a
  cause, recommends a remedy, or reduces the dimensions to a score. The
  conclusion sentence is chosen in the order `classify_dimension_status`
  decides, so a dimension that failed is never narrated as a coverage problem,
  and an `indeterminate` dimension is narrated as one the drill cannot rule on
  -- the narration never uses the word "passed", which is the word a reader
  would carry away.

- `src/exitdrill/wording.py` is now the one table every reader-facing string
  that is not a count, a digest, or free payload text comes from: dimension
  labels, nouns and questions, result-state names and meanings, coverage
  clauses, and the limitation sentences. The HTML report and `explain` both read
  it, so the two surfaces cannot disagree about what a receipt says; before it,
  each held its own copy, which is the same shape as a document restating a
  bound the code no longer enforces. The report's rendered bytes are unchanged.
  `tests/test_explain.py` requires an entry for every member of every enum the
  narration reads, requires each limitation sentence to appear exactly once, and
  binds each dimension question to the wording `README.md` publishes. The
  disclosure gate scans both narrations and proves it reports a record value
  injected into them.

- `exitdrill report` renders a comparison document as an offline, script-free
  HTML page, the way it already rendered a receipt. The comparison round trip
  closed in #102, but its only output was JSON, so a reader who was not the
  operator was handed `count_deltas` and left to read them by eye. `report` now
  routes on the `schema_version` the file declares about itself: a receipt with
  operand receipts, or a comparison without them, is a usage error rather than
  one document rendered as the other. A comparison requires `--reference` and
  `--candidate` and goes through the same `verify_comparison_files`
  recomputation `verify-comparison` uses, so a forged delta exits 2 with no page
  written and the output directory not created.

  The page carries the comparability checks and any reason codes, the signed
  count deltas per dimension, both receipts' statuses with their transitions,
  the observed loss-signal changes, and the six comparison limitations. It adds
  no aggregate score and no ranking: transitions and assessments come from the
  document's own closed vocabularies, and their pill carries no colour, because
  a difference here is a fact and not a verdict. An `incomparable` document
  renders its reason codes and says in terms that no dimension table follows,
  instead of a table of zeros -- absence rendered as absence rather than as a
  measurement. The word `uncertain` reaches the page only when a dimension's
  assessment is `uncertain`, which is why empty summary buckets are not printed.

  Both reports now render through one page shell, so the content-security
  policy, stylesheet, escaping, and footer claim cannot drift apart between
  them; the receipt report's bytes are unchanged. The two gates that guard the
  report surface were extended to the new artifact rather than left pointed at
  the old one: `tests/test_report_offline_safety.py` runs its element,
  attribute, link, stylesheet, and CSP allowlists over both renderers with
  synthetic and with hostile payload text, and `tests/test_disclosure.py` adds
  the comparison report to the corpus it scans and to the control it computes
  its exclusions from, with a negative control proving it reports a record value
  injected into the new page. `make demo-compare` writes
  `examples/synthetic-crm/out/comparison.html`.

- `tests/test_release_versions.py` holds the declared version to the releases
  that exist. `pyproject.toml` declares `0.1.0` and `git tag -l` prints nothing:
  nothing has been tagged, `release.yml` has never been dispatched, and there is
  no GitHub Release. That is the intended state, and nothing here demands a tag.
  What it demands is that the repository keep saying so and that the copies of
  the number keep agreeing. No tag passes, but `README.md` must carry "No tag or
  release exists yet" and `docs/RELEASE.md` its "unreleased technical alpha"
  line; a tag that appears must carry the declared version, must retire both
  sentences, and must have a `CHANGELOG.md` section behind it, which
  `release.yml` refuses to build without; `CITATION.cff` must state the declared
  version and must carry no `date-released` while no tag exists — the field
  GitHub's citation panel and Zenodo read, and the one that elsewhere in this
  portfolio was moved by a version bump with a date invented to sit beside it.

  The README's Status line now reads `technical alpha (0.1.0, untagged)`. The
  version appeared in `pyproject.toml`, `exitdrill.__version__` and
  `CITATION.cff` and nowhere a reader of the README would find it, so a bump
  could move all three and leave the page describing something else.

  Because a missing tag and an unfetched tag are indistinguishable from inside a
  checkout, the tag checks skip with the reason on a shallow or tagless clone
  rather than reading absence as evidence, and `verify-python` now checks out
  with `fetch-depth: 0` and `fetch-tags: true`. A further check asserts that it
  does — without it these would be gates that always skip, the shape #89 already
  had to close once. Each check was proved by breaking it and confirming the
  mutation landed first; removing one of the three copies of the README sentence
  left the suite green, so the control was redone against all three.

- `exitdrill history` lines up a series of same-scope receipts as a timeline,
  and `verify-history` recomputes one from its source receipts. `compare`
  answers "did this export lose more than that one?" for exactly two receipts;
  an organisation rehearsing an exit repeats the drill after each vendor fix,
  each schema change, each quarter, and reading that as N-1 hand-chained
  comparisons is work nobody does. The verb is a pure reduction: nothing is
  averaged, trended, forecast, scored, or attributed to a cause, and no envelope
  timestamp is read. The order is the caller's argument order, or filename order
  under `--dir`, and the document says which.

  The first receipt sets the series scope under exactly the comparability
  predicates and reason codes `compare` enforces, so "in this series" and
  "comparable with the first receipt" cannot become two different questions. A
  receipt outside that scope is a gap carrying its reason codes: it never
  appears as zero counts, which would publish "this could not be measured" as
  "nothing was missing". For the same reason an adjacent pair touching a gap
  carries no direction at all rather than one computed from a single side, and
  `--fail-on-loss-signal-increase` exits 2 when the last adjacent pair is not
  comparable, because returning 0 there would read as "nothing increased".

  `exitdrill report history.json --receipt ... --receipt ...` renders it as a
  table-first offline page through the same shell the receipt and comparison
  reports use, and the timeline's gap cells say "No measurement" where a reading
  would otherwise go. The document is `exitdrill/history/v0.1` with a committed
  public JSON Schema, validated on every build and every verify beside the
  source-bound recomputation, the same pairing the comparison document uses.
  `make demo-compare` writes `examples/synthetic-crm/out/history.json` and
  `history.html`, and both are inside the record-value disclosure gate.

- Committed public JSON Schemas for the receipt and both input contracts, and
  `exitdrill schema list` / `exitdrill schema show NAME` to read them. Only the
  comparison document had one; the receipt, the baseline and the normalized
  export were defined by Python validators, which an outside implementer can
  read but cannot execute in their own language, and a reviewer handed a receipt
  could check its shape only by trusting the producer's code. ADR 0001 bets that
  other people write the source-specific normalizer, so the contract has to be a
  machine-checkable artifact. `schemas/receipt-v0.3`, `baseline-v0.3`,
  `export-v0.1` and `exercise-plan-v0.1` are now packaged in the wheel beside the
  comparison and history schemas, and validated at every load and every verify.

  The check runs after the semantic validators, not before, which is the one
  place this departs from the proposal in #134. Schema-first would replace every
  precise message -- the field and the relation that failed -- with a single
  conformance error, and the precise message is the more useful of the two for
  whoever has to fix the document. It is the pairing
  `verify_comparison_document` already describes and gives its reasons for.

  `docs/DATA-CONTRACTS.md` maps each subcommand to the schemas of its inputs and
  outputs, and states the boundary plainly: the count arithmetic, the status
  algebra, the payload checksum, the offset-aware timestamp rule and the
  uniqueness rules are relations between two values, which no Draft 2020-12
  schema can express. A schema believed to check more than it does is worse than
  no schema, so each of those is listed by name and `tests/test_schemas.py` holds
  the list against the code in both directions: an invariant the document forgets
  and one the validators stop enforcing both fail the suite. The suite also
  mutates a receipt, a baseline, an export and a plan once per locally
  expressible invariant and requires the schema to reject each, and validates
  every committed example so a schema stricter than its validator cannot ship.

### Added

- `tests/test_gates.py` now binds the offline binding gate's blind spot to the
  README. Three new checks: every field in `DYNAMIC_FIELD_PATHS` must have a
  disclosure phrase in a pinned table, every one of those phrases must appear
  in the README, and the gate itself must fail when its binding table is empty.
  The exclusion table is read out of the script's source rather than restated,
  so a copy cannot drift from the table the gate applies. Growing the exclusion
  table was the one edit that weakened this gate without changing its success
  line, which still reported nine files checked. Each guard was proved by
  breaking it and confirming that only its own test failed.

- `tests/test_canary_disclosure.py`: the same merge-gating record-value check,
  extended to the two real-process canaries, and the binding ADR 0021 left
  open. Each canary scanned its own aggregate output for a hand-written
  `_RAW_SENTINELS` tuple that nothing tied to its capture bundle. Measured:
  changing one sentinel in each script to a value no longer present left all
  510 pre-existing tests passing and both offline acceptance summaries
  byte-identical, and leaking the relationship type `assigned_to` into the
  Directus normalization manifest did the same. The new gate derives 22
  Directus and 23 CiviCRM record values from the committed captures, proves
  each still occurs in the capture bytes, proves every file in each bundle is
  classified, covers every aggregate artifact both canaries produce, and
  requires every hand-written sentinel to be one of those derived values. See
  ADR 0022.

- `docs/ROADMAP.md` now carries the multiyear arc, split into the work that
  fits inside the feature freeze and the work the outside-person usability
  gate in issue #51 blocks, with who can open each gate stated explicitly.
- Negative tests for six trust-boundary rejection branches that had none
  (issues #53, #54, #57, and #61). Each was proved to fire by neutering the
  guard it pins and confirming that test, and only that test, fails:
  `exitdrill validate`'s baseline/export identity guard (both halves of the
  `or`), `matches_field_type`'s unsupported-type fallback, `strict_json.py`'s
  dict-nesting depth limit and its invalid-UTF-8 rejection, and the
  `isinstance` guard shared by all four `_enum_value` call sites, which was
  covered at one call site out of four. A seventh branch found while closing
  #57, the RecursionError arm that stops a raw interpreter error from escaping
  the loader when a document is nested past the parser's own limit, is now
  covered too. `models.py`, `receipt_validation.py`, and `strict_json.py` are
  at 100% branch coverage.
- Issue #55 is decided. `report.py`'s malformed-dimension guard is confirmed
  unreachable through both public entry points, by reading and by measurement,
  and is kept rather than deleted or marked no-cover: it is commented with the
  chain that makes it unreachable, exercised directly by unit tests so it is a
  check that has been shown to fire, and the call ordering the finding depends
  on is now itself pinned by a test. `report.py` reaches 100% branch coverage
  with no pragma. See ADR 0023.
- `tests/test_canary_gate_assertions.py`: proof that the two canary
  acceptance scripts' four privacy assertions can fail. Until now the only
  thing exercising them was a subprocess run of the whole script against
  evidence that passes, which cannot distinguish a working assertion from one
  that has stopped working. Each case is parametrized over the script's own
  `_RAW_SENTINELS` or `_SENSITIVE_KEYS`, so a value added to either is proved
  to fire without anyone remembering to add a case, and the secret-key cases
  cover three casings so the `.lower()` in the walk is pinned too. Proved by
  neutering each of six behaviours in turn: the Directus raw-value scan, the
  CiviCRM secret-key check, its key lowercasing, its sentinel scan, its
  filesystem-path scan, and its recursion into nested dictionaries. Each
  neutering failed only the cases for that behaviour.
- `tests/test_documented_counts.py`: the counts the README, the Directus
  example README, and `docs/ARCHITECTURE.md` publish are now bound to the
  evidence they describe. Nine hand-written numbers had nothing tying them to
  an artifact, so a recapture or a normalizer change would have left the prose
  confidently wrong with no gate noticing, because prose is not executed. Each
  test computes the number from the committed evidence, renders the documented
  sentence with it, and requires that sentence to be present, so it fails in
  both directions: evidence that moves without the prose, and prose that is
  reworded without re-pointing the binding.
- `tests/test_report_offline_safety.py`: the HTML report's offline and
  script-free claims are now enforced against the rendered document. Three
  published statements assert them (the report's own footer, the README's
  Accessibility row, and the README's Performance N/A rationale) and none was
  checked; the only related test was one `"<script" not in ...` substring
  against the clean fixture. Measured: adding an `@import url(...)` web font to
  the report stylesheet, and separately deleting the Content-Security-Policy
  meta tag, each left the entire pre-existing suite passing. The new module
  parses the document with the standard library's HTML parser, holds its
  element and attribute sets to pinned allowlists, requires every link to stay
  in-document and the stylesheet to fetch nothing, and runs all of it a second
  time against a receipt whose free text is markup, script URLs, and a
  stylesheet import.
- `tests/test_directus_canary_bounds.py`: the Directus canary's untested
  trust-boundary rejection branches are closed. `directus_canary.py` verifies
  an untrusted capture bundle before anything else in the project reads it, and
  carried 69 uncovered statements, almost all a single `raise` with a distinct
  message; deleting any of them left the whole suite green. This is the work
  issue #57 asked for on `strict_json.py`, applied to the canary's separate
  copy of that boundary. Branch coverage for the module goes from 84% to 99%,
  and the two statements that remain are structurally unreachable, named in the
  suite with the reason rather than left as unexplained red lines.
- `tests/test_remaining_trust_boundaries.py`: the last untested rejection
  branches outside the two canaries are closed. `paths.py` (the single
  attachment-root boundary), `loader.py`, `exercise.py`, and `comparison.py`
  reach 100% branch coverage; `evaluator.py` goes from 92% to 96%. The three
  branches that remain across the project are structurally unreachable and are
  named in the suite with the reason and with assertions that fail if the
  reason stops holding, rather than marked no-cover.
- `tests/test_civicrm_target_canary_bounds.py`: the CiviCRM target canary's
  untested rejection branches are closed, the same way the Directus one's were.
  The module is the second separate copy of the outermost trust boundary and
  carried 29 uncovered statements: its own bounded JSON limits, its own
  regular-file and directory checks, the evidence index's byte and schema
  bindings, and the atomic-output paths. Branch coverage goes from 95% to 99%,
  and the one statement that remains is structurally unreachable and named in
  the suite with the reason.

- `tests/test_disclosure.py`: a merge-gating check that no aggregate artifact
  on the `examples/synthetic-crm` path republishes a record-level value, per
  `AGENTS.md` invariant 7. Both canaries already scanned their own output for a
  hand-written `_RAW_SENTINELS` tuple; the flagship demo path had only three
  string literals in one report test, checking the rendered HTML and not the
  receipt or comparison document. Measured: leaking the permission principal
  `worker-001` into all five artifacts left every one of the 492 pre-existing
  tests passing. The new gate derives its corpus from the fixture files,
  asserts every derived value actually occurs in the input bytes before
  trusting it, searches literal and HTML-escaped forms so escaping cannot act
  as a bypass, and computes rather than hardcodes the two values ExitDrill's
  own vocabulary makes indistinguishable. See ADR 0021.

- `.github/workflows/codeql.yml`: a CodeQL `actions`-language scan of every
  workflow file, generally available since 2025-04-22. It is a second,
  independent engine from zizmor (different rule set, results in the
  Security tab) and is now a required status check alongside `verify`.
- Portfolio standards conformance documentation: a Standards Conformance
  table and an AI-assisted development disclosure in the README, a roadmap
  with the milestone gates and the Quality & Metrics ledger
  (`docs/ROADMAP.md`), and a reasoned internationalization N/A declaration
  (`docs/I18N.md`).
- `.github/allowed_signers`, the SSH allowed-signers file the release
  workflow uses to verify a signed annotated release tag.
- `docs/RELEASE.md` (release posture and the publication-blocking checklist)
  and `docs/INCIDENT-RESPONSE.md` (the incident process the Standards
  Conformance table already cited) are now committed and linked from the
  README's Documentation list.
- `compare_snapshots` and `verify_comparison_document` now load the packaged
  `receipt-comparison-v0.1.schema.json` at runtime and validate every
  comparison document against it, matching the self-check pattern
  `civicrm_target_canary.py` already used for its own result schemas. The
  public schema previously validated only in tests, against the repo copy;
  the installed package never opened it.
- `examples/directus-11.17.4-civic-case/README.md` now documents the
  adversarial derivative the top-level README cites: the six mutations, that
  row and file counts are preserved by construction, that the derivative is
  never committed (generated per run into a `TemporaryDirectory`), the
  per-dimension observed-loss-signal table, and a claim-limits paragraph
  scoped to the derivative (issue #32). Matches the shape the CiviCRM example
  README already used.
- `scripts/check_browser_capture_bindings.mjs`: a real, offline reproducibility
  gate for issue #31. Nothing previously bound the nine committed
  `browser-*.json` files to the four `civicrm_browser_*.mjs` scripts that
  produced them; `make lint-lab` only parses them. Each of those four scripts
  writes a hardcoded literal unconditionally once every live browser/DOM
  assertion above it passes, so the committed file should always equal that
  literal. This gate extracts the literal directly from each script's source
  and requires canonical equality with the corresponding committed file --
  catching either side drifting from the other, without a live CiviCRM,
  Playwright, or Docker. It explicitly excludes the handful of fields only a
  live page can produce (axe-core's rule counts and version, one measured
  keyboard tab-count) rather than silently trusting them; those are listed
  by name in the script. Verified against three real scenarios: a mutated
  script (caught), a hand-edited committed file (caught), and a change to
  only a live-only field (correctly not flagged, since that case is out of
  this gate's scope). Wired into `tests/test_gates.py` (skips cleanly
  without Node, like the existing lab-syntax gate) and into
  `make demo-civicrm-target-canary`, both of which run in the required
  `verify` CI job.
- `examples/civicrm-6.16.2-target-roundtrip/README.md`: a new "Recapturing
  this profile" section documents the actual manual re-capture procedure
  (the `civicrm_target_roundtrip_lab.mjs` orchestrator's CLI entry point and
  prerequisites) and reports, honestly, that a real attempt at it during
  this work completed CiviCRM provisioning but failed at the first browser
  step on a 15-second visibility-wait timeout roughly four minutes in --
  a harness reliability question, not evidence against the scripts'
  determinism once a run completes. No automated or scheduled live
  recapture exists; this stays a documented manual procedure, matching the
  project's paused feature scope.

### Fixed

- The 90% branch-coverage gate measured `src/exitdrill` only, so nothing
  measured `scripts/` -- the directory holding `check_wheel.py`, both canary
  demo gates and the two adversary builders (issue #86). Measured with the
  scope added and nothing else changed: `scripts/` is at 33% and the project as
  a whole at 82%, below the floor the gate has been reporting as met. Most of
  that gap is not untested code: the gate tests run `python scripts/<gate>.py`
  as real subprocesses, because what they assert is its exit code and its exact
  stdout, and coverage does not follow into a child process on its own.
  `tests/conftest.py` now sets `COVERAGE_PROCESS_START` and `COVERAGE_FILE` at
  session start and `[tool.coverage.run]` sets `parallel = true`, which brings
  the real figures to 99% for `src/exitdrill`, 82% for `scripts/` and 95%
  together. `make test` now floors each scope separately as well as the run as
  a whole, so a well-covered scope can no longer carry a poorly covered one.
- CI never set `EXITDRILL_REQUIRE_GATE_TOOLS`, so the mechanism issue #89 added
  was built and left switched off: the four gate tests that need `node` or `uv`
  would still have skipped themselves in CI, green, if a workflow edit removed
  the tool they depend on. The `Verify` step now sets it to `1`, which turns a
  missing tool into a failure there while a local checkout without the tools
  still skips. Proved by hiding `node` from `PATH`: the two node-dependent
  gates fail with the flag set and skip without it.
- `requires-python` admitted 3.12, 3.13 and 3.14 while CI ran only 3.12, so two
  of the three declared interpreters were never exercised (issue #90). Measured
  on the unrun ones: 3.13 is clean, and 3.14 failed three tests. All three
  wrote their input as a literal 20,000 levels of nesting to reach the
  `RecursionError` arm that `strict_json`, `directus_canary` and
  `civicrm_target_canary` each put between a raw interpreter error and their
  trust boundary. CPython 3.14 bounds decoder recursion by remaining C stack
  rather than by a fixed count, so 20,000 parses there and the depth check
  caught the document instead -- the arm stopped being exercised on 3.14 while
  the same literal still defeated 3.12 and 3.13. The trust boundary held
  throughout: the document was rejected fail-closed on every version, only by a
  different guard than the tests named. The three now take their input from a
  `json_the_parser_cannot_walk` fixture that searches for a depth the running
  decoder actually refuses and fails the run if none exists, and the `verify`
  job runs under a 3.12/3.13/3.14 matrix so a declared interpreter cannot go
  unrun again. Measured after: coverage reports each of the three arms executed
  on 3.14, where all three were missing before.
- A receipt claiming every row exported, none restored, and none invalid
  verified as `pass` and rendered as "Structurally restorable" (issue #81).
  `evaluator._dimension_result` floors `invalid_count` at
  `exported_count - restored_count`, so no drill can emit that dimension, but
  `receipt_validation` bounded `restored_count` from above and never from
  below. `_validate_dimension` now re-derives the floor. Measured before the
  fix, not assumed: a receipt built from the synthetic example with every
  `restored_count` zeroed and rehashed passed `verify_receipt` and rendered a
  Restored column of 0 beside an Exported column of 2. `validate_payload`'s
  docstring now settles the question the issue raised: the accepted set is
  exactly the set `run_drill` can emit, and every other relation the
  evaluator guarantees was checked and found already enforced.
- `load_receipt` patched `strict_json`'s error message afterwards with
  `str(exc).replace("document exceeds", "receipt exceeds", 1)`, a
  string-literal coupling across a module boundary that nothing bound (issue
  #85). Measured: deleting the rewrite left all 137 tests over
  `test_receipt.py`, `test_comparison.py` and `test_report.py` passing,
  because every assertion matched on `"2 MiB"`, which both wordings contain.
  The live failure was the reverse direction -- rewording `strict_json`'s
  message would make `.replace()` match nothing and silently revert the
  caller to the generic noun. `load_strict_json` now takes a
  `document_label` beside its existing `size_label` and composes each
  document-scoped message at the raise site, the shape the two canaries'
  `where` parameter already uses; `load_exercise_plan` passes its own noun
  too, and `_load_object` keeps the default, which is the noun it already
  used. Each of the six labelled raise sites is pinned by a test that fails
  if the noun reverts.
- `scripts/check_browser_capture_bindings.mjs` reported success having compared
  nothing. `checked` was counted but never floored, so an emptied `BINDINGS`
  table printed "verified 0 committed browser-*.json files bind to the literal
  their capture script declares" and exited 0, through `make
  demo-civicrm-target-canary` and through the CI step that runs it. Measured
  before the fix, not assumed. The count is now floored the way `lint-lab`
  floors its own with `test "$checked" -gt 0` and `check_wheel.py` floors its
  with `if not referenced`.
- The README named three of the four field groups the offline binding check
  cannot verify. `DYNAMIC_FIELD_PATHS` excludes axe-core's `engine_version`,
  its three rule counts, its `violations` list, and the keyboard tab-count from
  comparison; the README's parenthetical listed the rule counts, the version,
  and the tab-count, and stopped, while pointing the reader at the script "for
  exactly which fields that is". `violations` is the field carrying the two
  serious accessibility findings `docs/ARCHITECTURE.md` publishes, so the one
  omission was the one that mattered most. The sentence now names it.

- `build_directus_lossy_canary.py`'s six adversarial-mutation labels were a
  separately maintained constant, never re-derived from the mutations the
  script actually applies (issue #32). `_mutate` now returns the label for
  each mutation as it applies it, and that returned list -- not a parallel
  hardcoded one -- is what the derivative's `adversarial-derivative.json`
  statement declares. `check_directus_canary_demo.py` now also asserts the
  exact mutation list on every run, so a future edit that adds, drops, or
  reorders a mutation without updating the label is caught immediately.
- The top-level README said the Directus derivative produces "six declared
  loss signals"; the evaluator observes them, the six mutation labels are
  what is declared, and those are two different sixes that happen to match
  by arithmetic today, not by construction (issue #32). Now reads "six
  observed loss signals."
- The wheel force-included 25 schemas; 12 were never loaded by any code
  (issue #33): the six superseded `civicrm-evidence-index` versions (only
  v0.7 is read), and all six `civicrm-evidence-verification` versions
  (nothing loads that family at all). `pyproject.toml`'s force-include block
  is trimmed to the 13 schemas `src/exitdrill/` actually references.
  `scripts/check_wheel.py`'s `committed_schemas` now derives the required
  set from a scan of `src/exitdrill/` for schema-filename literals instead
  of globbing every file under `schemas/`, so the gate enforces "referenced
  by real code," not "exists in the tree." `receipt-comparison-v0.1` is the
  one schema that moved from "referenced by tests only" to "referenced by
  real code" rather than being dropped -- see the runtime self-check added
  above. New tests in `tests/test_gates.py` assert the force-include table
  matches exactly what source code references, and pin the concrete
  regression: a superseded schema that still exists on disk must not ship
  even if it sneaks back into the packaged entries. The 12 superseded files
  stay in `schemas/` and git history; nothing is deleted.

- Thirteen paths — twelve documents and `docs/adr/` — were hidden from every
  `git status` by `.git/info/exclude`, a per-clone file that is never pushed
  and was itself untracked. Nothing in the repository recorded that these
  paths existed or why they were unpublished, and because `docs/adr/` was
  one of them, a new ADR written there (the portfolio's canonical discovery
  path per `docs/adr/0000-record-architecture-decisions.md`) would silently
  fail to appear in `git status` or `git add`. Each of the twelve documents
  was read in full and judged individually. Two were purely technical and
  public-appropriate with no existing committed equivalent
  (`docs/RELEASE.md`, `docs/INCIDENT-RESPONSE.md`) and are now committed.
  Two were stale, non-sensitive duplicates already fully superseded by a
  committed doc (`docs/I18N.LOCAL-DRAFT.md` by `docs/I18N.md`;
  `docs/OBSERVABILITY.md` by the Observability scope section of
  `docs/ROADMAP.md`) and stay out to avoid two disagreeing sources of
  truth. Eight were private product-strategy, competitive-intelligence,
  brand, or legal material — buyer/kill-gate economics, a rejected private
  codename and competitor scan, brand-positioning strategy, a trademark
  clearance memo, and customer-discovery scripts (`docs/PRD.md`,
  `docs/RESEARCH.md`, `docs/NAMING.md`, `docs/NAMING-CLEARANCE.md`,
  `docs/RED-TEAM.md`, `docs/DISCOVERY-PACK.md`, `docs/USER-RESEARCH.md`,
  `docs/ROADMAP.LOCAL-DRAFT.md`) — and stay out. `.git/info/exclude` is
  emptied back to the git default template, the decision to keep the eight
  private and two superseded documents unpublished is now recorded in a
  tracked, commented `.gitignore`, and `docs/adr/` is no longer excluded
  anywhere so a future ADR left there is visible instead of vanishing.
  `CONTRIBUTING.md` no longer directs contributors to read "the PRD," a file
  that would not exist in a fresh public clone.

- The attachments dimension no longer hides one class of loss behind another.
  An exported attachment can fail byte verification, be refused by the
  reference model's foreign key, or both, and those are disjoint populations.
  The evaluator reported `max()` of the two population sizes, so whichever set
  was smaller became invisible: an export carrying an unrestorable attachment
  could newly corrupt a *restorable* attachment's bytes and still publish an
  identical `invalid_count`, identical `restored_count`, and identical
  `observed_remediation_signals`. `exitdrill compare
  --fail-on-loss-signal-increase` then exited 0 and recorded
  `no_observed_loss_signal_change` for attachments — a silent-loss false
  negative in the one dimension the tool exists to watch. The evaluator now
  tracks which attachments failed each check and reports the size of their
  union, so overlapping failures still count once while disjoint ones both
  count. The restoration shortfall remains a fail-closed floor. No other
  dimension was affected: each has only one reachable failure mode, so `max()`
  was already exact there. Every existing fixture, demo, and canary summary is
  unchanged.
- Every command that reads `uv.lock` now uses `--locked` instead of `--frozen`,
  so a `pyproject.toml` dependency change that was never relocked fails the
  build instead of passing it. `uv sync --frozen` and `uv export --frozen`
  install and export whatever the lockfile already says and exit 0 on a drifted
  lockfile, which meant a newly declared runtime dependency was neither
  installed for the merge gate nor present in the requirement set handed to
  `pip-audit`. Two gates cover the change: one asserts the real flag behaviour
  against `uv`, and one keeps `--frozen` out of the Makefile and both
  workflows.
- The offline CiviCRM acceptance gate now requires the empty-target
  precondition control to be rejected *for that precondition*. It previously
  accepted any `CiviCRMTargetCanaryError`, so a derivative that stopped
  exercising the precondition but broke in some unrelated way still counted
  toward `adversarial_controls_detected`.

### Changed

- `write_receipt`, `write_report` and `write_comparison` now share one
  implementation, `atomic_write.write_bounded_file`, instead of carrying three
  copies of the same bounded `mkstemp` + `fsync` + `os.replace` sequence
  (issue #93). Each caller keeps its own size bound, error type and rejection
  wording, which are parameters rather than duplicated code, so no message
  changed. The bound is still checked before `mkdir` and before `mkstemp`, so
  the write ordering `docs/THREAT-MODEL.md` states is unchanged and each
  caller's "the parent directory still does not exist" assertion passes as
  written.
- All three writers now fsync the parent directory after `os.replace`, which
  is the half of "atomically write" the docstrings claimed and the code did
  not do. `os.replace` is atomic against a concurrent reader, but the
  directory entry it creates is not durable until the directory is synced, so
  a crash could come back with the payload on disk and nothing naming it. The
  directory fsync is tolerated rather than required: a platform with no
  directory descriptor still gets its artifact and loses only crash
  durability, which it could not have offered anyway. The alternative the
  issue offered -- weakening the docstrings to "atomically replace" and
  disclaiming durability -- was not taken, because the file fsync was already
  being paid for and the missing step is one syscall.

- The receipt envelope's `claimed_generated_at` must now be an ISO 8601
  timestamp with an explicit UTC offset, the same contract
  `baseline.captured_at`, `export.exported_at` and every `occurred_at`
  already meet through `timestamps.parse_timestamp` (issue #83). It
  previously accepted any non-blank string, so `exitdrill drill
  --claimed-generated-at "sometime last spring"` wrote a receipt that
  `verify` accepted and `report` rendered. This narrows the accepted receipt
  contract without advancing `exitdrill/receipt/v0.3`: `build_receipt` has
  only ever emitted offset-aware ISO 8601, so no receipt this tool wrote
  stops verifying, but a hand-edited or hand-built one with a loose value
  now does. Invariant 8 is unchanged and the field is still untrusted --
  shape validation is not authentication, and `signature_status` and
  `trusted_time` remain what carry the disclaimer; the shape only makes the
  value mean the same thing to every reader.
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
