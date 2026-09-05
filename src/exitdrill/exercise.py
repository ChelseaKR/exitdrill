"""Synthetic-only preflight contract for a future real-target exercise."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from exitdrill.models import Coverage, Dimension
from exitdrill.strict_json import StrictJsonError, load_strict_json

_MAX_PLAN_BYTES = 1024 * 1024
_PLAN_KEYS = {
    "schema_version",
    "exercise_id",
    "data_mode",
    "source",
    "baseline",
    "target_sandbox",
    "workflow_probes",
    "evidence_controls",
}
_REQUIRED_PROBES = {
    "find_record": "lookup",
    "traverse_relationships": "relationship",
    "retrieve_attachment": "attachment",
    "authorized_access": "permission_allow",
    "unauthorized_denial": "permission_deny",
}


class ExercisePlanError(ValueError):
    """Raised when a synthetic exercise plan crosses the safe preflight boundary."""


@dataclass(frozen=True, slots=True)
class ExercisePlan:
    """Validated plan metadata; no connector, credentials, or target data."""

    exercise_id: str
    source_system: str
    target_system: str


def _object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ExercisePlanError(f"{context} must be an object")
    return cast(dict[str, object], value)


def _exact(value: dict[str, object], expected: set[str], context: str) -> None:
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise ExercisePlanError(f"{context} has unknown field(s): {', '.join(unknown)}")
    if missing:
        raise ExercisePlanError(f"{context} is missing field(s): {', '.join(missing)}")


def _string(value: dict[str, object], key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ExercisePlanError(f"{context}.{key} must be a non-empty string")
    return item.strip()


def _required_boolean(
    value: dict[str, object],
    key: str,
    expected: bool,
    context: str,
) -> None:
    if value.get(key) is not expected:
        label = "true" if expected else "false"
        raise ExercisePlanError(f"{context}.{key} must be {label}")


def _validate_baseline(raw: object) -> None:
    value = _object(raw, "exercise baseline")
    _exact(
        value, {"captured_before_export", "coverage", "source_descriptions"}, "exercise baseline"
    )
    _required_boolean(value, "captured_before_export", True, "exercise baseline")
    coverage = _object(value["coverage"], "exercise baseline coverage")
    _exact(coverage, {dimension.value for dimension in Dimension}, "exercise baseline coverage")
    for dimension in Dimension:
        try:
            Coverage(_string(coverage, dimension.value, "exercise baseline coverage"))
        except ValueError as exc:
            raise ExercisePlanError("exercise baseline coverage is unsupported") from exc
    descriptions = value.get("source_descriptions")
    if (
        not isinstance(descriptions, list)
        or not descriptions
        or any(not isinstance(item, str) or not item.strip() for item in descriptions)
    ):
        raise ExercisePlanError(
            "exercise baseline.source_descriptions must contain non-empty strings"
        )


def _validate_target(raw: object) -> str:
    value = _object(raw, "target sandbox")
    _exact(
        value,
        {
            "system",
            "version",
            "empty",
            "isolated",
            "egress_blocked",
            "automations_disabled",
            "production_data_allowed",
        },
        "target sandbox",
    )
    for key in ("empty", "isolated", "egress_blocked", "automations_disabled"):
        _required_boolean(value, key, True, "target sandbox")
    _required_boolean(value, "production_data_allowed", False, "target sandbox")
    _string(value, "version", "target sandbox")
    return _string(value, "system", "target sandbox")


def _validate_probes(raw: object) -> None:
    if not isinstance(raw, list):
        raise ExercisePlanError("workflow_probes must be an array")
    probes: dict[str, str] = {}
    for index, item in enumerate(raw):
        context = f"workflow_probes[{index}]"
        value = _object(item, context)
        _exact(value, {"id", "kind", "required"}, context)
        _required_boolean(value, "required", True, context)
        probe_id = _string(value, "id", context)
        if probe_id in probes:
            raise ExercisePlanError("workflow probe ids must be unique")
        probes[probe_id] = _string(value, "kind", context)
    if probes != _REQUIRED_PROBES:
        raise ExercisePlanError("workflow probes must be exactly the five required safety probes")


def _validate_evidence(raw: object) -> None:
    value = _object(raw, "evidence controls")
    expected = {
        "target_readback_required",
        "raw_disposition_matrix_required",
        "raw_remediation_matrix_required",
        "human_attestation_required",
    }
    _exact(value, expected, "evidence controls")
    for key in expected:
        _required_boolean(value, key, True, "evidence controls")


def load_exercise_plan(path: Path) -> ExercisePlan:
    """Validate a synthetic-only plan without executing any source or target action."""
    try:
        raw, _source_sha256 = load_strict_json(
            path,
            max_bytes=_MAX_PLAN_BYTES,
            size_label="1 MiB",
            document_label="exercise plan",
        )
    except StrictJsonError as exc:
        raise ExercisePlanError(str(exc)) from exc
    value = _object(raw, "exercise plan")
    _exact(value, _PLAN_KEYS, "exercise plan")
    if value.get("schema_version") != "exitdrill/exercise-plan/v0.1":
        raise ExercisePlanError("unsupported exercise plan schema")
    if value.get("data_mode") != "synthetic_only":
        raise ExercisePlanError("exercise plan data_mode must remain synthetic_only")
    source = _object(value["source"], "exercise source")
    _exact(
        source, {"system", "version", "export_mechanism", "customer_obtainable"}, "exercise source"
    )
    _required_boolean(source, "customer_obtainable", True, "exercise source")
    source_system = _string(source, "system", "exercise source")
    _string(source, "version", "exercise source")
    _string(source, "export_mechanism", "exercise source")
    _validate_baseline(value["baseline"])
    target_system = _validate_target(value["target_sandbox"])
    _validate_probes(value["workflow_probes"])
    _validate_evidence(value["evidence_controls"])
    return ExercisePlan(
        exercise_id=_string(value, "exercise_id", "exercise plan"),
        source_system=source_system,
        target_system=target_system,
    )
