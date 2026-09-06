import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from itertools import product
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator, ValidationError

from exitdrill import comparison as comparison_module
from exitdrill.canonical import canonical_json_bytes, sha256_bytes
from exitdrill.comparison import (
    ComparisonError,
    DimensionSnapshot,
    ReceiptSnapshot,
    _compare_dimension,
    _extra_transition,
    _validate_comparison_schema,
    compare_receipt_files,
    compare_snapshots,
    comparison_has_observed_loss_signal_increase,
    load_comparison,
    snapshot_receipt,
    verify_comparison_document,
    verify_comparison_files,
    write_comparison,
)
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import (
    Coverage,
    Dimension,
    DimensionStatus,
    JsonValue,
    classify_overall_status,
)
from exitdrill.receipt import ReceiptError, build_receipt, verify_receipt, write_receipt


def _receipt(export_root: Path, baseline_root: Path) -> dict[str, JsonValue]:
    result = run_drill(
        load_baseline(baseline_root / "baseline.json"),
        load_export(export_root / "export.json"),
        export_root / "export-files",
    )
    return build_receipt(result, claimed_generated_at="2026-07-22T20:00:00Z")


def _good_receipt(example_root: Path) -> dict[str, JsonValue]:
    return _receipt(example_root, example_root)


def _lossy_receipt(example_root: Path) -> dict[str, JsonValue]:
    lossy = Path(__file__).parents[1] / "examples" / "synthetic-crm-lossy"
    return _receipt(lossy, example_root)


def _payload(receipt: dict[str, JsonValue]) -> dict[str, JsonValue]:
    value = receipt["payload"]
    assert isinstance(value, dict)
    return value


def _dimension(receipt: dict[str, JsonValue], name: Dimension) -> dict[str, JsonValue]:
    dimensions = _payload(receipt)["dimensions"]
    assert isinstance(dimensions, list)
    for item in dimensions:
        assert isinstance(item, dict)
        if item["name"] == name.value:
            return item
    raise AssertionError(f"missing dimension {name}")


def _finalize(receipt: dict[str, JsonValue], export_character: str) -> None:
    payload = _payload(receipt)
    dimensions = payload["dimensions"]
    assert isinstance(dimensions, list)
    statuses: set[DimensionStatus] = set()
    remediation = 0
    for raw in dimensions:
        assert isinstance(raw, dict)
        statuses.add(DimensionStatus(cast(str, raw["status"])))
        remediation += cast(int, raw["missing_count"]) + cast(int, raw["invalid_count"])
    payload["overall_status"] = classify_overall_status(statuses).value
    payload["observed_remediation_signals"] = remediation
    payload["export_sha256"] = export_character * 64
    receipt["payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    verify_receipt(receipt)


def _write(path: Path, receipt: dict[str, JsonValue]) -> None:
    write_receipt(path, receipt)


def test_duplicate_payload_reports_no_new_measurement(example_root: Path) -> None:
    reference = _good_receipt(example_root)
    candidate = deepcopy(reference)
    candidate["envelope"] = {
        "claimed_generated_at": "1900-01-01T00:00:00Z",
        "signature_status": "not_signed",
        "trusted_time": False,
    }
    result = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))

    assert result["comparability"] == "comparable"
    assert result["measurement_relationship"] == "duplicate_payload"
    assert result["ordering_basis"] == "caller_supplied_unverified"
    assert result["limitations"] == [
        "inputs_are_unsigned_and_unauthenticated",
        "comparison_output_is_unsigned_and_unauthenticated",
        "aggregate_only_cannot_observe_record_identity_churn",
        "operand_order_is_caller_supplied_unverified",
        "does_not_bind_export_generation_or_evaluator_version",
        "does_not_prove_operational_equivalence",
    ]
    assert result["summary"] == {
        "mixed_loss_signal_changes": [],
        "no_observed_loss_signal_change": [item.value for item in Dimension],
        "observed_loss_signal_decreases": [],
        "observed_loss_signal_increases": [],
        "uncertain": [],
    }
    assert all(
        item["assessment"] == "no_observed_loss_signal_change"
        for item in cast(list[dict[str, object]], result["dimensions"])
    )
    assert comparison_has_observed_loss_signal_increase(result) is False


def test_lossy_candidate_surfaces_each_dimension_increase(example_root: Path) -> None:
    result = compare_snapshots(
        snapshot_receipt(_good_receipt(example_root)),
        snapshot_receipt(_lossy_receipt(example_root)),
    )
    summary = cast(dict[str, object], result["summary"])
    assert result["comparability"] == "comparable"
    assert summary["observed_loss_signal_increases"] == [item.value for item in Dimension]
    assert "score" not in result
    assert comparison_has_observed_loss_signal_increase(result) is True


