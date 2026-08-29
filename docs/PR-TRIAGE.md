# Open pull-request triage

Audited 2026-08-28 against `main` at `4910e1a`.

## Summary

Four open pull requests, all authored by the maintainer, all test-only plus a
CHANGELOG entry, all reported by GitHub as `CONFLICTING` / `DIRTY`.

**None of them is stacked.** Every one bases on `main`, so no pull request here
would auto-close if another's base were merged and its branch deleted. They can
land in any order.

**Every conflict is the same one, and it is trivial.** `git merge-tree` against
`4910e1a` shows exactly one conflicted file in each case, `CHANGELOG.md`, and
exactly one conflicted hunk: each branch appended a bullet to the same
`### Added` list that `#70` and `#71` also appended to. Both sides are wanted.
Resolving is "keep both, in either order".

**All four still pass on today's `main`.** Verified by merging `4910e1a` into a
detached copy of each head, resolving the CHANGELOG hunk by keeping both sides,
and running `make verify` capturing its own exit code:

| PR | Branch | Merged gate | Tests | Coverage |
|---|---|---|---|---|
| #72 | `test/bind-the-report-offline-safety-claims` | EXIT=0 | 658 passed | 93.35% |
| #73 | `test/close-directus-canary-trust-boundary-branches` | EXIT=0 | 723 passed | 96.97% |
| #74 | `test/close-remaining-trust-boundary-branches` | EXIT=0 | 672 passed | 94.77% |
| #75 | `test/close-civicrm-canary-trust-boundary-branches` | EXIT=0 | 673 passed | 94.54% |

The coverage percentages in the pull-request bodies were measured against
`508293f`, when the project total was 93.03%. `main` has since moved to 93.35%,
so the bodies understate the resulting totals slightly. The direction and the
per-module numbers still hold.

## Classification

| PR | Class | Notes |
|---|---|---|
| #72 | Real gap, closed | The report's offline and script-free claims were asserted in three published places and checked by one substring. The body's "measured" section names two changes that broke the claim outright while the whole suite stayed green. |
| #73 | Real gap, closed | 69 uncovered rejection statements on the Directus canary's trust boundary. Largest single coverage movement of the four. |
| #74 | Real gap, closed, with one honest negative | Reports that neutering the `evaluator.py` entity-insert early return does **not** fail its test, and says why, rather than claiming a proof it does not have. That is the correct disposition, not a defect in the pull request. |
| #75 | Real gap, closed | The CiviCRM canary's copy of the same boundary. |

## Recommended order

Any. If a single order is wanted, largest coverage movement first so the later
resolutions are against the higher floor: #73, #74, #75, #72.

## What is not blocked on anything

Nothing here is blocked on review of another. The only work each needs is the
one-hunk CHANGELOG resolution at merge time.

## Open issue

| Issue | Class | Notes |
|---|---|---|
| #51 | Aspiration / process gate, not a defect | Asks an outside person to run the synthetic demo and answer seven questions. Verified 2026-08-28: `make demo-compare` reproduces the exact four-line summary the issue publishes, including "5 loss signals" and the changed-dimension list, so a tester following it will not be misled by wrong expected output. Correctly labelled `help wanted`. Nothing to fix; it closes when someone outside the project answers it. |
