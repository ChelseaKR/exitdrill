"""Normalize one pinned synthetic Directus canary into ExitDrill's export model."""

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
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from exitdrill.canonical import canonical_json_bytes

if TYPE_CHECKING:
    from exitdrill.models import JsonValue

_PROFILE = "directus-11.17.4-civic-case/v0.1"
_SOURCE_VERSION = "11.17.4"
_SOURCE_SYSTEM = "Directus 11.17.4 synthetic civic-case sandbox"
_BUNDLE_SCHEMA = "exitdrill/directus-native-bundle/v0.1"
_NORMALIZATION_SCHEMA = "exitdrill/directus-normalization/v0.1"
_ACQUISITION_SURFACE = "documented_first_party_rest_api"
_LIMITATIONS = (
    "operator_asserted_acquisition_context",
    "bundle_is_unsigned_and_unauthenticated",
    "does_not_prove_export_completeness",
    "does_not_prove_operational_equivalence",
)
_OUTPUT_LIMITATIONS = (
    "synthetic_fixture_only",
    "source_bundle_is_unsigned_and_unauthenticated",
    "normalization_does_not_prove_source_export_completeness",
    "normalization_does_not_prove_operational_equivalence",
)
_FILE_IDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
)
_EXPECTED_FILES = (
    "activity.json",
    f"assets/{_FILE_IDS[0]}.txt",
    f"assets/{_FILE_IDS[1]}.txt",
    "case-people.json",
    "cases.json",
    "files.json",
    "people.json",
    "permissions.json",
    "policies.json",
    "schema.json",
)
_ROOT_ENTRIES = frozenset(
    {
        "activity.json",
        "assets",
        "capture-manifest.json",
        "case-people.json",
        "cases.json",
        "files.json",
        "people.json",
        "permissions.json",
        "policies.json",
        "schema.json",
    }
)
_ASSET_ENTRIES = frozenset(f"{item}.txt" for item in _FILE_IDS)
_MANIFEST_KEYS = frozenset(
    {
        "acquisition_surface",
        "adapter_profile",
        "bundle_sha256",
        "data_mode",
        "drill_id",
        "exported_at",
        "files",
        "isolated_sandbox",
        "limitations",
        "production_data_allowed",
        "schema_version",
        "source_system",
        "source_version",
    }
)
_COLLECTIONS = frozenset({"exitdrill_case_people", "exitdrill_cases", "exitdrill_people"})
_REQUIRED_FIELDS = {
    ("exitdrill_case_people", "id"): "integer",
    ("exitdrill_case_people", "case_id"): "integer",
    ("exitdrill_case_people", "person_id"): "integer",
    ("exitdrill_case_people", "relation_type"): "string",
    ("exitdrill_cases", "id"): "integer",
    ("exitdrill_cases", "status"): "string",
    ("exitdrill_cases", "priority"): "integer",
    ("exitdrill_cases", "document"): "uuid",
    ("exitdrill_people", "id"): "integer",
    ("exitdrill_people", "display_name"): "string",
    ("exitdrill_people", "active"): "boolean",
}
_COLLECTION_META_KEYS = frozenset(
    {
        "accountability",
        "archive_app_filter",
        "archive_field",
        "archive_value",
        "collapse",
        "collection",
        "color",
        "display_template",
        "group",
        "hidden",
        "icon",
        "item_duplication_fields",
        "note",
        "preview_url",
        "singleton",
        "sort",
        "sort_field",
        "translations",
        "unarchive_value",
        "versioning",
    }
)
_FIELD_META_KEYS = frozenset(
    {
        "collection",
        "conditions",
        "display",
        "display_options",
        "field",
        "group",
        "hidden",
        "interface",
        "note",
        "options",
        "readonly",
        "required",
        "searchable",
        "sort",
        "special",
        "translations",
        "validation",
        "validation_message",
        "width",
    }
)
_FIELD_SCHEMA_KEYS = frozenset(
    {
        "data_type",
        "default_value",
        "foreign_key_column",
        "foreign_key_table",
        "generation_expression",
        "has_auto_increment",
        "is_generated",
        "is_indexed",
        "is_nullable",
        "is_primary_key",
        "is_unique",
        "max_length",
        "name",
        "numeric_precision",
        "numeric_scale",
        "table",
    }
)
_RELATION_META_KEYS = frozenset(
    {
        "junction_field",
        "many_collection",
        "many_field",
        "one_allowed_collections",
        "one_collection",
        "one_collection_field",
        "one_deselect_action",
        "one_field",
        "sort_field",
    }
)
_RELATION_SCHEMA_KEYS = frozenset(
    {
        "column",
        "constraint_name",
        "foreign_key_column",
        "foreign_key_table",
        "on_delete",
        "on_update",
        "table",
    }
)
_RELATIONS = frozenset(
    {
        ("exitdrill_case_people", "case_id", "exitdrill_cases"),
        ("exitdrill_case_people", "person_id", "exitdrill_people"),
        ("exitdrill_cases", "document", "directus_files"),
    }
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_JSON_BYTES = 512 * 1024
_MAX_ASSET_BYTES = 16 * 1024 * 1024
_MAX_BUNDLE_BYTES = 32 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 20_000
_MAX_SQLITE_INTEGER = 9_223_372_036_854_775_807
_SCHEMA_SHA256 = "8bf86c28c528b46e6065d2790e2b4acf7517ab54ddb409f5afd077e50d9c5b5a"


class DirectusCanaryError(ValueError):
    """Raised when a Directus canary bundle is outside the pinned profile."""


def _fail(message: str) -> DirectusCanaryError:
    return DirectusCanaryError(message)


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


def _identifier(value: object, where: str) -> str:
    result = _string(value, where, max_length=128)
    if not _IDENTIFIER.fullmatch(result):
        raise _fail(f"{where} must be a stable identifier")
    return result


def _integer(value: object, where: str, *, minimum: int = 0) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > _MAX_SQLITE_INTEGER
    ):
        raise _fail(f"{where} must be an integer in the supported SQLite range")
    return value