def test_swapping_operands_negates_deltas_and_reverses_loss_direction(
    example_root: Path,
) -> None:
    good = snapshot_receipt(_good_receipt(example_root))
    lossy = snapshot_receipt(_lossy_receipt(example_root))
    forward = compare_snapshots(good, lossy)
    reverse = compare_snapshots(lossy, good)
    forward_dimensions = cast(list[dict[str, object]], forward["dimensions"])
    reverse_dimensions = cast(list[dict[str, object]], reverse["dimensions"])
    for first, second in zip(forward_dimensions, reverse_dimensions, strict=True):
        first_deltas = cast(dict[str, int], first["count_deltas"])
        second_deltas = cast(dict[str, int], second["count_deltas"])
        assert first["name"] == second["name"]
        assert all(first_deltas[key] == -second_deltas[key] for key in first_deltas)
    reverse_summary = cast(dict[str, object], reverse["summary"])
    assert reverse_summary["observed_loss_signal_decreases"] == [item.value for item in Dimension]
    assert comparison_has_observed_loss_signal_increase(reverse) is False


def test_repeated_comparison_is_byte_deterministic(example_root: Path) -> None:
    reference = snapshot_receipt(_good_receipt(example_root))
    candidate = snapshot_receipt(_lossy_receipt(example_root))
    first = canonical_json_bytes(compare_snapshots(reference, candidate))
    second = canonical_json_bytes(compare_snapshots(reference, candidate))
    assert first == second


def test_untrusted_envelope_text_is_ignored_and_not_disclosed(example_root: Path) -> None:
    # The marker is timestamp-shaped because `claimed_generated_at` now has to
    # be offset-aware ISO 8601 (issue #83); the envelope no longer carries any
    # free text. The offset is one no fixture uses, so the marker is still a
    # value that can only have come from this envelope.
    reference = _good_receipt(example_root)
    candidate = deepcopy(reference)
    marker = "1970-01-02T03:04:05+13:45"
    candidate["envelope"] = {
        "claimed_generated_at": marker,
        "signature_status": "not_signed",
        "trusted_time": False,
    }
    result = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    assert result["measurement_relationship"] == "duplicate_payload"
    assert marker not in canonical_json_bytes(result).decode("utf-8")


def test_unusual_operand_filenames_are_not_disclosed(
    tmp_path: Path,
    example_root: Path,
) -> None:
    reference = tmp_path / "-reference-\u2603\nprivate.json"
    candidate = tmp_path / "--candidate-\u2602\nprivate.json"
    _write(reference, _good_receipt(example_root))
    _write(candidate, _lossy_receipt(example_root))
    encoded = canonical_json_bytes(compare_receipt_files(reference, candidate)).decode("utf-8")
    assert reference.name not in encoded
    assert candidate.name not in encoded
    assert str(tmp_path) not in encoded


def test_extra_only_change_is_not_ranked_as_loss(example_root: Path) -> None:
    reference = _good_receipt(example_root)
    candidate = deepcopy(reference)
    entity = _dimension(candidate, Dimension.ENTITIES)
    entity.update(
        {
            "exported_count": 3,
            "extra_count": 1,
            "restored_count": 3,
            "status": "finding",
        }
    )
    _finalize(candidate, "a")

    result = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    compared = cast(list[dict[str, object]], result["dimensions"])[0]
    assert compared["assessment"] == "no_observed_loss_signal_change"
    assert compared["extra_count_transition"] == "changed_from_zero"
    assert compared["status_transition"] == "changed"
    assert comparison_has_observed_loss_signal_increase(result) is False


def test_mixed_missing_and_invalid_changes_remain_mixed(example_root: Path) -> None:
    reference = _good_receipt(example_root)
    candidate = _good_receipt(example_root)
    reference_entity = _dimension(reference, Dimension.ENTITIES)
    reference_entity.update(
        {
            "extra_count": 1,
            "invalid_count": 1,
            "missing_count": 1,
            "restored_count": 1,
            "status": "fail",
        }
    )
    candidate_entity = _dimension(candidate, Dimension.ENTITIES)
    candidate_entity.update(
        {
            "extra_count": 0,
            "invalid_count": 2,
            "missing_count": 0,
            "restored_count": 0,
            "status": "fail",
        }
    )
    _finalize(reference, "b")
    _finalize(candidate, "c")

    result = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    compared = cast(list[dict[str, object]], result["dimensions"])[0]
    assert compared["assessment"] == "mixed_loss_signal_change"
    assert compared["observed_loss_signal_increases"] == ["invalid_count_increased"]
    assert compared["observed_loss_signal_decreases"] == ["missing_count_decreased"]
    assert comparison_has_observed_loss_signal_increase(result) is True


