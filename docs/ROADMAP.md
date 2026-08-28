# Roadmap

ExitDrill is a synthetic-data technical alpha. Feature scope is paused at the
boundary stated in the README: the next milestone is an outside person running
the synthetic demo without help and explaining whether the receipt answers
their exit question. Until that happens the project adds no new connector,
evidence family, or data category.

## Milestones

| Milestone | State |
|---|---|
| Structural evaluator with five separate dimensions | Done |
| Synthetic clean and lossy CRM demos with comparison policy | Done |
| Directus 11.17.4 source canary with adversarial derivative | Done |
| CiviCRM 6.16.2 target-roundtrip canary with indexed, verified evidence | Done |
| Outside-person demo walkthrough (usability gate) | Open; blocks all new feature scope |
| Data-governance gate for any non-synthetic input | Open; prohibitive until satisfied (see `docs/DATA-GOVERNANCE.md`) |
| First tagged release (v0.1.0) | Not scheduled; no tag exists and nothing has been published |

## Metrics

Per the portfolio Quality & Metrics standard, each metric is AUTO (merge
blocking in CI) or REVIEW (human disposition with a committed, dated
artifact). Nothing in this table is aspirational.

| Metric | Target | Measured by | Gate | Owner |
|--------|--------|-------------|------|-------|
| Branch coverage [CQ-08] | >= 90% | `pytest --cov` with `--cov-fail-under=90` inside `make verify` | AUTO | maintainer |
| Ruff lint and format | 0 findings | `make lint` inside `make verify` | AUTO | maintainer |
| Strict mypy (src, tests, scripts) | 0 errors | `make type` inside `make verify` | AUTO | maintainer |
| SHA-pinned `uses:` [SEC-25] | 100% | zizmor job in `ci.yml` | AUTO | maintainer |
| Dependency vulnerabilities | 0 known (strict pip-audit; npm audit at high) | `dependency-scan` job in `ci.yml` | AUTO | maintainer |
| Secret scan | 0 findings | gitleaks job in `ci.yml` | AUTO | maintainer |
| SAST | 0 Semgrep findings (p/python, p/nodejs) | `sast` job in `ci.yml` | AUTO | maintainer |
| Declared demo outcomes | clean, lossy, and comparison-policy exit codes reproduced | `make demo-compare-policy` in CI | AUTO | maintainer |
| Record-value disclosure (`AGENTS.md` invariant 7) | 0 record values in any aggregate artifact on the synthetic demo path | `tests/test_disclosure.py` inside `make verify` | AUTO | maintainer |
| Record-value disclosure, canary paths (`AGENTS.md` invariant 7) | 0 record values in any aggregate artifact the Directus or CiviCRM canary produces, with every hand-written sentinel proved still present in its capture | `tests/test_canary_disclosure.py` inside `make verify` | AUTO | maintainer |
| Offline canary acceptance | Directus and CiviCRM acceptance summaries match byte for byte | pytest acceptance tests inside `make verify`, plus `make demo-civicrm-target-canary` in CI | AUTO | maintainer |
| Threat model [QM-14] | current for every new trust surface | `docs/THREAT-MODEL.md` | REVIEW | maintainer |
| Responsible-tech audit | current for every capability change | `docs/RESPONSIBLE-TECH-AUDITS.md` | REVIEW | maintainer |

## Multiyear arc

This is the shape of the next two to three years, written so that a reader can
tell what is built from what is planned, and so that nothing here quietly
reinterprets the feature freeze above.

The arc has one hard boundary in the middle of it. Everything in Track A is
work that fits inside the freeze: correctness, gate integrity, privacy
enforcement, and documentation truth. None of it adds a connector, an evidence
family, or a data category. Everything in Track B is blocked, and stays blocked,
until an outside person completes the walkthrough in issue #51 and says whether
the receipt answers their exit question. No amount of engineering opens that
gate. It is a question about whether this tool is understandable by someone who
did not build it, and only a person who did not build it can answer it.

### Track A: inside the freeze

| Phase | Scope | State |
|---|---|---|
| A1 | Bind the canary disclosure checks to their fixtures, and cover both canaries' aggregate artifacts with a derived corpus (ADR 0022) | Done |
| A2 | Close the untested trust-boundary branches recorded in issues #53, #54, #57, and #61 | Planned |
| A3 | Decide the `_dimension_rows` reachability question in issue #55, and make the codebase reflect the decision | Planned |
| A4 | Sweep the remaining hand-written expectations in the offline gate scripts, binding or deriving each one that is not already bound to the artifact it checks | Planned |
| A5 | Keep the published claims and the enforced gates in step: every claim the README or a canary README makes is either enforced by `make verify` or stated as unenforced | Continuous |

Track A is deliberately unglamorous. The recurring defect this project has
found in itself is not a wrong answer; it is a check that reports a clean
result whether or not it is still checking anything. ADR 0021 and ADR 0022 are
both records of that defect. A4 exists because the same question has not yet
been asked of every remaining guard.

### The gate

| Gate | Who can open it | What it blocks |
|---|---|---|
| Outside-person demo walkthrough (issue #51) | An outside person, not the maintainer and not an agent | Every new connector, evidence family, and data category |
| Data-governance gate (`docs/DATA-GOVERNANCE.md`) | The maintainer, after a reviewed sensitive-data design and a design-partner agreement | Any non-synthetic input |

### Track B: after the gate, planned and not built

Nothing below has been started, and none of it may be started before the gate
above opens. The ordering is a current intention, not a commitment; what the
walkthrough finds may reorder or remove any of it.

| Phase | Scope | Blocked by |
|---|---|---|
| B1 | Disposition of the walkthrough findings. May be documentation-only, may be a usability change, may be a decision that the receipt does not answer the question it claims to | #51 |
| B2 | A second source canary against a different real product, which is the first thing the freeze forbids and needs its own ADR and threat-model update | #51 |
| B3 | Whatever design the second canary shows is genuinely shared, rather than a connector SDK invented before two real pairs exist (`AGENTS.md`) | #51, B2 |
| B4 | Non-synthetic input handling | Data-governance gate |
| B5 | First tagged release, v0.1.0 | #51, and a maintainer decision that the claims are stable |

## Observability scope (Tier C)

ExitDrill is an offline, single-run CLI and library with no hosted service, so
the tracing, metrics, and SLO surfaces of the portfolio observability standard
are out of scope at this tier. Operational evidence is deterministic exit
codes, replayable receipts, and rendered reports. A structured
`--log-format json` opt-in is not implemented and is not claimed. Adding a
hosted or long-running surface reopens this decision.
