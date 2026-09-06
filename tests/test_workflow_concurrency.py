"""Every commit pushed to a branch must be able to get its own CI verdict.

A workflow that runs on a push to a branch and keys its ``concurrency:`` group on
the ref alone gives every commit on that branch ONE shared slot. GitHub allows one
running plus one pending run per group, so with ``cancel-in-progress: true`` the
second push cancels the run the first commit was still executing, and with
``false`` a third push evicts the second from the pending slot.

Either way the commit lands with no verdict at all, and it is reported as
``cancelled`` or is simply absent -- never as red -- so nothing surfaces it.
Measured elsewhere in this portfolio on 2026-09-06: three consecutive pushes to
one repository's ``main`` each cancelled the previous commit's gate run.

The rule enforced here: if a workflow runs on a push to a BRANCH and declares a
workflow-level concurrency group, that group must vary per commit -- it must
reference ``github.sha`` or ``github.run_id``. Pull-request runs may keep a per-PR
group and cancel superseded commits: a superseded PR commit really is stale, a
merged branch commit never is.

Two things are deliberately NOT this defect:

* a JOB-level ``concurrency:`` block. Serialising a single job -- a Pages deploy,
  say -- is correct. Only the column-zero, workflow-level block is examined.
* a ``push:`` trigger restricted to tags. Every tag is a unique ref, so a ref-only
  key already gives each release its own slot.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

#: Converging workflows describe a property of the REPOSITORY rather than of one
#: commit, so successive runs are meant to collapse onto a single slot and only
#: the newest answer is worth having. Exempting them is a judgement, not an
#: oversight, and each entry has to earn its place -- which is what
#: ``test_converging_exemptions_stay_narrow`` below is for.
CONVERGING_WORKFLOWS: dict[str, str] = {
    "scorecard.yml": "OpenSSF Scorecard grades the repository, not the commit",
    "openssf-scorecard.yml": "same, under the other name the action ships with",
    "pages.yml": (
        "publishes the repository's current state to GitHub Pages; two commits "
        "cannot be live at once, so the newest deploy is the only one worth having"
    ),
}

_PER_COMMIT = re.compile(r"github\.sha|github\.run_id")


def _top_level_block(source: str, key: str) -> str | None:
    """Return the column-zero ``key:`` block, or None if the file has no such key.

    The block runs from its own key line to the next line starting in column zero,
    so an indented job-level block can never be returned in place of the
    workflow-level one.
    """
    opening = re.search(rf"^(?:{key}|'{key}'|\"{key}\"):", source, re.MULTILINE)
    if opening is None:
        return None
    rest = source[opening.start() :]
    newline = rest.find("\n")
    if newline < 0:
        return rest
    following = re.search(r"^\S", rest[newline + 1 :], re.MULTILINE)
    if following is None:
        return rest
    return rest[: newline + 1 + following.start()]


def _workflow_files() -> list[Path]:
    return sorted(p for p in WORKFLOWS.iterdir() if p.suffix in {".yml", ".yaml"})


def _pushes_to_a_branch(triggers: str) -> bool:
    """True when this ``on:`` block fires on a push to a branch (not only tags)."""
    inline = re.match(r"^(?:on|'on'|\"on\"):[ \t]*\[([^\]]*)\]", triggers)
    if inline is not None:
        return "push" in [item.strip() for item in inline.group(1).split(",")]
    push = re.search(r"^ {2}push:[^\n]*\n((?: {3,}[^\n]*\n|\n)*)", triggers, re.MULTILINE)
    if push is None:
        return False
    body = push.group(1)
    tags = re.search(r"^ {3,}tags(?:-ignore)?:", body, re.MULTILINE) is not None
    branches = re.search(r"^ {3,}branches(?:-ignore)?:", body, re.MULTILINE) is not None
    return branches or not tags


def _branch_push_workflows() -> Iterator[tuple[Path, str]]:
    for path in _workflow_files():
        source = path.read_text(encoding="utf-8")
        triggers = _top_level_block(source, "on")
        if triggers is None or not _pushes_to_a_branch(triggers):
            continue
        yield path, source


def test_workflow_directory_is_populated() -> None:
    """A gate that examines nothing passes everything."""
    assert _workflow_files(), f"no workflow files under {WORKFLOWS} -- this gate would be vacuous"


def test_every_workflow_declares_a_trigger_block() -> None:
    """If the block parser regresses, every file falls through and the gate below is vacuous."""
    missing = [
        path.name
        for path in _workflow_files()
        if _top_level_block(path.read_text(encoding="utf-8"), "on") is None
    ]
    assert missing == [], (
        f"no top-level trigger block parsed from: {missing} -- the parser is broken"
    )


def test_at_least_one_workflow_runs_on_a_push_to_a_branch() -> None:
    """The per-commit rule below proves nothing if it matches no workflow at all."""
    assert list(_branch_push_workflows()), "no workflow runs on a push to a branch"


def test_converging_exemptions_stay_narrow() -> None:
    """Widening the exemption must take editing this list, not just adding a name.

    An exemption is how a real defect gets waved through later: name the offending
    workflow here and the check below stops seeing it. Pinning the set means that
    silencing a workflow is a visible, reviewable diff with a reason attached.
    """
    assert set(CONVERGING_WORKFLOWS) == {
        "scorecard.yml",
        "openssf-scorecard.yml",
        "pages.yml",
    }
    assert all(reason for reason in CONVERGING_WORKFLOWS.values())


def test_branch_push_concurrency_groups_vary_per_commit() -> None:
    offenders: list[str] = []
    for path, source in _branch_push_workflows():
        concurrency = _top_level_block(source, "concurrency")
        # No workflow-level group at all is not this defect: there is no shared
        # slot for a later push to evict an earlier commit from.
        if concurrency is None:
            continue
        group = re.search(r"^ {2}group:[ \t]*(.+?)[ \t]*$", concurrency, re.MULTILINE)
        assert group is not None, f"{path.name}: workflow-level concurrency block declares no group"
        if _PER_COMMIT.search(group.group(1)) or path.name in CONVERGING_WORKFLOWS:
            continue
        offenders.append(f"{path.name}: {group.group(1)}")

    assert offenders == [], (
        "these workflows give every commit on a branch one shared CI slot, so a later "
        "push cancels or evicts an earlier commit's run and that commit gets no verdict: "
        f"{offenders}. Append a per-commit discriminator to the group, e.g. "
        "group: <name>-${{ github.event_name == 'pull_request' && 'pr' || github.sha }}, "
        "and leave cancel-in-progress as it was."
    )
