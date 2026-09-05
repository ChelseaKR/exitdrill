"""Bind what the repository exposes to what its committed documents describe.

`exitdrill validate-exercise` shipped with its own module, a committed example
plan, an accepted ADR, and the first step of `make demo`, and for all of that
time appeared in no committed document (issue #98). Someone running the
documented demo saw it execute, got `synthetic_protocol_valid` back, and had
nowhere to read what it had validated. Nothing noticed, because whether a
subcommand is described anywhere had never been something a gate was asked.

That is Track A5 in `docs/ROADMAP.md`: the published claims and the enforced
gates have to stay in step, and the way to keep them there is to make the gate
enumerate rather than restate. Both checks below ask the source what exists --
argparse for the subcommands, the decisions directory for the ADRs -- so
something added tomorrow is covered without anyone remembering to add a case
here.
"""

from __future__ import annotations

import re
import subprocess
from argparse import _SubParsersAction
from pathlib import Path
from shutil import which

from exitdrill.cli import _parser

PROJECT = Path(__file__).parents[1]


def test_adr_compatibility_index_covers_every_accepted_decision() -> None:
    index = (PROJECT / "docs/adr/0000-record-architecture-decisions.md").read_text(encoding="utf-8")
    decisions = sorted((PROJECT / "docs/decisions").glob("[0-9][0-9][0-9][0-9]-*.md"))

    assert decisions
    for decision in decisions:
        assert f"../decisions/{decision.name}" in index


def _subcommands() -> tuple[str, ...]:
    """Ask the parser what the CLI exposes rather than restating a list here."""
    for action in _parser()._actions:
        if isinstance(action, _SubParsersAction):
            names = tuple(str(name) for name in action.choices)
            assert names, "the CLI parser exposes no subcommands"
            return names
    raise AssertionError("the CLI parser no longer exposes a subparser action")


def _committed_documents() -> tuple[Path, ...]:
    """Every committed Markdown file, from tracking status rather than a directory.

    `git ls-files` is the same source of truth `make lint-lab` uses to
    enumerate the browser-lab scripts. It matters that this is tracking status
    and not a tree walk: an uncommitted scratch file describing a command would
    otherwise satisfy a check about what the repository publishes.
    """
    git = which("git")
    assert git is not None, "git is required to enumerate the committed documents"
    completed = subprocess.run(  # noqa: S603 - resolved interpreter and fixed arguments
        [git, "ls-files", "*.md"],
        cwd=PROJECT,
        check=True,
        capture_output=True,
        text=True,
    )
    documents = tuple(sorted(PROJECT / line for line in completed.stdout.splitlines() if line))
    assert documents, "no committed Markdown documents were found"
    return documents


def _describes(text: str, command: str) -> bool:
    """Whether a document names this subcommand in a form a reader can act on.

    Two accepted forms: the full invocation `exitdrill <name>`, and the bare
    name in code formatting. Both are followed by a boundary that is neither a
    word character nor a hyphen, so `exitdrill validate-exercise` does not also
    satisfy `validate` -- without that, deleting the one documented invocation
    of a command could leave a longer command's name standing in for it.

    What this cannot check is whether the description is any good. It is a
    presence check, and a subcommand named once in passing satisfies it. The
    prose around each command is the maintainer's to judge; this only stops one
    from being published with no prose at all.
    """
    pattern = rf"(?:exitdrill {re.escape(command)}|`{re.escape(command)}`)(?![\w-])"
    return re.search(pattern, text) is not None


def test_every_cli_subcommand_is_described_in_a_committed_document() -> None:
    documents = _committed_documents()
    corpus = {path: path.read_text(encoding="utf-8") for path in documents}

    undocumented = [
        command
        for command in _subcommands()
        if not any(_describes(text, command) for text in corpus.values())
    ]

    assert not undocumented, (
        f"these subcommands appear in no committed document: {undocumented}; "
        "a command that runs in the documented demo and is named nowhere is the "
        "defect issue #98 recorded"
    )


def test_the_subcommand_binding_rejects_a_name_no_document_carries() -> None:
    """Guards against a matcher that passed for any input.

    The first case runs against the real corpus, so it differs from the check
    above only in the name it asks about. The second pins the boundary that
    stops a longer command's name from standing in for a shorter one, which is
    the one way this check could pass while a command went undescribed.
    """
    corpus = [path.read_text(encoding="utf-8") for path in _committed_documents()]

    assert not any(_describes(text, "validate-invented") for text in corpus)
    assert not _describes("exitdrill validate-exercise plan.json", "validate")
    assert _describes("exitdrill validate baseline.json export.json", "validate")
    assert _describes("`validate-exercise` is the command", "validate-exercise")
