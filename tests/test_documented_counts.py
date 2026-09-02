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
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
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
