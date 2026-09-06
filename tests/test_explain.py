"""`exitdrill explain` must say what the receipt says, and no more.

Issue #133's argument is that the next milestone is not code: it is an outside
person running the demo and saying whether the receipt answers their exit
question (#51). The receipt is correct and closed, and it is also a dense JSON
document whose limitations are snake_case codes.

Narration is therefore held to a narrower contract than "is it readable". Every
sentence must be derived from a receipt field or from `wording.py`; the
limitation claims must survive verbatim and in full; an `indeterminate`
dimension must never be narrated with the word a reader would carry away as a
pass; and an invalid receipt must produce no narration at all rather than a
partial one. Each of those is checked here against the output.

The wording tables are shared with the HTML report, so the two surfaces cannot
disagree about what a receipt says. That sharing is only worth anything while
the tables stay complete, so the last section requires an entry for every
member of every enum the narration reads.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from exitdrill.canonical import canonical_json_bytes, sha256_bytes
from exitdrill.cli import main
from exitdrill.evaluator import run_drill
from exitdrill.explain import (
    NARRATION_SCHEMA_VERSION,
    narrate_receipt,
    render_narration_text,
)
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import (
    TRUST_LIMITATIONS,
    Coverage,
    Dimension,
    DimensionStatus,
    JsonValue,
    OverallStatus,
)
from exitdrill.receipt import ReceiptError, build_receipt, write_receipt
from exitdrill.report import render_receipt_report
from exitdrill.wording import (
    COVERAGE_SENTENCES,
    DIMENSION_LABELS,
    DIMENSION_NOUNS,
    DIMENSION_QUESTIONS,
    LIMITATION_SENTENCES,
    OVERALL_SENTENCES,
    STATUS_LABELS,
    counted,
    label,
    were,
)

PROJECT = Path(__file__).parents[1]
CLEAN = PROJECT / "examples" / "synthetic-crm"
LOSSY = PROJECT / "examples" / "synthetic-crm-lossy"
README = PROJECT / "README.md"

# Every limitation code the three document kinds can be handed, so the shared
# table is required to carry all of them. Kept as literals rather than imported
# from the modules that emit them, so a code silently dropped there is a failure
# here rather than a matched pair of deletions.
HISTORY_LIMITATIONS = (
    "adjacent_directions_are_observations_not_a_trend",
    "aggregate_only_cannot_observe_record_identity_churn",
    "does_not_bind_export_generation_or_evaluator_version",
    "does_not_prove_operational_equivalence",
    "history_output_is_unsigned_and_unauthenticated",
    "inputs_are_unsigned_and_unauthenticated",
    "series_order_is_caller_supplied_unverified",
)

COMPARISON_LIMITATIONS = (
    "aggregate_only_cannot_observe_record_identity_churn",
    "comparison_output_is_unsigned_and_unauthenticated",
    "does_not_bind_export_generation_or_evaluator_version",
    "does_not_prove_operational_equivalence",
    "inputs_are_unsigned_and_unauthenticated",
    "operand_order_is_caller_supplied_unverified",
)


def receipt_for(export_root: Path, baseline: Path, claimed: str) -> dict[str, JsonValue]:
    result = run_drill(
        load_baseline(baseline),
        load_export(export_root / "export.json"),
        export_root / "export-files",
    )
    return build_receipt(result, claimed_generated_at=claimed)


def clean_receipt() -> dict[str, JsonValue]:
    return receipt_for(CLEAN, CLEAN / "baseline.json", "2026-07-22T20:00:00Z")


def lossy_receipt() -> dict[str, JsonValue]:
    return receipt_for(LOSSY, CLEAN / "baseline.json", "2026-07-22T20:05:00Z")


def narrated_text(receipt: dict[str, JsonValue]) -> str:
    return render_narration_text(narrate_receipt(deepcopy(receipt)))


def partial_coverage_baseline(tmp_path: Path, dimension: str) -> Path:
    """The demo baseline with one dimension's coverage declared partial."""
    document = json.loads((CLEAN / "baseline.json").read_text(encoding="utf-8"))
    document["coverage"][dimension] = "partial"
    destination = tmp_path / f"baseline-partial-{dimension}.json"
    destination.write_text(json.dumps(document), encoding="utf-8")
    return destination


