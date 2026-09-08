"""The release's cheap gates, held to running first and to being runnable.

`release.yml` refuses to build a candidate whose tag does not match the package
version, and refuses to publish one with no `## [<version>]` section in
`CHANGELOG.md`. Both are file reads. Between them sat `uv sync --locked`, `make
verify`, both declared demos and the wheel build, and the notes gate came
*after* all of it.

That ordering is a real cost — until `v0.1.0` was cut the changelog carried no
dated section at all, so the very first dispatch of `release.yml` would have
spent the entire build job and then failed on a missing heading — but the ordering is the smaller half. The larger half is that
a gate written as inline shell inside a workflow can be executed in exactly one
place: a dispatched release run. The maintainer about to cut the tag cannot run
it, no test can exercise it, and its first execution is the occasion where
being wrong is most expensive.

`scripts/check_release_preflight.py` is that gate somewhere it can be run.
These checks hold three things:

* it runs before anything expensive, in the workflow, by step order;
* the workflow and `make release-preflight` call the same script, so the check
  cannot drift back into YAML that nothing can execute;
* release notes for the next tag are staged *now*, not discovered missing at
  tag time — the one assertion in `tests/test_release_versions.py` that
  `CHANGELOG.md` carries the section is guarded by `if not tags: ... return`
  and so cannot fire until a tag exists, which is after it could have helped.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = PROJECT / ".github" / "workflows" / "release.yml"
MAKEFILE = PROJECT / "Makefile"
RELEASE_DOC = PROJECT / "docs" / "RELEASE.md"
CHANGELOG = PROJECT / "CHANGELOG.md"
README = PROJECT / "README.md"
PREFLIGHT = PROJECT / "scripts" / "check_release_preflight.py"

#: The step name that has to come first, and the command that has to come
#: after it. Matched against the workflow text rather than restated from it.
PREFLIGHT_STEP = "Refuse the release before anything expensive runs"
EXPENSIVE_COMMAND = "make verify"


def _declared_version() -> str:
    """The version `pyproject.toml` declares, read here rather than imported.

    The script is exercised as a subprocess throughout — that is what the
    workflow runs, and importing it instead would stop proving the exit codes
    and messages the workflow reads.
    """
    manifest = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    version = manifest["project"]["version"]
    assert isinstance(version, str)
    return version


def _section(changelog: str, version: str) -> list[str] | None:
    """The `## [<version>]` section of a changelog, heading included.

    A restatement, deliberately: it lets a test say what it expects the script
    to have extracted without importing the script's own implementation of the
    question. Every use is cross-checked against the file the script wrote.
    """
    lines = changelog.splitlines()
    opening = f"## [{version}]"
    try:
        start = next(index for index, line in enumerate(lines) if line.startswith(opening))
    except StopIteration:
        return None
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith("## [")),
        len(lines),
    )
    return lines[start:end]


def _run(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the preflight as the workflow runs it: a real subprocess."""
    return subprocess.run(  # noqa: S603 - fixed argv, interpreter from sys.executable
        [sys.executable, str(PREFLIGHT), *arguments],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=os.environ,
        check=False,
    )


def _runs(body: str, command: str) -> bool:
    """Does this step actually run the command, rather than mention it?

    `tests/test_release_versions.py._runs` learned this the hard way: a job that
    only named a gate in a comment explaining itself was pulled into a check's
    scope by a raw text match. This file reproduced the same fault on its first
    run — the comment introducing the preflight step names `make verify`, and
    an unindented comment block belongs to the step above it, so `setup-uv`
    read as a step that runs the build.
    """
    return any(command in line for line in body.splitlines() if not line.lstrip().startswith("#"))


