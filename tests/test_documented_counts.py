"""Bind the counts the documentation publishes to the evidence they describe.

The README and `docs/ARCHITECTURE.md` state specific numbers about the two
canaries: five target-interface probes pass, six source-to-target gaps remain,
the adversarial derivative produces six observed loss signals, nine browser
observations are committed, the accessibility scan reports 32 passing rules and
two serious violations, the Roles summary is reached on Tab press 69, and the
evidence index binds twelve artifacts of which eleven are results.

Every one of those was a hand-written number with nothing tying it to the
artifact it describes. A recapture, a fixture change, or a normalizer change
would leave the prose confidently wrong, and no gate would notice, because
prose is not executed. That is the same defect ADR 0021 and ADR 0022 removed
from the sentinel corpora, in the one place where being wrong is most visible
to a reader who cannot check.

Each test here computes the number from the committed evidence, renders the
documented sentence with it, and requires that sentence to appear in the
document. It therefore fails in both directions: if the evidence moves the
prose must be updated, and if the prose is reworded the binding must be
re-pointed rather than silently lost.

Whitespace is collapsed on both sides, because the documents hard-wrap and a
claim can straddle a line break. Nothing else about the sentence is relaxed.

The second half of the module applies the same rule to the declared input
bounds, which had the same defect in a worse form: the values were enforced in
`src/exitdrill` and published nowhere at all. Those are enumerated from the
source rather than listed here, so the check covers a bound added after it was
written.
"""

from __future__ import annotations

import ast
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import cast

import pytest

from exitdrill.civicrm_target_canary import normalize_civicrm_target_canary
from exitdrill.directus_canary import normalize_directus_canary
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import JsonValue

PROJECT = Path(__file__).parents[1]
README = PROJECT / "README.md"
ARCHITECTURE = PROJECT / "docs" / "ARCHITECTURE.md"
THREAT_MODEL = PROJECT / "docs" / "THREAT-MODEL.md"
SOURCE = PROJECT / "src" / "exitdrill"
DIRECTUS_README = PROJECT / "examples" / "directus-11.17.4-civic-case" / "README.md"
DIRECTUS_NATIVE = PROJECT / "examples" / "directus-11.17.4-civic-case" / "native"
CIVICRM_NATIVE = PROJECT / "examples" / "civicrm-6.16.2-target-roundtrip" / "native"
BASELINE = PROJECT / "examples" / "directus-11.17.4-civic-case" / "baseline.json"

_WORDS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)


def word(count: int) -> str:
    """Render a count the way the documents spell it out.

    Deliberately raises rather than falling back to digits for a count outside
    the table. A silent fallback would let a changed count render as a string
    the document happens not to contain, which reads as a documentation failure
    when it is really an unhandled case here.
    """
    return _WORDS[count]


def flat(text: str) -> str:
    return " ".join(text.split())


def assert_documented(document: Path, sentence: str) -> None:
    assert flat(sentence) in flat(document.read_text(encoding="utf-8")), sentence


def _json_object(path: Path) -> dict[str, JsonValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, JsonValue], value)


@contextmanager
def _civicrm_normalized() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="exitdrill-documented-counts-") as raw:
        out = Path(raw) / "normalized"
        normalize_civicrm_target_canary(CIVICRM_NATIVE / "capture-manifest.json", out)
        yield out


def _remediation_signals(normalized: Path) -> int:
    payload = run_drill(
        load_baseline(BASELINE),
        load_export(normalized / "export.json"),
        normalized / "export-files",
    ).payload()
    return cast(int, payload["observed_remediation_signals"])


# ---------------------------------------------------------------------------
# The renderer itself, so a claim cannot match for the wrong reason.
# ---------------------------------------------------------------------------


def test_the_number_renderer_is_correct() -> None:
    """If `word` were wrong, every claim below would fail for the wrong reason.

    Pinned so a reader of a failure can rule this out immediately.
    """
    assert [word(index) for index in range(5, 13)] == [
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
    ]
    with pytest.raises(IndexError):
        word(13)


