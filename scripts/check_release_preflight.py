"""Every precondition `release.yml` refuses to build without, runnable now.

Two of the release job's gates are cheap and one is not. Checking that the
dispatched tag matches the package version costs a file read; extracting the
release notes for that version out of `CHANGELOG.md` costs another. Running
`uv sync --locked`, `make verify`, both declared demos and the wheel build
costs the better part of half an hour on a runner.

Those two cheap gates used to run last, after the expensive one, written as
inline shell inside the workflow. That has two consequences and both are real.
The first is that a release with no `## [<version>]` section burns the entire
verify-and-build job before saying so. The second is worse: a gate that exists
only inside a workflow's YAML cannot be run by the maintainer who is about to
cut the tag, cannot be unit-tested, and is therefore first executed on the one
occasion when it is most expensive to be wrong. `CHANGELOG.md` has held only
`## [Unreleased]` for the life of this repository, so the first dispatch of
`release.yml` would have failed exactly this way.

This script is that gate, moved somewhere it can be executed. `release.yml`
calls it before it syncs anything, and `make release-preflight` calls it from a
laptop. `tests/test_release_preflight.py` binds the two together so the check
cannot drift back into YAML.

It also closes a hole the inline version had. The shell test was `[ -s
release-notes.md ]` — is the extracted file non-empty — and the extraction
prints the heading line. A `## [0.1.0]` heading with nothing under it therefore
produced a one-line file, passed, and published a GitHub Release whose entire
body was its own version number. An empty section is not release notes; it is
the absence of release notes rendered as a value. Here a section has to carry
at least one non-blank line that is not its own heading.

Failures are reported together rather than one per run, because the maintainer
running this wants the whole list before she tags, not the first item of it.

Exit codes: 0 every precondition holds; 1 one or more do not; 2 the repository
could not be read at all.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: A stable SemVer release version. `release-authorize.yml` requires the tag to
#: be stable SemVer, so a prerelease or build-metadata version cannot be
#: released and is rejected here rather than at the end of the job.
STABLE_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

#: Any Keep a Changelog level-two section heading, e.g. `## [0.1.0] - 2026-09-07`
#: or `## [Unreleased]`. Used to find where the version's section ends.
SECTION_HEADING = re.compile(r"^## \[")


class PreflightError(Exception):
    """The repository could not be read well enough to answer the question."""


def package_version(pyproject: Path) -> str:
    """The version `pyproject.toml` declares, which is the one being released."""
    try:
        manifest = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except OSError as error:
        raise PreflightError(f"cannot read {pyproject}: {error}") from error
    except tomllib.TOMLDecodeError as error:
        raise PreflightError(f"{pyproject} is not valid TOML: {error}") from error
    try:
        version = manifest["project"]["version"]
    except (KeyError, TypeError) as error:
        raise PreflightError(f"{pyproject} declares no [project] version") from error
    if not isinstance(version, str):
        raise PreflightError(f"{pyproject} declares a non-string version: {version!r}")
    return version


def extract_section(changelog: str, version: str) -> list[str] | None:
    """The `## [<version>]` section of a changelog, heading included.

    ``None`` means there is no such section. A list means there is one, and its
    first element is the heading; a section with nothing under its heading is a
    one-element list, which is what the caller has to reject.
    """
    lines = changelog.splitlines()
    opening = f"## [{version}]"
    try:
        start = next(index for index, line in enumerate(lines) if line.startswith(opening))
    except StopIteration:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if SECTION_HEADING.match(lines[index]):
            end = index
            break
    return lines[start:end]


def _has_body(section: Sequence[str]) -> bool:
    """Does the section say anything beyond naming itself?"""
    return any(line.strip() for line in section[1:])


def check(
    *,
    version: str,
    changelog_path: Path,
    tag: str | None,
) -> tuple[list[str], list[str]]:
    """Every failed precondition, and the release notes if there are any.

    Returns ``(problems, notes)``. ``problems`` empty means the release may
    proceed; ``notes`` is then the extracted section, ready to be written out.
    """
    problems: list[str] = []

    if STABLE_SEMVER.match(version) is None:
        problems.append(
            f"pyproject.toml declares version {version!r}, which is not stable SemVer; "
            "release-authorize.yml accepts only vMAJOR.MINOR.PATCH"
        )

    if tag is not None and tag != f"v{version}":
        problems.append(
            f"the dispatched tag is {tag!r} and pyproject.toml declares {version!r}; "
            f"they have to match, so the tag would have to be 'v{version}'"
        )

    try:
        changelog = changelog_path.read_text(encoding="utf-8")
    except OSError as error:
        raise PreflightError(f"cannot read {changelog_path}: {error}") from error

    section = extract_section(changelog, version)
    notes: list[str] = []
    if section is None:
        staged = extract_section(changelog, "Unreleased")
        remedy = (
            "rename the '## [Unreleased]' section to it and start a new empty one"
            if staged is not None and _has_body(staged)
            else "write one"
        )
        problems.append(
            f"{changelog_path.name} has no '## [{version}]' section; {remedy}. "
            "release.yml publishes that section as the release notes and refuses to "
            "build without it"
        )
    elif not _has_body(section):
        problems.append(
            f"{changelog_path.name} has a '## [{version}]' heading with nothing under it, "
            "so the release notes would be the version number and nothing else"
        )
    else:
        notes = section

    return problems, notes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--tag",
        default=None,
        help="the tag being released; required to equal v<package version>",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="the version to check; defaults to the one pyproject.toml declares",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="the repository to read; defaults to this script's own repository",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the extracted release notes here when every precondition holds",
    )
    arguments = parser.parse_args(argv)

    root: Path = arguments.root
    try:
        version = arguments.version or package_version(root / "pyproject.toml")
        problems, notes = check(
            version=version,
            changelog_path=root / "CHANGELOG.md",
            tag=arguments.tag,
        )
    except PreflightError as error:
        print(f"release preflight could not run: {error}", file=sys.stderr)
        return 2

    if problems:
        print(f"release preflight failed for {version}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    if arguments.out is not None:
        arguments.out.write_text("\n".join(notes) + "\n", encoding="utf-8")
        print(f"release preflight passed for {version}; notes written to {arguments.out}")
    else:
        print(f"release preflight passed for {version}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    raise SystemExit(main())
