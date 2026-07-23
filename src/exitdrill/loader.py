"""Strict bounded loading for ExitDrill baselines and export packages."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from exitdrill.models import (
    AttachmentRecord,
    AuditEvent,
    Baseline,
    Coverage,
    Dimension,
    EntityRecord,
    ExpectedAttachment,
    ExpectedAuditEvent,
    ExpectedEntity,
    ExportPackage,
    FieldRequirement,
    JsonScalar,
    Permission,
    Relationship,
)
from exitdrill.strict_json import StrictJsonError, load_strict_json
from exitdrill.timestamps import TimestampError, parse_timestamp

_MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SCALAR_TYPES = {"string", "number", "boolean"}
_BASELINE_KEYS = {
    "schema_version",
    "drill_id",
    "source_system",
    "captured_at",
    "coverage",
    "entities",
    "relationships",
    "attachments",
    "permissions",
    "audit_events",
}
_EXPORT_KEYS = {
    "schema_version",
    "drill_id",
    "source_system",
    "exported_at",
    "entities",
    "relationships",
    "attachments",
    "permissions",
    "audit_events",
}


class PackageError(ValueError):
    """Raised when a baseline or export package is invalid."""


def _load_object(path: Path) -> tuple[dict[str, object], str]:
    try:
        raw, source_sha256 = load_strict_json(
            path,
            max_bytes=_MAX_DOCUMENT_BYTES,
            size_label="4 MiB",
        )
    except StrictJsonError as exc:
        raise PackageError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise PackageError("document must be a JSON object")
    return cast(dict[str, object], raw), source_sha256


def _exact_keys(value: Mapping[str, object], allowed: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(allowed - set(value))
    if unknown:
        raise PackageError(f"{context} has unknown field(s): {', '.join(unknown)}")
    if missing:
        raise PackageError(f"{context} is missing field(s): {', '.join(missing)}")


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PackageError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _items(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise PackageError(f"{context} must be an array")
    return cast(list[object], value)


def _string(value: Mapping[str, object], key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise PackageError(f"{context}.{key} must be a non-empty string")
    return item.strip()


def _identifier(value: Mapping[str, object], key: str, context: str) -> str:
    item = _string(value, key, context)
    if not _ID_PATTERN.fullmatch(item):
        raise PackageError(f"{context}.{key} must be a stable identifier")
    return item


def _sha256(value: Mapping[str, object], key: str, context: str) -> str:
    item = _string(value, key, context)
    if not _SHA256_PATTERN.fullmatch(item):
        raise PackageError(f"{context}.{key} must be a lowercase SHA-256 digest")
    return item


def _timestamp(value: Mapping[str, object], key: str, context: str) -> str:
    item = _string(value, key, context)
    try:
        parse_timestamp(item, f"{context}.{key}")
    except TimestampError as exc:
        raise PackageError(str(exc)) from exc
    return item


def _parse_relationship(raw: object, context: str) -> Relationship:
    value = _mapping(raw, context)
    _exact_keys(value, {"type", "from_type", "from_id", "to_type", "to_id"}, context)
    return Relationship(
        relation_type=_identifier(value, "type", context),
        from_type=_identifier(value, "from_type", context),
        from_id=_identifier(value, "from_id", context),
        to_type=_identifier(value, "to_type", context),
        to_id=_identifier(value, "to_id", context),
    )


def _parse_permission(raw: object, context: str) -> Permission:
    value = _mapping(raw, context)
    _exact_keys(value, {"principal_id", "scope_type", "scope_id", "role"}, context)
    return Permission(
        principal_id=_identifier(value, "principal_id", context),
        scope_type=_identifier(value, "scope_type", context),
        scope_id=_identifier(value, "scope_id", context),
        role=_identifier(value, "role", context),
    )


def _parse_expected_entity(raw: object, context: str) -> ExpectedEntity:
    value = _mapping(raw, context)
    _exact_keys(value, {"type", "id", "required_fields"}, context)
    requirements: list[FieldRequirement] = []
    for index, item in enumerate(_items(value["required_fields"], f"{context}.required_fields")):
        item_context = f"{context}.required_fields[{index}]"
        field = _mapping(item, item_context)
        _exact_keys(field, {"name", "type"}, item_context)
        value_type = _string(field, "type", item_context)
        if value_type not in _SCALAR_TYPES:
            raise PackageError(f"{item_context}.type is unsupported")
        requirements.append(
            FieldRequirement(
                name=_identifier(field, "name", item_context),
                value_type=value_type,
            )
        )
    if len({item.name for item in requirements}) != len(requirements):
        raise PackageError(f"{context}.required_fields names must be unique")
    return ExpectedEntity(
        entity_type=_identifier(value, "type", context),
        entity_id=_identifier(value, "id", context),
        required_fields=tuple(requirements),
    )


def _parse_entity(raw: object, context: str) -> EntityRecord:
    value = _mapping(raw, context)
    _exact_keys(value, {"type", "id", "fields"}, context)
    fields = _mapping(value["fields"], f"{context}.fields")
    parsed_fields: dict[str, JsonScalar] = {}
    for name, field_value in fields.items():
        if not _ID_PATTERN.fullmatch(name):
            raise PackageError(f"{context}.fields has an invalid field name")
        if isinstance(field_value, list | dict):
            raise PackageError(f"{context}.fields.{name} must be a JSON scalar")
        parsed_fields[name] = cast(JsonScalar, field_value)
    return EntityRecord(
        entity_type=_identifier(value, "type", context),
        entity_id=_identifier(value, "id", context),
        fields=parsed_fields,
    )


def _parse_expected_attachment(raw: object, context: str) -> ExpectedAttachment:
    value = _mapping(raw, context)
    _exact_keys(value, {"id", "owner_type", "owner_id", "content_sha256"}, context)
    return ExpectedAttachment(
        attachment_id=_identifier(value, "id", context),
        owner_type=_identifier(value, "owner_type", context),
        owner_id=_identifier(value, "owner_id", context),
        content_sha256=_sha256(value, "content_sha256", context),
    )


def _parse_attachment(raw: object, context: str) -> AttachmentRecord:
    value = _mapping(raw, context)
    _exact_keys(
        value,
        {"id", "owner_type", "owner_id", "relative_path", "content_sha256"},
        context,
    )
    return AttachmentRecord(
        attachment_id=_identifier(value, "id", context),
        owner_type=_identifier(value, "owner_type", context),
        owner_id=_identifier(value, "owner_id", context),
        relative_path=_string(value, "relative_path", context),
        content_sha256=_sha256(value, "content_sha256", context),
    )


def _parse_expected_audit(raw: object, context: str) -> ExpectedAuditEvent:
    value = _mapping(raw, context)
    _exact_keys(
        value,
        {"event_id", "object_type", "object_id", "action", "occurred_at"},
        context,
    )
    return ExpectedAuditEvent(
        event_id=_identifier(value, "event_id", context),
        object_type=_identifier(value, "object_type", context),
        object_id=_identifier(value, "object_id", context),
        action=_identifier(value, "action", context),
        occurred_at=_timestamp(value, "occurred_at", context),
    )


def _parse_audit(raw: object, context: str) -> AuditEvent:
    value = _mapping(raw, context)
    _exact_keys(value, {"event_id", "object_type", "object_id", "action", "occurred_at"}, context)
    return AuditEvent(
        event_id=_identifier(value, "event_id", context),
        object_type=_identifier(value, "object_type", context),
        object_id=_identifier(value, "object_id", context),
        action=_identifier(value, "action", context),
        occurred_at=_timestamp(value, "occurred_at", context),
    )


def _parse_list[T](
    root: Mapping[str, object],
    key: str,
    parser: Callable[[object, str], T],
) -> tuple[T, ...]:
    return tuple(
        parser(item, f"{key}[{index}]") for index, item in enumerate(_items(root[key], key))
    )


def _require_unique[T](items: tuple[T, ...], key: Callable[[T], object], context: str) -> None:
    values = [key(item) for item in items]
    if len(values) != len(set(values)):
        raise PackageError(f"{context} keys must be unique")


def load_baseline(path: Path) -> Baseline:
    """Load and validate an independently captured exit baseline."""
    raw, source_sha256 = _load_object(path)
    _exact_keys(raw, _BASELINE_KEYS, "baseline")
    if raw["schema_version"] != "exitdrill/baseline/v0.2":
        raise PackageError("unsupported baseline schema")
    coverage_raw = _mapping(raw["coverage"], "coverage")
    expected_dimensions = {item.value for item in Dimension}
    _exact_keys(coverage_raw, expected_dimensions, "coverage")
    try:
        coverage = {
            item: Coverage(_string(coverage_raw, item.value, "coverage")) for item in Dimension
        }
    except ValueError as exc:
        raise PackageError("coverage value is unsupported") from exc
    entities = _parse_list(raw, "entities", _parse_expected_entity)
    relationships = _parse_list(raw, "relationships", _parse_relationship)
    attachments = _parse_list(raw, "attachments", _parse_expected_attachment)
    permissions = _parse_list(raw, "permissions", _parse_permission)
    audit_events = _parse_list(raw, "audit_events", _parse_expected_audit)
    for items, key, context in (
        (entities, lambda item: item.key, "entities"),
        (relationships, lambda item: item.key, "relationships"),
        (attachments, lambda item: item.attachment_id, "attachments"),
        (permissions, lambda item: item.key, "permissions"),
        (audit_events, lambda item: item.event_id, "audit_events"),
    ):
        _require_unique(items, key, context)
    return Baseline(
        drill_id=_identifier(raw, "drill_id", "baseline"),
        source_system=_string(raw, "source_system", "baseline"),
        captured_at=_timestamp(raw, "captured_at", "baseline"),
        coverage=coverage,
        entities=entities,
        relationships=relationships,
        attachments=attachments,
        permissions=permissions,
        audit_events=audit_events,
        source_sha256=source_sha256,
    )


def load_export(path: Path) -> ExportPackage:
    """Load and validate a normalized vendor export package."""
    raw, source_sha256 = _load_object(path)
    _exact_keys(raw, _EXPORT_KEYS, "export")
    if raw["schema_version"] != "exitdrill/export/v0.1":
        raise PackageError("unsupported export schema")
    entities = _parse_list(raw, "entities", _parse_entity)
    relationships = _parse_list(raw, "relationships", _parse_relationship)
    attachments = _parse_list(raw, "attachments", _parse_attachment)
    permissions = _parse_list(raw, "permissions", _parse_permission)
    audit_events = _parse_list(raw, "audit_events", _parse_audit)
    for items, key, context in (
        (entities, lambda item: item.key, "entities"),
        (relationships, lambda item: item.key, "relationships"),
        (attachments, lambda item: item.attachment_id, "attachments"),
        (permissions, lambda item: item.key, "permissions"),
        (audit_events, lambda item: item.event_id, "audit_events"),
    ):
        _require_unique(items, key, context)
    return ExportPackage(
        drill_id=_identifier(raw, "drill_id", "export"),
        source_system=_string(raw, "source_system", "export"),
        exported_at=_timestamp(raw, "exported_at", "export"),
        entities=entities,
        relationships=relationships,
        attachments=attachments,
        permissions=permissions,
        audit_events=audit_events,
        source_sha256=source_sha256,
    )