def _boolean(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise _fail(f"{where} must be a boolean")
    return value


def _directus_boolean(value: object, where: str) -> bool:
    if not isinstance(value, int) or isinstance(value, bool) or value not in (0, 1):
        raise _fail(f"{where} must be the Directus integer boolean 0 or 1")
    return bool(value)


def _optional_object(value: object, where: str) -> dict[str, object] | None:
    if value is None:
        return None
    return _object(value, where)


def _timestamp(value: object, where: str) -> str:
    result = _string(value, where, max_length=64)
    try:
        parsed = datetime.fromisoformat(result)
    except ValueError as exc:
        raise _fail(f"{where} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _fail(f"{where} must include a UTC offset")
    return result


def _sha256(value: object, where: str) -> str:
    result = _string(value, where, max_length=64)
    if not _SHA256.fullmatch(result):
        raise _fail(f"{where} must be a lowercase SHA-256 digest")
    return result


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
    except DirectusCanaryError:
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
    path: Path,
    where: str,
    expected: frozenset[str],
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


def _validate_root_entries(entries: Mapping[str, os.DirEntry[str]]) -> None:
    if set(entries) != _ROOT_ENTRIES:
        raise _fail("bundle root has an unexpected entry set")
    for name, entry in entries.items():
        if entry.is_symlink():
            raise _fail("bundle entries must not be symbolic links")
        expected_directory = name == "assets"
        if expected_directory != entry.is_dir(follow_symlinks=False):
            raise _fail("bundle entry has an unexpected file type")
        if not expected_directory and not entry.is_file(follow_symlinks=False):
            raise _fail("bundle entry is not a regular file")


def _require_closed_bundle(root: Path, manifest_path: Path) -> None:
    if manifest_path.name != "capture-manifest.json":
        raise _fail("manifest must be named capture-manifest.json")
    if root.is_symlink() or manifest_path.is_symlink():
        raise _fail("bundle paths must not be symbolic links")
    if not root.is_dir():
        raise _fail("bundle root must be a directory")
    root_entries = _directory_entries(root, "bundle root", _ROOT_ENTRIES)
    _validate_root_entries(root_entries)
    asset_entries = _directory_entries(root / "assets", "asset directory", _ASSET_ENTRIES)
    if set(asset_entries) != _ASSET_ENTRIES:
        raise _fail("asset directory has an unexpected entry set")
    if any(
        entry.is_symlink() or not entry.is_file(follow_symlinks=False)
        for entry in asset_entries.values()
    ):
        raise _fail("asset entries must be regular files")


def _parse_manifest(document: bytes) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest = _decode_json(document, "capture manifest")
    _exact_keys(manifest, _MANIFEST_KEYS, "capture manifest")
    expected_constants: tuple[tuple[str, object], ...] = (
        ("acquisition_surface", _ACQUISITION_SURFACE),
        ("adapter_profile", _PROFILE),
        ("data_mode", "synthetic_only"),
        ("isolated_sandbox", True),
        ("limitations", list(_LIMITATIONS)),
        ("production_data_allowed", False),
        ("schema_version", _BUNDLE_SCHEMA),
        ("source_system", _SOURCE_SYSTEM),
        ("source_version", _SOURCE_VERSION),
    )
    for field, expected in expected_constants:
        if manifest[field] != expected or type(manifest[field]) is not type(expected):
            raise _fail(f"capture manifest {field} does not match the pinned profile")
    _identifier(manifest["drill_id"], "capture manifest drill_id")
    _timestamp(manifest["exported_at"], "capture manifest exported_at")
    _sha256(manifest["bundle_sha256"], "capture manifest bundle_sha256")
    raw_files = _array(manifest["files"], "capture manifest files", length=len(_EXPECTED_FILES))
    files: list[dict[str, object]] = []
    for index, raw in enumerate(raw_files):
        item = _object(raw, f"capture manifest files[{index}]")
        _exact_keys(item, {"bytes", "path", "sha256"}, f"capture manifest files[{index}]")
        path = _string(item["path"], f"capture manifest files[{index}].path", max_length=128)
        size = _integer(item["bytes"], f"capture manifest files[{index}].bytes")
        digest = _sha256(item["sha256"], f"capture manifest files[{index}].sha256")
        files.append({"bytes": size, "path": path, "sha256": digest})
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


def _api_data(document: bytes, where: str, *, length: int) -> list[object]:
    response = _decode_json(document, where)
    _exact_keys(response, {"data"}, where)
    return _array(response["data"], f"{where}.data", length=length)


def _parse_people(document: bytes) -> tuple[list[dict[str, JsonValue]], set[int]]:
    entities: list[dict[str, JsonValue]] = []
    ids: set[int] = set()
    for index, raw in enumerate(_api_data(document, "people response", length=3)):
        where = f"people response.data[{index}]"
        item = _object(raw, where)
        _exact_keys(item, {"active", "display_name", "id"}, where)
        native_id = _integer(item["id"], f"{where}.id", minimum=1)
        if native_id in ids:
            raise _fail("people ids must be unique")
        ids.add(native_id)
        entities.append(
            {
                "fields": {
                    "active": _directus_boolean(item["active"], f"{where}.active"),
                    "display_name": _string(item["display_name"], f"{where}.display_name"),
                },
                "id": str(native_id),
                "type": "person",
            }
        )
    return entities, ids


def _parse_cases(
    document: bytes,
) -> tuple[list[dict[str, JsonValue]], set[int], dict[str, int]]:
    entities: list[dict[str, JsonValue]] = []
    ids: set[int] = set()
    owner_by_file: dict[str, int] = {}
    for index, raw in enumerate(_api_data(document, "cases response", length=2)):
        where = f"cases response.data[{index}]"
        item = _object(raw, where)
        _exact_keys(item, {"document", "id", "priority", "status"}, where)
        native_id = _integer(item["id"], f"{where}.id", minimum=1)
        document_id = _string(item["document"], f"{where}.document", max_length=36)
        if native_id in ids or document_id in owner_by_file:
            raise _fail("case and document identifiers must be unique")
        if document_id not in _FILE_IDS:
            raise _fail("case document is outside the pinned attachment inventory")
        ids.add(native_id)
        owner_by_file[document_id] = native_id
        entities.append(
            {
                "fields": {
                    "document": document_id,
                    "priority": _integer(item["priority"], f"{where}.priority"),
                    "status": _identifier(item["status"], f"{where}.status"),
                },
                "id": str(native_id),
                "type": "case",
            }
        )
    if set(owner_by_file) != set(_FILE_IDS):
        raise _fail("cases must reference both pinned attachments exactly once")
    return entities, ids, owner_by_file


def _parse_relationships(
    document: bytes,
    case_ids: set[int],
    person_ids: set[int],
) -> list[dict[str, JsonValue]]:
    relationships: list[dict[str, JsonValue]] = []
    native_ids: set[int] = set()
    keys: set[tuple[str, int, int]] = set()
    for index, raw in enumerate(_api_data(document, "case-people response", length=2)):
        where = f"case-people response.data[{index}]"
        item = _object(raw, where)
        _exact_keys(item, {"case_id", "id", "person_id", "relation_type"}, where)
        native_id = _integer(item["id"], f"{where}.id", minimum=1)
        case_id = _integer(item["case_id"], f"{where}.case_id", minimum=1)
        person_id = _integer(item["person_id"], f"{where}.person_id", minimum=1)
        relation_type = _identifier(item["relation_type"], f"{where}.relation_type")
        key = (relation_type, case_id, person_id)
        if native_id in native_ids or key in keys:
            raise _fail("case-person relationships must have unique identifiers and keys")
        if case_id not in case_ids or person_id not in person_ids:
            raise _fail("case-person relationship references an unknown entity")
        native_ids.add(native_id)
        keys.add(key)
        relationships.append(
            {
                "from_id": str(case_id),
                "from_type": "case",
                "to_id": str(person_id),
                "to_type": "person",
                "type": relation_type,
            }
        )
    return relationships


def _parse_files(
    document: bytes,
    assets: Mapping[str, bytes],
    owner_by_file: Mapping[str, int],
) -> tuple[list[dict[str, JsonValue]], list[tuple[str, bytes]]]:
    attachments: list[dict[str, JsonValue]] = []
    copies: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_api_data(document, "files response", length=2)):
        where = f"files response.data[{index}]"
        item = _object(raw, where)
        _exact_keys(item, {"filename_download", "filesize", "id", "type"}, where)
        file_id = _string(item["id"], f"{where}.id", max_length=36)
        if file_id not in _FILE_IDS or file_id in seen:
            raise _fail("file id is duplicated or outside the pinned attachment inventory")
        seen.add(file_id)
        if _string(item["type"], f"{where}.type") != "text/plain":
            raise _fail("pinned attachments must have text/plain media type")
        filename = _string(item["filename_download"], f"{where}.filename_download")
        if not filename.endswith(".txt") or "/" in filename or "\\" in filename:
            raise _fail("attachment download name must be a plain .txt filename")
        content = assets[f"assets/{file_id}.txt"]
        if _integer(item["filesize"], f"{where}.filesize") != len(content):
            raise _fail("file metadata size does not match captured attachment bytes")
        digest = hashlib.sha256(content).hexdigest()
        attachments.append(
            {
                "content_sha256": digest,
                "id": file_id,
                "owner_id": str(owner_by_file[file_id]),
                "owner_type": "case",
                "relative_path": f"attachments/{file_id}.txt",
            }
        )
        copies.append((file_id, content))
    if seen != set(_FILE_IDS):
        raise _fail("files response does not contain the pinned attachment inventory")
    return attachments, copies


def _parse_policy(document: bytes) -> str:
    item = _object(
        _api_data(document, "policies response", length=1)[0], "policies response.data[0]"
    )
    _exact_keys(item, {"admin_access", "app_access", "id", "name"}, "policies response.data[0]")
    policy_id = _string(item["id"], "policies response.data[0].id", max_length=36)
    if policy_id != "33333333-3333-4333-8333-333333333333":
        raise _fail("policy id does not match the pinned profile")
    _string(item["name"], "policies response.data[0].name")
    if not _boolean(item["app_access"], "policies response.data[0].app_access"):
        raise _fail("pinned policy must allow application access")
    if _boolean(item["admin_access"], "policies response.data[0].admin_access"):
        raise _fail("pinned policy must not allow administrator access")
    return policy_id


def _permission_digest(item: Mapping[str, object], where: str) -> str:
    fields_raw = _array(item["fields"], f"{where}.fields")
    fields = [_identifier(value, f"{where}.fields") for value in fields_raw]
    if not fields or len(fields) != len(set(fields)):
        raise _fail("permission fields must be a non-empty unique list")
    semantic: dict[str, object] = {
        "action": _identifier(item["action"], f"{where}.action"),
        "fields": fields,
        "permissions": _object(item["permissions"], f"{where}.permissions"),
        "presets": _optional_object(item["presets"], f"{where}.presets"),
        "validation": _optional_object(item["validation"], f"{where}.validation"),
    }
    return hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()


def _parse_permissions(document: bytes, policy_id: str) -> list[dict[str, JsonValue]]:
    permissions: list[dict[str, JsonValue]] = []
    native_ids: set[int] = set()
    collections: set[str] = set()
    for index, raw in enumerate(_api_data(document, "permissions response", length=2)):
        where = f"permissions response.data[{index}]"
        item = _object(raw, where)
        _exact_keys(
            item,
            {
                "action",
                "collection",
                "fields",
                "id",
                "permissions",
                "policy",
                "presets",
                "validation",
            },
            where,
        )
        native_id = _integer(item["id"], f"{where}.id", minimum=1)
        collection = _string(item["collection"], f"{where}.collection")
        action = _identifier(item["action"], f"{where}.action")
        if native_id in native_ids or collection in collections:
            raise _fail("permission ids and collection scopes must be unique")
        if collection not in {"exitdrill_cases", "exitdrill_people"}:
            raise _fail("permission collection is outside the pinned profile")
        if item["policy"] != policy_id or action != "read":
            raise _fail("permission policy or action does not match the pinned profile")
        native_ids.add(native_id)
        collections.add(collection)
        digest = _permission_digest(item, where)
        permissions.append(
            {
                "principal_id": f"policy:{policy_id}",
                "role": f"{action}:{digest}",
                "scope_id": collection,
                "scope_type": "directus_collection_scope",
            }
        )
    if collections != {"exitdrill_cases", "exitdrill_people"}:
        raise _fail("permissions must cover the two pinned collections")
    return permissions


def _parse_activity(document: bytes, case_ids: set[int]) -> list[dict[str, JsonValue]]:
    events: list[dict[str, JsonValue]] = []
    ids: set[int] = set()
    object_ids: set[int] = set()
    for index, raw in enumerate(_api_data(document, "activity response", length=2)):
        where = f"activity response.data[{index}]"
        item = _object(raw, where)
        _exact_keys(item, {"action", "collection", "id", "item", "timestamp"}, where)
        event_id = _integer(item["id"], f"{where}.id", minimum=1)
        item_id_raw = _identifier(item["item"], f"{where}.item")
        try:
            object_id = int(item_id_raw)
        except ValueError as exc:
            raise _fail("activity item must identify a case integer") from exc
        if event_id in ids or object_id in object_ids:
            raise _fail("activity event and object identifiers must be unique")
        if object_id not in case_ids or item["collection"] != "exitdrill_cases":
            raise _fail("activity must reference a pinned case")
        ids.add(event_id)
        object_ids.add(object_id)
        events.append(
            {
                "action": _identifier(item["action"], f"{where}.action"),
                "event_id": f"directus_activity:{event_id}",
                "object_id": str(object_id),
                "object_type": "case",
                "occurred_at": _timestamp(item["timestamp"], f"{where}.timestamp"),
            }
        )
    return events


def _schema_collection(raw: object, index: int) -> str:
    where = f"schema.data.collections[{index}]"
    item = _object(raw, where)
    _exact_keys(item, {"collection", "meta", "schema"}, where)
    name = _string(item["collection"], f"{where}.collection")
    meta = _object(item["meta"], f"{where}.meta")
    schema = _object(item["schema"], f"{where}.schema")
    _exact_keys(meta, _COLLECTION_META_KEYS, f"{where}.meta")
    _exact_keys(schema, {"name"}, f"{where}.schema")
    if meta.get("collection") != name or schema != {"name": name}:
        raise _fail("schema collection metadata is inconsistent")
    return name


def _schema_field(raw: object, index: int) -> tuple[str, str, str]:
    where = f"schema.data.fields[{index}]"
    item = _object(raw, where)
    _exact_keys(item, {"collection", "field", "meta", "schema", "type"}, where)
    collection = _string(item["collection"], f"{where}.collection")
    field = _string(item["field"], f"{where}.field")
    field_type = _string(item["type"], f"{where}.type")
    meta = _object(item["meta"], f"{where}.meta")
    schema = _object(item["schema"], f"{where}.schema")
    _exact_keys(meta, _FIELD_META_KEYS, f"{where}.meta")
    _exact_keys(schema, _FIELD_SCHEMA_KEYS, f"{where}.schema")
    if meta.get("collection") != collection or meta.get("field") != field:
        raise _fail("schema field metadata is inconsistent")
    if schema.get("table") != collection or schema.get("name") != field:
        raise _fail("schema field storage metadata is inconsistent")
    return collection, field, field_type


def _schema_relation(raw: object, index: int) -> tuple[str, str, str]:
    where = f"schema.data.relations[{index}]"
    item = _object(raw, where)
    _exact_keys(item, {"collection", "field", "meta", "related_collection", "schema"}, where)
    collection = _string(item["collection"], f"{where}.collection")
    field = _string(item["field"], f"{where}.field")
    related = _string(item["related_collection"], f"{where}.related_collection")
    meta = _object(item["meta"], f"{where}.meta")
    schema = _object(item["schema"], f"{where}.schema")
    _exact_keys(meta, _RELATION_META_KEYS, f"{where}.meta")
    _exact_keys(schema, _RELATION_SCHEMA_KEYS, f"{where}.schema")
    expected_meta = {
        "many_collection": collection,
        "many_field": field,
        "one_collection": related,
    }
    expected_schema = {
        "column": field,
        "foreign_key_column": "id",
        "foreign_key_table": related,
        "on_delete": "NO ACTION",
        "on_update": "NO ACTION",
        "table": collection,
    }
    if any(meta.get(key) != value for key, value in expected_meta.items()):
        raise _fail("schema relation metadata is inconsistent")
    if any(schema.get(key) != value for key, value in expected_schema.items()):
        raise _fail("schema relation storage metadata is inconsistent")
    return collection, field, related


def _validate_schema(document: bytes) -> None:
    if hashlib.sha256(document).hexdigest() != _SCHEMA_SHA256:
        raise _fail("schema snapshot does not match the pinned profile")
    response = _decode_json(document, "schema response")
    _exact_keys(response, {"data"}, "schema response")
    data = _object(response["data"], "schema.data")
    _exact_keys(
        data,
        {"collections", "directus", "fields", "relations", "systemFields", "vendor", "version"},
        "schema.data",
    )
    if data["version"] != 1 or type(data["version"]) is not int:
        raise _fail("schema snapshot version does not match the pinned profile")
    if data["directus"] != _SOURCE_VERSION or data["vendor"] != "sqlite":
        raise _fail("schema source version or database vendor does not match the pinned profile")
    collections = {
        _schema_collection(raw, index)
        for index, raw in enumerate(
            _array(data["collections"], "schema.data.collections", length=3)
        )
    }
    if collections != _COLLECTIONS:
        raise _fail("schema collections do not match the pinned profile")
    fields = {
        key: field_type
        for index, raw in enumerate(
            _array(data["fields"], "schema.data.fields", length=len(_REQUIRED_FIELDS))
        )
        for collection, field, field_type in [_schema_field(raw, index)]
        for key in [(collection, field)]
    }
    if fields != _REQUIRED_FIELDS:
        raise _fail("schema fields do not match the pinned profile")
    relations = {
        _schema_relation(raw, index)
        for index, raw in enumerate(_array(data["relations"], "schema.data.relations", length=3))
    }
    if relations != _RELATIONS:
        raise _fail("schema relations do not match the pinned profile")
    system_fields = _array(data["systemFields"], "schema.data.systemFields", length=3)
    for index, raw in enumerate(system_fields):
        where = f"schema.data.systemFields[{index}]"
        item = _object(raw, where)
        _exact_keys(item, {"collection", "field", "schema"}, where)
        _string(item["collection"], f"{where}.collection")
        _string(item["field"], f"{where}.field")
        nested = _object(item["schema"], f"{where}.schema")
        _exact_keys(nested, {"is_indexed"}, f"{where}.schema")
        _boolean(nested["is_indexed"], f"{where}.schema.is_indexed")


def _technical_entities() -> list[dict[str, JsonValue]]:
    return [
        {
            "fields": {"collection": collection},
            "id": collection,
            "type": "directus_collection_scope",
        }
        for collection in ("exitdrill_cases", "exitdrill_people")
    ]


def _sort_export_lists(export: dict[str, JsonValue]) -> None:
    for key in ("entities", "relationships", "attachments", "permissions", "audit_events"):
        items = cast(list[object], export[key])
        items.sort(key=lambda item: canonical_json_bytes(item))


def _build_export(
    manifest: Mapping[str, object], documents: Mapping[str, bytes]
) -> tuple[dict[str, JsonValue], list[tuple[str, bytes]]]:
    _validate_schema(documents["schema.json"])
    people, person_ids = _parse_people(documents["people.json"])
    cases, case_ids, owner_by_file = _parse_cases(documents["cases.json"])
    relationships = _parse_relationships(documents["case-people.json"], case_ids, person_ids)
    attachments, copies = _parse_files(documents["files.json"], documents, owner_by_file)
    policy_id = _parse_policy(documents["policies.json"])
    permissions = _parse_permissions(documents["permissions.json"], policy_id)
    audit_events = _parse_activity(documents["activity.json"], case_ids)
    export: dict[str, JsonValue] = {
        "attachments": cast("list[JsonValue]", attachments),
        "audit_events": cast("list[JsonValue]", audit_events),
        "drill_id": cast(str, manifest["drill_id"]),
        "entities": cast("list[JsonValue]", [*people, *cases, *_technical_entities()]),
        "exported_at": cast(str, manifest["exported_at"]),
        "permissions": cast("list[JsonValue]", permissions),
        "relationships": cast("list[JsonValue]", relationships),
        "schema_version": "exitdrill/export/v0.1",
        "source_system": _SOURCE_SYSTEM,
    }
    _sort_export_lists(export)
    return export, copies


def _normalization_manifest(
    manifest: Mapping[str, object],
    export_document: bytes,
    copies: Sequence[tuple[str, bytes]],
) -> dict[str, JsonValue]:
    attachment_facts = sorted(
        (
            {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for _, content in copies
        ),
        key=lambda item: cast(str, item["sha256"]),
    )
    attachment_bundle_sha256 = hashlib.sha256(canonical_json_bytes(attachment_facts)).hexdigest()
    return {
        "adapter_profile": _PROFILE,
        "attachment_bundle_sha256": attachment_bundle_sha256,
        "counts": {
            "attachment_bytes": sum(len(content) for _, content in copies),
            "attachments": len(copies),
            "audit_events": 2,
            "entities": 7,
            "permissions": 2,
            "relationships": 2,
        },
        "drill_id": cast(str, manifest["drill_id"]),
        "export_sha256": hashlib.sha256(export_document).hexdigest(),
        "limitations": list(_OUTPUT_LIMITATIONS),
        "schema_version": _NORMALIZATION_SCHEMA,
        "source_bundle_sha256": cast(str, manifest["bundle_sha256"]),
        "source_system": _SOURCE_SYSTEM,
    }


def _write_output(
    out_dir: Path,
    export_document: bytes,
    copies: Sequence[tuple[str, bytes]],
    result: Mapping[str, JsonValue],
) -> None:
    parent = out_dir.parent
    if not parent.exists() or not parent.is_dir():
        raise _fail("output parent must be an existing directory")
    try:
        temporary = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.tmp-", dir=parent))
    except OSError as exc:
        raise _fail("normalized output could not be materialized") from exc
    try:
        attachment_dir = temporary / "export-files" / "attachments"
        attachment_dir.mkdir(parents=True)
        (temporary / "export.json").write_bytes(export_document)
        for file_id, content in copies:
            (attachment_dir / f"{file_id}.txt").write_bytes(content)
        (temporary / "normalization-manifest.json").write_bytes(
            canonical_json_bytes(result) + b"\n"
        )
        if out_dir.exists() or out_dir.is_symlink():
            raise _fail("output directory already exists")
        temporary.rename(out_dir)
    except DirectusCanaryError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(temporary, ignore_errors=True)
        raise _fail("normalized output could not be materialized") from exc
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def normalize_directus_canary(manifest_path: Path, out_dir: Path) -> dict[str, JsonValue]:
    """Validate and atomically normalize the one supported Directus canary profile."""
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
        raise _fail("output directory must be outside the native bundle")
    if resolved_out.exists() or resolved_out.is_symlink():
        raise _fail("output directory already exists")
    manifest_document = _read_regular_file(
        manifest_path,
        max_bytes=_MAX_MANIFEST_BYTES,
        where="capture manifest",
    )
    manifest, files = _parse_manifest(manifest_document)
    documents = _read_verified_bundle(root, files)
    export, copies = _build_export(manifest, documents)
    export_document = canonical_json_bytes(export) + b"\n"
    result = _normalization_manifest(manifest, export_document, copies)
    _write_output(resolved_out, export_document, copies, result)
    return result
