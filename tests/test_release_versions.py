"""The declared version, held to the releases that exist.

`pyproject.toml` declares `0.1.0`. `git tag -l` prints nothing: nothing has been
tagged, `release.yml` has never been dispatched, and there is no GitHub Release
and no registry publication. That is the intended state — `docs/RELEASE.md`
opens with "ExitDrill is an unreleased technical alpha" and lists eight things
that have to exist before publication — and a version number no artifact
carries is exactly what a version under development is.

What that state requires is that the repository keep saying so, and that every
restatement of the number keep agreeing. Across this portfolio the recurring
failure is the opposite: a version bump moves `CITATION.cff` and a
`date-released` gets invented beside it, or a README goes on describing a
release that was never cut. `tests/test_packaging.py` already pins
`exitdrill.__version__` to `pyproject.toml`. These checks add the two questions
it cannot answer — has anything actually been released, and does what the
repository claims about that match — and they answer them against git rather
than against another copy of the number.

A missing tag and an unfetched tag are indistinguishable from inside a
checkout, so nothing here concludes "no tag exists" from a checkout that would
not have shown one (`_why_tags_are_unreadable`). Reading an empty tag list out
of a shallow clone and calling it evidence is absence rendered as a value.
`test_ci_fetches_the_tags_these_checks_read` is the other half: without it these
checks would skip in the run that gates a merge, which is the shape issue #89
already had to close once.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

import exitdrill

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CITATION = ROOT / "CITATION.cff"
CHANGELOG = ROOT / "CHANGELOG.md"
README = ROOT / "README.md"
RELEASE_DOC = ROOT / "docs" / "RELEASE.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

#: The top-level ``version:`` and ``date-released:`` of the citation file,
#: matched line by line rather than parsed: no YAML parser is a dependency
#: here, and each field is one line.
CITATION_VERSION = re.compile(r'^version:\s*"?([^"\s#]+)"?\s*$', re.MULTILINE)
CITATION_DATE = re.compile(r'^date-released:\s*"?(\d{4}-\d{2}-\d{2})"?\s*$', re.MULTILINE)

#: A release tag, with or without the ``v``. Anything else under ``refs/tags``
#: is not a release and is not counted as one.
RELEASE_TAG = re.compile(r"^v?(\d+\.\d+\.\d+(?:[-+.].+)?)$")

#: The one line under the title that a reader takes the project's state from.
README_STATUS = re.compile(r"^\*\*Status:\*\*(.*)$", re.MULTILINE)

#: What the README says about tags today. Pinned so that cutting one makes this
#: sentence false loudly rather than quietly.
README_SAYS_NO_TAG = "No tag or release exists yet"


def _manifest_version() -> str:
    manifest = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = manifest["project"]["version"]
    assert isinstance(version, str)
    return version


def _git(*args: str) -> str | None:
    """Run git in the checkout. ``None`` means the answer is unavailable."""
    executable = shutil.which("git")
    if executable is None:
        return None
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, resolved path, no shell
            [executable, "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError:  # pragma: no cover - git present but unusable
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def _why_tags_are_unreadable() -> str | None:
    """Why an empty tag list here would prove nothing, or ``None`` if it proves something."""
    if not (ROOT / ".git").exists():
        return f"no .git in {ROOT}: an installed tree carries no tags to read"
    if shutil.which("git") is None:
        return "no git executable on PATH"
    if _git("rev-parse", "--is-inside-work-tree") != "true":
        return "not a git work tree"
    if _git("rev-parse", "--is-shallow-repository") == "true":
        return "shallow checkout: tags are not fetched, so an empty tag list is not evidence"
    if (_git("config", "--get", "remote.origin.tagOpt") or "") == "--no-tags":
        return "clone configured with tagOpt=--no-tags, so tags were never fetched"
    return None


def _release_tags() -> list[str]:
    """Release tags, newest first."""
    listed = _git("tag", "--list", "--sort=-v:refname") or ""
    return [tag for tag in listed.splitlines() if RELEASE_TAG.match(tag.strip())]


def _tag_version(tag: str) -> str:
    matched = RELEASE_TAG.match(tag)
    assert matched is not None, tag
    return matched.group(1)


def _require_readable_tags() -> list[str]:
    reason = _why_tags_are_unreadable()
    if reason is not None:
        pytest.skip(f"cannot measure the repository's tags: {reason}")
    return _release_tags()


def test_the_declared_version_is_held_to_the_tags_that_exist() -> None:
    """No tag is a legitimate state here. Not saying so is not.

    Nothing demands a tag: `docs/RELEASE.md` lists eight preconditions for
    publication and most are open. What is demanded is that the repository say
    which state it is in, in the README, where somebody deciding whether to
    install this will read it.
    """
    tags = _require_readable_tags()
    declared = _manifest_version()
    readme = README.read_text(encoding="utf-8")

    if not tags:
        assert README_SAYS_NO_TAG in readme, (
            f"pyproject.toml declares {declared} and no tag exists, so no artifact carries "
            f"that version, and README.md no longer says so ({README_SAYS_NO_TAG!r} is "
            "gone). A reader is left to assume a release."
        )
        assert "unreleased technical alpha" in RELEASE_DOC.read_text(encoding="utf-8")
        return

    newest = tags[0]
    assert README_SAYS_NO_TAG not in readme, (
        f"README.md still says {README_SAYS_NO_TAG!r}, and {newest} exists"
    )
    assert declared in {_tag_version(tag) for tag in tags}, (
        f"pyproject.toml declares {declared} and no tag carries it. Newest tag: {newest}. "
        f"Tags: {', '.join(tags)}. Either the declared version is unreleased and the "
        "README has to say so, or the tag is missing."
    )
    heading = f"## [{declared}]"
    assert heading in CHANGELOG.read_text(encoding="utf-8"), (
        f"{newest} exists and CHANGELOG.md has no {heading!r} section. "
        "release.yml refuses to build without it."
    )


def test_the_status_line_names_the_version_and_says_it_is_untagged() -> None:
    """The version is otherwise stated nowhere a reader of the README would find it.

    Before this, `pyproject.toml`, `exitdrill.__version__` and `CITATION.cff`
    were the only places the number appeared, and none of them is on the page
    somebody reads to decide what this is.
    """
    tags = _require_readable_tags()
    declared = _manifest_version()

    status_match = README_STATUS.search(README.read_text(encoding="utf-8"))
    assert status_match is not None, "README.md has no `**Status:**` line"
    status = " ".join(status_match.group(1).split())

    assert declared in status, (
        f"pyproject.toml declares {declared} and the README's Status line does not name it: "
        f"{status!r}. Newest tag: {tags[0] if tags else 'none'}."
    )
    if not tags:
        assert "untagged" in status, (
            f"no tag exists, so nothing carries {declared}, and the README's Status line "
            f"does not say it is untagged: {status!r}"
        )
    else:
        assert "untagged" not in status, (
            f"the README's Status line still says untagged, and {tags[0]} exists"
        )


def test_every_restatement_of_the_version_agrees_with_the_manifest() -> None:
    """One source of truth, and the copies of it checked rather than trusted.

    `tests/test_packaging.py` pins `exitdrill.__version__`; this adds the
    citation file, which nothing held to anything.
    """
    declared = _manifest_version()
    assert exitdrill.__version__ == declared

    cited = CITATION_VERSION.findall(CITATION.read_text(encoding="utf-8"))
    assert cited == [declared], f"CITATION.cff states version {cited}, pyproject.toml {declared}"


def test_the_citation_dates_no_release_that_was_never_cut() -> None:
    """`date-released` is read by GitHub's citation panel and by Zenodo, not by a reader.

    It is absent today and has to stay absent while no tag exists. Elsewhere in
    this portfolio the same field was moved by a version bump and a date was
    invented to sit beside it, which is what this forecloses.
    """
    tags = _require_readable_tags()
    dated = CITATION_DATE.findall(CITATION.read_text(encoding="utf-8"))
    if not tags:
        assert not dated, (
            f"CITATION.cff carries date-released {dated[0]!r} and no tag exists in this "
            "repository, so it dates a release that was never cut"
        )
        return
    assert dated, f"CITATION.cff carries no date-released and {tags[0]} exists"


def _jobs(workflow: str) -> dict[str, str]:
    """Split a workflow into its jobs. No YAML parser is a dependency here."""
    lines = workflow.splitlines()
    try:
        first = next(i for i, line in enumerate(lines) if line.rstrip() == "jobs:")
    except StopIteration:  # pragma: no cover - a workflow with no jobs
        return {}
    starts = [
        (index, matched.group(1))
        for index in range(first + 1, len(lines))
        if (matched := re.match(r"^  ([A-Za-z0-9_-]+):\s*$", lines[index])) is not None
    ]
    bounds = [*[index for index, _ in starts], len(lines)]
    return {name: "\n".join(lines[bounds[n] : bounds[n + 1]]) for n, (_, name) in enumerate(starts)}


def _runs(body: str, command: str) -> bool:
    """Does this job actually run the command, rather than mention it?

    Comments are prose. A job that only named the gate in a comment explaining
    itself was pulled into this check's scope by a raw text match.
    """
    lines = body.splitlines()
    return any(command in line for line in lines if not line.lstrip().startswith("#"))


def test_ci_fetches_the_tags_these_checks_read() -> None:
    """Otherwise the tag checks skip in CI and gate nothing.

    `actions/checkout` fetches one commit and no tags by default, which is the
    shape `_why_tags_are_unreadable` refuses to draw a conclusion from. The job
    that runs `make verify` has to ask for the tags.
    """
    jobs = _jobs(CI_WORKFLOW.read_text(encoding="utf-8"))
    running = {name: body for name, body in jobs.items() if _runs(body, "make verify")}
    assert running, ".github/workflows/ci.yml has no job that runs `make verify`"
    for name, body in running.items():
        assert "actions/checkout" in body, f"job {name!r} runs make verify without a checkout"
        assert "fetch-depth: 0" in body, (
            f"job {name!r} checks out shallow, so tests/test_release_versions.py skips there"
        )
        assert "fetch-tags: true" in body, (
            f"job {name!r} does not fetch tags, so tests/test_release_versions.py skips there"
        )