def _release_build_steps() -> list[tuple[str, str]]:
    """The release workflow's build-job steps in order, each as (label, body).

    No YAML parser is a dependency here, and `tests/test_release_versions.py`
    already splits workflows by indentation for the same reason. A step's label
    is its `name:` where it has one and its `uses:` reference otherwise, so
    nothing is silently dropped from the ordering.
    """
    lines = RELEASE_WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.rstrip() == "  build:")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[index])
        ),
        len(lines),
    )
    boundaries = [index for index in range(start, end) if lines[index].startswith("      - ")]
    steps: list[tuple[str, str]] = []
    for position, first in enumerate(boundaries):
        last = boundaries[position + 1] if position + 1 < len(boundaries) else end
        body = "\n".join(lines[first:last])
        label = next(
            (
                matched.group(1).strip()
                for matched in (re.match(r"^      - (?:name|uses): (.+)$", lines[first]),)
                if matched is not None
            ),
            lines[first].strip(),
        )
        steps.append((label, body))
    return steps


# ---------------------------------------------------------------------------
# The ordering, and where the gate lives.
# ---------------------------------------------------------------------------


def test_the_cheap_gates_run_before_the_expensive_build() -> None:
    """A release with no notes must not cost a full verify-and-build first.

    This is the check that would have caught the original ordering. It reads
    step order out of the workflow, so moving the preflight back after the
    build — or deleting it — fails here rather than at tag time.
    """
    steps = _release_build_steps()
    labels = [label for label, _ in steps]
    assert PREFLIGHT_STEP in labels, (
        f"release.yml's build job has no {PREFLIGHT_STEP!r} step; its steps are {labels}"
    )

    building = [
        label for label, body in steps if _runs(body, EXPENSIVE_COMMAND) and label != PREFLIGHT_STEP
    ]
    assert building, f"release.yml's build job runs no step containing {EXPENSIVE_COMMAND!r}"

    preflight_at = labels.index(PREFLIGHT_STEP)
    for label in building:
        assert preflight_at < labels.index(label), (
            f"release.yml runs {label!r} before {PREFLIGHT_STEP!r}, so a release with no "
            "CHANGELOG section burns the whole build before the gate that would refuse it"
        )


def test_the_workflow_runs_the_preflight_a_maintainer_can_also_run() -> None:
    """The gate has to be a script, not shell only a dispatched run can execute.

    A check that exists solely inside workflow YAML is unrunnable by the person
    about to tag and untestable by anything. Both call sites are pinned to the
    same script so the two cannot drift apart.
    """
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    makefile = MAKEFILE.read_text(encoding="utf-8")
    relative = "scripts/check_release_preflight.py"

    assert relative in workflow, f"release.yml no longer runs {relative}"
    assert relative in makefile, f"the Makefile no longer runs {relative}"
    assert re.search(r"^release-preflight:$", makefile, re.MULTILINE), (
        "the Makefile has no `release-preflight` target, so the gate is CI-only again"
    )


def test_the_release_document_describes_the_workflow_that_exists() -> None:
    """`docs/RELEASE.md` said two things about `release.yml` that were not true.

    It said "a `v*` tag builds and uploads a release candidate", and no
    workflow in this repository has a tag trigger at all — the release is
    dispatch-only. It also said "the candidate workflow intentionally has no
    publish permission", and the publish job holds `contents: write` and calls
    `gh release create`. Both understated nothing and overstated one thing that
    matters: a reader was told the release path could not publish, and it can.

    Each claim is now read back out of the workflow rather than restated.
    """
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    document = " ".join(RELEASE_DOC.read_text(encoding="utf-8").split())

    triggers = re.search(r"^on:\n((?:  .*\n|\n)*)", workflow, re.MULTILINE)
    assert triggers is not None, "release.yml declares no `on:` block"
    assert "workflow_dispatch" in triggers.group(1)
    assert "tags:" not in triggers.group(1), (
        "release.yml now has a tag trigger, and docs/RELEASE.md says pushing a tag builds nothing"
    )
    assert "workflow_dispatch" in document, (
        "docs/RELEASE.md no longer says the release workflow is dispatch-only"
    )

    publishing = workflow.split("  publish:", 1)
    assert len(publishing) == 2, "release.yml has no publish job"
    assert "contents: write" in publishing[1], (
        "the publish job no longer holds `contents: write`, and docs/RELEASE.md says it does"
    )
    assert "gh release create" in publishing[1]
    assert "contents: write" in document and "GitHub Release" in document, (
        "docs/RELEASE.md no longer discloses that the publish job can create a release"
    )


