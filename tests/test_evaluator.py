import json
from dataclasses import replace
from pathlib import Path

import pytest

from exitdrill.evaluator import DrillError, run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import (
    Coverage,
    Dimension,
    DimensionStatus,
    DrillResult,
    OverallStatus,
)


def _json(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _write(path: Path, raw: object) -> None:
    path.write_text(json.dumps(raw), encoding="utf-8")


def _run(root: Path) -> DrillResult:
    return run_drill(
        load_baseline(root / "baseline.json"),
        load_export(root / "export.json"),
        root / "export-files",
    )


def test_clean_fixture_is_structurally_restorable(example_root: Path) -> None:
    result = _run(example_root)
    assert result.overall_status is OverallStatus.STRUCTURALLY_RESTORABLE
    assert all(item.status is DimensionStatus.PASS for item in result.dimensions)
    assert result.payload()["observed_remediation_signals"] == 0
    limitations = result.payload()["trust_limitations"]
    assert isinstance(limitations, list)
    assert "does_not_prove_operational_equivalence" in limitations
    assert "does_not_verify_field_value_equivalence" in limitations
    assert "does_not_verify_permission_principal_identity" in limitations


def test_missing_entity_blocks_structural_restore(copied_example: Path) -> None:
    path = copied_example / "export.json"
    raw = _json(path)
    entities = raw["entities"]
    assert isinstance(entities, list)
    entities.pop()
    _write(path, raw)
    result = _run(copied_example)
    assert result.overall_status is OverallStatus.NOT_STRUCTURALLY_RESTORABLE
    entity = result.dimensions[0]
    assert entity.missing_count == 1
    assert entity.status is DimensionStatus.FAIL


def test_extra_entity_is_a_finding(copied_example: Path) -> None:
    path = copied_example / "export.json"
    raw = _json(path)
    entities = raw["entities"]
    assert isinstance(entities, list)
    entities.append({"type": "person", "id": "person-extra", "fields": {}})
    _write(path, raw)
    result = _run(copied_example)
    assert result.overall_status is OverallStatus.STRUCTURALLY_RESTORABLE_WITH_FINDINGS
    assert result.dimensions[0].extra_count == 1


def test_partial_baseline_is_indeterminate(copied_example: Path) -> None:
    path = copied_example / "baseline.json"
    raw = _json(path)
    coverage = raw["coverage"]
    assert isinstance(coverage, dict)
    coverage["audit_events"] = "partial"
    _write(path, raw)
    result = _run(copied_example)
    assert result.overall_status is OverallStatus.INDETERMINATE
    assert result.dimensions[-1].status is DimensionStatus.INDETERMINATE


@pytest.mark.parametrize(
    ("entity_index", "field", "value"),
    [
        (0, "display_name", ""),
        (0, "active", 1),
        (1, "priority", True),
    ],
)
def test_required_field_shape_loss_fails(
    copied_example: Path,
    entity_index: int,
    field: str,
    value: object,
) -> None:
    path = copied_example / "export.json"
    raw = _json(path)
    raw["entities"][entity_index]["fields"][field] = value  # type: ignore[index]
    _write(path, raw)
    result = _run(copied_example)
    assert result.dimensions[0].invalid_count == 1
    assert result.overall_status is OverallStatus.NOT_STRUCTURALLY_RESTORABLE


def test_orphaned_relationship_fails_reference_restore(copied_example: Path) -> None:
    path = copied_example / "export.json"
    raw = _json(path)
    raw["relationships"][0]["to_id"] = "missing-person"  # type: ignore[index]
    _write(path, raw)
    result = _run(copied_example)
    relationship = result.dimensions[1]
    assert relationship.invalid_count == 1
    assert relationship.restored_count == 0


def test_one_orphan_does_not_erase_valid_reference_readback(copied_example: Path) -> None:
    baseline_path = copied_example / "baseline.json"
    export_path = copied_example / "export.json"
    baseline = _json(baseline_path)
    package = _json(export_path)
    expected_relationships = baseline["relationships"]
    actual_relationships = package["relationships"]
    assert isinstance(expected_relationships, list)
    assert isinstance(actual_relationships, list)
    second_expected = dict(expected_relationships[0])
    second_expected["type"] = "secondary_case_subject"
    expected_relationships.append(second_expected)
    second_actual = dict(actual_relationships[0])
    second_actual["type"] = "secondary_case_subject"
    actual_relationships.append(second_actual)
    actual_relationships[0]["to_id"] = "missing-person"
    _write(baseline_path, baseline)
    _write(export_path, package)

    result = _run(copied_example)
    relationship = result.dimensions[1]
    assert relationship.exported_count == 2
    assert relationship.restored_count == 1
    assert relationship.invalid_count == 1


@pytest.mark.parametrize("dimension", ["permissions", "audit_events"])
def test_orphaned_scoped_records_fail_restore(copied_example: Path, dimension: str) -> None:
    path = copied_example / "export.json"
    raw = _json(path)
    key = "scope_id" if dimension == "permissions" else "object_id"
    raw[dimension][0][key] = "missing-case"  # type: ignore[index]
    _write(path, raw)
    result = _run(copied_example)
    selected = next(item for item in result.dimensions if item.dimension.value == dimension)
    assert selected.status is DimensionStatus.FAIL
    assert selected.invalid_count == 1


@pytest.mark.parametrize("mode", ["missing", "corrupt", "escape"])
def test_attachment_bytes_fail_closed(copied_example: Path, mode: str) -> None:
    export_path = copied_example / "export.json"
    attachment = copied_example / "export-files" / "attachments" / "intake.txt"
    if mode == "missing":
        attachment.unlink()
    elif mode == "corrupt":
        attachment.write_text("changed", encoding="utf-8")
    else:
        raw = _json(export_path)
        raw["attachments"][0]["relative_path"] = "../../baseline.json"  # type: ignore[index]
        _write(export_path, raw)
    result = _run(copied_example)
    attachments = result.dimensions[2]
    assert attachments.invalid_count == 1
    assert attachments.status is DimensionStatus.FAIL


def test_drill_identity_must_match(example_root: Path) -> None:
    baseline = load_baseline(example_root / "baseline.json")
    package = load_export(example_root / "export.json")
    with pytest.raises(DrillError, match="drill ids"):
        run_drill(baseline, replace(package, drill_id="different"), example_root / "export-files")
    with pytest.raises(DrillError, match="source systems"):
        run_drill(
            baseline,
            replace(package, source_system="Different CRM"),
            example_root / "export-files",
        )


def test_audit_action_or_time_mutation_is_detected(copied_example: Path) -> None:
    path = copied_example / "export.json"
    raw = _json(path)
    raw["audit_events"][0]["action"] = "synthetic_wrong_action"  # type: ignore[index]
    _write(path, raw)
    result = _run(copied_example)
    audit = result.dimensions[-1]
    assert audit.status is DimensionStatus.FAIL
    assert audit.missing_count == 1
    assert audit.extra_count == 1


@pytest.mark.parametrize(
    ("document", "field", "value", "message"),
    [
        ("baseline", "captured_at", "2026-07-23T20:00:00Z", "capture"),
        ("baseline", "audit_events.0.occurred_at", "2026-07-22T18:30:00Z", "baseline audit"),
        ("export", "audit_events.0.occurred_at", "2026-07-22T19:30:00Z", "export audit"),
    ],
)
def test_drill_rejects_incoherent_chronology(
    copied_example: Path,
    document: str,
    field: str,
    value: str,
    message: str,
) -> None:
    path = copied_example / f"{document}.json"
    raw = _json(path)
    if field == "captured_at":
        raw[field] = value
    else:
        raw["audit_events"][0]["occurred_at"] = value  # type: ignore[index]
    _write(path, raw)
    with pytest.raises(DrillError, match=message):
        _run(copied_example)


def test_same_type_field_value_changes_remain_out_of_scope(copied_example: Path) -> None:
    path = copied_example / "export.json"
    raw = _json(path)
    raw["entities"][0]["fields"]["display_name"] = "Different synthetic string"  # type: ignore[index]
    _write(path, raw)
    result = _run(copied_example)
    assert result.overall_status is OverallStatus.STRUCTURALLY_RESTORABLE
    limitations = result.payload()["trust_limitations"]
    assert isinstance(limitations, list)
    assert "does_not_verify_field_value_equivalence" in limitations


def test_payload_preserves_complete_dimension_denominator(example_root: Path) -> None:
    result = _run(example_root)
    names = {item.dimension for item in result.dimensions}
    assert names == set(Dimension)
    assert all(item.coverage is Coverage.COMPLETE for item in result.dimensions)
