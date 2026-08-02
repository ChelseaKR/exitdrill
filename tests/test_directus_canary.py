from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from exitdrill.canonical import canonical_json_bytes
from exitdrill.directus_canary import DirectusCanaryError, normalize_directus_canary
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import Dimension, DimensionStatus, OverallStatus

_FILE_IDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
)
_FILE_PATHS = (
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
_RELATIONS = (
    ("exitdrill_case_people", "case_id", "exitdrill_cases"),
    ("exitdrill_case_people", "person_id", "exitdrill_people"),
    ("exitdrill_cases", "document", "directus_files"),
)
_FIELDS = (
    ("exitdrill_case_people", "id", "integer"),
    ("exitdrill_case_people", "case_id", "integer"),
    ("exitdrill_case_people", "person_id", "integer"),
    ("exitdrill_case_people", "relation_type", "string"),
    ("exitdrill_cases", "id", "integer"),
    ("exitdrill_cases", "status", "string"),
    ("exitdrill_cases", "priority", "integer"),
    ("exitdrill_cases", "document", "uuid"),
    ("exitdrill_people", "id", "integer"),
    ("exitdrill_people", "display_name", "string"),
    ("exitdrill_people", "active", "boolean"),
)


def _schema() -> dict[str, object]:
    collection_meta_keys = {
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
    field_meta_keys = {
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
    field_schema_keys = {
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
    relation_meta_keys = {
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
    relation_schema_keys = {
        "column",
        "constraint_name",
        "foreign_key_column",
        "foreign_key_table",
        "on_delete",
        "on_update",
        "table",
    }
    collections = [
        {
            "collection": name,
            "meta": {**dict.fromkeys(collection_meta_keys), "collection": name},
            "schema": {"name": name},
        }
        for name in ("exitdrill_case_people", "exitdrill_cases", "exitdrill_people")
    ]
    fields = [
        {
            "collection": collection,
            "field": field,
            "meta": {
                **dict.fromkeys(field_meta_keys),
                "collection": collection,
                "field": field,
            },
            "schema": {
                **dict.fromkeys(field_schema_keys),
                "name": field,
                "table": collection,
            },
            "type": field_type,
        }
        for collection, field, field_type in _FIELDS
    ]
    relations = [
        {
            "collection": collection,
            "field": field,
            "meta": {
                **dict.fromkeys(relation_meta_keys),
                "many_collection": collection,
                "many_field": field,
                "one_collection": related,
            },
            "related_collection": related,
            "schema": {
                **dict.fromkeys(relation_schema_keys),
                "column": field,
                "foreign_key_column": "id",
                "foreign_key_table": related,
                "on_delete": "NO ACTION",
                "on_update": "NO ACTION",
                "table": collection,
            },
        }
        for collection, field, related in _RELATIONS
    ]
    return {
        "data": {
            "collections": collections,
            "directus": "11.17.4",
            "fields": fields,
            "relations": relations,
            "systemFields": [
                {
                    "collection": "directus_activity",
                    "field": "timestamp",
                    "schema": {"is_indexed": True},
                },
                {
                    "collection": "directus_revisions",
                    "field": "activity",
                    "schema": {"is_indexed": True},
                },
                {
                    "collection": "directus_revisions",
                    "field": "parent",
                    "schema": {"is_indexed": True},
                },
            ],
            "vendor": "sqlite",
            "version": 1,
        }
    }


def _responses() -> dict[str, object]:
    return {
        "activity.json": {
            "data": [
                {
                    "action": "create",
                    "collection": "exitdrill_cases",
                    "id": 21,
                    "item": "1",
                    "timestamp": "2026-08-02T02:38:28.259Z",
                },
                {
                    "action": "create",
                    "collection": "exitdrill_cases",
                    "id": 22,
                    "item": "2",
                    "timestamp": "2026-08-02T02:38:28.269Z",
                },
            ]
        },
        "case-people.json": {
            "data": [
                {"case_id": 1, "id": 1, "person_id": 1, "relation_type": "assigned_to"},
                {"case_id": 2, "id": 2, "person_id": 2, "relation_type": "assigned_to"},
            ]
        },
        "cases.json": {
            "data": [
                {"document": _FILE_IDS[0], "id": 1, "priority": 2, "status": "open"},
                {"document": _FILE_IDS[1], "id": 2, "priority": 3, "status": "open"},
            ]
        },
        "files.json": {
            "data": [
                {
                    "filename_download": "synthetic-intake-a.txt",
                    "filesize": 28,
                    "id": _FILE_IDS[0],
                    "type": "text/plain",
                },
                {
                    "filename_download": "synthetic-intake-b.txt",
                    "filesize": 28,
                    "id": _FILE_IDS[1],
                    "type": "text/plain",
                },
            ]
        },
        "people.json": {
            "data": [
                {"active": 1, "display_name": "Synthetic Person Alpha", "id": 1},
                {"active": 1, "display_name": "Synthetic Person Bravo", "id": 2},
                {"active": 0, "display_name": "Synthetic Person Canary", "id": 3},
            ]
        },
        "permissions.json": {
            "data": [
                {
                    "action": "read",
                    "collection": "exitdrill_cases",
                    "fields": ["id", "status", "priority", "document"],
                    "id": 1,
                    "permissions": {},
                    "policy": "33333333-3333-4333-8333-333333333333",
                    "presets": None,
                    "validation": None,
                },
                {
                    "action": "read",
                    "collection": "exitdrill_people",
                    "fields": ["id", "display_name", "active"],
                    "id": 2,
                    "permissions": {},
                    "policy": "33333333-3333-4333-8333-333333333333",
                    "presets": None,
                    "validation": None,
                },
            ]
        },
        "policies.json": {
            "data": [
                {
                    "admin_access": False,
                    "app_access": True,
                    "id": "33333333-3333-4333-8333-333333333333",
                    "name": "Synthetic Case Worker",
                }
            ]
        },
        "schema.json": _schema(),
    }


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _base_manifest(files: list[dict[str, object]]) -> dict[str, object]:
    return {
        "acquisition_surface": "documented_first_party_rest_api",
        "adapter_profile": "directus-11.17.4-civic-case/v0.1",
        "bundle_sha256": hashlib.sha256(canonical_json_bytes(files)).hexdigest(),
        "data_mode": "synthetic_only",
        "drill_id": "directus-civic-case-exit-001",
        "exported_at": "2026-08-02T02:38:28.542Z",
        "files": files,
        "isolated_sandbox": True,
        "limitations": [
            "operator_asserted_acquisition_context",
            "bundle_is_unsigned_and_unauthenticated",
            "does_not_prove_export_completeness",
            "does_not_prove_operational_equivalence",
        ],
        "production_data_allowed": False,
        "schema_version": "exitdrill/directus-native-bundle/v0.1",
        "source_system": "Directus 11.17.4 synthetic civic-case sandbox",
        "source_version": "11.17.4",
    }


def _inventory(root: Path) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for relative in _FILE_PATHS:
        document = (root / relative).read_bytes()
        result.append(
            {
                "bytes": len(document),
                "path": relative,
                "sha256": hashlib.sha256(document).hexdigest(),
            }
        )
    return result


def _create_bundle(root: Path) -> Path:
    (root / "assets").mkdir(parents=True)
    (root / f"assets/{_FILE_IDS[0]}.txt").write_bytes(b"Invented intake note alpha.\n")
    (root / f"assets/{_FILE_IDS[1]}.txt").write_bytes(b"Invented intake note bravo.\n")
    for name, value in _responses().items():
        _write_json(root / name, value)
    committed_schema = (
        Path(__file__).parents[1]
        / "examples"
        / "directus-11.17.4-civic-case"
        / "native"
        / "schema.json"
    )
    (root / "schema.json").write_bytes(committed_schema.read_bytes())
    manifest = root / "capture-manifest.json"
    _write_json(manifest, _base_manifest(_inventory(root)))
    return manifest


def _refresh_manifest(manifest_path: Path) -> None:
    manifest = _read_json(manifest_path)
    files = _inventory(manifest_path.parent)
    manifest["files"] = files
    manifest["bundle_sha256"] = hashlib.sha256(canonical_json_bytes(files)).hexdigest()
    _write_json(manifest_path, manifest)


def _mutate_json(manifest: Path, filename: str, mutate: Callable[[dict[str, Any]], None]) -> None:
    path = manifest.parent / filename
    raw = _read_json(path)
    mutate(raw)
    _write_json(path, raw)
    _refresh_manifest(manifest)


def _roles(out_dir: Path) -> dict[str, str]:
    export = _read_json(out_dir / "export.json")
    return {item["scope_id"]: item["role"] for item in export["permissions"]}


def test_normalizes_pinned_profile_and_loads_as_exitdrill_export(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "native")
    out_dir = tmp_path / "normalized"

    result = normalize_directus_canary(manifest, out_dir)
    package = load_export(out_dir / "export.json")

    assert result["counts"] == {
        "attachment_bytes": 56,
        "attachments": 2,
        "audit_events": 2,
        "entities": 7,
        "permissions": 2,
        "relationships": 2,
    }
    assert len(package.entities) == 7
    entities = {(item.entity_type, item.entity_id): item.fields for item in package.entities}
    assert entities[("person", "1")]["active"] is True
    assert entities[("person", "3")]["active"] is False
    assert entities[("directus_collection_scope", "exitdrill_cases")] == {
        "collection": "exitdrill_cases"
    }
    assert entities[("directus_collection_scope", "exitdrill_people")] == {
        "collection": "exitdrill_people"
    }
    assert {item.relation_type for item in package.relationships} == {"assigned_to"}
    assert {item.event_id for item in package.audit_events} == {
        "directus_activity:21",
        "directus_activity:22",
    }
    assert all(item.object_type == "case" for item in package.audit_events)
    assert all(re.fullmatch(r"read:[0-9a-f]{64}", item.role) for item in package.permissions)
    assert all(item.principal_id.startswith("policy:") for item in package.permissions)
    assert all(item.scope_type == "directus_collection_scope" for item in package.permissions)
    assert _roles(out_dir) == {
        "exitdrill_cases": "read:0fcaa4ece823393f4e5ccfc2426e26859693cf80052aaf4b8b78c7ceb3e45a8c",
        "exitdrill_people": "read:ce05c47ea42741b5272eccf39dd56d55f7e8d373dbff4c9d6da220266215a38b",
    }
    for attachment in package.attachments:
        copied = out_dir / "export-files" / attachment.relative_path
        assert (
            copied.read_bytes()
            == (manifest.parent / "assets" / f"{attachment.attachment_id}.txt").read_bytes()
        )
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == attachment.content_sha256
    assert _read_json(out_dir / "normalization-manifest.json") == result


def test_committed_native_fixture_passes_all_five_drill_dimensions(tmp_path: Path) -> None:
    example = Path(__file__).parents[1] / "examples/directus-11.17.4-civic-case"
    out_dir = tmp_path / "normalized"

    normalize_directus_canary(example / "native/capture-manifest.json", out_dir)
    baseline = load_baseline(example / "baseline.json")
    package = load_export(out_dir / "export.json")
    result = run_drill(baseline, package, out_dir / "export-files")

    assert result.overall_status is OverallStatus.STRUCTURALLY_RESTORABLE
    assert {item.dimension for item in result.dimensions} == set(Dimension)
    assert all(item.status is DimensionStatus.PASS for item in result.dimensions)


def test_normalization_is_byte_deterministic(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "native")
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_result = normalize_directus_canary(manifest, first)
    second_result = normalize_directus_canary(manifest, second)

    assert first_result == second_result
    for relative in (
        "export.json",
        "normalization-manifest.json",
        f"export-files/attachments/{_FILE_IDS[0]}.txt",
        f"export-files/attachments/{_FILE_IDS[1]}.txt",
    ):
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


def test_source_record_array_order_does_not_change_export(tmp_path: Path) -> None:
    first_manifest = _create_bundle(tmp_path / "native-first")
    second_manifest = _create_bundle(tmp_path / "native-second")

    for filename in (
        "people.json",
        "cases.json",
        "case-people.json",
        "files.json",
        "permissions.json",
        "activity.json",
    ):
        _mutate_json(
            second_manifest,
            filename,
            lambda raw: cast(list[object], raw["data"]).reverse(),
        )
    first_out = tmp_path / "first"
    second_out = tmp_path / "second"

    normalize_directus_canary(first_manifest, first_out)
    normalize_directus_canary(second_manifest, second_out)

    assert (first_out / "export.json").read_bytes() == (second_out / "export.json").read_bytes()


def test_permission_field_order_is_bound_into_semantic_role(tmp_path: Path) -> None:
    reference_manifest = _create_bundle(tmp_path / "reference-native")
    reordered_manifest = _create_bundle(tmp_path / "reordered-native")
    _mutate_json(
        reordered_manifest,
        "permissions.json",
        lambda raw: cast(list[str], raw["data"][0]["fields"]).reverse(),
    )
    reference_out = tmp_path / "reference"
    reordered_out = tmp_path / "reordered"

    normalize_directus_canary(reference_manifest, reference_out)
    normalize_directus_canary(reordered_manifest, reordered_out)

    assert _roles(reference_out)["exitdrill_cases"] != _roles(reordered_out)["exitdrill_cases"]
    assert _roles(reference_out)["exitdrill_people"] == _roles(reordered_out)["exitdrill_people"]


def test_permission_field_or_filter_mutation_changes_only_semantic_role(tmp_path: Path) -> None:
    reference_manifest = _create_bundle(tmp_path / "reference-native")
    changed_manifest = _create_bundle(tmp_path / "changed-native")
    _mutate_json(
        changed_manifest,
        "permissions.json",
        lambda raw: raw["data"][0].update(
            {
                "fields": ["id", "status"],
                "permissions": {"status": {"_eq": "privacy-filter-marker"}},
            }
        ),
    )
    reference_out = tmp_path / "reference"
    changed_out = tmp_path / "changed"

    normalize_directus_canary(reference_manifest, reference_out)
    result = normalize_directus_canary(changed_manifest, changed_out)

    assert _roles(reference_out)["exitdrill_cases"] != _roles(changed_out)["exitdrill_cases"]
    assert _roles(reference_out)["exitdrill_people"] == _roles(changed_out)["exitdrill_people"]
    assert "privacy-filter-marker" not in canonical_json_bytes(result).decode("utf-8")


def test_printable_result_and_written_manifest_are_aggregate_hash_only(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "private-input-path-marker")
    _mutate_json(
        manifest,
        "people.json",
        lambda raw: raw["data"][0].update({"display_name": "private-person-record-marker"}),
    )
    _mutate_json(
        manifest,
        "cases.json",
        lambda raw: raw["data"][0].update({"status": "private-status-marker"}),
    )
    first_asset = manifest.parent / f"assets/{_FILE_IDS[0]}.txt"
    first_asset.write_bytes(b"private-attachment-content-marker\n")
    _mutate_json(
        manifest,
        "files.json",
        lambda raw: raw["data"][0].update({"filesize": len(first_asset.read_bytes())}),
    )
    _refresh_manifest(manifest)

    result = normalize_directus_canary(manifest, tmp_path / "out")
    encoded = canonical_json_bytes(result).decode("utf-8")

    for marker in (
        str(manifest.parent),
        "private-input-path-marker",
        "private-person-record-marker",
        "private-status-marker",
        "private-attachment-content-marker",
        _FILE_IDS[0],
        "33333333-3333-4333-8333-333333333333",
        "2026-08-02T02:38:28.542Z",
    ):
        assert marker not in encoded
    assert _read_json(tmp_path / "out" / "normalization-manifest.json") == result


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("acquisition_surface", "database_dump"),
        ("adapter_profile", "directus-11.17.5-civic-case/v0.1"),
        ("data_mode", "production"),
        ("isolated_sandbox", False),
        ("limitations", ["does_not_prove_operational_equivalence"]),
        ("production_data_allowed", True),
        ("schema_version", "exitdrill/directus-native-bundle/v0.2"),
        ("source_system", "Another source"),
        ("source_version", "11.17.5"),
    ],
)
def test_rejects_manifest_profile_mismatches(tmp_path: Path, field: str, value: object) -> None:
    manifest_path = _create_bundle(tmp_path / "native")
    manifest = _read_json(manifest_path)
    manifest[field] = value
    _write_json(manifest_path, manifest)

    with pytest.raises(DirectusCanaryError, match="pinned profile"):
        normalize_directus_canary(manifest_path, tmp_path / "out")


def test_rejects_manifest_unknown_and_duplicate_fields(tmp_path: Path) -> None:
    manifest_path = _create_bundle(tmp_path / "native")
    manifest = _read_json(manifest_path)
    manifest["unknown"] = True
    _write_json(manifest_path, manifest)
    with pytest.raises(DirectusCanaryError, match="invalid field set"):
        normalize_directus_canary(manifest_path, tmp_path / "unknown-out")

    manifest_path = _create_bundle(tmp_path / "duplicate-native")
    document = manifest_path.read_bytes()
    manifest_path.write_bytes(
        document.replace(
            b'{"acquisition_surface"', b'{"adapter_profile":"forged","acquisition_surface"', 1
        )
    )
    with pytest.raises(DirectusCanaryError, match="duplicate JSON"):
        normalize_directus_canary(manifest_path, tmp_path / "duplicate-out")


def test_field_set_error_does_not_echo_attacker_controlled_key(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "private-input-location")
    marker = "private-record-value-must-not-reach-stderr"
    _mutate_json(
        manifest,
        "people.json",
        lambda raw: raw["data"][0].update({marker: True}),
    )

    with pytest.raises(DirectusCanaryError) as raised:
        normalize_directus_canary(manifest, tmp_path / "out")

    assert marker not in str(raised.value)
    assert str(manifest.parent) not in str(raised.value)
    assert str(raised.value) == "people response.data[0] has an invalid field set"


@pytest.mark.parametrize("declared_field", ["bytes", "sha256"])
def test_rejects_declared_file_size_or_digest_mismatch(tmp_path: Path, declared_field: str) -> None:
    manifest_path = _create_bundle(tmp_path / "native")
    manifest = _read_json(manifest_path)
    item = manifest["files"][0]
    item[declared_field] = item[declared_field] + 1 if declared_field == "bytes" else "0" * 64
    manifest["bundle_sha256"] = hashlib.sha256(canonical_json_bytes(manifest["files"])).hexdigest()
    _write_json(manifest_path, manifest)

    with pytest.raises(DirectusCanaryError, match="does not match the capture manifest"):
        normalize_directus_canary(manifest_path, tmp_path / "out")


def test_rejects_bundle_digest_and_path_inventory_changes(tmp_path: Path) -> None:
    manifest_path = _create_bundle(tmp_path / "native")
    manifest = _read_json(manifest_path)
    manifest["bundle_sha256"] = "0" * 64
    _write_json(manifest_path, manifest)
    with pytest.raises(DirectusCanaryError, match="bundle digest"):
        normalize_directus_canary(manifest_path, tmp_path / "digest-out")

    manifest_path = _create_bundle(tmp_path / "path-native")
    manifest = _read_json(manifest_path)
    manifest["files"][0]["path"] = "renamed.json"
    manifest["bundle_sha256"] = hashlib.sha256(canonical_json_bytes(manifest["files"])).hexdigest()
    _write_json(manifest_path, manifest)
    with pytest.raises(DirectusCanaryError, match="file list"):
        normalize_directus_canary(manifest_path, tmp_path / "path-out")


def test_rejects_tampered_or_extra_bundle_files(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "native")
    (manifest.parent / "people.json").write_bytes(b"{}\n")
    with pytest.raises(DirectusCanaryError, match=r"byte size|digest"):
        normalize_directus_canary(manifest, tmp_path / "tamper-out")

    manifest = _create_bundle(tmp_path / "extra-native")
    (manifest.parent / "undeclared.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(DirectusCanaryError, match="unexpected entry set"):
        normalize_directus_canary(manifest, tmp_path / "extra-out")


def test_rejects_symlinks_and_nonregular_entries(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "symlink-native")
    people = manifest.parent / "people.json"
    target = tmp_path / "people-target.json"
    people.rename(target)
    people.symlink_to(target)
    with pytest.raises(DirectusCanaryError, match="symbolic links"):
        normalize_directus_canary(manifest, tmp_path / "symlink-out")

    manifest = _create_bundle(tmp_path / "nonregular-native")
    people = manifest.parent / "people.json"
    people.unlink()
    people.mkdir()
    with pytest.raises(DirectusCanaryError, match="unexpected file type"):
        normalize_directus_canary(manifest, tmp_path / "nonregular-out")


@pytest.mark.parametrize("value", [True, 2, -1, "1", 1.0, None])
def test_directus_integer_booleans_are_strict(tmp_path: Path, value: object) -> None:
    manifest = _create_bundle(tmp_path / "native")
    _mutate_json(
        manifest,
        "people.json",
        lambda raw: raw["data"][0].update({"active": value}),
    )

    with pytest.raises(DirectusCanaryError, match="integer boolean 0 or 1"):
        normalize_directus_canary(manifest, tmp_path / "out")


@pytest.mark.parametrize(
    ("filename", "index", "field"),
    [
        ("people.json", 2, "id"),
        ("cases.json", 1, "id"),
        ("case-people.json", 1, "id"),
        ("activity.json", 1, "id"),
    ],
)
def test_native_ids_must_fit_the_supported_sqlite_range(
    tmp_path: Path,
    filename: str,
    index: int,
    field: str,
) -> None:
    manifest = _create_bundle(tmp_path / "native")
    _mutate_json(
        manifest,
        filename,
        lambda raw: raw["data"][index].update({field: 10**40}),
    )

    with pytest.raises(DirectusCanaryError, match="supported SQLite range"):
        normalize_directus_canary(manifest, tmp_path / "out")


def test_rejects_unknown_api_fields_duplicate_keys_and_wrong_cardinality(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "unknown-native")
    _mutate_json(
        manifest,
        "people.json",
        lambda raw: raw["data"][0].update({"unknown": "value"}),
    )
    with pytest.raises(DirectusCanaryError, match="invalid field set"):
        normalize_directus_canary(manifest, tmp_path / "unknown-out")

    manifest = _create_bundle(tmp_path / "duplicate-native")
    path = manifest.parent / "people.json"
    path.write_bytes(path.read_bytes().replace(b'"active":1', b'"active":1,"active":0', 1))
    _refresh_manifest(manifest)
    with pytest.raises(DirectusCanaryError, match="duplicate JSON"):
        normalize_directus_canary(manifest, tmp_path / "duplicate-out")

    manifest = _create_bundle(tmp_path / "count-native")
    _mutate_json(manifest, "people.json", lambda raw: raw["data"].pop())
    with pytest.raises(DirectusCanaryError, match="exactly 3"):
        normalize_directus_canary(manifest, tmp_path / "count-out")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw: raw["data"].update({"vendor": "postgres"}), "pinned profile"),
        (lambda raw: raw["data"].update({"directus": "11.17.5"}), "pinned profile"),
        (lambda raw: raw["data"]["collections"].pop(), "pinned profile"),
        (
            lambda raw: raw["data"]["fields"][0].update({"type": "string"}),
            "pinned profile",
        ),
        (
            lambda raw: raw["data"]["fields"][1]["meta"].update({"required": False}),
            "pinned profile",
        ),
        (
            lambda raw: raw["data"]["relations"][0].update(
                {"related_collection": "exitdrill_people"}
            ),
            "pinned profile",
        ),
        (
            lambda raw: raw["data"]["relations"][0]["meta"].update(
                {"one_deselect_action": "delete"}
            ),
            "pinned profile",
        ),
        (
            lambda raw: raw["data"]["systemFields"][0].update({"collection": "directus_users"}),
            "pinned profile",
        ),
    ],
)
def test_rejects_schema_profile_changes(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    manifest = _create_bundle(tmp_path / "native")
    _mutate_json(manifest, "schema.json", mutate)

    with pytest.raises(DirectusCanaryError, match=message):
        normalize_directus_canary(manifest, tmp_path / "out")


@pytest.mark.parametrize(
    ("filename", "mutate", "message"),
    [
        (
            "case-people.json",
            lambda raw: raw["data"][0].update({"person_id": 999}),
            "unknown entity",
        ),
        (
            "cases.json",
            lambda raw: raw["data"][0].update({"document": _FILE_IDS[1]}),
            "unique",
        ),
        (
            "files.json",
            lambda raw: raw["data"][0].update({"filesize": 999}),
            "metadata size",
        ),
        (
            "permissions.json",
            lambda raw: raw["data"][0].update({"action": "update"}),
            "policy or action",
        ),
        (
            "policies.json",
            lambda raw: raw["data"][0].update({"admin_access": True}),
            "must not allow administrator",
        ),
        (
            "activity.json",
            lambda raw: raw["data"][0].update({"collection": "exitdrill_people"}),
            "reference a pinned case",
        ),
    ],
)
def test_rejects_cross_document_integrity_failures(
    tmp_path: Path,
    filename: str,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    manifest = _create_bundle(tmp_path / "native")
    _mutate_json(manifest, filename, mutate)

    with pytest.raises(DirectusCanaryError, match=message):
        normalize_directus_canary(manifest, tmp_path / "out")


def test_existing_destination_is_never_modified(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "native")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    sentinel = out_dir / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(DirectusCanaryError, match="already exists"):
        normalize_directus_canary(manifest, out_dir)

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert list(out_dir.iterdir()) == [sentinel]


def test_output_must_not_be_nested_inside_native_bundle(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "native")
    out_dir = manifest.parent / "normalized"

    with pytest.raises(DirectusCanaryError, match="outside the native bundle"):
        normalize_directus_canary(manifest, out_dir)

    assert not out_dir.exists()
    assert set(path.name for path in manifest.parent.iterdir()) == {
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


def test_failed_materialization_removes_temporary_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _create_bundle(tmp_path / "native")
    original = Path.write_bytes

    def fail_on_manifest(path: Path, data: bytes) -> int:
        if path.name == "normalization-manifest.json":
            raise OSError("injected write failure")
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_on_manifest)

    with pytest.raises(DirectusCanaryError, match="normalized output could not be materialized"):
        normalize_directus_canary(manifest, tmp_path / "out")

    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".out.tmp-*"))


def test_output_parent_must_exist_without_leaving_artifacts(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "native")
    out_dir = tmp_path / "missing-parent" / "out"

    with pytest.raises(DirectusCanaryError, match="output parent"):
        normalize_directus_canary(manifest, out_dir)

    assert not out_dir.parent.exists()


def test_manifest_path_name_and_root_symlink_are_rejected(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "native")
    renamed = manifest.with_name("manifest.json")
    manifest.rename(renamed)
    with pytest.raises(DirectusCanaryError, match="named capture-manifest"):
        normalize_directus_canary(renamed, tmp_path / "name-out")

    real_root = tmp_path / "real-native"
    _create_bundle(real_root)
    linked_root = tmp_path / "linked-native"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(DirectusCanaryError, match="symbolic links"):
        normalize_directus_canary(linked_root / "capture-manifest.json", tmp_path / "link-out")


def test_adapter_has_no_evaluation_or_reporting_dependency() -> None:
    source = (Path(__file__).parents[1] / "src/exitdrill/directus_canary.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "exitdrill.evaluator",
        "exitdrill.receipt",
        "exitdrill.comparison",
        "exitdrill.report",
    ):
        assert forbidden not in source
    assert "directus_activity:" in source
    assert '"directus_collection_scope"' in source
