"""Closed semantic validation for aggregate drill-result payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import cast

from exitdrill.models import (
    TRUST_LIMITATIONS,
    Coverage,
    Dimension,
    DimensionStatus,
    OverallStatus,
    classify_dimension_status,
    classify_overall_status,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PAYLOAD_KEYS = {
    "baseline_sha256",
    "decision_scope",
    "dimensions",
    "drill_id",
    "export_sha256",
    "observed_remediation_signals",
    "overall_status",
    "schema_version",
    "source_system",
    "trust_limitations",
}
_DIMENSION_KEYS = {
    "coverage",
    "expected_count",
    "exported_count",
    "extra_count",
    "invalid_count",
    "missing_count",
    "name",
    "restored_count",
    "status",
}


class PayloadError(ValueError):
    """Raised when a receipt payload violates the closed result contract."""


def _object(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PayloadError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _exact_fields(value: Mapping[str, object], expected: set[str], context: str) -> None:
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise PayloadError(f"{context} has unknown field(s): {', '.join(unknown)}")
    if missing:
        raise PayloadError(f"{context} is missing field(s): {', '.join(missing)}")


def _nonempty_string(value: Mapping[str, object], key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise PayloadError(f"{context}.{key} must be a non-empty string")
    return item


def _nonnegative_integer(value: Mapping[str, object], key: str, context: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise PayloadError(f"{context}.{key} must be a non-negative integer")
    return item


def _enum_value[T: StrEnum](
    enum_type: type[T],
    value: Mapping[str, object],
    key: str,
    context: str,
) -> T:
    item = value.get(key)
    if not isinstance(item, str):
        # Distinct message from the ValueError branch below: without this,
        # a test asserting only "{key} is unsupported" can't tell the two
        # branches apart, and can't detect this isinstance guard being
        # removed (enum_type(item) below raises the same ValueError for a
        # non-string item that isn't a valid member either).
        raise PayloadError(f"{context}.{key} is unsupported: expected a string")
    try:
        return enum_type(item)
    except ValueError as exc:
        raise PayloadError(f"{context}.{key} is unsupported") from exc


def _validate_dimension(
    raw: object,
    index: int,
) -> tuple[Dimension, DimensionStatus, int]:
    context = f"receipt payload dimensions[{index}]"
    value = _object(raw, context)
    _exact_fields(value, _DIMENSION_KEYS, context)
    dimension = _enum_value(Dimension, value, "name", context)
    coverage = _enum_value(Coverage, value, "coverage", context)
    status = _enum_value(DimensionStatus, value, "status", context)
    counts = {
        key: _nonnegative_integer(value, key, context)
        for key in (
            "expected_count",
            "exported_count",
            "restored_count",
            "missing_count",
            "extra_count",
            "invalid_count",
        )
    }
    # Every relation `evaluator._dimension_result` guarantees is re-derived
    # here, because this validator accepts exactly the payloads `run_drill`
    # can emit (see `validate_payload`). Each unenforced relation is a receipt
    # no drill could have written that verifies anyway.
    if counts["missing_count"] > counts["expected_count"]:
        raise PayloadError(f"{context}.missing_count exceeds expected_count")
    if counts["extra_count"] > counts["exported_count"]:
        raise PayloadError(f"{context}.extra_count exceeds exported_count")
    if counts["restored_count"] > counts["exported_count"]:
        raise PayloadError(f"{context}.restored_count exceeds exported_count")
    if counts["invalid_count"] > counts["exported_count"]:
        raise PayloadError(f"{context}.invalid_count exceeds exported_count")
    # The evaluator's fail-closed restoration floor, restated: a caller may
    # never report fewer invalid items than the reference model refused, so
    # `invalid_count >= exported_count - restored_count` holds for every
    # dimension `_dimension_result` produces. `restored_count` had an upper
    # bound and no lower one, so a receipt claiming every row exported, none
    # restored, and none invalid passed as `pass` and rendered as
    # structurally restorable (issue #81).
    if counts["invalid_count"] < counts["exported_count"] - counts["restored_count"]:
        raise PayloadError(f"{context}.invalid_count is below the restoration shortfall")
    if (
        counts["expected_count"] - counts["missing_count"]
        != counts["exported_count"] - counts["extra_count"]
    ):
        raise PayloadError(f"{context} expected/exported intersection is inconsistent")
    expected_status = classify_dimension_status(
        coverage,
        missing_count=counts["missing_count"],
        extra_count=counts["extra_count"],
        invalid_count=counts["invalid_count"],
    )
    if status is not expected_status:
        raise PayloadError(f"{context}.status contradicts its counts or coverage")
    remediation = counts["missing_count"] + counts["invalid_count"]
    return dimension, status, remediation


def validate_payload(raw: object) -> None:
    """Validate one complete aggregate result payload without trusting its hash.

    The accepted set is exactly the set `run_drill` can emit, not a larger
    one; issue #81 asked for that to be decided rather than assumed. A
    receipt is read by people who will not re-run the drill, so a payload
    this validator accepts is a claim the tool stands behind, and any
    relation the evaluator guarantees but this validator omits is a receipt
    no drill could have produced that verifies anyway. Every such relation is
    re-derived: the count bounds and the restoration floor in
    `_validate_dimension`, the expected/exported intersection identity, the
    dimension and overall status algebra, the remediation-signal sum, and the
    full trust-limitation list. Nothing here authenticates the payload; a
    caller still needs `--baseline`/`--export` replay for that.
    """
    value = _object(raw, "receipt payload")
    _exact_fields(value, _PAYLOAD_KEYS, "receipt payload")
    if value.get("schema_version") != "exitdrill/drill-result/v0.3":
        raise PayloadError("unsupported receipt payload schema")
    if value.get("decision_scope") != "offline_structural_exit_drill_only":
        raise PayloadError("receipt payload decision scope is unsupported")
    for key in ("baseline_sha256", "export_sha256"):
        item = _nonempty_string(value, key, "receipt payload")
        if not _SHA256_PATTERN.fullmatch(item):
            raise PayloadError(f"receipt payload.{key} must be a lowercase SHA-256 digest")
    _nonempty_string(value, "drill_id", "receipt payload")
    _nonempty_string(value, "source_system", "receipt payload")
    dimensions = value.get("dimensions")
    if not isinstance(dimensions, list):
        raise PayloadError("receipt payload.dimensions must be an array")
    parsed = [_validate_dimension(item, index) for index, item in enumerate(dimensions)]
    names = [item[0] for item in parsed]
    if len(names) != len(Dimension) or set(names) != set(Dimension):
        raise PayloadError("receipt payload must contain every dimension exactly once")
    statuses = {item[1] for item in parsed}
    overall_status = _enum_value(
        OverallStatus,
        value,
        "overall_status",
        "receipt payload",
    )
    if overall_status is not classify_overall_status(statuses):
        raise PayloadError("receipt payload overall_status contradicts dimension statuses")
    remediation = _nonnegative_integer(
        value,
        "observed_remediation_signals",
        "receipt payload",
    )
    if remediation != sum(item[2] for item in parsed):
        raise PayloadError("receipt payload remediation signals contradict its dimensions")
    if value.get("trust_limitations") != list(TRUST_LIMITATIONS):
        raise PayloadError("receipt payload trust limitations are incomplete or unsupported")
