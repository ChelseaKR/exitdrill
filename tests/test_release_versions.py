"""The declared version, held to the releases that exist.

A version number no artifact carries is exactly what a version under
development is, and a project is entitled to one right up until a tag exists.
What both worlds require is that the repository keep saying which one it is in,
and that every restatement of the number keep agreeing.

Across this portfolio the recurring failure is the opposite, in both
directions: a version bump moves `CITATION.cff` and a `date-released` gets
invented beside it; or a tag is cut and the sentences saying none was go on
standing, because each was checked against the code and never against the
repository. Both happened here. `tests/test_packaging.py` already pins
`exitdrill.__version__` to `pyproject.toml`; these checks add the questions it
cannot answer -- has anything actually been released, does what the repository
claims about that match, and has every sentence that said nothing was been
retired -- and they answer them against git rather than against another copy of
the number.

Publication to a package registry is a separate question from tagging, and
`docs/RELEASE.md` holds the preconditions for it.

A missing tag and an unfetched tag are indistinguishable from inside a
checkout, so nothing here draws a conclusion from a checkout that would not
have shown a tag (`_why_tags_are_unreadable`). Reading an empty tag list out of
a shallow clone and calling it evidence is absence rendered as a value.
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


#: Sentences in this tree that assert, in the present tense, that nothing has
#: been tagged or released. Every one is verbatim from a file here, and every
#: one was true when it was written.
#:
#: They are matched case-insensitively as substrings, which makes this a
#: denylist, with a denylist's one guarantee: it finds a phrasing somebody has
#: already written here, and it cannot find one nobody has thought of yet. That
#: is the whole of what it claims. The structural half of the question is
#: `test_the_citation_dates_no_release_that_was_never_cut` and the two
#: directions in `test_the_declared_version_is_held_to_the_tags_that_exist`,
#: which compare values against the repository's tags and need no vocabulary at
#: all. This exists because the same fact is *also* stated in prose, in more
#: than one file, and prose is where it outlived the release.
CLAIMS_OF_NO_RELEASE: tuple[str, ...] = (
    README_SAYS_NO_TAG,
    "no tag exists",
    "nothing has been tagged",
    "nothing has been published",
    "has never been dispatched",
    "there is no GitHub Release",
    "unreleased technical alpha",
)

#: Suffixes worth reading. A binary, a lockfile or a captured fixture does not
#: carry a sentence a reader takes a fact from.
PROSE_SUFFIXES = frozenset({".md", ".cff", ".py", ".toml", ".yml", ".yaml", ".txt"})

#: `CHANGELOG.md` is exempt because its dated sections are the record of what
#: was true on the day of each release, not a claim about today. Rewriting a
#: shipped section so a past sentence reads true now would destroy the record
#: this check exists to protect. This module is exempt as a *file*, because the
#: tuple above puts every claim in it verbatim; its prose is read from
#: `__doc__` instead, which is where its own stale paragraph was.
CLAIM_SCAN_EXEMPT = frozenset({"CHANGELOG.md"})

THIS_FILE = Path(__file__).resolve()


def _tracked_prose_files() -> list[Path]:
    """Every tracked file whose text a reader could take a fact from."""
    listed = _git("ls-files", "-z")
    if listed is None:  # pragma: no cover - git unusable; the caller skips first
        return []
    paths: list[Path] = []
    for name in listed.split("\0"):
        if not name or name in CLAIM_SCAN_EXEMPT:
            continue
        path = ROOT / name
        if path.suffix in PROSE_SUFFIXES and path.is_file():
            paths.append(path)
    return paths


def _claims_in(text: str) -> list[str]:
    lowered = text.lower()
    return [claim for claim in CLAIMS_OF_NO_RELEASE if claim.lower() in lowered]


def test_the_claim_vocabulary_is_real_and_not_self_matching() -> None:
    """The floor under the scan below, and the reason it may read `__doc__`.

    Two ways the next check could pass while examining nothing: an empty claim
    list, and a claim list nothing here has ever said. The README's own
    sentence is in it by construction, so at least one entry is a sentence this
    project really wrote; and none of them is in this module's docstring, which
    is what makes reading `__doc__` for this one file a measurement rather than
    a way of exempting it.
    """
    assert CLAIMS_OF_NO_RELEASE, "an empty claim list scans every file and finds nothing"
    assert README_SAYS_NO_TAG in CLAIMS_OF_NO_RELEASE, (
        "the vocabulary does not cover the one sentence this repository already pins "
        "in both directions, so it is not a generalisation of anything"
    )
    assert not _claims_in(__doc__ or ""), (
        "this module's docstring states, in the present tense, that nothing has been "
        "tagged or released. That was true until v0.1.0. Describe the rule, not the day."
    )


def test_no_document_says_this_repository_is_untagged_once_it_is() -> None:
    """A sentence saying nothing was ever released has to go when something is.

    `README_SAYS_NO_TAG` is pinned in both directions -- required while no tag
    exists, refused once one does -- and it was pinned *in one file*. The same
    fact was also stated in `docs/ROADMAP.md`'s milestone table and in this
    module's own docstring. Cutting v0.1.0 made both false and nothing said so,
    because each had been checked against the code and never against the
    repository.

    This is the same two-directional rule applied to every tracked file. The
    other direction -- that something must say so while no tag exists -- is
    `test_the_declared_version_is_held_to_the_tags_that_exist`, which is why
    this half only runs once a tag exists.
    """
    tags = _require_readable_tags()
    scanned = _tracked_prose_files()
    assert len(scanned) > 20, (
        f"only {len(scanned)} file(s) to read: this scan has stopped finding the tree, "
        f"and a scan that reads nothing reports the same clean result as one that read "
        f"everything"
    )
    if not tags:
        return

    stale: list[str] = []
    for path in scanned:
        text = (__doc__ or "") if path.resolve() == THIS_FILE else path.read_text(encoding="utf-8")
        for claim in _claims_in(text):
            stale.append(f"{path.relative_to(ROOT)}: {claim!r}")

    assert not stale, (
        f"{tags[0]} exists, and these still say nothing has ever been released: "
        f"{'; '.join(stale)}. Tags carried: {', '.join(tags)}. Either the sentence is "
        f"stale or the tag should not be there."
    )


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