def test_whitespace_collapsing_joins_lines_without_erasing_word_boundaries() -> None:
    """`flat` must survive the documents' hard wrapping and nothing more.

    The claims are matched as substrings, which is safe only because each one
    is a long distinctive sentence. What has to hold is that collapsing a run
    of whitespace never removes a boundary that separates two words, so a
    hard-wrapped claim matches and a run-together one does not.
    """
    assert flat("five  target-interface\nprobes") == "five target-interface probes"
    assert "six signals" not in flat("sixsignals")
    assert "sixsignals" not in flat("six\nsignals")


# ---------------------------------------------------------------------------
# README claims about the CiviCRM target canary.
# ---------------------------------------------------------------------------


def test_readme_target_probe_pass_count_matches_the_evidence() -> None:
    with _civicrm_normalized() as normalized:
        result = _json_object(normalized / "target-result.json")
        probes = cast(list[dict[str, JsonValue]], result["probe_results"])
        passes = sum(1 for probe in probes if probe["state"] == "pass")

    assert_documented(README, f"{word(passes).capitalize()} target-interface probes pass,")


def test_readme_source_to_target_gap_count_matches_the_evaluator() -> None:
    with _civicrm_normalized() as normalized:
        signals = _remediation_signals(normalized)

    assert_documented(
        README,
        f"while the structural evaluation still reports {word(signals)} source-to-target gaps.",
    )


def test_readme_browser_observation_count_matches_the_committed_captures() -> None:
    observations = sorted(CIVICRM_NATIVE.glob("browser-*.json"))

    assert_documented(
        README,
        f"The {word(len(observations))} committed browser-workflow, accessibility, "
        "and keyboard observations",
    )


# ---------------------------------------------------------------------------
# README and example-README claims about the Directus adversarial derivative.
# ---------------------------------------------------------------------------


def _directus_lossy_signals_and_mutations() -> tuple[int, int]:
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "exitdrill_lossy_builder", PROJECT / "scripts" / "build_directus_lossy_canary.py"
    )
    assert spec is not None and spec.loader is not None
    builder = module_from_spec(spec)
    spec.loader.exec_module(builder)

    with tempfile.TemporaryDirectory(prefix="exitdrill-documented-lossy-") as raw:
        root = Path(raw)
        lossy_native = root / "lossy-native"
        statement = root / "statement.json"
        builder.build_lossy_canary(DIRECTUS_NATIVE, lossy_native, statement)
        normalized = root / "lossy-normalized"
        normalize_directus_canary(lossy_native / "capture-manifest.json", normalized)
        signals = _remediation_signals(normalized)
        mutations = cast(list[str], _json_object(statement)["mutations"])
    return signals, len(mutations)


def test_readme_adversarial_loss_signal_count_matches_the_evaluator() -> None:
    signals, _ = _directus_lossy_signals_and_mutations()

    assert_documented(
        README,
        f"equal-count adversarial derivative produces {word(signals)} observed loss signals.",
    )


def test_directus_readme_mutation_and_signal_arithmetic_matches_the_builder() -> None:
    """The example README states the arithmetic, so both halves are bound.

    Binding only the signal count would leave the mutation count free to drift
    away from the sentence that claims they are equal.
    """
    signals, mutations = _directus_lossy_signals_and_mutations()

    assert_documented(
        DIRECTUS_README,
        f"so {word(mutations)} mutations producing {word(signals)} signals holds by arithmetic",
    )


# ---------------------------------------------------------------------------
# ARCHITECTURE claims about the browser observations and the evidence index.
# ---------------------------------------------------------------------------


def test_architecture_accessibility_numbers_match_the_capture() -> None:
    scan = _json_object(CIVICRM_NATIVE / "browser-accessibility.json")
    violations = cast(list[dict[str, JsonValue]], scan["violations"])
    by_rule = {cast(str, item["rule_id"]): cast(int, item["node_count"]) for item in violations}
    serious = sum(1 for item in violations if item["impact"] == "serious")

    assert_documented(
        ARCHITECTURE,
        f"The fixed observation reports {scan['passes_rule_count']} passing rules, "
        f"{scan['incomplete_rule_count']} incomplete, "
        f"{scan['inapplicable_rule_count']} inapplicable, "
        f"and {word(serious)} serious violations: `color-contrast` affecting "
        f"{word(by_rule['color-contrast'])} nodes and `link-in-text-block` affecting "
        f"{word(by_rule['link-in-text-block'])}.",
    )


