"""Deterministic aggregate comparison for two verified drill receipts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from exitdrill.canonical import canonical_json_bytes
from exitdrill.models import Coverage, Dimension, DimensionStatus, JsonValue
from exitdrill.receipt import ReceiptError, load_receipt, verify_receipt

_COMPARISON_LIMITATIONS = (
    "inputs_are_unsigned_and_unauthenticated",
    "comparison_output_is_unsigned_and_unauthenticated",
    "aggregate_only_cannot_observe_record_identity_churn",
    "operand_order_is_caller_supplied_unverified",
    "does_not_bind_export_generation_or_evaluator_version",
    "does_not_prove_operational_equivalence",
)


class ComparisonError(ValueError):
    """Raised when a comparison document does not match its source receipts."""


@dataclass(frozen=True, slots=True)
class DimensionSnapshot:
    """One semantically validated aggregate dimension."""

    name: Dimension
    coverage: Coverage
    status: DimensionStatus
    expected_count: int
    exported_count: int
    restored_count: int
    missing_count: int
    extra_count: int
    invalid_count: int


@dataclass(frozen=True, slots=True)
class ReceiptSnapshot:
    """Comparison-safe fields extracted from one verified receipt."""

    receipt_schema_version: str
    result_schema_version: str
    decision_scope: str
    drill_id: str
    source_system: str
    baseline_sha256: str
    export_sha256: str
    payload_sha256: str
    trust_limitations: tuple[str, ...]
    dimensions: tuple[DimensionSnapshot, ...]

    @property
    def dimensions_by_name(self) -> dict[Dimension, DimensionSnapshot]:
        return {item.name: item for item in self.dimensions}


def _dimension_snapshot(raw: dict[str, JsonValue]) -> DimensionSnapshot:
    return DimensionSnapshot(
        name=Dimension(cast(str, raw["name"])),
        coverage=Coverage(cast(str, raw["coverage"])),
        status=DimensionStatus(cast(str, raw["status"])),
        expected_count=cast(int, raw["expected_count"]),
        exported_count=cast(int, raw["exported_count"]),
        restored_count=cast(int, raw["restored_count"]),
        missing_count=cast(int, raw["missing_count"]),
        extra_count=cast(int, raw["extra_count"]),
        invalid_count=cast(int, raw["invalid_count"]),
    )


def snapshot_receipt(receipt: dict[str, JsonValue]) -> ReceiptSnapshot:
    """Verify and reduce a receipt to fields that comparison is allowed to use."""
    verify_receipt(receipt)
    payload = cast(dict[str, JsonValue], receipt["payload"])
    raw_dimensions = cast(list[JsonValue], payload["dimensions"])
    by_name = {
        item.name: item
        for item in (_dimension_snapshot(cast(dict[str, JsonValue], raw)) for raw in raw_dimensions)
    }
    limitations = cast(list[JsonValue], payload["trust_limitations"])
    return ReceiptSnapshot(
        receipt_schema_version=cast(str, receipt["schema_version"]),
        result_schema_version=cast(str, payload["schema_version"]),
        decision_scope=cast(str, payload["decision_scope"]),
        drill_id=cast(str, payload["drill_id"]),
        source_system=cast(str, payload["source_system"]),
        baseline_sha256=cast(str, payload["baseline_sha256"]),
        export_sha256=cast(str, payload["export_sha256"]),
        payload_sha256=cast(str, receipt["payload_sha256"]),
        trust_limitations=tuple(cast(str, item) for item in limitations),
        dimensions=tuple(by_name[dimension] for dimension in Dimension),
    )


def load_receipt_snapshot(path: Path) -> ReceiptSnapshot:
    """Strict-load and semantically validate one bounded receipt file."""
    try:
        receipt = load_receipt(path)
    except OSError as exc:
        raise ReceiptError("comparison input could not be read") from exc
    return snapshot_receipt(receipt)


def _metadata(snapshot: ReceiptSnapshot) -> dict[str, JsonValue]:
    return {
        "baseline_sha256": snapshot.baseline_sha256,
        "drill_id": snapshot.drill_id,
        "export_sha256": snapshot.export_sha256,
        "payload_sha256": snapshot.payload_sha256,
        "receipt_schema_version": snapshot.receipt_schema_version,
        "result_schema_version": snapshot.result_schema_version,
        "source_system": snapshot.source_system,
    }


def _scope(
    reference: ReceiptSnapshot,
    candidate: ReceiptSnapshot,
) -> tuple[dict[str, bool], list[str]]:
    reference_dimensions = reference.dimensions_by_name
    candidate_dimensions = candidate.dimensions_by_name
    checks_and_reasons = (
        (
            "baseline_sha256_equal",
            reference.baseline_sha256 == candidate.baseline_sha256,
            "baseline_sha256_changed",
        ),
        ("drill_id_equal", reference.drill_id == candidate.drill_id, "drill_id_changed"),
        (
            "source_system_equal",
            reference.source_system == candidate.source_system,
            "source_system_changed",
        ),
        (
            "receipt_schema_version_equal",
            reference.receipt_schema_version == candidate.receipt_schema_version,
            "receipt_schema_version_changed",
        ),
        (
            "result_schema_version_equal",
            reference.result_schema_version == candidate.result_schema_version,
            "result_schema_version_changed",
        ),
        (
            "decision_scope_equal",
            reference.decision_scope == candidate.decision_scope,
            "decision_scope_changed",
        ),
        (
            "dimension_coverage_equal",
            all(
                reference_dimensions[item].coverage is candidate_dimensions[item].coverage
                for item in Dimension
            ),
            "dimension_coverage_changed",
        ),
        (
            "dimension_expected_counts_equal",
            all(
                reference_dimensions[item].expected_count
                == candidate_dimensions[item].expected_count
                for item in Dimension
            ),
            "dimension_expected_counts_changed",
        ),
        (
            "trust_limitations_equal",
            reference.trust_limitations == candidate.trust_limitations,
            "trust_limitations_changed",
        ),
    )
    checks = {name: passed for name, passed, _reason in checks_and_reasons}
    reasons = [reason for _name, passed, reason in checks_and_reasons if not passed]
    return checks, reasons


def _signed_delta(reference: int, candidate: int) -> int:
    return candidate - reference


def _loss_signals(
    missing_delta: int,
    invalid_delta: int,
) -> tuple[list[str], list[str]]:
    regressions: list[str] = []
    improvements: list[str] = []
    for name, delta in (
        ("missing_count", missing_delta),
        ("invalid_count", invalid_delta),
    ):
        if delta > 0:
            regressions.append(f"{name}_increased")
        elif delta < 0:
            improvements.append(f"{name}_decreased")
    return regressions, improvements


def _assessment(
    coverage: Coverage,
    regressions: list[str],
    improvements: list[str],
) -> str:
    if coverage is not Coverage.COMPLETE:
        return "uncertain"
    if regressions and improvements:
        return "mixed_loss_signal_change"
    if regressions:
        return "observed_loss_signals_increased"
    if improvements:
        return "observed_loss_signals_decreased"
    return "no_observed_loss_signal_change"


def _extra_transition(reference: int, candidate: int) -> str:
    if reference == candidate:
        return "unchanged"
    if reference == 0:
        return "changed_from_zero"
    if candidate == 0:
        return "returned_to_zero"
    return "increased" if candidate > reference else "decreased"


def _compare_dimension(
    reference: DimensionSnapshot,
    candidate: DimensionSnapshot,
) -> dict[str, JsonValue]:
    deltas = {
        "expected_count": _signed_delta(reference.expected_count, candidate.expected_count),
        "exported_count": _signed_delta(reference.exported_count, candidate.exported_count),
        "restored_count": _signed_delta(reference.restored_count, candidate.restored_count),
        "missing_count": _signed_delta(reference.missing_count, candidate.missing_count),
        "extra_count": _signed_delta(reference.extra_count, candidate.extra_count),
        "invalid_count": _signed_delta(reference.invalid_count, candidate.invalid_count),
    }
    regressions, improvements = _loss_signals(
        deltas["missing_count"],
        deltas["invalid_count"],
    )
    return {
        "assessment": _assessment(reference.coverage, regressions, improvements),
        "candidate_status": candidate.status.value,
        "count_deltas": cast(dict[str, JsonValue], deltas),
        "coverage": reference.coverage.value,
        "extra_count_transition": _extra_transition(
            reference.extra_count,
            candidate.extra_count,
        ),
        "name": reference.name.value,
        "observed_loss_signal_decreases": cast(list[JsonValue], improvements),
        "observed_loss_signal_increases": cast(list[JsonValue], regressions),
        "reference_status": reference.status.value,
        "status_transition": ("unchanged" if reference.status is candidate.status else "changed"),
    }


def _empty_summary() -> dict[str, JsonValue]:
    return {
        "mixed_loss_signal_changes": [],
        "no_observed_loss_signal_change": [],
        "observed_loss_signal_decreases": [],
        "observed_loss_signal_increases": [],
        "uncertain": [],
    }


def _build_comparison(
    reference: ReceiptSnapshot,
    candidate: ReceiptSnapshot,
) -> dict[str, JsonValue]:
    scope_checks, reasons = _scope(reference, candidate)
    result: dict[str, JsonValue] = {
        "candidate": _metadata(candidate),
        "comparability": "incomparable" if reasons else "comparable",
        "decision_scope": "offline_aggregate_receipt_change_only",
        "dimensions": [],
        "incomparable_reasons": cast(list[JsonValue], reasons),
        "limitations": cast(list[JsonValue], list(_COMPARISON_LIMITATIONS)),
        "measurement_relationship": (
            "duplicate_payload"
            if reference.payload_sha256 == candidate.payload_sha256
            else "distinct_payloads"
        ),
        "ordering_basis": "caller_supplied_unverified",
        "reference": _metadata(reference),
        "schema_version": "exitdrill/receipt-comparison/v0.1",
        "scope_checks": cast(dict[str, JsonValue], scope_checks),
        "summary": _empty_summary(),
    }
    if reasons:
        return result
    reference_dimensions = reference.dimensions_by_name
    candidate_dimensions = candidate.dimensions_by_name
    comparisons = [
        _compare_dimension(reference_dimensions[item], candidate_dimensions[item])
        for item in Dimension
    ]
    summary = _empty_summary()
    summary_key = {
        "observed_loss_signals_increased": "observed_loss_signal_increases",
        "observed_loss_signals_decreased": "observed_loss_signal_decreases",
        "mixed_loss_signal_change": "mixed_loss_signal_changes",
        "no_observed_loss_signal_change": "no_observed_loss_signal_change",
        "uncertain": "uncertain",
    }
    for item in comparisons:
        key = summary_key[cast(str, item["assessment"])]
        cast(list[JsonValue], summary[key]).append(cast(str, item["name"]))
    result["dimensions"] = cast(list[JsonValue], comparisons)
    result["summary"] = summary
    return result


def _verify_comparison_against_snapshots(
    comparison: dict[str, JsonValue],
    reference: ReceiptSnapshot,
    candidate: ReceiptSnapshot,
) -> None:
    expected = _build_comparison(reference, candidate)
    try:
        matches = canonical_json_bytes(comparison) == canonical_json_bytes(expected)
    except (TypeError, ValueError) as exc:
        raise ComparisonError("comparison document is not valid JSON data") from exc
    if not matches:
        raise ComparisonError("comparison document does not match its source receipts")


def compare_snapshots(
    reference: ReceiptSnapshot,
    candidate: ReceiptSnapshot,
) -> dict[str, JsonValue]:
    """Compare aggregate evidence without inferring chronology or a score."""
    result = _build_comparison(reference, candidate)
    _verify_comparison_against_snapshots(result, reference, candidate)
    return result


def verify_comparison_document(
    comparison: dict[str, JsonValue],
    reference_receipt: dict[str, JsonValue],
    candidate_receipt: dict[str, JsonValue],
) -> None:
    """Verify every comparison field by recomputing it from two valid source receipts."""
    _verify_comparison_against_snapshots(
        comparison,
        snapshot_receipt(reference_receipt),
        snapshot_receipt(candidate_receipt),
    )


def _comparison_has_observed_loss_signal_increase(
    comparison: dict[str, JsonValue],
) -> bool:
    """Return whether a comparable result directly observed a missing/invalid increase."""
    if comparison["comparability"] != "comparable":
        return False
    dimensions = cast(list[JsonValue], comparison["dimensions"])
    return any(
        bool(
            cast(
                list[JsonValue],
                cast(dict[str, JsonValue], item)["observed_loss_signal_increases"],
            )
        )
        for item in dimensions
    )


def compare_receipt_files(
    reference_path: Path,
    candidate_path: Path,
) -> dict[str, JsonValue]:
    """Strict-load, validate, and compare two receipt files in caller-supplied order."""
    return compare_snapshots(
        load_receipt_snapshot(reference_path),
        load_receipt_snapshot(candidate_path),
    )