def test_equal_partial_coverage_forces_uncertain_assessment(example_root: Path) -> None:
    reference = _good_receipt(example_root)
    candidate = _good_receipt(example_root)
    for receipt in (reference, candidate):
        entity = _dimension(receipt, Dimension.ENTITIES)
        entity["coverage"] = "partial"
    reference_entity = _dimension(reference, Dimension.ENTITIES)
    reference_entity.update(
        {
            "exported_count": 1,
            "missing_count": 1,
            "restored_count": 1,
            "status": "fail",
        }
    )
    _dimension(candidate, Dimension.ENTITIES)["status"] = "indeterminate"
    _finalize(reference, "d")
    _finalize(candidate, "e")

    result = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    compared = cast(list[dict[str, object]], result["dimensions"])[0]
    assert compared["assessment"] == "uncertain"
    assert compared["observed_loss_signal_decreases"] == ["missing_count_decreased"]
    assert comparison_has_observed_loss_signal_increase(result) is False


def test_partial_coverage_keeps_uncertain_but_exposes_direct_increase(
    example_root: Path,
) -> None:
    reference = _good_receipt(example_root)
    candidate = _good_receipt(example_root)
    for receipt in (reference, candidate):
        entity = _dimension(receipt, Dimension.ENTITIES)
        entity.update({"coverage": "partial", "status": "indeterminate"})
    candidate_entity = _dimension(candidate, Dimension.ENTITIES)
    candidate_entity.update(
        {
            "exported_count": 1,
            "missing_count": 1,
            "restored_count": 1,
            "status": "fail",
        }
    )
    _finalize(reference, "d")
    _finalize(candidate, "e")

    result = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    compared = cast(list[dict[str, object]], result["dimensions"])[0]
    assert compared["assessment"] == "uncertain"
    assert compared["observed_loss_signal_increases"] == ["missing_count_increased"]
    assert comparison_has_observed_loss_signal_increase(result) is True


def test_same_aggregates_with_distinct_payload_is_not_duplicate(example_root: Path) -> None:
    reference = _good_receipt(example_root)
    candidate = deepcopy(reference)
    _payload(candidate)["export_sha256"] = "f" * 64
    candidate["payload_sha256"] = sha256_bytes(canonical_json_bytes(_payload(candidate)))

    result = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    assert result["measurement_relationship"] == "distinct_payloads"
    assert cast(dict[str, object], result["summary"])["no_observed_loss_signal_change"] == [
        item.value for item in Dimension
    ]


def test_shuffled_dimension_order_does_not_change_alignment(example_root: Path) -> None:
    reference = _good_receipt(example_root)
    candidate = deepcopy(reference)
    dimensions = _payload(candidate)["dimensions"]
    assert isinstance(dimensions, list)
    dimensions.reverse()
    candidate["payload_sha256"] = sha256_bytes(canonical_json_bytes(_payload(candidate)))

    result = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    compared = cast(list[dict[str, object]], result["dimensions"])
    assert [item["name"] for item in compared] == [item.value for item in Dimension]
    assert all(item["assessment"] == "no_observed_loss_signal_change" for item in compared)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda item: replace(item, receipt_schema_version="exitdrill/receipt/v9"),
            "receipt_schema_version_changed",
        ),
        (
            lambda item: replace(item, result_schema_version="exitdrill/drill-result/v9"),
            "result_schema_version_changed",
        ),
        (lambda item: replace(item, decision_scope="different_scope"), "decision_scope_changed"),
        (lambda item: replace(item, drill_id="different-drill"), "drill_id_changed"),
        (
            lambda item: replace(item, source_system="Different synthetic source"),
            "source_system_changed",
        ),
        (
            lambda item: replace(item, trust_limitations=("different",)),
            "trust_limitations_changed",
        ),
    ],
)
def test_contract_or_scope_mismatch_is_explicitly_incomparable(
    example_root: Path,
    mutation: Callable[[ReceiptSnapshot], ReceiptSnapshot],
    reason: str,
) -> None:
    reference = snapshot_receipt(_good_receipt(example_root))
    candidate = mutation(reference)
    result = compare_snapshots(reference, candidate)
    assert result["comparability"] == "incomparable"
    assert reason in cast(list[str], result["incomparable_reasons"])
    assert result["dimensions"] == []
    assert comparison_has_observed_loss_signal_increase(result) is False


