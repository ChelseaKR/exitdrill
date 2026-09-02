"""Bind the roundtrip lab's declared constants to the values they must equal.

`scripts/check_browser_capture_bindings.mjs` already settled the principle for the nine
browser observations: a literal a capture script declares, and a committed artifact that
literal produces, must be checkable offline, because otherwise editing either one leaves
the pair silently disagreeing until somebody runs a live capture.

`scripts/civicrm_target_roundtrip_lab.mjs` was outside that binding, and it carries the
same shape of literal. It hand-declares:

* `expectedSourceNormalization`, which is a copy of the whole aggregate
  `exitdrill.directus_canary.normalize_directus_canary` returns for the committed Directus
  canary under `examples/directus-11.17.4-civic-case/native/`. Nine keys, two of them
  sha256 digests over committed bytes and one a counts table.
* three container image pins, `applicationImage`, `databaseImage` and `browserImage`,
  which `exitdrill.civicrm_target_canary` also pins in `_IMAGES` and requires the
  committed capture manifest to carry.
* `sourceProfile` and `targetProfile`, which the same module pins as `_SOURCE_PROFILE`
  and `_PROFILE`.

Nothing compared any of them. `make demo-civicrm-target-canary` checks that the committed
`capture-manifest.json` binds the recomputed Directus normalization, and
`normalize_civicrm_target_canary` checks that manifest against the Python constants, so
the committed capture is well covered. The lab script is the other half of that loop: it
is what writes the manifest on the next real recapture. A digest changed on the Python
side and not here, or here and not there, produces a recapture the validator rejects, and
until now the only way to find out was to stand up CiviCRM, MariaDB and Playwright in
Docker and run it.

Measured 2026-08-29, before this file existed: every constant checked here already agreed.
Nothing was keeping it that way.

The comparison is exact. `expectedSourceNormalization` is recomputed rather than pinned, so
this file writes down none of the digests itself: a second hand-typed copy of the thing
under test is what the check exists to remove.

`_object_literal` is a parser, so it gets negative tests, per AGENTS.md.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest

from exitdrill.civicrm_target_canary import _IMAGES, _PROFILE, _SOURCE_PROFILE
from exitdrill.directus_canary import normalize_directus_canary

PROJECT = Path(__file__).parents[1]
LAB = PROJECT / "scripts" / "civicrm_target_roundtrip_lab.mjs"
DIRECTUS_MANIFEST = (
    PROJECT / "examples" / "directus-11.17.4-civic-case" / "native" / "capture-manifest.json"
)

_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
_BARE_KEY = re.compile(r"(?<=[{,])(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _as_json(text: str) -> str:
    """One object literal rewritten as JSON: bare keys quoted, trailing commas dropped.

    Both substitutions are applied only to the spans between string literals, never
    inside one, so a digest or a sentence that happens to contain ``, word:`` or a comma
    before a brace is copied through untouched instead of being silently rewritten.
    """
    pieces: list[str] = []
    end = 0
    for found in _STRING.finditer(text):
        pieces.append(
            _TRAILING_COMMA.sub(r"\1", _BARE_KEY.sub(r'\1"\2"\3', text[end : found.start()]))
        )
        pieces.append(found.group(0))
        end = found.end()
    pieces.append(_TRAILING_COMMA.sub(r"\1", _BARE_KEY.sub(r'\1"\2"\3', text[end:])))
    return "".join(pieces)


class LabSourceError(ValueError):
    """The lab script does not declare what this file was pointed at."""


def _declaration(source: str, name: str) -> int:
    """Index just past ``const <name> = `` , failing if it is not declared exactly once."""
    matches = list(re.finditer(rf"(?m)^const {re.escape(name)}\s*=\s*", source))
    if len(matches) != 1:
        raise LabSourceError(f"{name} is declared {len(matches)} times, expected exactly one")
    return matches[0].end()


def string_literal(source: str, name: str) -> str:
    """One ``const <name> = "..."`` string, allowing the value to sit on the next line."""
    start = _declaration(source, name)
    match = re.match(r'\s*"((?:[^"\\]|\\.)*)"\s*;', source[start:])
    if match is None:
        raise LabSourceError(f"{name} is not declared as a single string literal")
    parsed: str = json.loads(f'"{match.group(1)}"')
    return parsed


def _object_literal(source: str, name: str) -> dict[str, Any]:
    """One ``const <name> = {...}`` object literal, as the data it denotes.

    Brace-matched rather than regex-terminated, because the literal nests. Bare keys are
    quoted and trailing commas dropped, which is the whole difference between this
    subset of JavaScript and JSON; anything else in the literal, a comment, a template
    string, a computed key, a function call, makes ``json.loads`` fail here rather than
    letting a value through unread.
    """
    start = _declaration(source, name)
    if not source[start:].startswith("{"):
        raise LabSourceError(f"{name} is not declared as an object literal")
    depth = 0
    for offset, character in enumerate(source[start:], start=start):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                text = source[start : offset + 1]
                break
    else:
        raise LabSourceError(f"{name} has an unterminated object literal")
    try:
        parsed = json.loads(_as_json(text))
    except json.JSONDecodeError as error:
        raise LabSourceError(f"{name} is not a JSON-expressible object literal") from error
    if not isinstance(parsed, dict):
        raise LabSourceError(f"{name} did not denote an object")
    return parsed


@pytest.fixture(scope="module")
def lab_source() -> str:
    return LAB.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def directus_normalization() -> dict[str, Any]:
    """The aggregate the committed Directus canary normalizes to, recomputed here.

    Into a temporary directory. A check that regenerated an artifact where the committed
    copy lives would repair the drift it exists to report and then find nothing.
    """
    with tempfile.TemporaryDirectory(prefix="exitdrill-lab-binding-") as raw:
        result = normalize_directus_canary(DIRECTUS_MANIFEST, Path(raw) / "normalized")
    return dict(result)


def test_the_lab_declares_the_source_normalization_the_committed_canary_produces(
    lab_source: str, directus_normalization: dict[str, Any]
) -> None:
    """The lab's whole `expectedSourceNormalization`, against a fresh normalization.

    Nine keys including two sha256 digests over committed bytes. Not a subset check: the
    lab asserts this object equals what the source normalization produced, so an extra
    key here is a claim the normalizer does not make.
    """
    declared = _object_literal(lab_source, "expectedSourceNormalization")
    assert declared == directus_normalization, (
        "scripts/civicrm_target_roundtrip_lab.mjs declares a source normalization that the "
        "committed Directus canary does not produce. The next real recapture would write a "
        "capture manifest exitdrill.civicrm_target_canary rejects. Re-derive it with "
        "`uv run exitdrill normalize-directus-canary` over "
        "examples/directus-11.17.4-civic-case/native/capture-manifest.json."
    )


@pytest.mark.parametrize(
    ("declared_as", "pinned_key"),
    (
        ("applicationImage", "application"),
        ("databaseImage", "database"),
        ("browserImage", "browser"),
    ),
)
def test_the_lab_runs_the_images_the_validator_requires(
    lab_source: str, declared_as: str, pinned_key: str
) -> None:
    """The container the lab starts, against the container the manifest must name."""
    assert string_literal(lab_source, declared_as) == _IMAGES[pinned_key], (
        f"{declared_as} in the lab script and _IMAGES[{pinned_key!r}] in "
        "exitdrill.civicrm_target_canary name different images. A capture taken with one "
        "cannot satisfy a validator pinned to the other."
    )


@pytest.mark.parametrize(
    ("declared_as", "pinned"),
    (("sourceProfile", _SOURCE_PROFILE), ("targetProfile", _PROFILE)),
)
def test_the_lab_declares_the_profiles_the_validator_pins(
    lab_source: str, declared_as: str, pinned: str
) -> None:
    assert string_literal(lab_source, declared_as) == pinned


class TestTheParserRefusesWhatItCannotRead:
    """AGENTS.md: a negative test for every parser. A parser that returns something
    plausible for input it did not understand would let a stale constant through as a
    pass, which is the failure this whole file exists to remove."""

    def test_an_absent_declaration_is_refused(self) -> None:
        with pytest.raises(LabSourceError):
            _object_literal("const other = {};\n", "expectedSourceNormalization")

    def test_a_duplicated_declaration_is_refused(self) -> None:
        with pytest.raises(LabSourceError):
            string_literal('const a = "one";\nconst a = "two";\n', "a")

    def test_a_non_object_declaration_is_refused(self) -> None:
        with pytest.raises(LabSourceError):
            _object_literal('const a = "text";\n', "a")

    def test_an_unterminated_object_is_refused(self) -> None:
        with pytest.raises(LabSourceError):
            _object_literal("const a = { b: 1,\n", "a")

    def test_a_literal_this_parser_cannot_express_is_refused(self) -> None:
        with pytest.raises(LabSourceError):
            _object_literal("const a = { b: compute() };\n", "a")

    def test_a_non_string_declaration_is_refused(self) -> None:
        with pytest.raises(LabSourceError):
            string_literal("const a = 5;\n", "a")

    def test_a_nested_object_with_trailing_commas_is_read_exactly(self) -> None:
        """The other direction: the subset the lab actually uses must parse to itself."""
        assert _object_literal(
            'const a = {\n  b: "x",\n  c: { d: 1, e: [2, 3,], },\n};\n', "a"
        ) == {"b": "x", "c": {"d": 1, "e": [2, 3]}}

    def test_a_string_split_across_lines_by_the_formatter_is_read(self) -> None:
        assert string_literal('const a =\n  "value";\n', "a") == "value"