def test_architecture_keyboard_tab_count_matches_the_capture() -> None:
    keyboard = _json_object(CIVICRM_NATIVE / "browser-keyboard.json")

    assert_documented(
        ARCHITECTURE,
        f"disclosure summary receives focus on press {keyboard['tab_steps_to_roles_summary']};",
    )


def test_architecture_evidence_index_counts_match_the_emitted_index() -> None:
    with _civicrm_normalized() as normalized:
        index = _json_object(normalized / "evidence-index.json")
        entries = cast(list[dict[str, JsonValue]], index["entries"])
        results = [entry for entry in entries if entry["filename"] != "export.json"]

    assert_documented(
        ARCHITECTURE,
        f"export and {word(len(results))} independent CiviCRM result artifacts.",
    )
    assert_documented(
        ARCHITECTURE,
        f"of the {word(len(entries))} fixed sibling artifacts, checks their lengths and digests,",
    )


# ---------------------------------------------------------------------------
# The binding itself must be able to fail.
# ---------------------------------------------------------------------------


def test_the_binding_reports_a_claim_the_document_does_not_make() -> None:
    """Guards against a helper that passed for any input.

    Uses the real README and a sentence built the same way the claims above are
    built, with a count the evidence does not produce.
    """
    with pytest.raises(AssertionError):
        assert_documented(README, f"{word(11).capitalize()} target-interface probes pass,")
    with pytest.raises(AssertionError):
        assert_documented(ARCHITECTURE, "disclosure summary receives focus on press 4242;")


# ---------------------------------------------------------------------------
# Every declared input bound, and the table that publishes it.
# ---------------------------------------------------------------------------
#
# Five of the eight bounds the evaluator enforced were stated in no committed
# document, including the 4 MiB baseline/export limit and the 200,000-node
# ceiling that applies to every document the tool reads (issue #99). A reader
# whose export was too large got exit 2 and a message, and nowhere to find out
# that the limit existed or what the rest of them were.
#
# Publishing the numbers by hand would have reproduced the defect this module
# was written to remove: a table of hand-written values with nothing tying them
# to the constants they describe. So the check enumerates instead. It walks the
# source for module-level `_MAX_*` assignments, renders each value the way the
# tables spell it out, and requires a table row naming that module and that
# constant to carry that exact value in a cell of its own.
#
# It therefore fails in three directions rather than one: a bound that moves
# without the table, a bound added with no row at all, and a table row whose
# value drifts from the source. There were nine bounds outside the canaries
# when this was written, not the eight the issue counted -- `comparison.py`
# gained one with the `verify-comparison` surface -- which is the drift itself,
# arriving between an issue being filed and being worked.


@dataclass(frozen=True)
class DeclaredBound:
    """One module-level `_MAX_*` constant, and where it is declared."""

    module: str
    name: str
    value: int


def render_bound(name: str, value: int) -> str:
    """Render a bound the way `docs/THREAT-MODEL.md` spells it out.

    Byte bounds are written in the unit they divide into exactly, because that
    is how they are declared in the source (`4 * 1024 * 1024`) and how an
    operator reads the rejection message. Everything else is a plain count.
    Deliberately has no fallback that quietly returns something matchable: a
    value the tables cannot express should fail here rather than silently look
    documented.
    """
    if not name.endswith("_BYTES"):
        return f"{value:,}"
    if value % (1024 * 1024) == 0:
        return f"{value // (1024 * 1024)} MiB"
    if value % 1024 == 0:
        return f"{value // 1024} KiB"
    return f"{value:,} bytes"


def _declared_bounds() -> tuple[DeclaredBound, ...]:
    """Every module-level `_MAX_*` constant declared under `src/exitdrill`.

    The AST decides where a constant is declared, so a name merely imported
    into another module cannot be credited to it. The value comes from the
    imported module rather than the AST, because these are written as
    expressions (`16 * 1024 * 1024`) that `ast.literal_eval` will not fold.
    """
    found: list[DeclaredBound] = []
    for path in sorted(SOURCE.glob("*.py")):
        if path.name == "__init__.py":
            continue
        module = import_module(f"exitdrill.{path.stem}")
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            targets = node.targets if isinstance(node, ast.Assign) else []
            for target in targets:
                if not isinstance(target, ast.Name) or not target.id.startswith("_MAX_"):
                    continue
                value = getattr(module, target.id)
                assert isinstance(value, int), f"{path.name}:{target.id} is not an integer bound"
                found.append(DeclaredBound(path.name, target.id, value))
    return tuple(found)