def test_multiple_scope_reasons_have_stable_contract_order(example_root: Path) -> None:
    reference = snapshot_receipt(_good_receipt(example_root))
    candidate = replace(
        reference,
        baseline_sha256="0" * 64,
        drill_id="different-drill",
        source_system="Different synthetic source",
    )
    result = compare_snapshots(reference, candidate)
    assert result["incomparable_reasons"] == [
        "baseline_sha256_changed",
        "drill_id_changed",
        "source_system_changed",
    ]


def test_changed_baseline_digest_is_incomparable(example_root: Path) -> None:
    reference = _good_receipt(example_root)
    candidate = deepcopy(reference)
    _payload(candidate)["baseline_sha256"] = "0" * 64
    candidate["payload_sha256"] = sha256_bytes(canonical_json_bytes(_payload(candidate)))
    result = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    assert result["incomparable_reasons"] == ["baseline_sha256_changed"]


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        ("coverage", "dimension_coverage_changed"),
        ("expected_count", "dimension_expected_counts_changed"),
    ],
)
def test_changed_dimension_scope_is_incomparable(
    example_root: Path,
    mode: str,
    reason: str,
) -> None:
    reference = _good_receipt(example_root)
    candidate = deepcopy(reference)
    entity = _dimension(candidate, Dimension.ENTITIES)
    if mode == "coverage":
        entity.update({"coverage": "partial", "status": "indeterminate"})
    else:
        entity.update({"expected_count": 3, "missing_count": 1, "status": "fail"})
    _finalize(candidate, "9")
    result = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    assert reason in cast(list[str], result["incomparable_reasons"])
    assert result["dimensions"] == []


def test_status_pairs_are_factual_not_ranked() -> None:
    base = DimensionSnapshot(
        name=Dimension.ENTITIES,
        coverage=Coverage.COMPLETE,
        status=DimensionStatus.PASS,
        expected_count=1,
        exported_count=1,
        restored_count=1,
        missing_count=0,
        extra_count=0,
        invalid_count=0,
    )
    for reference_status, candidate_status in product(DimensionStatus, repeat=2):
        compared = _compare_dimension(
            replace(base, status=reference_status),
            replace(base, status=candidate_status),
        )
        assert compared["assessment"] == "no_observed_loss_signal_change"
        expected = "unchanged" if reference_status is candidate_status else "changed"
        assert compared["status_transition"] == expected


@pytest.mark.parametrize(
    ("reference", "candidate", "transition"),
    [
        (0, 0, "unchanged"),
        (0, 1, "changed_from_zero"),
        (2, 0, "returned_to_zero"),
        (1, 2, "increased"),
        (2, 1, "decreased"),
    ],
)
def test_extra_count_transitions_are_descriptive_not_ranked(
    reference: int,
    candidate: int,
    transition: str,
) -> None:
    assert _extra_transition(reference, candidate) == transition


def test_swapping_operands_inverts_directional_extra_transition() -> None:
    base = DimensionSnapshot(
        name=Dimension.ENTITIES,
        coverage=Coverage.COMPLETE,
        status=DimensionStatus.FINDING,
        expected_count=1,
        exported_count=2,
        restored_count=2,
        missing_count=0,
        extra_count=1,
        invalid_count=0,
    )
    larger = replace(base, exported_count=3, restored_count=3, extra_count=2)
    assert _compare_dimension(base, larger)["extra_count_transition"] == "increased"
    assert _compare_dimension(larger, base)["extra_count_transition"] == "decreased"


def test_summary_is_a_total_partition_of_comparable_dimensions(example_root: Path) -> None:
    result = compare_snapshots(
        snapshot_receipt(_good_receipt(example_root)),
        snapshot_receipt(_lossy_receipt(example_root)),
    )
    summary = cast(dict[str, JsonValue], result["summary"])
    names = [
        cast(str, name) for values in summary.values() for name in cast(list[JsonValue], values)
    ]
    assert len(names) == len(Dimension)
    assert set(names) == {dimension.value for dimension in Dimension}


