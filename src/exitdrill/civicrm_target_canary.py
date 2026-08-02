"""Verify and normalize one closed synthetic CiviCRM target-roundtrip bundle.

The JSON evidence files are deterministic capture projections of actual APIv4
responses. They preserve selected ``values`` unchanged while deliberately omitting
unneeded public response metadata; they are not byte-raw HTTP bodies.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from exitdrill.canonical import canonical_json_bytes

if TYPE_CHECKING:
    from exitdrill.models import JsonValue

_PROFILE = "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1"
_SOURCE_PROFILE = "directus-11.17.4-civic-case/v0.1"
_BUNDLE_SCHEMA = "exitdrill/civicrm-target-roundtrip-bundle/v0.1"
_RESULT_SCHEMA = "exitdrill/civicrm-target-roundtrip-result/v0.1"
_UI_RESULT_SCHEMA = "exitdrill/civicrm-ui-surface-result/v0.1"
_SOURCE_SYSTEM = "Directus 11.17.4 synthetic civic-case sandbox"
_TARGET_SYSTEM = "CiviCRM Standalone"
_TARGET_VERSION = "6.16.2"
_DRILL_ID = "directus-civic-case-exit-001"
# This is the source observation timestamp carried through the target read-back package.
# It is not a target capture time and supplies no trusted-time claim.
_SOURCE_EXPORTED_AT = "2026-08-02T02:38:28.542Z"
_ACQUISITION_SURFACE = (
    "supported_api_v4_authenticated_private_file_readback_and_authenticated_server_rendered_ui"
)
_FILE_IDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
)
_EXPECTED_FILES = (
    "contacts.json",
    "cases.json",
    "relationships.json",
    "files.json",
    "entity-files.json",
    "identity-writer.json",
    "identity-reader.json",
    "identity-allow.json",
    "identity-deny.json",
    "permission-allow.json",
    "permission-deny.json",
    "ui-contact-summary.json",
    f"assets/{_FILE_IDS[0]}.txt",
    f"assets/{_FILE_IDS[1]}.txt",
)
_ROOT_ENTRIES = frozenset(
    {
        "assets",
        "capture-manifest.json",
        *(path for path in _EXPECTED_FILES if "/" not in path),
    }
)
_ASSET_ENTRIES = frozenset(f"{file_id}.txt" for file_id in _FILE_IDS)
_MANIFEST_KEYS = frozenset(
    {
        "acquisition_surface",
        "bundle_sha256",
        "data_mode",
        "disposition_counts",
        "files",
        "identity_separation",
        "images",
        "limitations",
        "sandbox",
        "schema_version",
        "source_profile",
        "source_normalization",
        "source_system",
        "target_profile",
        "target_system",
        "target_version",
    }
)
_IMAGES: dict[str, object] = {
    "application": (
        "civicrm/civicrm:6.16.2-php8.5@"
        "sha256:cdf062708b054670cc0f9b452e0b883840af71ce6db21615304f9e7ffe44b93f"
    ),
    "database": (
        "mariadb:10.11.18@sha256:be981e4113326ada8d6004174dd09eeaefc03094037f811182a52d4f2e737350"
    ),
}
_SANDBOX: dict[str, object] = {
    "application_empty_before_write": True,
    "attachments_private": True,
    "egress_blocked": True,
    "hibp_lookup_disabled": True,
    "mail_disabled": True,
    "no_public_ingress": True,
    "run_owned": True,
    "scheduled_jobs_disabled": True,
    "source_identity_collisions_absent": True,
}
_IDENTITY_SEPARATION: dict[str, object] = {
    "all_principals_distinct": True,
    "allow_and_deny_distinct": True,
    "permission_checks_enabled": True,
    "reader_independent_from_writer": True,
    "same_permission_query_and_object": True,
    "writer_credential_excluded_from_business_readback": True,
}
_SOURCE_NORMALIZATION: dict[str, object] = {
    "adapter_profile": _SOURCE_PROFILE,
    "attachment_bundle_sha256": "b1e24857570523f2d1606bb3ef0d32708680b369b631c623df83db95f16c177d",
    "export_sha256": "2e2a4280c7e9b2249b443a861e3eb8498a379bd462b2b4ad5637208d9698a51b",
    "schema_version": "exitdrill/directus-normalization/v0.1",
    "source_bundle_sha256": "a67048bf25c07b73aa0bff26372090c0a7e5ce77871b49259d0a96110998be49",
}
_REPRESENTED_COUNTS: dict[str, object] = {
    "attachments": 2,
    "audit_events": 0,
    "entities": 5,
    "permissions": 0,
    "relationships": 2,
}
_UNMAPPED_COUNTS: dict[str, object] = {
    "attachments": 0,
    "audit_events": 2,
    "entities": 2,
    "permissions": 2,
    "relationships": 0,
}
_TARGET_GENERATED_COUNTS: dict[str, object] = {
    "acl_entity_roles": 2,
    "acl_group_contacts": 4,
    "acl_groups": 3,
    "acl_roles": 2,
    "acls": 2,
    "case_activities": 2,
    "case_contacts": 2,
    "case_types": 1,
    "custom_field_groups": 2,
    "custom_fields": 7,
    "helper_contacts": 1,
    "principals": 4,
    "relationship_types_created": 0,
    "relationship_types_referenced": 1,
    "roles": 4,
}
_DISPOSITION_COUNTS: dict[str, object] = {
    "represented": _REPRESENTED_COUNTS,
    "target_generated": _TARGET_GENERATED_COUNTS,
    "unmapped": _UNMAPPED_COUNTS,
}
_BUNDLE_LIMITATIONS = (
    "operator_asserted_execution_context",
    "bundle_is_unsigned_and_unauthenticated",
    "synthetic_fixture_only",
    "source_capture_is_not_a_vendor_native_export",
    "does_not_prove_operational_equivalence",
    "server_rendered_ui_does_not_prove_browser_interaction",
    "manage_case_and_case_workflow_not_observed",
)
_RESULT_LIMITATIONS = (
    "synthetic_fixture_only",
    "target_evidence_is_unsigned_and_unauthenticated",
    "source_capture_is_not_a_vendor_native_export",
    "does_not_prove_operational_equivalence",
    "does_not_prove_cutover_or_source_deletion",
    "does_not_prove_permission_principal_equivalence",
    "source_permissions_and_audit_history_are_not_restored",
    "target_scaffolding_is_not_source_data",
    "api_probes_do_not_prove_ui_usability",
    "target_version_and_execution_context_are_operator_asserted",
)
_UI_RESULT_LIMITATIONS = (
    "synthetic_fixture_only",
    "target_evidence_is_unsigned_and_unauthenticated",
    "server_rendered_html_projection_only",
    "does_not_prove_browser_interaction_or_javascript_behavior",
    "does_not_prove_accessibility_or_end_to_end_task_completion",
    "manage_case_and_case_workflow_not_observed",
    "does_not_prove_operational_equivalence",
    "target_version_and_execution_context_are_operator_asserted",
)
_CONTACT_KEYS = frozenset(
    {
        "display_name",
        "exitdrill_person_profile.source_active",
        "exitdrill_person_profile.source_display_name",
        "exitdrill_person_profile.source_id",
        "id",
    }
)
_CASE_KEYS = frozenset(
    {
        "case_type_id:name",
        "exitdrill_case_profile.source_document_id",
        "exitdrill_case_profile.source_id",
        "exitdrill_case_profile.source_priority",
        "exitdrill_case_profile.source_status",
        "id",
        "start_date",
        "status_id:name",
        "subject",
    }
)
_RELATIONSHIP_TYPE_FIELD = "relationship_type_id.name_a_b"
_RELATIONSHIP_KEYS = frozenset(
    {
        "case_id",
        "contact_id_a",
        "contact_id_b",
        "description",
        "id",
        "is_active",
        _RELATIONSHIP_TYPE_FIELD,
    }
)
_FILE_KEYS = frozenset({"description", "file_name", "id", "is_public", "mime_type"})
_ENTITY_FILE_KEYS = frozenset({"entity_id", "entity_table", "file_id", "id"})
_PERMISSION_VALUE_KEYS = frozenset({"display_name", "id"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_JSON_BYTES = 512 * 1024
_MAX_ASSET_BYTES = 16 * 1024 * 1024
_MAX_BUNDLE_BYTES = 32 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 20_000
_MAX_INTEGER = 9_223_372_036_854_775_807


class CiviCRMTargetCanaryError(ValueError):
    """Raised when target evidence is outside the one pinned CiviCRM profile."""


def _fail(message: str) -> CiviCRMTargetCanaryError:
    return CiviCRMTargetCanaryError(message)


def _exact_keys(
    value: Mapping[str, object], expected: set[str] | frozenset[str], where: str
) -> None:
    if set(value) != set(expected):
        raise _fail(f"{where} has an invalid field set")


def _object(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _fail(f"{where} must be an object")
    return cast(dict[str, object], value)


def _array(value: object, where: str, *, length: int | None = None) -> list[object]:
    if not isinstance(value, list):
        raise _fail(f"{where} must be an array")
    result = cast(list[object], value)
    if length is not None and len(result) != length:
        raise _fail(f"{where} must contain exactly {length} items")
    return result


def _string(value: object, where: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise _fail(f"{where} must be a non-empty trimmed string")
    if len(value) > max_length:
        raise _fail(f"{where} exceeds its length limit")
    return value


def _source_id(value: object, where: str) -> str:
    result = _string(value, where, max_length=128)
    if not _SOURCE_ID.fullmatch(result):
        raise _fail(f"{where} must be a stable source identifier")
    return result


def _uuid(value: object, where: str) -> str:
    result = _string(value, where, max_length=36)
    if not _UUID.fullmatch(result):
        raise _fail(f"{where} must be a lowercase UUID")
    return result


def _integer(value: object, where: str, *, minimum: int = 0) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > _MAX_INTEGER
    ):
        raise _fail(f"{where} must be an integer in the supported range")
    return value


def _boolean(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise _fail(f"{where} must be a boolean")
    return value


def _sha256(value: object, where: str) -> str:
    result = _string(value, where, max_length=64)
    if not _SHA256.fullmatch(result):
        raise _fail(f"{where} must be a lowercase SHA-256 digest")
    return result


def _require_literal(value: object, expected: object, where: str) -> None:
    if type(value) is not type(expected):
        raise _fail(f"{where} does not match the pinned profile")
    if isinstance(expected, dict):
        actual = cast(dict[str, object], value)
        _exact_keys(actual, set(expected), where)
        for key, nested in expected.items():
            _require_literal(actual[key], nested, f"{where}.{key}")
    elif isinstance(expected, list):
        actual_list = cast(list[object], value)
        if len(actual_list) != len(expected):
            raise _fail(f"{where} does not match the pinned profile")
        for index, nested in enumerate(expected):
            _require_literal(actual_list[index], nested, f"{where}[{index}]")
    elif value != expected:
        raise _fail(f"{where} does not match the pinned profile")


def _json_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _fail("duplicate JSON object key is not permitted")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise _fail(f"non-finite JSON number is not permitted: {value}")


def _validate_json_bounds(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            raise _fail("JSON exceeds the node limit")
        if isinstance(current, float) and not math.isfinite(current):
            raise _fail("non-finite JSON number is not permitted")
        if isinstance(current, dict | list):
            if depth >= _MAX_JSON_DEPTH:
                raise _fail("JSON exceeds the nesting limit")
            children = current.values() if isinstance(current, dict) else current
            stack.extend((child, depth + 1) for child in children)


def _decode_json(document: bytes, where: str) -> dict[str, object]:
    try:
        raw = json.loads(
            document.decode("utf-8"),
            object_pairs_hook=_json_object_pairs,
            parse_constant=_reject_json_constant,
        )
        _validate_json_bounds(raw)
    except UnicodeDecodeError as exc:
        raise _fail(f"{where} is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise _fail(f"{where} is not valid JSON") from exc
    except RecursionError as exc:
        raise _fail(f"{where} exceeds the parser nesting limit") from exc
    except CiviCRMTargetCanaryError:
        raise
    except ValueError as exc:
        raise _fail(f"{where} is not valid JSON") from exc
    return _object(raw, where)


def _read_regular_file(path: Path, *, max_bytes: int, where: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise _fail(f"{where} is not a regular file")
            document = handle.read(max_bytes + 1)
    except OSError as exc:
        raise _fail(f"{where} could not be read as a regular file") from exc
    if len(document) > max_bytes:
        raise _fail(f"{where} exceeds its byte limit")
    return document


def _directory_entries(
    path: Path, where: str, expected: frozenset[str]
) -> dict[str, os.DirEntry[str]]:
    result: dict[str, os.DirEntry[str]] = {}
    try:
        with os.scandir(path) as iterator:
            for entry in iterator:
                if entry.name not in expected or entry.name in result:
                    raise _fail(f"{where} has an unexpected entry set")
                result[entry.name] = entry
    except OSError as exc:
        raise _fail(f"{where} could not be inspected") from exc
    if set(result) != expected:
        raise _fail(f"{where} has an unexpected entry set")
    return result


def _require_closed_bundle(root: Path, manifest_path: Path) -> None:
    if manifest_path.name != "capture-manifest.json":
        raise _fail("manifest must be named capture-manifest.json")
    if root.is_symlink() or manifest_path.is_symlink():
        raise _fail("bundle paths must not be symbolic links")
    if not root.is_dir():
        raise _fail("bundle root must be a directory")
    root_entries = _directory_entries(root, "bundle root", _ROOT_ENTRIES)
    for name, entry in root_entries.items():
        if entry.is_symlink():
            raise _fail("bundle entries must not be symbolic links")
        is_assets = name == "assets"
        if is_assets != entry.is_dir(follow_symlinks=False):
            raise _fail("bundle entry has an unexpected file type")
        if not is_assets and not entry.is_file(follow_symlinks=False):
            raise _fail("bundle entry is not a regular file")
    asset_entries = _directory_entries(root / "assets", "asset directory", _ASSET_ENTRIES)
    if any(
        entry.is_symlink() or not entry.is_file(follow_symlinks=False)
        for entry in asset_entries.values()
    ):
        raise _fail("asset entries must be regular files")


def _parse_manifest(document: bytes) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest = _decode_json(document, "capture manifest")
    _exact_keys(manifest, _MANIFEST_KEYS, "capture manifest")
    constants: tuple[tuple[str, object], ...] = (
        ("acquisition_surface", _ACQUISITION_SURFACE),
        ("data_mode", "synthetic_only"),
        ("disposition_counts", _DISPOSITION_COUNTS),
        ("identity_separation", _IDENTITY_SEPARATION),
        ("images", _IMAGES),
        ("limitations", list(_BUNDLE_LIMITATIONS)),
        ("sandbox", _SANDBOX),
        ("schema_version", _BUNDLE_SCHEMA),
        ("source_profile", _SOURCE_PROFILE),
        ("source_normalization", _SOURCE_NORMALIZATION),
        ("source_system", _SOURCE_SYSTEM),
        ("target_profile", _PROFILE),
        ("target_system", _TARGET_SYSTEM),
        ("target_version", _TARGET_VERSION),
    )
    for field, expected in constants:
        _require_literal(manifest[field], expected, f"capture manifest {field}")
    _sha256(manifest["bundle_sha256"], "capture manifest bundle_sha256")
    raw_files = _array(manifest["files"], "capture manifest files", length=len(_EXPECTED_FILES))
    files: list[dict[str, object]] = []
    for index, raw in enumerate(raw_files):
        where = f"capture manifest files[{index}]"
        item = _object(raw, where)
        _exact_keys(item, {"bytes", "path", "sha256"}, where)
        files.append(
            {
                "bytes": _integer(item["bytes"], f"{where}.bytes"),
                "path": _string(item["path"], f"{where}.path", max_length=128),
                "sha256": _sha256(item["sha256"], f"{where}.sha256"),
            }
        )
    if tuple(cast(str, item["path"]) for item in files) != _EXPECTED_FILES:
        raise _fail("capture manifest file list does not match the pinned profile")
    expected_bundle = hashlib.sha256(canonical_json_bytes(files)).hexdigest()
    if manifest["bundle_sha256"] != expected_bundle:
        raise _fail("capture manifest bundle digest does not match its file inventory")
    return manifest, files


def _read_verified_bundle(root: Path, files: Sequence[Mapping[str, object]]) -> dict[str, bytes]:
    documents: dict[str, bytes] = {}
    total = 0
    for item in files:
        relative = cast(str, item["path"])
        limit = _MAX_ASSET_BYTES if relative.startswith("assets/") else _MAX_JSON_BYTES
        document = _read_regular_file(root / relative, max_bytes=limit, where=relative)
        total += len(document)
        if total > _MAX_BUNDLE_BYTES:
            raise _fail("bundle exceeds its total byte limit")
        if len(document) != item["bytes"]:
            raise _fail(f"{relative} byte size does not match the capture manifest")
        if hashlib.sha256(document).hexdigest() != item["sha256"]:
            raise _fail(f"{relative} digest does not match the capture manifest")
        documents[relative] = document
    return documents


def _api_values(
    document: bytes,
    where: str,
    *,
    allowed_lengths: frozenset[int],
) -> list[object]:
    response = _decode_json(document, where)
    base_keys = {"count", "countFetched", "values"}
    if set(response) not in (base_keys, {*base_keys, "countMatched"}):
        raise _fail(f"{where} has an invalid field set")
    values = _array(response["values"], f"{where}.values")
    if len(values) not in allowed_lengths:
        expected = ", ".join(str(item) for item in sorted(allowed_lengths))
        raise _fail(f"{where}.values must contain one of these item counts: {expected}")
    counts = [
        _integer(response["count"], f"{where}.count"),
        _integer(response["countFetched"], f"{where}.countFetched"),
    ]
    if "countMatched" in response:
        counts.append(_integer(response["countMatched"], f"{where}.countMatched"))
    if any(count != len(values) for count in counts):
        raise _fail(f"{where} counts do not match its values")
    return values


def _parse_identity(document: bytes, purpose: str) -> tuple[int, int]:
    where = f"{purpose} identity"
    identity = _decode_json(document, where)
    _exact_keys(identity, {"contact_id", "cred", "flow", "user_id"}, where)
    if identity["flow"] != "header" or identity["cred"] != "pass":
        raise _fail(f"{where} does not match the pinned AuthX profile")
    return (
        _integer(identity["contact_id"], f"{where}.contact_id", minimum=1),
        _integer(identity["user_id"], f"{where}.user_id", minimum=1),
    )


def _parse_identities(documents: Mapping[str, bytes]) -> set[int]:
    identities = [
        _parse_identity(documents[f"identity-{purpose}.json"], purpose)
        for purpose in ("writer", "reader", "allow", "deny")
    ]
    contact_ids = {item[0] for item in identities}
    user_ids = {item[1] for item in identities}
    if len(contact_ids) != 4 or len(user_ids) != 4:
        raise _fail("writer, reader, allow, and deny identities must be distinct")
    return contact_ids


def _parse_contacts(
    document: bytes,
) -> tuple[list[dict[str, JsonValue]], dict[int, str]]:
    entities: list[dict[str, JsonValue]] = []
    source_by_target: dict[int, str] = {}
    source_ids: set[str] = set()
    values = _api_values(document, "contacts response", allowed_lengths=frozenset({3}))
    for index, raw in enumerate(values):
        where = f"contacts response.values[{index}]"
        item = _object(raw, where)
        _exact_keys(item, _CONTACT_KEYS, where)
        target_id = _integer(item["id"], f"{where}.id", minimum=1)
        source_id = _source_id(
            item["exitdrill_person_profile.source_id"],
            f"{where}.exitdrill_person_profile.source_id",
        )
        if target_id in source_by_target or source_id in source_ids:
            raise _fail("contact target and source identifiers must be unique")
        native_display_name = _string(item["display_name"], f"{where}.display_name")
        source_display_name = _string(
            item["exitdrill_person_profile.source_display_name"],
            f"{where}.exitdrill_person_profile.source_display_name",
        )
        if native_display_name != source_display_name:
            raise _fail("target and source contact display names must match")
        source_by_target[target_id] = source_id
        source_ids.add(source_id)
        entities.append(
            {
                "fields": {
                    "active": _boolean(
                        item["exitdrill_person_profile.source_active"],
                        f"{where}.exitdrill_person_profile.source_active",
                    ),
                    "display_name": source_display_name,
                },
                "id": source_id,
                "type": "person",
            }
        )
    if source_ids != {"1", "2", "3"}:
        raise _fail("contacts do not match the pinned source identity inventory")
    return entities, source_by_target


def _parse_cases(
    document: bytes,
) -> tuple[list[dict[str, JsonValue]], dict[int, str]]:
    entities: list[dict[str, JsonValue]] = []
    source_by_target: dict[int, str] = {}
    source_ids: set[str] = set()
    document_ids: set[str] = set()
    values = _api_values(document, "cases response", allowed_lengths=frozenset({2}))
    for index, raw in enumerate(values):
        where = f"cases response.values[{index}]"
        item = _object(raw, where)
        _exact_keys(item, _CASE_KEYS, where)
        if item["case_type_id:name"] != "exitdrill_civic_case":
            raise _fail("case type does not match the pinned target configuration")
        if item["status_id:name"] != "Open":
            raise _fail("target case status does not match the pinned target configuration")
        _string(item["subject"], f"{where}.subject")
        _string(item["start_date"], f"{where}.start_date", max_length=64)
        target_id = _integer(item["id"], f"{where}.id", minimum=1)
        source_id = _source_id(
            item["exitdrill_case_profile.source_id"],
            f"{where}.exitdrill_case_profile.source_id",
        )
        document_id = _uuid(
            item["exitdrill_case_profile.source_document_id"],
            f"{where}.exitdrill_case_profile.source_document_id",
        )
        if target_id in source_by_target or source_id in source_ids or document_id in document_ids:
            raise _fail("case target, source, and document identifiers must be unique")
        source_by_target[target_id] = source_id
        source_ids.add(source_id)
        document_ids.add(document_id)
        entities.append(
            {
                "fields": {
                    "document": document_id,
                    "priority": _integer(
                        item["exitdrill_case_profile.source_priority"],
                        f"{where}.exitdrill_case_profile.source_priority",
                    ),
                    "status": _source_id(
                        item["exitdrill_case_profile.source_status"],
                        f"{where}.exitdrill_case_profile.source_status",
                    ),
                },
                "id": source_id,
                "type": "case",
            }
        )
    if source_ids != {"1", "2"} or document_ids != set(_FILE_IDS):
        raise _fail("cases do not match the pinned source identity inventory")
    return entities, source_by_target


def _parse_relationships(
    document: bytes,
    person_by_target: Mapping[int, str],
    case_by_target: Mapping[int, str],
    identity_contact_ids: set[int],
) -> list[dict[str, JsonValue]]:
    relationships: list[dict[str, JsonValue]] = []
    target_ids: set[int] = set()
    keys: set[tuple[int, int]] = set()
    helper_ids: set[int] = set()
    values = _api_values(document, "relationships response", allowed_lengths=frozenset({2}))
    for index, raw in enumerate(values):
        where = f"relationships response.values[{index}]"
        item = _object(raw, where)
        _exact_keys(item, _RELATIONSHIP_KEYS, where)
        target_id = _integer(item["id"], f"{where}.id", minimum=1)
        case_id = _integer(item["case_id"], f"{where}.case_id", minimum=1)
        helper_id = _integer(item["contact_id_a"], f"{where}.contact_id_a", minimum=1)
        person_id = _integer(item["contact_id_b"], f"{where}.contact_id_b", minimum=1)
        if item[_RELATIONSHIP_TYPE_FIELD] != "Case Coordinator is":
            raise _fail("relationship type does not match the pinned target configuration")
        if item["description"] != "ExitDrill assigned_to":
            raise _fail("relationship description does not match the pinned target profile")
        if not _boolean(item["is_active"], f"{where}.is_active"):
            raise _fail("pinned target relationships must be active")
        key = (case_id, person_id)
        if target_id in target_ids or key in keys:
            raise _fail("target relationship identifiers and endpoints must be unique")
        if case_id not in case_by_target or person_id not in person_by_target:
            raise _fail("target relationship references an unknown source-mapped entity")
        target_ids.add(target_id)
        keys.add(key)
        helper_ids.add(helper_id)
        relationships.append(
            {
                "from_id": case_by_target[case_id],
                "from_type": "case",
                "to_id": person_by_target[person_id],
                "to_type": "person",
                "type": "assigned_to",
            }
        )
    if (
        len(helper_ids) != 1
        or next(iter(helper_ids)) in person_by_target
        or next(iter(helper_ids)) in identity_contact_ids
    ):
        raise _fail("relationships must use one target-only helper contact")
    return relationships


def _parse_files(document: bytes) -> dict[int, str]:
    source_by_target: dict[int, str] = {}
    source_ids: set[str] = set()
    values = _api_values(document, "files response", allowed_lengths=frozenset({2}))
    for index, raw in enumerate(values):
        where = f"files response.values[{index}]"
        item = _object(raw, where)
        _exact_keys(item, _FILE_KEYS, where)
        target_id = _integer(item["id"], f"{where}.id", minimum=1)
        source_id = _uuid(item["description"], f"{where}.description")
        filename = _string(item["file_name"], f"{where}.file_name")
        if "/" in filename or "\\" in filename or not filename.endswith(".txt"):
            raise _fail("target file name must be a plain .txt filename")
        expected_filename = f"{source_id.replace('-', '_')}.txt"
        if filename != expected_filename:
            raise _fail("target file name does not match pinned CiviCRM normalization")
        if item["mime_type"] != "text/plain" or _boolean(item["is_public"], f"{where}.is_public"):
            raise _fail("target files must be private text/plain attachments")
        if target_id in source_by_target or source_id in source_ids:
            raise _fail("target and source file identifiers must be unique")
        source_by_target[target_id] = source_id
        source_ids.add(source_id)
    if source_ids != set(_FILE_IDS):
        raise _fail("files do not match the pinned source attachment inventory")
    return source_by_target


def _parse_entity_files(
    document: bytes,
    file_by_target: Mapping[int, str],
    case_by_target: Mapping[int, str],
    documents: Mapping[str, bytes],
) -> tuple[list[dict[str, JsonValue]], list[tuple[str, bytes]]]:
    attachments: list[dict[str, JsonValue]] = []
    copies: list[tuple[str, bytes]] = []
    target_ids: set[int] = set()
    linked_files: set[int] = set()
    values = _api_values(document, "entity-files response", allowed_lengths=frozenset({2}))
    for index, raw in enumerate(values):
        where = f"entity-files response.values[{index}]"
        item = _object(raw, where)
        _exact_keys(item, _ENTITY_FILE_KEYS, where)
        target_id = _integer(item["id"], f"{where}.id", minimum=1)
        file_id = _integer(item["file_id"], f"{where}.file_id", minimum=1)
        case_id = _integer(item["entity_id"], f"{where}.entity_id", minimum=1)
        if item["entity_table"] != "civicrm_case":
            raise _fail("entity-file association must target civicrm_case")
        if target_id in target_ids or file_id in linked_files:
            raise _fail("entity-file identifiers and file associations must be unique")
        if file_id not in file_by_target or case_id not in case_by_target:
            raise _fail("entity-file association references an unknown target record")
        target_ids.add(target_id)
        linked_files.add(file_id)
        source_id = file_by_target[file_id]
        content = documents[f"assets/{source_id}.txt"]
        attachments.append(
            {
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "id": source_id,
                "owner_id": case_by_target[case_id],
                "owner_type": "case",
                "relative_path": f"attachments/{source_id}.txt",
            }
        )
        copies.append((source_id, content))
    if linked_files != set(file_by_target):
        raise _fail("entity-files do not cover the pinned target file inventory")
    return attachments, copies


def _permission_values(
    document: bytes,
    where: str,
    person_by_target: Mapping[int, str],
) -> list[object]:
    values = _api_values(document, where, allowed_lengths=frozenset({0, 1}))
    if not values:
        return values
    item = _object(values[0], f"{where}.values[0]")
    _exact_keys(item, _PERMISSION_VALUE_KEYS, f"{where}.values[0]")
    target_id = _integer(item["id"], f"{where}.values[0].id", minimum=1)
    display_name = _string(item["display_name"], f"{where}.values[0].display_name")
    if person_by_target.get(target_id) != "1" or display_name != "Synthetic Person Alpha":
        raise _fail(f"{where} does not address the pinned permission-probe object")
    return values


def _probe_result(probe_id: str, state: str, evidence_kind: str) -> dict[str, JsonValue]:
    return {"evidence_kind": evidence_kind, "id": probe_id, "state": state}


def _parse_ui_surface(document: bytes, expected: Mapping[str, object], where: str) -> None:
    surface = _decode_json(document, where)
    _require_literal(surface, expected, where)


def _ui_surface_result() -> dict[str, JsonValue]:
    surfaces = [
        _probe_result(
            "contact_summary",
            "observed",
            "authenticated_server_rendered_html_projection",
        ),
    ]
    return {
        "decision_scope": "pinned_synthetic_ui_surface_only",
        "limitations": list(_UI_RESULT_LIMITATIONS),
        "schema_version": _UI_RESULT_SCHEMA,
        "surface_results": cast("list[JsonValue]", surfaces),
        "target_profile": _PROFILE,
    }


def _target_result(allow_count: int, deny_count: int) -> dict[str, JsonValue]:
    probes = [
        _probe_result("record_lookup", "pass", "independent_api_v4_readback"),
        _probe_result("relationship_traversal", "pass", "independent_api_v4_relationship_readback"),
        _probe_result("attachment_retrieval", "pass", "authenticated_private_file_bytes"),
        _probe_result(
            "authorized_access",
            "pass" if allow_count == 1 else "fail",
            "permission_enforced_api_v4_contact_get",
        ),
        _probe_result(
            "unauthorized_denial",
            "pass" if deny_count == 0 else "fail",
            "permission_enforced_api_v4_contact_get",
        ),
    ]
    return {
        "decision_scope": "pinned_synthetic_target_roundtrip_only",
        "limitations": list(_RESULT_LIMITATIONS),
        "probe_results": cast("list[JsonValue]", probes),
        "represented_counts": cast("dict[str, JsonValue]", dict(_REPRESENTED_COUNTS)),
        "schema_version": _RESULT_SCHEMA,
        "source_profile": _SOURCE_PROFILE,
        "target_generated_counts": cast("dict[str, JsonValue]", dict(_TARGET_GENERATED_COUNTS)),
        "target_profile": _PROFILE,
        "unmapped_counts": cast("dict[str, JsonValue]", dict(_UNMAPPED_COUNTS)),
    }


def _sort_export_lists(export: dict[str, JsonValue]) -> None:
    for key in ("entities", "relationships", "attachments", "permissions", "audit_events"):
        items = cast(list[object], export[key])
        items.sort(key=canonical_json_bytes)


def _build_output(
    documents: Mapping[str, bytes],
) -> tuple[
    dict[str, JsonValue],
    list[tuple[str, bytes]],
    dict[str, JsonValue],
    dict[str, JsonValue],
]:
    identity_contact_ids = _parse_identities(documents)
    people, person_by_target = _parse_contacts(documents["contacts.json"])
    cases, case_by_target = _parse_cases(documents["cases.json"])
    if identity_contact_ids & set(person_by_target):
        raise _fail("probe identities must not collide with source-mapped contacts")
    relationships = _parse_relationships(
        documents["relationships.json"],
        person_by_target,
        case_by_target,
        identity_contact_ids,
    )
    file_by_target = _parse_files(documents["files.json"])
    attachments, copies = _parse_entity_files(
        documents["entity-files.json"], file_by_target, case_by_target, documents
    )
    allow_values = _permission_values(
        documents["permission-allow.json"], "permission-allow response", person_by_target
    )
    deny_values = _permission_values(
        documents["permission-deny.json"], "permission-deny response", person_by_target
    )
    _parse_ui_surface(
        documents["ui-contact-summary.json"],
        {
            "authenticated_identity": "reader",
            "http_status": 200,
            "observed_labels": ["Cases", "Synthetic Person Alpha"],
            "observed_regions": ["contact_summary"],
            "route": "civicrm/contact/view",
            "surface": "contact_summary",
        },
        "contact-summary UI projection",
    )
    export: dict[str, JsonValue] = {
        "attachments": cast("list[JsonValue]", attachments),
        "audit_events": [],
        "drill_id": _DRILL_ID,
        "entities": cast("list[JsonValue]", [*people, *cases]),
        "exported_at": _SOURCE_EXPORTED_AT,
        "permissions": [],
        "relationships": cast("list[JsonValue]", relationships),
        "schema_version": "exitdrill/export/v0.1",
        "source_system": _SOURCE_SYSTEM,
    }
    _sort_export_lists(export)
    return (
        export,
        copies,
        _target_result(len(allow_values), len(deny_values)),
        _ui_surface_result(),
    )


def _write_output(
    out_dir: Path,
    export_document: bytes,
    copies: Sequence[tuple[str, bytes]],
    result: Mapping[str, JsonValue],
    ui_result: Mapping[str, JsonValue],
) -> None:
    parent = out_dir.parent
    if not parent.exists() or not parent.is_dir():
        raise _fail("output parent must be an existing directory")
    try:
        temporary = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.tmp-", dir=parent))
    except OSError as exc:
        raise _fail("target output could not be materialized") from exc
    try:
        attachment_dir = temporary / "export-files" / "attachments"
        attachment_dir.mkdir(parents=True)
        (temporary / "export.json").write_bytes(export_document)
        for source_id, content in copies:
            (attachment_dir / f"{source_id}.txt").write_bytes(content)
        (temporary / "target-result.json").write_bytes(canonical_json_bytes(result) + b"\n")
        (temporary / "ui-surface-result.json").write_bytes(canonical_json_bytes(ui_result) + b"\n")
        if out_dir.exists() or out_dir.is_symlink():
            raise _fail("output directory already exists")
        temporary.rename(out_dir)
    except CiviCRMTargetCanaryError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(temporary, ignore_errors=True)
        raise _fail("target output could not be materialized") from exc
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def normalize_civicrm_target_canary(manifest_path: Path, out_dir: Path) -> dict[str, JsonValue]:
    """Validate and atomically normalize the pinned synthetic CiviCRM target bundle.

    The neutral export inherits the pinned source observation timestamp. It does not
    represent a target capture time and the returned aggregate result makes no trusted-time
    claim.
    """
    if out_dir.exists() or out_dir.is_symlink():
        raise _fail("output directory already exists")
    root = manifest_path.parent
    _require_closed_bundle(root, manifest_path)
    try:
        resolved_root = root.resolve(strict=True)
        resolved_out = out_dir.resolve(strict=False)
    except OSError as exc:
        raise _fail("bundle or output location could not be resolved") from exc
    if resolved_out == resolved_root or resolved_out.is_relative_to(resolved_root):
        raise _fail("output directory must be outside the capture bundle")
    if resolved_out.exists() or resolved_out.is_symlink():
        raise _fail("output directory already exists")
    manifest_document = _read_regular_file(
        manifest_path,
        max_bytes=_MAX_MANIFEST_BYTES,
        where="capture manifest",
    )
    _, files = _parse_manifest(manifest_document)
    documents = _read_verified_bundle(root, files)
    export, copies, result, ui_result = _build_output(documents)
    export_document = canonical_json_bytes(export) + b"\n"
    _write_output(resolved_out, export_document, copies, result, ui_result)
    return result