def test_the_workflow_keeps_no_second_copy_of_the_extraction() -> None:
    """Two implementations of one gate is one implementation nothing tests.

    The section extraction used to be inline `awk`. If it comes back, the
    script and the workflow can disagree and only the workflow's answer counts.
    """
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "awk" not in workflow, (
        "release.yml extracts the changelog section itself again; the script is the gate"
    )
    assert "tomllib" not in workflow, (
        "release.yml reads the package version itself again; the script is the gate"
    )


# ---------------------------------------------------------------------------
# What the script decides.
# ---------------------------------------------------------------------------


def _repo(tmp_path: Path, *, version: str, changelog: str) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{version}"\n', encoding="utf-8"
    )
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return root


READY = "# Changelog\n\n## [0.1.0] - 2026-09-07\n\n### Added\n\n- The first thing.\n"


def test_a_section_with_content_passes_and_writes_the_notes(tmp_path: Path) -> None:
    root = _repo(tmp_path, version="0.1.0", changelog=READY)
    out = tmp_path / "release-notes.md"

    done = _run("--root", str(root), "--tag", "v0.1.0", "--out", str(out))

    assert done.returncode == 0, done.stderr
    assert out.read_text(encoding="utf-8") == (
        "## [0.1.0] - 2026-09-07\n\n### Added\n\n- The first thing.\n"
    )


def test_a_missing_section_fails_and_names_the_version(tmp_path: Path) -> None:
    """The state this repository is actually in today."""
    root = _repo(
        tmp_path,
        version="0.1.0",
        changelog="# Changelog\n\n## [Unreleased]\n\n### Added\n\n- Something staged.\n",
    )

    done = _run("--root", str(root), "--tag", "v0.1.0")

    assert done.returncode == 1
    assert "no '## [0.1.0]' section" in done.stderr
    assert "rename the '## [Unreleased]' section" in done.stderr


def test_a_missing_section_with_nothing_staged_says_write_one(tmp_path: Path) -> None:
    root = _repo(tmp_path, version="0.1.0", changelog="# Changelog\n\n## [Unreleased]\n")

    done = _run("--root", str(root))

    assert done.returncode == 1
    assert "write one" in done.stderr


def test_a_heading_with_nothing_under_it_is_not_release_notes(tmp_path: Path) -> None:
    """The hole the inline `[ -s release-notes.md ]` test could not see.

    The extraction prints the heading, so an empty section produced a one-line
    file, satisfied "non-empty", and would have published a GitHub Release
    whose entire body was its own version number.
    """
    root = _repo(
        tmp_path,
        version="0.1.0",
        changelog="# Changelog\n\n## [0.1.0]\n\n## [0.0.9]\n\n- Older.\n",
    )
    out = tmp_path / "release-notes.md"

    done = _run("--root", str(root), "--out", str(out))

    assert done.returncode == 1
    assert "nothing under it" in done.stderr
    assert not out.exists(), "notes were written for a release the gate refused"


def test_a_tag_that_does_not_match_the_package_version_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, version="0.1.0", changelog=READY)

    done = _run("--root", str(root), "--tag", "v0.2.0")

    assert done.returncode == 1
    assert "v0.1.0" in done.stderr


def test_a_version_that_is_not_stable_semver_fails(tmp_path: Path) -> None:
    """`release-authorize.yml` accepts only stable SemVer; say so here, not there."""
    root = _repo(
        tmp_path,
        version="0.1.0rc1",
        changelog="# Changelog\n\n## [0.1.0rc1]\n\n- Candidate.\n",
    )

    done = _run("--root", str(root))

    assert done.returncode == 1
    assert "stable SemVer" in done.stderr


def test_an_explicit_version_overrides_the_manifest(tmp_path: Path) -> None:
    root = _repo(tmp_path, version="9.9.9", changelog=READY)

    assert _run("--root", str(root), "--version", "0.1.0").returncode == 0
    assert _run("--root", str(root)).returncode == 1