def test_files_are_strictly_validated_and_paths_are_not_serialized(
    tmp_path: Path,
    example_root: Path,
) -> None:
    reference_path = tmp_path / "secret-reference-name.json"
    candidate_path = tmp_path / "secret-candidate-name.json"
    _write(reference_path, _good_receipt(example_root))
    _write(candidate_path, _lossy_receipt(example_root))
    result = compare_receipt_files(reference_path, candidate_path)
    encoded = canonical_json_bytes(result).decode("utf-8")
    assert str(tmp_path) not in encoded
    assert reference_path.name not in encoded
    assert candidate_path.name not in encoded

    malformed = json.dumps(_good_receipt(example_root)).replace(
        '"schema_version": "exitdrill/receipt/v0.3"',
        '"schema_version": "exitdrill/receipt/v0.3", "schema_version": "exitdrill/receipt/v0.3"',
        1,
    )
    candidate_path.write_text(malformed, encoding="utf-8")
    with pytest.raises(ReceiptError, match="duplicate object key"):
        compare_receipt_files(reference_path, candidate_path)

    candidate_path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    # Matched in full: "2 MiB" alone also matched `strict_json`'s generic
    # noun, so it could not see which one came out (issue #85).
    with pytest.raises(ReceiptError, match="receipt exceeds the 2 MiB limit"):
        compare_receipt_files(reference_path, candidate_path)


def test_rehashed_but_semantically_invalid_receipt_cannot_be_compared(
    tmp_path: Path,
    example_root: Path,
) -> None:
    reference = _good_receipt(example_root)
    candidate = deepcopy(reference)
    dimensions = _payload(candidate)["dimensions"]
    assert isinstance(dimensions, list)
    dimensions.pop()
    candidate["payload_sha256"] = sha256_bytes(canonical_json_bytes(_payload(candidate)))
    reference_path = tmp_path / "reference.json"
    candidate_path = tmp_path / "candidate.json"
    _write(reference_path, reference)
    candidate_path.write_bytes(canonical_json_bytes(candidate) + b"\n")
    with pytest.raises(ReceiptError, match="every dimension exactly once"):
        compare_receipt_files(reference_path, candidate_path)


def test_public_comparison_schema_validates_generated_outputs(example_root: Path) -> None:
    project = Path(__file__).parents[1]
    schema_path = project / "schemas" / "receipt-comparison-v0.1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert all(
        definition.get("additionalProperties") is False
        for definition in schema["$defs"].values()
        if definition.get("type") == "object"
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    comparable = compare_snapshots(
        snapshot_receipt(_good_receipt(example_root)),
        snapshot_receipt(_lossy_receipt(example_root)),
    )
    reference = snapshot_receipt(_good_receipt(example_root))
    incomparable = compare_snapshots(reference, replace(reference, baseline_sha256="0" * 64))
    validator.validate(comparable)
    validator.validate(incomparable)


def test_validate_comparison_schema_accepts_real_comparison_output(example_root: Path) -> None:
    """The runtime self-check (issue #33) must accept what the evaluator itself
    produces -- this is what makes the schema genuinely load-bearing rather
    than a file the package merely carries.
    """
    comparison = compare_snapshots(
        snapshot_receipt(_good_receipt(example_root)),
        snapshot_receipt(_lossy_receipt(example_root)),
    )
    _validate_comparison_schema(comparison)  # must not raise


def test_validate_comparison_schema_rejects_a_structurally_wrong_document() -> None:
    with pytest.raises(ComparisonError, match="does not satisfy the public comparison schema"):
        _validate_comparison_schema(cast(dict[str, JsonValue], {"not": "a comparison document"}))


def test_semantic_verifier_accepts_generated_comparison(example_root: Path) -> None:
    reference = _good_receipt(example_root)
    candidate = _lossy_receipt(example_root)
    comparison = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    verify_comparison_document(comparison, reference, candidate)


