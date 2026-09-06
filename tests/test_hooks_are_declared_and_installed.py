"""A declared hook that nothing installs is a gate that cannot fail.

``.pre-commit-config.yaml`` declares four hooks, one of them ``stages:
[pre-push]``. ``pre-commit install`` writes only the ``pre-commit`` hook, so
the strict mypy hook needed a second command that nothing in this repository
named: there was no ``make hooks`` target, ``CONTRIBUTING.md`` did not mention
hooks at all, and ``.git/hooks`` held nothing but the stock samples. Meanwhile
the README's Code Quality row lists "pre-commit hooks" among the standards that
*apply*.

That is the shape this project is careful about everywhere else: something
declared, believed, and inert. ``make hooks`` installs them. These tests keep
the two files in step, so a hook declared later for a stage nobody installs
fails here rather than sitting configured and unrun.

``.pre-commit-config.yaml`` is read as text rather than parsed. That is a
narrow choice with a stated reason: no YAML library is a dependency of this
project, adding one for this would be out of proportion, and the question here
is not whether the file is structurally valid -- ``pre-commit`` itself answers
that on every run -- but whether a stage token appearing anywhere in it is
installed. The extraction is therefore deliberately over-broad: it takes every
stage name it can find, and an unrecognised one fails rather than being
ignored.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
CONFIG = PROJECT / ".pre-commit-config.yaml"
MAKEFILE = PROJECT / "Makefile"
CONTRIBUTING = PROJECT / "CONTRIBUTING.md"

# The stage a hook runs at when it declares none. `pre-commit install` with no
# --hook-type writes exactly this one, which is why the default needs no flag
# and everything else does.
DEFAULT_STAGE = "pre-commit"

# Stage names that name a git hook of the same name. A stage outside this set
# is not silently accepted: `test_every_declared_stage_is_a_known_git_hook`
# fails on it, so a new stage has to be looked at rather than assumed covered.
KNOWN_STAGES = frozenset(
    {
        "pre-commit",
        "pre-merge-commit",
        "pre-push",
        "prepare-commit-msg",
        "commit-msg",
        "post-checkout",
        "post-commit",
        "post-merge",
        "post-rewrite",
    }
)

_STAGES = re.compile(r"^\s*stages:\s*\[([^\]]*)\]", re.MULTILINE)
_HOOK_ID = re.compile(r"^\s*-\s*id:\s*(\S+)", re.MULTILINE)


def declared_stages() -> set[str]:
    """Every stage the config asks for, including the implicit default.

    The default is included unconditionally because a config with any hook at
    all has at least one hook running at the default stage unless every single
    one overrides it, and a target that installed no default hook would be
    wrong in the ordinary case.
    """
    text = CONFIG.read_text(encoding="utf-8")
    found = {DEFAULT_STAGE} if _HOOK_ID.search(text) else set()
    for match in _STAGES.finditer(text):
        for token in match.group(1).split(","):
            name = token.strip().strip("\"'")
            if name:
                found.add(name)
    return found


def hooks_recipe() -> str:
    """The body of the Makefile's `hooks` target."""
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^hooks:\n((?:\t.*\n)+)", text, re.MULTILINE)
    assert match is not None, "the Makefile has no `hooks:` target with a recipe"
    return match.group(1)


def test_the_config_declares_the_hooks_this_test_is_about() -> None:
    """A guard on the guard: if the config empties out, everything below is vacuous."""
    text = CONFIG.read_text(encoding="utf-8")
    ids = set(_HOOK_ID.findall(text))
    assert ids >= {"gitleaks", "ruff", "ruff-format", "mypy"}, ids
    assert "stages: [pre-push]" in text


def test_every_declared_stage_is_a_known_git_hook() -> None:
    unknown = declared_stages() - KNOWN_STAGES
    assert not unknown, (
        f"{unknown} is declared in .pre-commit-config.yaml and this test does not know "
        f"which git hook it writes. Look it up and add it to KNOWN_STAGES rather than "
        f"assuming `make hooks` already installs it."
    )


def test_make_hooks_installs_every_declared_stage() -> None:
    """The whole point. A stage nobody installs is a hook that never runs."""
    recipe = hooks_recipe()
    for stage in sorted(declared_stages()):
        if stage == DEFAULT_STAGE:
            # Written by `pre-commit install` with no flag.
            assert re.search(r"pre-commit install(?!\s+--hook-type)", recipe), recipe
            continue
        assert f"--hook-type {stage}" in recipe, (
            f".pre-commit-config.yaml declares a hook at stage {stage!r}, and the "
            f"Makefile's `hooks` target does not install it. `pre-commit install` alone "
            f"writes only the {DEFAULT_STAGE} hook, so that hook is configured and inert."
        )


def test_the_hooks_target_is_phony() -> None:
    """There is no file called `hooks`, and a directory of that name would shadow it."""
    phony = re.search(r"^\.PHONY:(.*)$", MAKEFILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert phony is not None
    assert "hooks" in phony.group(1).split()


def test_contributing_tells_a_contributor_to_install_them() -> None:
    """The gap was never only the missing target; nothing pointed anyone at it."""
    text = CONTRIBUTING.read_text(encoding="utf-8")
    assert "make hooks" in text
    assert "pre-push" in text
