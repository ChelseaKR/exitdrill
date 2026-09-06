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

## Known limits this plan does not close

> **Both are closed as of 2026-09-06, and this section is now bound to the code
> by `tests/test_documentation.py::test_the_plan_publishes_no_limit_the_code_has_closed`.**
> A plan that goes on publishing a limit the tree has since closed is the same
> defect this plan was written about, pointed at the plan: a statement about
> what is enforced, outliving the enforcement. It failed in the direction that
> understates the project rather than overstates it, which is the safer
> direction and still not a true one. The test fails if either entry is
> reinstated while its closure stands, and it fails if a closure is reverted
> while the entry stays deleted.

- ~~**Coverage does not measure `scripts/`.**~~ **Closed (#125.)** The two
  acceptance scripts are roughly 52KB of Python that decide whether the canaries
  pass, and for a while no coverage floor applied to their rejection branches.
  `[tool.coverage.run] source` is now `["exitdrill", "scripts"]` with
  `parallel = true`, and `tests/conftest.py` sets `COVERAGE_PROCESS_START` so
  coverage follows the gate scripts into the subprocesses the suite runs them
  as. `docs/ROADMAP.md` carries the three resulting floors: 90% for
  `src/exitdrill`, 80% for `scripts/`, and 90% for both together.
- ~~**The binding gate stubs `pageErrors` as `{ length: 2 }` for every
  script.**~~ **Closed.** The stub is still a fabricated value, and it is still
  safe for the same reason: exactly one capture script reads `pageErrors` inside
  its declared literal, and that script cannot reach its literal unless
  `pageErrors.length === 2`. What has changed is that both halves of that
  reasoning are now enforced rather than asserted in a comment.
  `scripts/check_browser_capture_bindings.mjs` fails if another script's
  declared literal starts reading `pageErrors`, if the owning script's literal
  stops reading it, or if the owning script stops proving
  `pageErrors.length === 2` first. A future script whose literal read
  `pageErrors` without that assertion would now fail the gate rather than be
  compared against a fabricated 2.
