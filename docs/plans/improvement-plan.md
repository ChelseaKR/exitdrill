# Improvement plan: offline binding gate and its disclosure

Audit date: 2026-08-28. Base: `main` at `4910e1a`.

This plan covers one audit of the merge gates, the four open pull requests, and
the one open issue. It is written to be executed and then left as the record of
what was executed, including the parts that found nothing.

## Phase 0: establish the baseline

`make verify < /dev/null; echo "EXIT=$?"` on `main` at `4910e1a`: exit 0, 641
passed, total coverage 93.35%. Logged to
`/private/tmp/er-audit/exitdrill-main-baseline.log`.

`make demo-compare` reproduces the exact four-line summary that issue #51 asks
an outside tester to confirm, including the loss-signal counts and the changed
dimension list. The issue's expected output is correct as published.

## Phase 1: audit each gate for the "cannot fail" property

Checked by name, against the source rather than the description:

| Gate | Finding |
|---|---|
| `uv sync --locked` in Makefile, ci.yml, release.yml | Sound. `test_frozen_lockfile_flag_cannot_observe_declared_dependency_drift` probes real `uv` to prove `--frozen` exits 0 on drift and `--locked` does not, and `test_every_lockfile_consuming_command_observes_lockfile_drift` forbids `--frozen` in all three files. |
| `make lint-lab` | Sound. Enumerates with `git ls-files '*.mjs'` under `set -e`, and floors the count with `test "$checked" -gt 0`. Both properties are pinned by tests. |
| `check_wheel.py` | Sound. `committed_schemas` raises when no schema reference is found, and that arm is tested. |
| `semgrep` | `semgrep scan --error` over `src tests scripts`, not `semgrep test`. Scope excludes `examples/` and `lab/`; the workflow files are covered by zizmor and CodeQL instead. |
| mypy scope | `files = ["src", "tests", "scripts"]`, strict, and pinned by `test_strict_type_checking_covers_the_committed_gate_scripts`. |
| ruff scope | `ruff format --check .` and `ruff check .`, so the gate scripts and tests are in scope. |
| coverage scope | `--cov=exitdrill` only. The acceptance scripts under `scripts/` are executed by the suite but not coverage-measured. Recorded below as a known limit, not fixed here. |
| `codeql.yml` trigger | `pull_request` with no branch filter, so a stacked pull request is scanned. Not the missing-scan pattern. |
| CI conclusions | Real. Every recent job has non-trivial durations, real step counts, and no Actions-budget annotation. No billing starvation in this repository. |
| `check_browser_capture_bindings.mjs` | **Two defects. See phase 2.** |

## Phase 2: the two defects

### 2a. The gate reported success having compared nothing

`main()` counted every comparison into `checked` and never floored it. With an
emptied `BINDINGS` table the script printed

```
verified 0 committed browser-*.json files bind to the literal their capture script declares
```

and exited 0. Measured, not inferred. This runs as a CI step and as the
README-documented `make demo-civicrm-target-canary`.

Fix: floor `checked`, matching `lint-lab` and `check_wheel.py`.

### 2b. The README named three of the four unverifiable field groups

`DYNAMIC_FIELD_PATHS` excludes six fields from comparison: axe-core's
`engine_version`, `incomplete_rule_count`, `inapplicable_rule_count`,
`passes_rule_count`, and `violations`, plus `tab_steps_to_roles_summary`. The
README's parenthetical named the rule counts, the version, and the tab-count,
and stopped, while pointing the reader at the script "for exactly which fields
that is". The script's own header comment does list the violation list.

`violations` carries the two serious accessibility findings
`docs/ARCHITECTURE.md` publishes, so the omitted group was the one a reader is
most likely to rely on.

Fix: name it in the README, and bind the two together so they cannot drift.

## Phase 3: the guards, and proof each can fail

Each guard was broken, the break confirmed to have landed, the suite run, and
the guard restored. Logged to `/private/tmp/er-audit/exitdrill-break-restore.log`.

| Guard | Break | Result |
|---|---|---|
| `checked === 0` floor | delete the floor block | only `test_the_binding_gate_fails_when_it_has_nothing_to_check` failed |
| README disclosure | revert the sentence to its previous wording | only `test_the_readme_discloses_every_field_the_binding_gate_cannot_verify` failed |
| exclusion table pin | add `browser-workflow.json: ["schema_version"]` to `DYNAMIC_FIELD_PATHS` | `test_every_excluded_field_has_a_disclosure_phrase` and the README test failed |

The third break is the important one: before this change, adding an exclusion
weakened the gate while its success line still read "verified 9".

## Known limits this plan did not close

Both were closed later, on `integration/wave-1`. The findings are kept as
written, with what closed them recorded underneath, because the finding is the
record and deleting it would leave the plan claiming a clean audit it did not
have.

- **Coverage does not measure `scripts/`.** The two acceptance scripts are
  roughly 52KB of Python that decide whether the canaries pass. They are
  executed by the suite through subprocesses and by direct import, and their
  privacy assertions are proved to fire by `tests/test_canary_gate_assertions.py`,
  but no coverage floor applies to their rejection branches. Closing this means
  either adding `scripts` to `[tool.coverage.run] source` and accepting a lower
  floor until the branches are covered, or a second coverage target. Left open
  deliberately rather than half-done.

  **Closed** (issue #86). `scripts` is now in `[tool.coverage.run] source` and
  in pytest's `--cov`, with `parallel = true`, and `tests/conftest.py` sets
  `COVERAGE_PROCESS_START` and `COVERAGE_FILE` at session start so coverage
  follows the suite into the subprocesses that run those gate scripts. The
  subprocess call sites stay subprocesses: they assert on a real invocation's
  exit code and stdout, which importing the module would stop proving. The
  first of the two routes above was taken, with the lower floor stated rather
  than averaged away: `make verify` applies three floors rather than one --
  `src/exitdrill` at 90%, `scripts/` at 80%, and both scopes together at 90% --
  so neither scope can hide behind the other. Measured on `integration/wave-1`
  at `454ddeb`: `src/exitdrill` 99%, `scripts/` 82%, combined 94.94%.

- **The binding gate stubs `pageErrors` as `{ length: 2 }` for every script.**
  Verified correct today: only `civicrm_browser_case_search_workflow.mjs`
  references `pageErrors` inside its declared output literal, and that script
  aborts unless `pageErrors.length === 2`. Nothing pins that this stays true. A
  future script whose literal reads `pageErrors` without that assertion would
  be compared against a fabricated 2.

  **Closed** (issue #87). `assertPageErrorsStubStillProven` in
  `scripts/check_browser_capture_bindings.mjs` now checks both halves of that
  "verified correct today" on every run instead of recording them in a comment.
  Any script other than `civicrm_browser_case_search_workflow.mjs` whose
  extracted literal reads `pageErrors` is a hard error, and that one script must
  still carry its `pageErrors.length !== 2` abort or the gate refuses to run.
  The check reads the extracted literal rather than the whole file, because all
  four capture scripts mention `pageErrors` legitimately outside their literal.
  The future script this bullet worried about now fails the gate instead of
  being silently compared against a fabricated 2.