def test_an_unreadable_repository_is_reported_as_unreadable(tmp_path: Path) -> None:
    """Absent is not the same answer as failing, and must not be reported as one."""
    missing = _run("--root", str(tmp_path / "nowhere"))
    assert missing.returncode == 2
    assert "could not run" in missing.stderr

    versionless = tmp_path / "versionless"
    versionless.mkdir()
    (versionless / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    (versionless / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    assert _run("--root", str(versionless)).returncode == 2

    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "pyproject.toml").write_text("[project\n", encoding="utf-8")
    (broken / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    assert _run("--root", str(broken)).returncode == 2

    typed = tmp_path / "typed"
    typed.mkdir()
    (typed / "pyproject.toml").write_text("[project]\nversion = 1\n", encoding="utf-8")
    (typed / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    assert _run("--root", str(typed)).returncode == 2

    no_changelog = tmp_path / "no-changelog"
    no_changelog.mkdir()
    (no_changelog / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
    assert _run("--root", str(no_changelog)).returncode == 2


@pytest.mark.parametrize(
    ("changelog", "expected"),
    [
        pytest.param(
            "# Changelog\n\n## [1.0.0]\n\n- a\n\n## [0.9.0]\n\n- b\n",
            "## [1.0.0]\n\n- a\n\n",
            id="stops-at-the-next-section",
        ),
        pytest.param(
            "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n- a\n",
            "## [1.0.0] - 2026-01-01\n\n- a\n",
            id="a-dated-heading-still-matches",
        ),
        pytest.param(
            "# Changelog\n\n## [0.9.0]\n\n- b\n\n## [1.0.0]\n\n- a\n",
            "## [1.0.0]\n\n- a\n",
            id="the-last-section-runs-to-the-end",
        ),
    ],
)
def test_the_extracted_notes_are_exactly_the_versions_own_section(
    tmp_path: Path, changelog: str, expected: str
) -> None:
    root = _repo(tmp_path, version="1.0.0", changelog=changelog)
    out = tmp_path / "notes.md"

    done = _run("--root", str(root), "--out", str(out))

    assert done.returncode == 0, done.stderr
    assert out.read_text(encoding="utf-8") == expected
    assert _section(changelog, "1.0.0") == expected.splitlines()


@pytest.mark.parametrize("heading", ["## [1.0.10]", "## [1.0.0-rc1]", "## [11.0.0]"])
def test_a_heading_that_merely_starts_the_same_is_not_the_versions_section(
    tmp_path: Path, heading: str
) -> None:
    """`1.0.0` must not match `1.0.10`. The closing bracket is what stops it."""
    changelog = f"# Changelog\n\n{heading}\n\n- a\n"
    root = _repo(tmp_path, version="1.0.0", changelog=changelog)

    done = _run("--root", str(root))

    assert done.returncode == 1
    assert "no '## [1.0.0]' section" in done.stderr
    assert _section(changelog, "1.0.0") is None


# ---------------------------------------------------------------------------
# The state of this repository, measurable before a tag exists.
# ---------------------------------------------------------------------------


def test_release_notes_for_the_next_tag_are_staged_now() -> None:
    """Three states, and the third is what the tag-conditional check cannot reach.

    `tests/test_release_versions.py` asserts the `## [<version>]` section only
    inside the branch it takes when a tag already exists, so until the first tag
    it made no claim about the changelog at all. This is the question that can
    be asked before the tag: is there anything to publish?

    * released — the declared version has its own section with content;
    * staged — `## [Unreleased]` has content and the README says untagged, so
      cutting the tag is a rename;
    * neither — there are no release notes and the release job would fail.

    The third state is the failure, and it is reachable today by emptying
    `## [Unreleased]`, which nothing else here would notice.
    """
    version = _declared_version()
    changelog = CHANGELOG.read_text(encoding="utf-8")

    released = _section(changelog, version)
    if released is not None and any(line.strip() for line in released[1:]):
        return

    staged = _section(changelog, "Unreleased")
    assert staged is not None, (
        f"CHANGELOG.md has neither a '## [{version}]' section nor '## [Unreleased]', so "
        "release.yml has nothing to publish as release notes for the next tag"
    )
    assert any(line.strip() for line in staged[1:]), (
        "CHANGELOG.md's '## [Unreleased]' section is empty and there is no "
        f"'## [{version}]' section, so the next tag would have no release notes"
    )
    assert "untagged" in README.read_text(encoding="utf-8"), (
        f"the release notes for {version} are still under '## [Unreleased]', so nothing "
        "carries that version, and the README no longer says it is untagged"
    )


def test_the_preflight_agrees_with_the_repository_it_ships_in() -> None:
    """Run the real gate against the real tree and require an honest verdict.

    Exactly one of two things has to be true: the preflight passes, or it fails
    for the one documented reason a tree before its first release fails: no
    section for the declared version. Any third answer — an unreadable manifest, a non-SemVer
    version, a heading with no body — is a defect this catches at merge time.
    """
    done = _run("--root", str(PROJECT))
    version = _declared_version()

    if done.returncode == 0:
        return
    assert done.returncode == 1, f"the preflight could not read this repository: {done.stderr}"
    assert done.stderr.count("  - ") == 1, (
        f"the preflight reports more than the expected pre-first-release state: {done.stderr}"
    )
    assert f"no '## [{version}]' section" in done.stderr, done.stderr


def _job_body(workflow: str, name: str) -> str:
    """The lines of one top-level job, heading excluded.

    Written here rather than reused: the only other job reader in this file is
    specific to the build job's steps, and a release job's shape is exactly
    what these assertions are about.
    """
    lines = workflow.splitlines()
    opening = f"  {name}:"
    start = next(index for index, line in enumerate(lines) if line == opening)
    end = next(
        (index for index in range(start + 1, len(lines)) if line_is_job(lines[index])),
        len(lines),
    )
    return "\n".join(lines[start + 1 : end])


def line_is_job(line: str) -> bool:
    """A top-level job heading: exactly two spaces of indent, then `name:`."""
    return bool(re.match(r"^  [A-Za-z0-9_-]+:\s*$", line))


def test_the_publish_job_does_not_ask_git_a_question_it_cannot_answer() -> None:
    """`gh release create --verify-tag` shells out to git, and publish has no checkout.

    The publish job holds the only write authority and deliberately never
    checks out code -- that separation is the reason it is split from the
    build. `--verify-tag` makes `gh` run git to confirm the tag exists locally,
    so in a job with no working tree it dies with `fatal: not a git repository`
    *after* the artifacts have already been built.

    Not hypothetical: run 34163784808, the first release this workflow ever
    performed, failed exactly there. `authorize` and `build` both succeeded and
    publication died on the flag.

    Nothing is lost by dropping it. The two lines above the call fetch the live
    tag ref through the API and assert it equals the object SHA `authorize`
    produced *after* verifying the tag's SSH signature against the committed
    allowed-signers file. That is an identity check. `--verify-tag` is only an
    existence check, and it was being made against a repository that is not
    there.
    """
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    publish = _job_body(workflow, "publish")

    assert _runs(publish, "gh release create"), "the publish job no longer creates the release"
    assert not _runs(publish, "--verify-tag"), (
        "publish runs `gh release create --verify-tag`, which shells out to git, in a job "
        "that never checks out code. It fails with `fatal: not a git repository` after the "
        "build has already succeeded. The API recheck above it verifies tag identity, which "
        "is strictly stronger."
    )
    assert _runs(publish, "GH_REPO:"), (
        "the publish job runs `gh` without setting GH_REPO. With no checkout there is no git "
        "remote for `gh` to infer the repository from, so it shells out to git and dies with "
        "`fatal: not a git repository` -- which is what run 34164224595 did even after "
        "--verify-tag was removed. Removing the flag was necessary and not sufficient."
    )
    assert not _runs(publish, "actions/checkout"), (
        "the publish job now checks out code. It holds the only `contents: write` authority, "
        "and keeping a working tree out of it is why --verify-tag was removed rather than "
        "satisfied."
    )