def _table_rows(document: Path) -> tuple[tuple[str, ...], ...]:
    """Split a Markdown document into rows of stripped cells."""
    rows: list[tuple[str, ...]] = []
    for line in document.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            rows.append(tuple(cell.strip() for cell in stripped.strip("|").split("|")))
    return tuple(rows)


def _row_documents(row: tuple[str, ...], bound: DeclaredBound) -> bool:
    """Whether one table row publishes this exact bound.

    The backticks around the names are load-bearing, not decoration: without
    them `_MAX_ATTACHMENT_BYTES` would match the row for
    `_MAX_TOTAL_ATTACHMENT_BYTES` and a missing row would look documented. The
    value has to be a whole cell rather than a substring for the same reason --
    a depth of 3 is a substring of a published 32.
    """
    joined = " ".join(row)
    return (
        f"`{bound.name}`" in joined
        and f"`{bound.module}`" in joined
        and render_bound(bound.name, bound.value) in row
    )


def test_the_bound_renderer_is_correct() -> None:
    """If `render_bound` were wrong, every bound below would fail for that reason.

    Pinned so a reader of a failure can rule it out immediately, and so the
    unit boundaries are stated rather than inferred from the current values.
    """
    assert render_bound("_MAX_DOCUMENT_BYTES", 4 * 1024 * 1024) == "4 MiB"
    assert render_bound("_MAX_MANIFEST_BYTES", 64 * 1024) == "64 KiB"
    assert render_bound("_MAX_ODD_BYTES", 1500) == "1,500 bytes"
    assert render_bound("_MAX_JSON_DEPTH", 64) == "64"
    assert render_bound("_MAX_JSON_NODES", 200_000) == "200,000"


def test_the_bound_discovery_finds_every_module_that_declares_one() -> None:
    """A discovery that silently found nothing would pass the check below.

    Two independent routes to the same set of modules: the AST walk the check
    uses, and a plain text search. A parse change that stopped seeing
    module-level assignments would leave the text search naming modules the
    walk does not, and fail here rather than reporting a clean documented set.
    """
    bounds = _declared_bounds()
    walked = {bound.module for bound in bounds}
    searched = {
        path.name
        for path in sorted(SOURCE.glob("*.py"))
        if "_MAX_" in path.read_text(encoding="utf-8") and path.name != "__init__.py"
    }

    assert walked == searched
    assert len(bounds) >= len(walked)
    assert ("strict_json.py", "_MAX_JSON_NODES") in {(item.module, item.name) for item in bounds}


def test_every_declared_input_bound_is_published_with_its_value() -> None:
    """Track A5, applied to the bounds: declared in source, or stated in a document."""
    rows = _table_rows(THREAT_MODEL)
    assert rows, "the threat model has no tables"

    undocumented = [
        f"{bound.module}:{bound.name} = {render_bound(bound.name, bound.value)}"
        for bound in _declared_bounds()
        if not any(_row_documents(row, bound) for row in rows)
    ]

    assert not undocumented, (
        "docs/THREAT-MODEL.md publishes no row carrying this module, this constant, "
        f"and this exact value: {undocumented}"
    )


def test_the_bound_binding_rejects_a_wrong_value_and_a_missing_row() -> None:
    """Guards against a matcher that passed for any input.

    Both cases run against the real threat model, so the difference between
    them and the check above is only the bound they are asked about.
    """
    rows = _table_rows(THREAT_MODEL)
    real = DeclaredBound("strict_json.py", "_MAX_JSON_NODES", 200_000)
    drifted = DeclaredBound("strict_json.py", "_MAX_JSON_NODES", 300_000)
    invented = DeclaredBound("strict_json.py", "_MAX_INVENTED_BYTES", 4 * 1024 * 1024)

    assert any(_row_documents(row, real) for row in rows)
    assert not any(_row_documents(row, drifted) for row in rows)
    assert not any(_row_documents(row, invented) for row in rows)