@pytest.mark.parametrize(
    "forgery",
    [
        "summary_partition",
        "measurement_relationship",
        "scope_check",
        "count_delta",
        "status_transition",
        "extra_transition",
        "loss_signal",
        "assessment",
    ],
)
def test_semantic_verifier_rejects_source_bound_forgery(
    example_root: Path,
    forgery: str,
) -> None:
    reference = _good_receipt(example_root)
    candidate = _lossy_receipt(example_root)
    forged = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    dimensions = cast(list[dict[str, JsonValue]], forged["dimensions"])
    summary = cast(dict[str, JsonValue], forged["summary"])
    if forgery == "summary_partition":
        summary["no_observed_loss_signal_change"] = summary["observed_loss_signal_increases"]
        summary["observed_loss_signal_increases"] = []
    elif forgery == "measurement_relationship":
        forged["measurement_relationship"] = "duplicate_payload"
    elif forgery == "scope_check":
        checks = cast(dict[str, JsonValue], forged["scope_checks"])
        checks["baseline_sha256_equal"] = False
    elif forgery == "count_delta":
        deltas = cast(dict[str, JsonValue], dimensions[0]["count_deltas"])
        deltas["missing_count"] = 0
    elif forgery == "status_transition":
        dimensions[0]["status_transition"] = "unchanged"
    elif forgery == "extra_transition":
        dimensions[0]["extra_count_transition"] = "unchanged"
    elif forgery == "loss_signal":
        dimensions[0]["observed_loss_signal_increases"] = []
    else:
        dimensions[0]["assessment"] = "uncertain"
    with pytest.raises(ComparisonError, match="does not match"):
        verify_comparison_document(forged, reference, candidate)


def _incomparable_schema_contradiction(
    reference: ReceiptSnapshot,
    contradiction: str,
) -> dict[str, JsonValue] | None:
    if contradiction in {"incomparable_nonempty_summary", "reason_scope_mismatch"}:
        invalid = compare_snapshots(reference, replace(reference, baseline_sha256="0" * 64))
        if contradiction == "incomparable_nonempty_summary":
            summary = cast(dict[str, JsonValue], invalid["summary"])
            summary["uncertain"] = [Dimension.ENTITIES.value]
        else:
            invalid["incomparable_reasons"] = ["drill_id_changed"]
        return invalid
    if contradiction != "incomparable_all_checks_true":
        return None
    invalid = compare_snapshots(reference, reference)
    invalid["comparability"] = "incomparable"
    invalid["dimensions"] = []
    invalid["incomparable_reasons"] = ["baseline_sha256_changed"]
    invalid["summary"] = {
        "mixed_loss_signal_changes": [],
        "no_observed_loss_signal_change": [],
        "observed_loss_signal_decreases": [],
        "observed_loss_signal_increases": [],
        "uncertain": [],
    }
    return invalid


def _delta_schema_contradiction(
    reference: ReceiptSnapshot,
    example_root: Path,
    contradiction: str,
) -> dict[str, JsonValue] | None:
    if contradiction not in {
        "missing_delta_signal_mismatch",
        "invalid_delta_signal_mismatch",
        "extra_transition_mismatch",
    }:
        return None
    invalid = compare_snapshots(
        reference,
        snapshot_receipt(_lossy_receipt(example_root)),
    )
    dimensions = cast(list[dict[str, JsonValue]], invalid["dimensions"])
    index = 2 if contradiction == "invalid_delta_signal_mismatch" else 0
    dimension = dimensions[index]
    if contradiction == "extra_transition_mismatch":
        dimension["extra_count_transition"] = "unchanged"
    else:
        dimension["assessment"] = "uncertain"
        dimension["observed_loss_signal_increases"] = []
    return invalid


def _comparable_schema_contradiction(
    reference: ReceiptSnapshot,
    contradiction: str,
) -> dict[str, JsonValue]:
    invalid = compare_snapshots(reference, reference)
    if contradiction == "comparable_false_scope":
        checks = cast(dict[str, JsonValue], invalid["scope_checks"])
        checks["baseline_sha256_equal"] = False
    elif contradiction == "duplicate_dimension":
        raw_dimensions = cast(list[JsonValue], invalid["dimensions"])
        raw_dimensions[-1] = deepcopy(raw_dimensions[0])
    elif contradiction == "assessment_signal_mismatch":
        assessment_dimensions = cast(list[dict[str, JsonValue]], invalid["dimensions"])
        assessment_dimensions[0]["assessment"] = "observed_loss_signals_increased"
    elif contradiction == "status_transition_mismatch":
        status_dimensions = cast(list[dict[str, JsonValue]], invalid["dimensions"])
        status_dimensions[0]["status_transition"] = "changed"
    elif contradiction == "unknown_nested_field":
        extended_dimensions = cast(list[dict[str, JsonValue]], invalid["dimensions"])
        extended_dimensions[0]["score"] = 0
    else:
        limitations = cast(list[JsonValue], invalid["limitations"])
        limitations[0], limitations[1] = limitations[1], limitations[0]
    return invalid


