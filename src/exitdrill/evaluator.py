"""Structural comparison and neutral reference restoration."""

from __future__ import annotations

import sqlite3
from collections.abc import Collection
from pathlib import Path

from exitdrill.canonical import canonical_json_bytes
from exitdrill.models import (
    Baseline,
    Coverage,
    Dimension,
    DimensionResult,
    DrillResult,
    EntityRecord,
    ExportPackage,
    FieldRequirement,
    OverallStatus,
    classify_dimension_status,
    classify_overall_status,
)
from exitdrill.paths import BoundedPathError, ByteBudget, sha256_bounded_file
from exitdrill.timestamps import parse_timestamp

_MAX_ATTACHMENT_BYTES = 16 * 1024 * 1024
_MAX_TOTAL_ATTACHMENT_BYTES = 128 * 1024 * 1024


class DrillError(ValueError):
    """Raised when inputs cannot belong to the same exit drill."""


def _value_matches(requirement: FieldRequirement, value: object) -> bool:
    if requirement.value_type == "string":
        return isinstance(value, str) and bool(value.strip())
    if requirement.value_type == "boolean":
        return isinstance(value, bool)
    if requirement.value_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    return False


def _dimension_result(
    dimension: Dimension,
    coverage: Coverage,
    expected: Collection[object],
    actual: Collection[object],
    restored_count: int,
    invalid_count: int,
) -> DimensionResult:
    missing_count = len(set(expected) - set(actual))
    extra_count = len(set(actual) - set(expected))
    effective_invalid = max(invalid_count, len(actual) - restored_count)
    status = classify_dimension_status(
        coverage,
        missing_count=missing_count,
        extra_count=extra_count,
        invalid_count=effective_invalid,
    )
    return DimensionResult(
        dimension=dimension,
        coverage=coverage,
        status=status,
        expected_count=len(expected),
        exported_count=len(actual),
        restored_count=restored_count,
        missing_count=missing_count,
        extra_count=extra_count,
        invalid_count=effective_invalid,
    )


