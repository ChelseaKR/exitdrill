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
| Offline canary acceptance | Directus and CiviCRM acceptance summaries match byte for byte | pytest acceptance tests inside `make verify`, plus `make demo-civicrm-target-canary` in CI | AUTO | maintainer |
| Threat model [QM-14] | current for every new trust surface | `docs/THREAT-MODEL.md` | REVIEW | maintainer |
| Responsible-tech audit | current for every capability change | `docs/RESPONSIBLE-TECH-AUDITS.md` | REVIEW | maintainer |

## Observability scope (Tier C)

ExitDrill is an offline, single-run CLI and library with no hosted service, so
the tracing, metrics, and SLO surfaces of the portfolio observability standard
are out of scope at this tier. Operational evidence is deterministic exit
codes, replayable receipts, and rendered reports. A structured
`--log-format json` opt-in is not implemented and is not claimed. Adding a
hosted or long-running surface reopens this decision.