@pytest.mark.parametrize(
    "contradiction",
    [
        "comparable_false_scope",
        "duplicate_dimension",
        "incomparable_nonempty_summary",
        "incomparable_all_checks_true",
        "reason_scope_mismatch",
        "assessment_signal_mismatch",
        "missing_delta_signal_mismatch",
        "invalid_delta_signal_mismatch",
        "status_transition_mismatch",
        "extra_transition_mismatch",
        "unknown_nested_field",
        "limitations_order_mismatch",
    ],
)
def test_public_comparison_schema_rejects_semantic_contradictions(
    example_root: Path,
    contradiction: str,
) -> None:
    project = Path(__file__).parents[1]
    schema = json.loads(
        (project / "schemas" / "receipt-comparison-v0.1.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    reference = snapshot_receipt(_good_receipt(example_root))
    invalid = _incomparable_schema_contradiction(reference, contradiction)
    if invalid is None:
        invalid = _delta_schema_contradiction(reference, example_root, contradiction)
    if invalid is None:
        invalid = _comparable_schema_contradiction(reference, contradiction)
    with pytest.raises(ValidationError):
        validator.validate(invalid)


# ---------------------------------------------------------------------------
# issue #82: the check compare_snapshots ran against its own output.
# ---------------------------------------------------------------------------


def test_compare_snapshots_no_longer_reverifies_the_document_it_just_built(
    example_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_build_comparison` is pure in two frozen snapshots.

    So recomputing it and requiring canonical byte equality with the value it
    had just returned compared a document with itself: it reported a clean
    result whether or not it was still checking anything, which is the defect
    family ADR 0021, ADR 0022 and ADR 0023 record. Making the recomputation
    raise proves `compare_snapshots` no longer calls it, and that
    `verify_comparison_document` -- where the document is caller-supplied and
    the check is real -- still does. This test fails if the call comes back.
    """

    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("compare_snapshots must not re-verify its own output")

    reference = _good_receipt(example_root)
    candidate = _lossy_receipt(example_root)
    expected = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    monkeypatch.setattr(comparison_module, "_verify_comparison_against_snapshots", _refuse)

    assert compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate)) == expected
    with pytest.raises(AssertionError, match="must not re-verify"):
        verify_comparison_document(expected, reference, candidate)


# ---------------------------------------------------------------------------
# issue #97: the comparison document as a written, re-verifiable artifact.
# ---------------------------------------------------------------------------


def test_written_comparison_round_trips_through_the_verifier(
    tmp_path: Path,
    example_root: Path,
) -> None:
    reference_path = tmp_path / "reference.json"
    candidate_path = tmp_path / "candidate.json"
    _write(reference_path, _good_receipt(example_root))
    _write(candidate_path, _lossy_receipt(example_root))
    comparison = compare_receipt_files(reference_path, candidate_path)
    written = tmp_path / "nested" / "comparison.json"

    write_comparison(written, comparison)

    assert written.read_bytes() == canonical_json_bytes(comparison) + b"\n"
    assert load_comparison(written) == comparison
    assert verify_comparison_files(written, reference_path, candidate_path) == comparison


def test_write_comparison_refuses_a_document_over_the_limit(tmp_path: Path) -> None:
    """Exercised against the writer's contract, not through `compare_snapshots`.

    A real comparison document holds five fixed dimensions and two metadata
    blocks, so it cannot approach 2 MiB; the bound is a fail-closed floor for
    any caller handing this writer a document from somewhere else. Stating the
    condition directly is what ADR 0023 asks for in place of a pragma.
    """
    parent = tmp_path / "not-created"
    oversized = cast(dict[str, JsonValue], {"comparability": "x" * (2 * 1024 * 1024)})

    with pytest.raises(ComparisonError, match="2 MiB"):
        write_comparison(parent / "comparison.json", oversized)
    assert not parent.exists()


def test_write_comparison_replaces_an_output_symlink_without_following_it(
    tmp_path: Path,
    example_root: Path,
) -> None:
    """The concrete difference from the shell redirection this replaced.

    `> comparison.json` writes through a symlink and truncates whatever is on
    the far end. `mkstemp` beside the target plus `os.replace` cannot.
    """
    comparison = compare_snapshots(
        snapshot_receipt(_good_receipt(example_root)),
        snapshot_receipt(_lossy_receipt(example_root)),
    )
    outside = tmp_path / "outside.json"
    outside.write_text("do not overwrite", encoding="utf-8")
    path = tmp_path / "comparison.json"
    path.symlink_to(outside)

    write_comparison(path, comparison)

    assert outside.read_text(encoding="utf-8") == "do not overwrite"
    assert not path.is_symlink()
    assert load_comparison(path) == comparison


def test_write_comparison_leaves_no_partial_file_after_a_replace_failure(
    tmp_path: Path,
    example_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comparison = compare_snapshots(
        snapshot_receipt(_good_receipt(example_root)),
        snapshot_receipt(_lossy_receipt(example_root)),
    )

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr("exitdrill.atomic_write.os.replace", fail_replace)
    with pytest.raises(OSError, match="synthetic"):
        write_comparison(tmp_path / "comparison.json", comparison)
    assert not (tmp_path / "comparison.json").exists()
    assert not list(tmp_path.glob(".comparison.json.*.tmp"))


def test_load_comparison_rejects_a_non_object_or_oversized_document(tmp_path: Path) -> None:
    path = tmp_path / "comparison.json"

    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ComparisonError, match="JSON object"):
        load_comparison(path)

    path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    with pytest.raises(ComparisonError, match="comparison exceeds the 2 MiB limit"):
        load_comparison(path)


def test_load_comparison_rejects_a_malformed_document(tmp_path: Path) -> None:
    path = tmp_path / "comparison.json"

    path.write_text('{"comparability":', encoding="utf-8")
    with pytest.raises(ComparisonError, match="not valid JSON"):
        load_comparison(path)

    marker = "invented-sensitive-duplicate"
    path.write_text(f'{{"{marker}": 1, "{marker}": 2}}', encoding="utf-8")
    with pytest.raises(ComparisonError, match="duplicate object key") as raised:
        load_comparison(path)
    assert marker not in str(raised.value)


def test_load_comparison_read_failure_does_not_disclose_the_path(tmp_path: Path) -> None:
    marker = "invented-private-missing-comparison"

    with pytest.raises(ComparisonError, match="comparison input could not be read") as raised:
        load_comparison(tmp_path / f"{marker}.json")
    assert marker not in str(raised.value)
    assert str(tmp_path) not in str(raised.value)


def test_verify_comparison_files_rejects_a_mismatched_receipt_pair(
    tmp_path: Path,
    example_root: Path,
) -> None:
    """An unforged document paired with receipts it does not describe.

    Nothing inside the document is wrong, so only recomputation from the two
    receipts actually supplied can catch it.
    """
    reference_path = tmp_path / "reference.json"
    candidate_path = tmp_path / "candidate.json"
    _write(reference_path, _good_receipt(example_root))
    _write(candidate_path, _lossy_receipt(example_root))
    written = tmp_path / "comparison.json"
    write_comparison(written, compare_receipt_files(reference_path, candidate_path))

    with pytest.raises(ComparisonError, match="does not match its source receipts"):
        verify_comparison_files(written, reference_path, reference_path)
    with pytest.raises(ComparisonError, match="does not match its source receipts"):
        verify_comparison_files(written, candidate_path, reference_path)


def test_verify_comparison_files_rejects_a_forged_field(
    tmp_path: Path,
    example_root: Path,
) -> None:
    reference_path = tmp_path / "reference.json"
    candidate_path = tmp_path / "candidate.json"
    _write(reference_path, _good_receipt(example_root))
    _write(candidate_path, _lossy_receipt(example_root))
    forged = compare_receipt_files(reference_path, candidate_path)
    summary = cast(dict[str, JsonValue], forged["summary"])
    summary["no_observed_loss_signal_change"] = summary["observed_loss_signal_increases"]
    summary["observed_loss_signal_increases"] = []
    written = tmp_path / "comparison.json"
    write_comparison(written, forged)

    with pytest.raises(ComparisonError, match="does not match its source receipts"):
        verify_comparison_files(written, reference_path, candidate_path)


def test_verify_comparison_files_rejects_an_unusable_source_receipt(
    tmp_path: Path,
    example_root: Path,
) -> None:
    """The receipt operands stay a trust boundary in this direction too."""
    reference_path = tmp_path / "reference.json"
    candidate_path = tmp_path / "candidate.json"
    _write(reference_path, _good_receipt(example_root))
    _write(candidate_path, _lossy_receipt(example_root))
    written = tmp_path / "comparison.json"
    write_comparison(written, compare_receipt_files(reference_path, candidate_path))
    candidate_path.write_text('{"schema_version":', encoding="utf-8")

    with pytest.raises(ReceiptError, match="not valid JSON"):
        verify_comparison_files(written, reference_path, candidate_path)

    marker = "invented-private-missing-receipt"
    with pytest.raises(ReceiptError, match="comparison input could not be read") as raised:
        verify_comparison_files(written, reference_path, tmp_path / f"{marker}.json")
    assert marker not in str(raised.value)