def _restore_reference_model(package: ExportPackage) -> dict[Dimension, int]:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE entities (
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            fields_json TEXT NOT NULL,
            PRIMARY KEY (entity_type, entity_id)
        );
        CREATE TABLE relationships (
            relation_type TEXT NOT NULL,
            from_type TEXT NOT NULL,
            from_id TEXT NOT NULL,
            to_type TEXT NOT NULL,
            to_id TEXT NOT NULL,
            PRIMARY KEY (relation_type, from_type, from_id, to_type, to_id),
            FOREIGN KEY (from_type, from_id) REFERENCES entities(entity_type, entity_id),
            FOREIGN KEY (to_type, to_id) REFERENCES entities(entity_type, entity_id)
        );
        CREATE TABLE attachments (
            attachment_id TEXT PRIMARY KEY,
            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            FOREIGN KEY (owner_type, owner_id) REFERENCES entities(entity_type, entity_id)
        );
        CREATE TABLE permissions (
            principal_id TEXT NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            role TEXT NOT NULL,
            PRIMARY KEY (principal_id, scope_type, scope_id, role),
            FOREIGN KEY (scope_type, scope_id) REFERENCES entities(entity_type, entity_id)
        );
        CREATE TABLE audit_events (
            event_id TEXT PRIMARY KEY,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            action TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            FOREIGN KEY (object_type, object_id) REFERENCES entities(entity_type, entity_id)
        );
        """
    )
    counts = {dimension: 0 for dimension in Dimension}
    try:
        connection.executemany(
            "INSERT INTO entities VALUES (?, ?, ?)",
            (
                (
                    item.entity_type,
                    item.entity_id,
                    canonical_json_bytes(item.fields).decode("utf-8"),
                )
                for item in package.entities
            ),
        )
        connection.commit()
        counts[Dimension.ENTITIES] = _table_count(connection, "entities")
    except sqlite3.IntegrityError:
        connection.rollback()
        connection.close()
        return counts
    operations: tuple[tuple[Dimension, str, tuple[tuple[object, ...], ...]], ...] = (
        (
            Dimension.RELATIONSHIPS,
            "INSERT INTO relationships VALUES (?, ?, ?, ?, ?)",
            tuple(item.key for item in package.relationships),
        ),
        (
            Dimension.ATTACHMENTS,
            "INSERT INTO attachments VALUES (?, ?, ?, ?)",
            tuple(
                (
                    item.attachment_id,
                    item.owner_type,
                    item.owner_id,
                    item.content_sha256,
                )
                for item in package.attachments
            ),
        ),
        (
            Dimension.PERMISSIONS,
            "INSERT INTO permissions VALUES (?, ?, ?, ?)",
            tuple(item.key for item in package.permissions),
        ),
        (
            Dimension.AUDIT_EVENTS,
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
            tuple(
                (
                    item.event_id,
                    item.object_type,
                    item.object_id,
                    item.action,
                    item.occurred_at,
                )
                for item in package.audit_events
            ),
        ),
    )
    table_names = {
        Dimension.RELATIONSHIPS: "relationships",
        Dimension.ATTACHMENTS: "attachments",
        Dimension.PERMISSIONS: "permissions",
        Dimension.AUDIT_EVENTS: "audit_events",
    }
    for dimension, statement, rows in operations:
        for row in rows:
            try:
                connection.execute(statement, row)
                connection.commit()
            except sqlite3.IntegrityError:
                connection.rollback()
        counts[dimension] = _table_count(connection, table_names[dimension])
    if tuple(connection.execute("PRAGMA foreign_key_check")):
        connection.close()
        return {dimension: 0 for dimension in Dimension}
    connection.close()
    return counts


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
    if row is None:
        return 0
    return int(row[0])


def _invalid_entities(
    expected_entities: tuple[object, ...],
    actual_by_key: dict[tuple[str, str], EntityRecord],
) -> int:
    invalid = 0
    for raw_expected in expected_entities:
        expected = raw_expected
        if not hasattr(expected, "key") or not hasattr(expected, "required_fields"):
            continue
        actual = actual_by_key.get(expected.key)
        if actual is None:
            continue
        if any(
            requirement.name not in actual.fields
            or not _value_matches(requirement, actual.fields[requirement.name])
            for requirement in expected.required_fields
        ):
            invalid += 1
    return invalid


def _invalid_attachments(
    baseline: Baseline,
    package: ExportPackage,
    attachment_root: Path,
) -> int:
    expected_hashes = {item.key: item.content_sha256 for item in baseline.attachments}
    total_budget = ByteBudget(_MAX_TOTAL_ATTACHMENT_BYTES)
    invalid = 0
    for item in package.attachments:
        try:
            actual_hash = sha256_bounded_file(
                attachment_root,
                item.relative_path,
                max_bytes=_MAX_ATTACHMENT_BYTES,
                total_budget=total_budget,
            )
        except (BoundedPathError, FileNotFoundError, OSError):
            invalid += 1
            continue
        if actual_hash != item.content_sha256:
            invalid += 1
            continue
        expected_hash = expected_hashes.get(item.key)
        if expected_hash is not None and expected_hash != actual_hash:
            invalid += 1
    return invalid


def _overall_status(results: tuple[DimensionResult, ...]) -> OverallStatus:
    return classify_overall_status({item.status for item in results})


def run_drill(
    baseline: Baseline,
    package: ExportPackage,
    attachment_root: Path,
) -> DrillResult:
    """Compare a normalized export with an independent baseline and restore it."""
    if baseline.drill_id != package.drill_id:
        raise DrillError("baseline and export drill ids do not match")
    if baseline.source_system != package.source_system:
        raise DrillError("baseline and export source systems do not match")
    captured_at = parse_timestamp(baseline.captured_at, "baseline.captured_at")
    exported_at = parse_timestamp(package.exported_at, "export.exported_at")
    if captured_at > exported_at:
        raise DrillError("baseline capture must not occur after the export")
    if any(
        parse_timestamp(item.occurred_at, "baseline.audit_event.occurred_at") > captured_at
        for item in baseline.audit_events
    ):
        raise DrillError("baseline audit event occurs after baseline capture")
    if any(
        parse_timestamp(item.occurred_at, "export.audit_event.occurred_at") > exported_at
        for item in package.audit_events
    ):
        raise DrillError("export audit event occurs after export creation")
    restored = _restore_reference_model(package)
    actual_entities = {item.key: item for item in package.entities}
    entity_result = _dimension_result(
        Dimension.ENTITIES,
        baseline.coverage[Dimension.ENTITIES],
        {item.key for item in baseline.entities},
        set(actual_entities),
        restored[Dimension.ENTITIES],
        _invalid_entities(tuple(baseline.entities), actual_entities),
    )
    results = (
        entity_result,
        _dimension_result(
            Dimension.RELATIONSHIPS,
            baseline.coverage[Dimension.RELATIONSHIPS],
            {item.key for item in baseline.relationships},
            {item.key for item in package.relationships},
            restored[Dimension.RELATIONSHIPS],
            len(package.relationships) if restored[Dimension.RELATIONSHIPS] == 0 else 0,
        ),
        _dimension_result(
            Dimension.ATTACHMENTS,
            baseline.coverage[Dimension.ATTACHMENTS],
            {item.key for item in baseline.attachments},
            {item.key for item in package.attachments},
            restored[Dimension.ATTACHMENTS],
            _invalid_attachments(baseline, package, attachment_root),
        ),
        _dimension_result(
            Dimension.PERMISSIONS,
            baseline.coverage[Dimension.PERMISSIONS],
            {item.key for item in baseline.permissions},
            {item.key for item in package.permissions},
            restored[Dimension.PERMISSIONS],
            len(package.permissions) if restored[Dimension.PERMISSIONS] == 0 else 0,
        ),
        _dimension_result(
            Dimension.AUDIT_EVENTS,
            baseline.coverage[Dimension.AUDIT_EVENTS],
            {item.key for item in baseline.audit_events},
            {item.key for item in package.audit_events},
            restored[Dimension.AUDIT_EVENTS],
            len(package.audit_events) if restored[Dimension.AUDIT_EVENTS] == 0 else 0,
        ),
    )
    return DrillResult(
        drill_id=baseline.drill_id,
        source_system=baseline.source_system,
        baseline_sha256=baseline.source_sha256,
        export_sha256=package.source_sha256,
        overall_status=_overall_status(results),
        dimensions=results,
    )