def receipt_with_extra_only(dimension: str) -> dict[str, JsonValue]:
    """A receipt whose one changed dimension is a `finding`: extras, no losses.

    No committed fixture produces one -- the lossy export adds extras and loses
    evidence at the same time, so every one of its dimensions fails. The
    payload is edited and rehashed, then put back through `verify_receipt` by
    the caller, so this cannot become a shape no drill could emit.
    """
    receipt = clean_receipt()
    payload = cast(dict[str, JsonValue], receipt["payload"])
    for raw in cast(list[JsonValue], payload["dimensions"]):
        entry = cast(dict[str, JsonValue], raw)
        if entry["name"] != dimension:
            continue
        entry["exported_count"] = cast(int, entry["exported_count"]) + 1
        entry["restored_count"] = cast(int, entry["restored_count"]) + 1
        entry["extra_count"] = 1
        entry["status"] = DimensionStatus.FINDING.value
    payload["overall_status"] = OverallStatus.STRUCTURALLY_RESTORABLE_WITH_FINDINGS.value
    receipt["payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    return receipt


# ---------------------------------------------------------------------------
# The narration states the demo's own facts, and states them stably.
# ---------------------------------------------------------------------------


def test_the_clean_receipt_narrates_the_demo_summarys_facts() -> None:
    text = narrated_text(clean_receipt())

    assert "Structurally restorable" in text
    assert "0 loss signals" in text
    assert "Invented CommunityCase CRM" in text
    for name in Dimension:
        assert f"{DIMENSION_LABELS[name.value]}: Pass" in text


def test_the_lossy_receipt_narrates_the_demo_summarys_facts() -> None:
    text = narrated_text(lossy_receipt())

    assert "Not structurally restorable" in text
    assert "5 loss signals" in text
    for name in Dimension:
        assert f"{DIMENSION_LABELS[name.value]}: Fail" in text
    assert "1 of 2 entities could not be accounted for, so this dimension fails." in text
    assert "1 of 1 relationship could not be accounted for, so this dimension fails." in text


def test_narration_is_byte_stable() -> None:
    receipt = clean_receipt()

    assert narrated_text(receipt) == narrated_text(deepcopy(receipt))
    assert canonical_json_bytes(narrate_receipt(deepcopy(receipt))) == canonical_json_bytes(
        narrate_receipt(deepcopy(receipt))
    )


def test_the_narration_declares_its_own_schema_and_scope() -> None:
    narration = narrate_receipt(clean_receipt())

    assert narration["schema_version"] == NARRATION_SCHEMA_VERSION
    assert narration["decision_scope"] == "verified_aggregate_receipt_narration_only"


def test_the_counts_narrated_are_the_receipts_counts() -> None:
    """Every number in a dimension's sentences comes from that dimension."""
    receipt = lossy_receipt()
    narration = narrate_receipt(deepcopy(receipt))
    payload = cast(dict[str, JsonValue], receipt["payload"])
    dimensions = cast(list[JsonValue], payload["dimensions"])

    for raw, told in zip(dimensions, cast(list[JsonValue], narration["dimensions"]), strict=True):
        entry = cast(dict[str, JsonValue], raw)
        sentences = cast(dict[str, JsonValue], told)
        nouns = DIMENSION_NOUNS[cast(str, entry["name"])]
        expected = cast(int, entry["expected_count"])
        exported = cast(int, entry["exported_count"])
        missing = cast(int, entry["missing_count"])
        assert f"The baseline declared {counted(expected, nouns)}." in cast(
            str, sentences["denominator"]
        )
        assert f"The export carried {counted(exported, nouns)}." in cast(str, sentences["found"])
        assert f"{missing} {were(missing)} missing" in cast(str, sentences["found"])


# ---------------------------------------------------------------------------
# The claims boundary survives verbatim and in full.
# ---------------------------------------------------------------------------


def test_every_limitation_the_contract_declares_appears_exactly_once() -> None:
    """The load-bearing claims are quoted, not paraphrased, and none is dropped."""
    text = narrated_text(clean_receipt())

    assert len(TRUST_LIMITATIONS) == 5
    for code in TRUST_LIMITATIONS:
        sentence = LIMITATION_SENTENCES[code]
        assert text.count(sentence) == 1, code
    assert all(code not in text for code in TRUST_LIMITATIONS)


def test_the_limitation_count_check_can_see_a_dropped_sentence() -> None:
    """A narration missing one claim must fail the check above, not pass it."""
    text = narrated_text(clean_receipt()).replace(
        LIMITATION_SENTENCES["does_not_prove_vendor_deletion"], ""
    )

    assert text.count(LIMITATION_SENTENCES["does_not_prove_vendor_deletion"]) == 0


def test_report_and_explain_cannot_disagree_about_the_limitations() -> None:
    """Both surfaces render the same sentence for the same code.

    This is what the shared `wording.py` buys. Before it, each surface had its
    own copy and could have been reworded independently.
    """
    receipt = clean_receipt()
    report = render_receipt_report(deepcopy(receipt))
    text = narrated_text(receipt)

    for code in TRUST_LIMITATIONS:
        assert LIMITATION_SENTENCES[code] in report, code
        assert LIMITATION_SENTENCES[code] in text, code


# ---------------------------------------------------------------------------
# An indeterminate dimension is narrated as one, and never as a pass.
# ---------------------------------------------------------------------------


def test_partial_coverage_narrates_the_caveat_and_never_the_word_passed(
    tmp_path: Path,
) -> None:
    receipt = receipt_for(
        CLEAN,
        partial_coverage_baseline(tmp_path, "permissions"),
        "2026-07-22T20:00:00Z",
    )
    text = narrated_text(receipt)

    assert "Permissions: Indeterminate" in text
    assert (
        "Baseline coverage for this dimension is partial, meaning the baseline accounts "
        "for only part of this evidence, so this dimension is indeterminate: the drill "
        "cannot say whether the evidence is whole." in text
    )
    assert "passed" not in text
    assert "Permissions: Pass" not in text


def test_a_failed_dimension_is_never_narrated_as_a_coverage_problem(tmp_path: Path) -> None:
    """Losses decide `fail` before coverage is consulted, and so does the prose.

    Partial coverage and observed losses on the same dimension is the case
    where a narration could quietly reassign the cause. The result algebra
    calls it `fail`; the sentence must say the evidence could not be accounted
    for, not that the baseline was thin.
    """
    receipt = receipt_for(
        LOSSY,
        partial_coverage_baseline(tmp_path, "permissions"),
        "2026-07-22T20:05:00Z",
    )
    text = narrated_text(receipt)

    assert "Permissions: Fail" in text
    assert "1 of 1 permission grant could not be accounted for, so this dimension fails." in text
    assert "so this dimension is indeterminate" not in text


def test_complete_coverage_still_narrates_a_pass() -> None:
    """Pins the other side, so the check above cannot pass on a narration that
    never reports a passing dimension at all."""
    text = narrated_text(clean_receipt())

    assert "Permissions: Pass" in text
    assert "so this dimension passes." in text
    assert "indeterminate" not in text


def test_a_finding_is_narrated_as_extras_rather_than_loss() -> None:
    receipt = receipt_with_extra_only("entities")
    text = narrated_text(receipt)

    assert "Structurally restorable with findings" in text
    assert "Entities: Finding" in text
    assert (
        "Nothing was missing or invalid, but the export carried 1 entity the baseline "
        "did not declare, so this dimension is a finding rather than a clean result." in text
    )


# ---------------------------------------------------------------------------
# An invalid receipt narrates nothing.
# ---------------------------------------------------------------------------


def test_an_invalid_receipt_produces_no_narration() -> None:
    """Semantic validation runs before any sentence is built.

    The contradiction is caught by `validate_payload`, not by the checksum,
    because `verify_receipt` validates the payload before comparing digests.
    Either way the narration never begins.
    """
    receipt = clean_receipt()
    payload = cast(dict[str, JsonValue], receipt["payload"])
    payload["observed_remediation_signals"] = 99

    with pytest.raises(ReceiptError, match="remediation signals contradict"):
        narrate_receipt(receipt)


def test_a_receipt_whose_checksum_was_forged_produces_no_narration() -> None:
    receipt = clean_receipt()
    receipt["payload_sha256"] = "0" * 64

    with pytest.raises(ReceiptError, match="checksum mismatch"):
        narrate_receipt(receipt)


def test_cli_exits_two_with_the_validation_error_and_no_partial_narration(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "receipt.json"
    write_receipt(path, clean_receipt())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["payload"]["observed_remediation_signals"] = 99
    path.write_text(json.dumps(document), encoding="utf-8")

    assert main(["explain", str(path)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "remediation signals contradict" in captured.err


def test_cli_rejects_a_malformed_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "malformed.json"
    path.write_text('{"schema_version":', encoding="utf-8")

    assert main(["explain", str(path)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not valid JSON" in captured.err


# ---------------------------------------------------------------------------
# The CLI surface: text by default, the same narration as JSON on request.
# ---------------------------------------------------------------------------


def test_cli_prints_the_narration_as_text(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "receipt.json"
    receipt = clean_receipt()
    write_receipt(path, receipt)

    assert main(["explain", str(path)]) == 0

    assert capsys.readouterr().out == narrated_text(receipt)


def test_cli_json_carries_the_same_narration_the_text_was_built_from(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "receipt.json"
    receipt = clean_receipt()
    write_receipt(path, receipt)

    assert main(["explain", str(path), "--json"]) == 0

    emitted = json.loads(capsys.readouterr().out)
    assert emitted == json.loads(canonical_json_bytes(narrate_receipt(deepcopy(receipt))))
    assert render_narration_text(emitted) == narrated_text(receipt)


# ---------------------------------------------------------------------------
# The shared tables stay complete, or the sharing means nothing.
# ---------------------------------------------------------------------------


def test_every_dimension_has_a_label_a_noun_and_a_question() -> None:
    for dimension in Dimension:
        assert dimension.value in DIMENSION_LABELS
        assert dimension.value in DIMENSION_NOUNS
        assert dimension.value in DIMENSION_QUESTIONS
        singular, plural = DIMENSION_NOUNS[dimension.value]
        assert singular and plural and singular != plural


def test_every_result_state_has_a_name_and_a_meaning() -> None:
    for status in DimensionStatus:
        assert status.value in STATUS_LABELS
    for overall in OverallStatus:
        assert overall.value in STATUS_LABELS
        assert overall.value in OVERALL_SENTENCES


def test_every_coverage_declaration_has_a_sentence() -> None:
    for coverage in Coverage:
        assert coverage.value in COVERAGE_SENTENCES


def test_every_limitation_code_either_surface_can_render_has_a_sentence() -> None:
    for code in (*TRUST_LIMITATIONS, *COMPARISON_LIMITATIONS, *HISTORY_LIMITATIONS):
        assert code in LIMITATION_SENTENCES, code
    assert set(LIMITATION_SENTENCES) == {
        *TRUST_LIMITATIONS,
        *COMPARISON_LIMITATIONS,
        *HISTORY_LIMITATIONS,
    }


def test_each_dimension_question_is_the_one_the_readme_publishes() -> None:
    """A reworded README has to reword the narration, and the reverse.

    The README's "What it checks" table is where a reader who has not run the
    tool learns what each dimension asks. Two answers to that question is one
    too many.
    """
    readme = " ".join(README.read_text(encoding="utf-8").split())

    for dimension in Dimension:
        assert DIMENSION_QUESTIONS[dimension.value] in readme, dimension.value
    assert "Are the expected identities and declared invented values present?" not in readme


def test_the_lookup_falls_back_to_the_code_rather_than_failing() -> None:
    assert label({"a": "A"}, "a") == "A"
    assert label({}, "some_unmapped_code") == "Some unmapped code"
