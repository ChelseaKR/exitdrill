"""Immutable domain models for structural exit drills."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

TRUST_LIMITATIONS = (
    "does_not_prove_operational_equivalence",
    "does_not_prove_vendor_deletion",
    "does_not_authenticate_export_or_baseline",
    "does_not_verify_field_value_equivalence",
    "does_not_verify_permission_principal_identity",
)


class Coverage(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class Dimension(StrEnum):
    ENTITIES = "entities"
    RELATIONSHIPS = "relationships"
    ATTACHMENTS = "attachments"
    PERMISSIONS = "permissions"
    AUDIT_EVENTS = "audit_events"


class DimensionStatus(StrEnum):
    PASS = "pass"  # noqa: S105 - evaluation state, not a credential
    FAIL = "fail"
    FINDING = "finding"
    INDETERMINATE = "indeterminate"


class OverallStatus(StrEnum):
    STRUCTURALLY_RESTORABLE = "structurally_restorable"
    STRUCTURALLY_RESTORABLE_WITH_FINDINGS = "structurally_restorable_with_findings"
    NOT_STRUCTURALLY_RESTORABLE = "not_structurally_restorable"
    INDETERMINATE = "indeterminate"


def classify_dimension_status(
    coverage: Coverage,
    *,
    missing_count: int,
    extra_count: int,
    invalid_count: int,
) -> DimensionStatus:
    """Apply the shared fail-closed dimension result algebra."""
    if missing_count or invalid_count:
        return DimensionStatus.FAIL
    if coverage is not Coverage.COMPLETE:
        return DimensionStatus.INDETERMINATE
    if extra_count:
        return DimensionStatus.FINDING
    return DimensionStatus.PASS


def classify_overall_status(statuses: Collection[DimensionStatus]) -> OverallStatus:
    """Apply the shared fail-closed overall result algebra."""
    if DimensionStatus.FAIL in statuses:
        return OverallStatus.NOT_STRUCTURALLY_RESTORABLE
    if DimensionStatus.INDETERMINATE in statuses:
        return OverallStatus.INDETERMINATE
    if DimensionStatus.FINDING in statuses:
        return OverallStatus.STRUCTURALLY_RESTORABLE_WITH_FINDINGS
    return OverallStatus.STRUCTURALLY_RESTORABLE


@dataclass(frozen=True, slots=True)
class FieldRequirement:
    name: str
    value_type: str


@dataclass(frozen=True, slots=True)
class ExpectedEntity:
    entity_type: str
    entity_id: str
    required_fields: tuple[FieldRequirement, ...]

    @property
    def key(self) -> tuple[str, str]:
        return self.entity_type, self.entity_id


@dataclass(frozen=True, slots=True)
class EntityRecord:
    entity_type: str
    entity_id: str
    fields: dict[str, JsonScalar]

    @property
    def key(self) -> tuple[str, str]:
        return self.entity_type, self.entity_id


@dataclass(frozen=True, slots=True)
class Relationship:
    relation_type: str
    from_type: str
    from_id: str
    to_type: str
    to_id: str

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (
            self.relation_type,
            self.from_type,
            self.from_id,
            self.to_type,
            self.to_id,
        )


@dataclass(frozen=True, slots=True)
class ExpectedAttachment:
    attachment_id: str
    owner_type: str
    owner_id: str
    content_sha256: str

    @property
    def key(self) -> tuple[str, str, str]:
        return self.attachment_id, self.owner_type, self.owner_id


@dataclass(frozen=True, slots=True)
class AttachmentRecord:
    attachment_id: str
    owner_type: str
    owner_id: str
    relative_path: str
    content_sha256: str

    @property
    def key(self) -> tuple[str, str, str]:
        return self.attachment_id, self.owner_type, self.owner_id


@dataclass(frozen=True, slots=True)
class Permission:
    principal_id: str
    scope_type: str
    scope_id: str
    role: str

    @property
    def key(self) -> tuple[str, str, str, str]:
        return self.principal_id, self.scope_type, self.scope_id, self.role


@dataclass(frozen=True, slots=True)
class ExpectedAuditEvent:
    event_id: str
    object_type: str
    object_id: str
    action: str
    occurred_at: str

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return self.event_id, self.object_type, self.object_id, self.action, self.occurred_at


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    object_type: str
    object_id: str
    action: str
    occurred_at: str

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return self.event_id, self.object_type, self.object_id, self.action, self.occurred_at


@dataclass(frozen=True, slots=True)
class Baseline:
    drill_id: str
    source_system: str
    captured_at: str
    coverage: dict[Dimension, Coverage]
    entities: tuple[ExpectedEntity, ...]
    relationships: tuple[Relationship, ...]
    attachments: tuple[ExpectedAttachment, ...]
    permissions: tuple[Permission, ...]
    audit_events: tuple[ExpectedAuditEvent, ...]
    source_sha256: str


@dataclass(frozen=True, slots=True)
class ExportPackage:
    drill_id: str
    source_system: str
    exported_at: str
    entities: tuple[EntityRecord, ...]
    relationships: tuple[Relationship, ...]
    attachments: tuple[AttachmentRecord, ...]
    permissions: tuple[Permission, ...]
    audit_events: tuple[AuditEvent, ...]
    source_sha256: str


@dataclass(frozen=True, slots=True)
class DimensionResult:
    dimension: Dimension
    coverage: Coverage
    status: DimensionStatus
    expected_count: int
    exported_count: int
    restored_count: int
    missing_count: int
    extra_count: int
    invalid_count: int

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "coverage": self.coverage.value,
            "expected_count": self.expected_count,
            "exported_count": self.exported_count,
            "extra_count": self.extra_count,
            "invalid_count": self.invalid_count,
            "missing_count": self.missing_count,
            "name": self.dimension.value,
            "restored_count": self.restored_count,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class DrillResult:
    drill_id: str
    source_system: str
    baseline_sha256: str
    export_sha256: str
    overall_status: OverallStatus
    dimensions: tuple[DimensionResult, ...]

    def payload(self) -> dict[str, JsonValue]:
        remediation_signals = sum(
            item.missing_count + item.invalid_count for item in self.dimensions
        )
        return {
            "baseline_sha256": self.baseline_sha256,
            "decision_scope": "offline_structural_exit_drill_only",
            "dimensions": [item.to_dict() for item in self.dimensions],
            "drill_id": self.drill_id,
            "export_sha256": self.export_sha256,
            "observed_remediation_signals": remediation_signals,
            "overall_status": self.overall_status.value,
            "schema_version": "exitdrill/drill-result/v0.2",
            "source_system": self.source_system,
            "trust_limitations": cast(
                JsonValue,
                list(TRUST_LIMITATIONS),
            ),
        }
