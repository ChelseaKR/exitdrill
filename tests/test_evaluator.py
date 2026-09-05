import hashlib
import json
from dataclasses import replace
from pathlib import Path
from shutil import copytree

import pytest

from exitdrill.comparison import (
    compare_snapshots,
    comparison_has_observed_loss_signal_increase,
    snapshot_receipt,
)
from exitdrill.evaluator import DrillError, run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import (
    Coverage,
    Dimension,
    DimensionResult,
    DimensionStatus,
    DrillResult,
    OverallStatus,
)
from exitdrill.receipt import build_receipt


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
    assert "field_value_equivalence_limited_to_declared_required_fields" in limitations
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


@pytest.mark.parametrize(
    ("entity_index", "field", "value"),
    [
        (0, "display_name", "Different synthetic string"),
        (0, "active", False),
        (1, "status", "closed"),
        (1, "priority", 3),
    ],
)
def test_same_type_field_value_changes_fail(
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
    assert result.overall_status is OverallStatus.NOT_STRUCTURALLY_RESTORABLE
    assert result.dimensions[0].invalid_count == 1
    limitations = result.payload()["trust_limitations"]
    assert isinstance(limitations, list)
    assert "field_value_equivalence_limited_to_declared_required_fields" in limitations


def test_multiple_field_value_mismatches_count_one_invalid_entity(copied_example: Path) -> None:
    path = copied_example / "export.json"
    raw = _json(path)
    fields = raw["entities"][0]["fields"]  # type: ignore[index]
    fields["display_name"] = "Different synthetic string"
    fields["active"] = False
    _write(path, raw)

    result = _run(copied_example)
    assert result.dimensions[0].invalid_count == 1
    assert result.payload()["observed_remediation_signals"] == 1


def test_extra_attachment_whose_bytes_contradict_its_own_digest_fails(
    copied_example: Path,
) -> None:
    """An exported attachment absent from the baseline is still byte-checked.

    Nothing in the baseline declares an expected digest for an extra attachment,
    so only the export's own `content_sha256` can be contradicted. Without that
    check the drill would downgrade a corrupt attachment to `extra`, and the
    receipt would read `structurally_restorable_with_findings` for an export
    whose attachment bytes are not the bytes it claims to ship.
    """
    (copied_example / "export-files" / "attachments" / "extra.txt").write_bytes(b"other bytes\n")
    path = copied_example / "export.json"
    raw = _json(path)
    attachments = raw["attachments"]
    assert isinstance(attachments, list)
    attachments.append(
        {
            "id": "attachment-002",
            "owner_type": "case",
            "owner_id": "case-001",
            "relative_path": "attachments/extra.txt",
            "content_sha256": "0" * 64,
        }
    )
    _write(path, raw)

    result = _run(copied_example)
    attachment_result = next(
        item for item in result.dimensions if item.dimension is Dimension.ATTACHMENTS
    )

    assert attachment_result.extra_count == 1
    assert attachment_result.invalid_count == 1
    assert attachment_result.status is DimensionStatus.FAIL
    assert result.overall_status is OverallStatus.NOT_STRUCTURALLY_RESTORABLE


def test_payload_preserves_complete_dimension_denominator(example_root: Path) -> None:
    result = _run(example_root)
    names = {item.dimension for item in result.dimensions}
    assert names == set(Dimension)
    assert all(item.coverage is Coverage.COMPLETE for item in result.dimensions)


def _add_unrestorable_attachment(root: Path, *, corrupt_its_bytes: bool = False) -> None:
    """Declare an attachment whose owning entity is absent from the export.

    The baseline and export declare the same key, so it produces no missing or
    extra count. Its only possible failure is the reference model's foreign key
    refusing it, which makes it an isolated restoration failure.
    """
    payload = b"orphan attachment bytes\n"
    digest = hashlib.sha256(payload).hexdigest()
    written = b"tampered orphan bytes\n" if corrupt_its_bytes else payload
    (root / "export-files" / "attachments" / "orphan.txt").write_bytes(written)
    record = {
        "id": "attachment-002",
        "owner_type": "case",
        "owner_id": "case-404",
        "content_sha256": digest,
    }
    baseline_path = root / "baseline.json"
    baseline = _json(baseline_path)
    baseline_attachments = baseline["attachments"]
    assert isinstance(baseline_attachments, list)
    baseline_attachments.append(dict(record))
    _write(baseline_path, baseline)

    export_path = root / "export.json"
    export = _json(export_path)
    export_attachments = export["attachments"]
    assert isinstance(export_attachments, list)
    export_attachments.append({**record, "relative_path": "attachments/orphan.txt"})
    _write(export_path, export)


def _attachments_of(root: Path) -> DimensionResult:
    return next(item for item in _run(root).dimensions if item.dimension is Dimension.ATTACHMENTS)


def test_unrestorable_attachment_alone_is_one_invalid(copied_example: Path) -> None:
    """Establish the control count for the union regression below."""
    _add_unrestorable_attachment(copied_example)
    attachments = _attachments_of(copied_example)
    assert attachments.exported_count == 2
    assert attachments.restored_count == 1
    assert (attachments.missing_count, attachments.extra_count) == (0, 0)
    assert attachments.invalid_count == 1
    assert attachments.status is DimensionStatus.FAIL


def test_attachment_byte_and_restore_failures_are_unioned_not_maximized(
    copied_example: Path,
) -> None:
    """Two disjoint attachment failures must count as two, not one.

    Byte verification and reference-model restoration are independent
    populations: an attachment can ship the wrong bytes, be refused by the
    foreign key, or both. Reporting `max()` of the two population sizes hides
    the smaller one entirely, so an export that newly corrupts an attachment
    while carrying an unrelated unrestorable one reports an unchanged
    `invalid_count` -- a silent loss in the dimension this tool exists to watch.
    """
    _add_unrestorable_attachment(copied_example)
    (copied_example / "export-files" / "attachments" / "intake.txt").write_text(
        "tampered", encoding="utf-8"
    )

    attachments = _attachments_of(copied_example)

    assert attachments.exported_count == 2
    assert attachments.restored_count == 1
    assert (attachments.missing_count, attachments.extra_count) == (0, 0)
    assert attachments.invalid_count == 2
    assert attachments.status is DimensionStatus.FAIL


def test_attachment_failing_both_checks_is_counted_once(copied_example: Path) -> None:
    """The union counts distinct attachments, so overlap must not double count."""
    _add_unrestorable_attachment(copied_example, corrupt_its_bytes=True)

    attachments = _attachments_of(copied_example)

    assert attachments.exported_count == 2
    assert attachments.restored_count == 1
    assert attachments.invalid_count == 1
    assert attachments.status is DimensionStatus.FAIL


def test_new_attachment_corruption_is_visible_to_the_comparison_gate(
    tmp_path: Path,
    example_root: Path,
) -> None:
    """The count regression above is what `--fail-on-loss-signal-increase` reads.

    Both exports carry the same unrestorable attachment; only the candidate also
    tampers with a restorable one. The receipts must therefore differ, and the
    comparison must observe an attachment loss-signal increase.
    """
    roots: dict[str, Path] = {}
    for name in ("reference", "candidate"):
        destination = tmp_path / name
        copytree(example_root, destination)
        _add_unrestorable_attachment(destination)
        roots[name] = destination
    (roots["candidate"] / "export-files" / "attachments" / "intake.txt").write_text(
        "tampered", encoding="utf-8"
    )

    snapshots = [
        snapshot_receipt(
            build_receipt(_run(roots[name]), claimed_generated_at="2026-07-22T20:00:00Z")
        )
        for name in ("reference", "candidate")
    ]
    comparison = compare_snapshots(*snapshots)

    assert comparison["comparability"] == "comparable"
    assert comparison_has_observed_loss_signal_increase(comparison)
    summary = comparison["summary"]
    assert isinstance(summary, dict)
    assert summary["observed_loss_signal_increases"] == ["attachments"]
