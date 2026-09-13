"""The required `secret-scan` check must read the history, not the commit it was handed.

`secret-scan` is a required status check on `main`. Until this change it was
`gitleaks/gitleaks-action`, which chooses its scan range from the event that
triggered the run:

    push of N commits   gitleaks detect --log-opts=--no-merges --first-parent BASE^..HEAD
    push of 1 commit    gitleaks detect --log-opts=-1            <- exactly one commit
    pull_request        the pull request's own commits

Every commit on `main` here arrived as a squash merge, which is a single-commit
push, and `ci.yml` declares neither `schedule` nor `workflow_dispatch` -- the two
events for which that action omits `--log-opts` entirely. So no lane in this
repository ever read more than 1 of `main`'s 98 commits, and a credential added
in one commit and deleted in the next was invisible to a check named
`secret-scan` that reported success.

`fetch-depth: 0` did not prevent that and could not. It decides how much history
`actions/checkout` puts on disk; it says nothing about how much of that history
the scanner is asked to read. A deep checkout handed to a one-commit scan is
precisely the state this repository was in. The assertions below are therefore
about the INVOCATION, and the `fetch-depth: 0` assertion is kept only as the
necessary precondition it actually is.

Measured on a throwaway clone of this repository at `main`: a random,
real-shaped AWS key planted in one commit and removed in the next left
`gitleaks git . --log-opts=-1` exiting 0 while `gitleaks git .` exited non-zero.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"

#: Four conformance checks elsewhere in this portfolio passed because they
#: matched a tool name inside a COMMENT. The comment above the scan step names
#: both the action that was removed and the flag that must not return, so every
#: assertion here reads the workflow with its comments stripped and cannot be
#: satisfied by prose.
_COMMENT = re.compile(r"(?m)^\s*#.*$|\s+#.*$")


def _ci_code() -> str:
    return _COMMENT.sub("", CI.read_text(encoding="utf-8"))


def _secret_scan_job() -> str:
    """The `secret-scan:` job block only, comments stripped.

    Other jobs in this workflow set `fetch-depth: 0` for their own reasons, so
    the precondition assertion below would keep passing on their behalf if it
    read the whole file.
    """
    code = _ci_code()
    opening = re.search(r"^  secret-scan:$", code, flags=re.MULTILINE)
    assert opening is not None, "no `secret-scan:` job in ci.yml -- it is a required check"
    rest = code[opening.start() :]
    following = re.search(r"^  \S", rest[len("  secret-scan:") :], flags=re.MULTILINE)
    if following is None:
        return rest
    return rest[: len("  secret-scan:") + following.start()]


def test_the_workflow_survives_having_its_comments_stripped() -> None:
    """A stripper that ate the file would make every assertion below vacuous."""
    code = _ci_code()
    assert "secret-scan:" in code, "no `secret-scan` job left after stripping comments"
    assert code.count("\n") > 50, "comment stripping removed most of the workflow"


def test_the_scanner_is_not_handed_a_commit_range() -> None:
    code = _ci_code()
    assert "gitleaks git . --no-banner --redact --exit-code 1" in code, (
        "the secret scan no longer runs `gitleaks git .`. Whatever replaces it has to "
        "walk every commit reachable from HEAD on every event, not a range chosen from "
        "the event that triggered the run."
    )
    assert "--log-opts" not in code, (
        "`--log-opts` scopes gitleaks to a commit range. A range picked from the "
        "triggering event degrades to `--log-opts=-1` on a single-commit push, which "
        "is every squash merge into `main` here."
    )


def test_the_event_driven_action_does_not_come_back() -> None:
    assert "gitleaks/gitleaks-action" not in _ci_code(), (
        "gitleaks/gitleaks-action derives its scan range from the event and reads "
        "exactly one commit on a single-commit push, so a required check using it "
        "reports on the tip rather than on the history."
    )


def test_the_pinned_binary_is_checksum_verified() -> None:
    """A downloaded scanner that is not verified is an unpinned dependency."""
    code = _ci_code()
    assert "gitleaks_checksums.txt" in code and "sha256sum --check --strict" in code, (
        "the gitleaks binary is fetched without checking it against the published checksums file"
    )


def test_the_checkout_still_fetches_the_history_the_scan_walks() -> None:
    """Necessary, not sufficient: without it there is no history on disk to walk.

    This assertion is deliberately not evidence that the scan reads history --
    that is what the invocation assertions above are for. It only rules out the
    other failure mode, where `gitleaks git .` faithfully walks the single
    commit `actions/checkout` was asked to fetch.
    """
    job = _secret_scan_job()
    assert re.search(r"^\s*fetch-depth:\s*0\s*$", job, flags=re.MULTILINE), (
        "`fetch-depth: 0` is gone from the secret-scan checkout, so the full-history "
        "invocation would have a single commit to walk"
    )


def test_the_job_keeps_the_name_the_ruleset_requires() -> None:
    """Renaming the job would stop the required context being reported at all."""
    assert re.search(r"^  secret-scan:$", _ci_code(), flags=re.MULTILINE), (
        "`secret-scan` is a required status check on `main`; a renamed job never "
        "reports that context and every pull request waits forever"
    )
