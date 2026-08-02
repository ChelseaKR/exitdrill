from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from exitdrill.canonical import canonical_json_bytes
from exitdrill.civicrm_target_canary import (
    CiviCRMTargetCanaryError,
    normalize_civicrm_target_canary,
)
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import Dimension, DimensionStatus, DrillResult, OverallStatus

_FILE_IDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
)
_FILE_PATHS = (
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
    "browser-workflow.json",
    "browser-accessibility.json",
    f"assets/{_FILE_IDS[0]}.txt",
    f"assets/{_FILE_IDS[1]}.txt",
)
_REPRESENTED = {
    "attachments": 2,
    "audit_events": 0,
    "entities": 5,
    "permissions": 0,
    "relationships": 2,
}
_UNMAPPED = {
    "attachments": 0,
    "audit_events": 2,
    "entities": 2,
    "permissions": 2,
    "relationships": 0,
}
_TARGET_GENERATED = {
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
_SANDBOX = {
    "application_empty_before_write": True,
    "attachments_private": True,
    "browser_artifact_retention_disabled": True,
    "browser_container_read_only": True,
    "browser_network_internal_only": True,
    "egress_blocked": True,
    "hibp_lookup_disabled": True,
    "mail_disabled": True,
    "no_public_ingress": True,
    "run_owned": True,
    "scheduled_jobs_disabled": True,
    "source_identity_collisions_absent": True,
}
_SEPARATION = {
    "all_principals_distinct": True,
    "allow_and_deny_distinct": True,
    "permission_checks_enabled": True,
    "reader_independent_from_writer": True,
    "same_permission_query_and_object": True,
    "writer_credential_excluded_from_business_readback": True,
}
_SOURCE_NORMALIZATION = {
    "adapter_profile": "directus-11.17.4-civic-case/v0.1",
    "attachment_bundle_sha256": "b1e24857570523f2d1606bb3ef0d32708680b369b631c623df83db95f16c177d",
    "export_sha256": "2e2a4280c7e9b2249b443a861e3eb8498a379bd462b2b4ad5637208d9698a51b",
    "schema_version": "exitdrill/directus-normalization/v0.1",
    "source_bundle_sha256": "a67048bf25c07b73aa0bff26372090c0a7e5ce77871b49259d0a96110998be49",
}
_BUNDLE_LIMITATIONS = [
    "operator_asserted_execution_context",
    "bundle_is_unsigned_and_unauthenticated",
    "synthetic_fixture_only",
    "source_capture_is_not_a_vendor_native_export",
    "does_not_prove_operational_equivalence",
    "server_rendered_ui_does_not_prove_browser_interaction",
    "single_case_browser_workflow_only",
    "browser_workflow_observed_with_known_jquery_notify_runtime_errors",
    "browser_workflow_does_not_prove_accessibility",
    "automated_accessibility_scan_does_not_establish_wcag_conformance",
]
_RESULT_LIMITATIONS = [
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
]


def _api(values: Sequence[object], *, matched: bool = False) -> dict[str, object]:
    response: dict[str, object] = {
        "count": len(values),
        "countFetched": len(values),
        "values": list(values),
    }
    if matched:
        response["countMatched"] = len(values)
    return response


def _responses() -> dict[str, object]:
    contacts = [
        {
            "display_name": "Synthetic Person Alpha",
            "exitdrill_person_profile.source_active": True,
            "exitdrill_person_profile.source_display_name": "Synthetic Person Alpha",
            "exitdrill_person_profile.source_id": "1",
            "id": 101,
        },
        {
            "display_name": "Synthetic Person Bravo",
            "exitdrill_person_profile.source_active": True,
            "exitdrill_person_profile.source_display_name": "Synthetic Person Bravo",
            "exitdrill_person_profile.source_id": "2",
            "id": 102,
        },
        {
            "display_name": "Synthetic Person Canary",
            "exitdrill_person_profile.source_active": False,
            "exitdrill_person_profile.source_display_name": "Synthetic Person Canary",
            "exitdrill_person_profile.source_id": "3",
            "id": 103,
        },
    ]
    cases = [
        {
            "case_type_id:name": "exitdrill_civic_case",
            "exitdrill_case_profile.source_document_id": _FILE_IDS[0],
            "exitdrill_case_profile.source_id": "1",
            "exitdrill_case_profile.source_priority": 2,
            "exitdrill_case_profile.source_status": "open",
            "id": 201,
            "start_date": "2026-08-02",
            "status_id:name": "Open",
            "subject": "Synthetic ExitDrill Case Alpha",
        },
        {
            "case_type_id:name": "exitdrill_civic_case",
            "exitdrill_case_profile.source_document_id": _FILE_IDS[1],
            "exitdrill_case_profile.source_id": "2",
            "exitdrill_case_profile.source_priority": 3,
            "exitdrill_case_profile.source_status": "open",
            "id": 202,
            "start_date": "2026-08-02",
            "status_id:name": "Open",
            "subject": "Synthetic ExitDrill Case Bravo",
        },
    ]
    relationships = [
        {
            "case_id": 201,
            "contact_id_a": 900,
            "contact_id_b": 101,
            "description": "ExitDrill assigned_to",
            "id": 301,
            "is_active": True,
            "relationship_type_id.name_a_b": "Case Coordinator is",
        },
        {
            "case_id": 202,
            "contact_id_a": 900,
            "contact_id_b": 102,
            "description": "ExitDrill assigned_to",
            "id": 302,
            "is_active": True,
            "relationship_type_id.name_a_b": "Case Coordinator is",
        },
    ]
    files = [
        {
            "description": _FILE_IDS[0],
            "file_name": f"{_FILE_IDS[0].replace('-', '_')}.txt",
            "id": 401,
            "is_public": False,
            "mime_type": "text/plain",
        },
        {
            "description": _FILE_IDS[1],
            "file_name": f"{_FILE_IDS[1].replace('-', '_')}.txt",
            "id": 402,
            "is_public": False,
            "mime_type": "text/plain",
        },
    ]
    entity_files = [
        {"entity_id": 201, "entity_table": "civicrm_case", "file_id": 401, "id": 501},
        {"entity_id": 202, "entity_table": "civicrm_case", "file_id": 402, "id": 502},
    ]
    permission_value = {
        "display_name": "Synthetic Person Alpha",
        "id": 101,
    }
    return {
        "cases.json": _api(cases),
        "contacts.json": _api(contacts),
        "entity-files.json": _api(entity_files),
        "files.json": _api(files),
        "identity-allow.json": {
            "contact_id": 903,
            "cred": "pass",
            "flow": "header",
            "user_id": 1003,
        },
        "identity-deny.json": {
            "contact_id": 904,
            "cred": "pass",
            "flow": "header",
            "user_id": 1004,
        },
        "identity-reader.json": {
            "contact_id": 902,
            "cred": "pass",
            "flow": "header",
            "user_id": 1002,
        },
        "identity-writer.json": {
            "contact_id": 901,
            "cred": "pass",
            "flow": "header",
            "user_id": 1001,
        },
        "permission-allow.json": _api([permission_value]),
        "permission-deny.json": _api([]),
        "relationships.json": _api(relationships),
        "ui-contact-summary.json": {
            "authenticated_identity": "reader",
            "http_status": 200,
            "observed_labels": ["Cases", "Synthetic Person Alpha"],
            "observed_regions": ["contact_summary"],
            "route": "civicrm/contact/view",
            "surface": "contact_summary",
        },
        "browser-workflow.json": {
            "browser_engine": "chromium",
            "data_mode": "synthetic_only",
            "known_runtime_errors": [
                {
                    "error_key": "jquery_notify_unavailable",
                    "occurrence_count": 2,
                }
            ],
            "retained_artifacts": [],
            "schema_version": "exitdrill/civicrm-browser-workflow-observation/v0.1",
            "steps": [
                "case_dashboard_opened",
                "case_located",
                "manage_case_opened",
                "case_controls_observed",
            ],
            "target_profile": ("directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1"),
        },
        "browser-accessibility.json": {
            "data_mode": "synthetic_only",
            "engine": "axe-core",
            "engine_version": "4.12.1",
            "inapplicable_rule_count": 29,
            "incomplete_rule_count": 0,
            "page_scope": "manage_case_document",
            "passes_rule_count": 32,
            "retained_artifacts": [],
            "rule_tags": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
            "schema_version": "exitdrill/civicrm-accessibility-observation/v0.1",
            "target_profile": ("directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1"),
            "violations": [
                {"impact": "serious", "node_count": 4, "rule_id": "color-contrast"},
                {"impact": "serious", "node_count": 2, "rule_id": "link-in-text-block"},
            ],
        },
    }


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


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


def _base_manifest(files: list[dict[str, object]]) -> dict[str, object]:
    return {
        "acquisition_surface": (
            "supported_api_v4_authenticated_private_file_readback_authenticated_"
            "server_rendered_ui_isolated_browser_workflow_and_automated_accessibility_scan"
        ),
        "bundle_sha256": hashlib.sha256(canonical_json_bytes(files)).hexdigest(),
        "data_mode": "synthetic_only",
        "disposition_counts": {
            "represented": _REPRESENTED,
            "target_generated": _TARGET_GENERATED,
            "unmapped": _UNMAPPED,
        },
        "files": files,
        "identity_separation": _SEPARATION,
        "images": {
            "application": (
                "civicrm/civicrm:6.16.2-php8.5@"
                "sha256:cdf062708b054670cc0f9b452e0b883840af71ce6db21615304f9e7ffe44b93f"
            ),
            "browser": (
                "mcr.microsoft.com/playwright:v1.62.0-noble@"
                "sha256:baed2032d533817f3dbe6425de795788430ba345e819a1201337009ba17c9d07"
            ),
            "database": (
                "mariadb:10.11.18@"
                "sha256:be981e4113326ada8d6004174dd09eeaefc03094037f811182a52d4f2e737350"
            ),
        },
        "limitations": _BUNDLE_LIMITATIONS,
        "sandbox": _SANDBOX,
        "schema_version": "exitdrill/civicrm-target-roundtrip-bundle/v0.1",
        "source_profile": "directus-11.17.4-civic-case/v0.1",
        "source_normalization": _SOURCE_NORMALIZATION,
        "source_system": "Directus 11.17.4 synthetic civic-case sandbox",
        "target_profile": ("directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1"),
        "target_system": "CiviCRM Standalone",
        "target_version": "6.16.2",
    }


def _create_bundle(root: Path) -> Path:
    (root / "assets").mkdir(parents=True)
    (root / f"assets/{_FILE_IDS[0]}.txt").write_bytes(b"Invented intake note alpha.\n")
    (root / f"assets/{_FILE_IDS[1]}.txt").write_bytes(b"Invented intake note bravo.\n")
    for filename, value in _responses().items():
        _write_json(root / filename, value)
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


def _result_state(result: dict[str, Any], probe_id: str) -> str:
    return cast(
        str,
        next(item["state"] for item in result["probe_results"] if item["id"] == probe_id),
    )


def _run_against_baseline(out_dir: Path) -> DrillResult:
    baseline = load_baseline(
        Path(__file__).parents[1] / "examples/directus-11.17.4-civic-case/baseline.json"
    )
    package = load_export(out_dir / "export.json")
    return run_drill(baseline, package, out_dir / "export-files")


def test_normalizes_closed_target_bundle_and_schema_validates(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "capture")
    out_dir = tmp_path / "out"

    result = normalize_civicrm_target_canary(manifest, out_dir)
    package = load_export(out_dir / "export.json")
    schema = _read_json(
        Path(__file__).parents[1] / "schemas/civicrm-target-roundtrip-result-v0.1.schema.json"
    )
    ui_schema = _read_json(
        Path(__file__).parents[1] / "schemas/civicrm-ui-surface-result-v0.1.schema.json"
    )
    browser_schema = _read_json(
        Path(__file__).parents[1] / "schemas/civicrm-browser-workflow-result-v0.1.schema.json"
    )
    accessibility_schema = _read_json(
        Path(__file__).parents[1] / "schemas/civicrm-accessibility-result-v0.1.schema.json"
    )
    ui_result = _read_json(out_dir / "ui-surface-result.json")
    browser_result = _read_json(out_dir / "browser-workflow-result.json")
    accessibility_result = _read_json(out_dir / "accessibility-result.json")

    Draft202012Validator(schema).validate(result)
    Draft202012Validator(ui_schema).validate(ui_result)
    Draft202012Validator(browser_schema).validate(browser_result)
    Draft202012Validator(accessibility_schema).validate(accessibility_result)
    assert _read_json(out_dir / "target-result.json") == result
    assert result["represented_counts"] == _REPRESENTED
    assert result["unmapped_counts"] == _UNMAPPED
    assert result["target_generated_counts"] == _TARGET_GENERATED
    assert result["limitations"] == _RESULT_LIMITATIONS
    probes = cast(list[dict[str, object]], result["probe_results"])
    assert all(item["state"] == "pass" for item in probes)
    assert [item["state"] for item in ui_result["surface_results"]] == ["observed"]
    assert [item["state"] for item in browser_result["workflow_results"]] == ["observed"]
    assert browser_result["known_runtime_errors"] == [
        {"error_key": "jquery_notify_unavailable", "occurrence_count": 2}
    ]
    assert accessibility_result["scan_result"]["violations"] == [
        {"impact": "serious", "node_count": 4, "rule_id": "color-contrast"},
        {"impact": "serious", "node_count": 2, "rule_id": "link-in-text-block"},
    ]
    assert package.drill_id == "directus-civic-case-exit-001"
    assert package.source_system == "Directus 11.17.4 synthetic civic-case sandbox"
    assert package.exported_at == "2026-08-02T02:38:28.542Z"
    assert len(package.entities) == 5
    assert len(package.relationships) == 2
    assert len(package.attachments) == 2
    assert package.permissions == ()
    assert package.audit_events == ()
    for attachment in package.attachments:
        copied = out_dir / "export-files" / attachment.relative_path
        assert (
            copied.read_bytes()
            == (manifest.parent / "assets" / f"{attachment.attachment_id}.txt").read_bytes()
        )
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == attachment.content_sha256


def test_expected_structural_result_keeps_all_six_missing_signals(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "capture")
    out_dir = tmp_path / "out"
    normalize_civicrm_target_canary(manifest, out_dir)

    result = _run_against_baseline(out_dir)
    dimensions = {item.dimension: item for item in result.dimensions}

    assert result.overall_status is OverallStatus.NOT_STRUCTURALLY_RESTORABLE
    assert dimensions[Dimension.ENTITIES].status is DimensionStatus.FAIL
    assert dimensions[Dimension.ENTITIES].missing_count == 2
    assert dimensions[Dimension.PERMISSIONS].missing_count == 2
    assert dimensions[Dimension.AUDIT_EVENTS].missing_count == 2
    assert dimensions[Dimension.RELATIONSHIPS].status is DimensionStatus.PASS
    assert dimensions[Dimension.ATTACHMENTS].status is DimensionStatus.PASS


def test_scalar_relationship_and_attachment_mutations_flow_to_evaluator(tmp_path: Path) -> None:
    scalar = _create_bundle(tmp_path / "scalar")

    def mutate_scalar(raw: dict[str, Any]) -> None:
        raw["values"][0]["display_name"] = "Synthetic Person Mutated"
        raw["values"][0]["exitdrill_person_profile.source_display_name"] = (
            "Synthetic Person Mutated"
        )

    _mutate_json(scalar, "contacts.json", mutate_scalar)
    scalar_out = tmp_path / "scalar-out"
    normalize_civicrm_target_canary(scalar, scalar_out)
    scalar_result = _run_against_baseline(scalar_out)
    assert (
        next(
            item for item in scalar_result.dimensions if item.dimension is Dimension.ENTITIES
        ).invalid_count
        == 1
    )

    relationship = _create_bundle(tmp_path / "relationship")
    _mutate_json(
        relationship,
        "relationships.json",
        lambda raw: raw["values"][0].update({"contact_id_b": 103}),
    )
    relationship_out = tmp_path / "relationship-out"
    normalize_civicrm_target_canary(relationship, relationship_out)
    relationship_result = _run_against_baseline(relationship_out)
    relationship_dimension = next(
        item for item in relationship_result.dimensions if item.dimension is Dimension.RELATIONSHIPS
    )
    assert relationship_dimension.missing_count == 1
    assert relationship_dimension.extra_count == 1

    attachment = _create_bundle(tmp_path / "attachment")
    asset = attachment.parent / f"assets/{_FILE_IDS[0]}.txt"
    asset.write_bytes(b"Invented intake note ALPHA.\n")
    _refresh_manifest(attachment)
    attachment_out = tmp_path / "attachment-out"
    normalize_civicrm_target_canary(attachment, attachment_out)
    attachment_result = _run_against_baseline(attachment_out)
    assert (
        next(
            item for item in attachment_result.dimensions if item.dimension is Dimension.ATTACHMENTS
        ).invalid_count
        == 1
    )


def test_permission_visibility_mutations_emit_failed_probe_not_parser_error(
    tmp_path: Path,
) -> None:
    denied_visible = _create_bundle(tmp_path / "deny-visible")
    allow = _read_json(denied_visible.parent / "permission-allow.json")
    _write_json(denied_visible.parent / "permission-deny.json", allow)
    _refresh_manifest(denied_visible)

    denied_result = normalize_civicrm_target_canary(denied_visible, tmp_path / "deny-out")

    assert _result_state(denied_result, "unauthorized_denial") == "fail"
    assert _result_state(denied_result, "authorized_access") == "pass"
    Draft202012Validator(
        _read_json(
            Path(__file__).parents[1] / "schemas/civicrm-target-roundtrip-result-v0.1.schema.json"
        )
    ).validate(denied_result)

    allow_empty = _create_bundle(tmp_path / "allow-empty")
    _write_json(allow_empty.parent / "permission-allow.json", _api([]))
    _refresh_manifest(allow_empty)
    allow_result = normalize_civicrm_target_canary(allow_empty, tmp_path / "allow-out")
    assert _result_state(allow_result, "authorized_access") == "fail"


def test_api_capture_projections_accept_optional_exact_count_matched(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "capture")
    for filename in (
        "contacts.json",
        "cases.json",
        "relationships.json",
        "files.json",
        "entity-files.json",
        "permission-allow.json",
        "permission-deny.json",
    ):
        _mutate_json(
            manifest,
            filename,
            lambda raw: raw.update({"countMatched": raw["count"]}),
        )

    normalize_civicrm_target_canary(manifest, tmp_path / "out")


@pytest.mark.parametrize(
    ("filename", "field", "replacement"),
    [
        ("ui-contact-summary.json", "authenticated_identity", "writer"),
        ("ui-contact-summary.json", "observed_regions", []),
        ("browser-workflow.json", "browser_engine", "firefox"),
        ("browser-workflow.json", "retained_artifacts", ["trace.zip"]),
        (
            "browser-workflow.json",
            "known_runtime_errors",
            [{"error_key": "other", "occurrence_count": 2}],
        ),
        ("browser-workflow.json", "steps", ["case_dashboard_opened"]),
        ("browser-accessibility.json", "engine_version", "4.12.0"),
        ("browser-accessibility.json", "retained_artifacts", ["page.html"]),
        ("browser-accessibility.json", "passes_rule_count", 33),
        ("browser-accessibility.json", "violations", []),
    ],
)
def test_rejects_ui_projection_drift(
    tmp_path: Path, filename: str, field: str, replacement: object
) -> None:
    manifest = _create_bundle(tmp_path / filename.removesuffix(".json"))
    _mutate_json(manifest, filename, lambda raw: raw.update({field: replacement}))

    with pytest.raises(CiviCRMTargetCanaryError, match="pinned profile"):
        normalize_civicrm_target_canary(manifest, tmp_path / "out")


def test_aggregate_result_never_contains_raw_values_ids_paths_or_bytes(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "private-input-path-marker")

    def mutate(raw: dict[str, Any]) -> None:
        raw["values"][0]["display_name"] = "private-person-marker"
        raw["values"][0]["exitdrill_person_profile.source_display_name"] = "private-person-marker"

    _mutate_json(manifest, "contacts.json", mutate)
    asset = manifest.parent / f"assets/{_FILE_IDS[0]}.txt"
    asset.write_bytes(b"private-attachment-marker\n")
    _refresh_manifest(manifest)

    result = normalize_civicrm_target_canary(manifest, tmp_path / "out")
    encoded = canonical_json_bytes(result).decode("utf-8")

    for marker in (
        str(manifest.parent),
        "private-input-path-marker",
        "private-person-marker",
        "private-attachment-marker",
        _FILE_IDS[0],
        "directus-civic-case-exit-001",
        "2026-08-02T02:38:28.542Z",
        "101",
    ):
        assert marker not in encoded


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("acquisition_surface", "database_dump"),
        ("data_mode", "production"),
        ("schema_version", "exitdrill/civicrm-target-roundtrip-bundle/v0.2"),
        ("source_profile", "directus-11.17.5-civic-case/v0.1"),
        ("source_system", "Another source"),
        ("target_profile", "generic-target/v1"),
        ("target_system", "Another target"),
        ("target_version", "6.16.3"),
    ],
)
def test_rejects_manifest_profile_drift(tmp_path: Path, field: str, value: object) -> None:
    manifest_path = _create_bundle(tmp_path / "capture")
    manifest = _read_json(manifest_path)
    manifest[field] = value
    _write_json(manifest_path, manifest)

    with pytest.raises(CiviCRMTargetCanaryError, match="pinned profile"):
        normalize_civicrm_target_canary(manifest_path, tmp_path / "out")


@pytest.mark.parametrize(
    ("container", "field", "value"),
    [
        ("sandbox", "application_empty_before_write", False),
        ("sandbox", "egress_blocked", False),
        ("sandbox", "no_public_ingress", 1),
        ("identity_separation", "all_principals_distinct", False),
        ("identity_separation", "permission_checks_enabled", False),
        (
            "identity_separation",
            "writer_credential_excluded_from_business_readback",
            False,
        ),
        ("images", "application", "civicrm/civicrm:latest"),
        ("disposition_counts", "represented", {"entities": 7}),
    ],
)
def test_rejects_safety_image_identity_and_count_drift_before_output(
    tmp_path: Path, container: str, field: str, value: object
) -> None:
    manifest_path = _create_bundle(tmp_path / "capture")
    manifest = _read_json(manifest_path)
    manifest[container][field] = value
    _write_json(manifest_path, manifest)
    out_dir = tmp_path / "out"

    with pytest.raises(CiviCRMTargetCanaryError, match=r"pinned profile|invalid field set"):
        normalize_civicrm_target_canary(manifest_path, out_dir)

    assert not out_dir.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("adapter_profile", "directus-generic/v1"),
        ("attachment_bundle_sha256", "0" * 64),
        ("export_sha256", "0" * 64),
        ("schema_version", "exitdrill/directus-normalization/v0.2"),
        ("source_bundle_sha256", "0" * 64),
    ],
)
def test_rejects_source_normalization_binding_drift(tmp_path: Path, field: str, value: str) -> None:
    manifest_path = _create_bundle(tmp_path / "capture")
    manifest = _read_json(manifest_path)
    manifest["source_normalization"][field] = value
    _write_json(manifest_path, manifest)
    out_dir = tmp_path / "out"

    with pytest.raises(CiviCRMTargetCanaryError, match="pinned profile"):
        normalize_civicrm_target_canary(manifest_path, out_dir)

    assert not out_dir.exists()


@pytest.mark.parametrize(
    "field",
    ["acl_entity_roles", "acl_group_contacts", "acl_groups", "acl_roles", "acls"],
)
def test_rejects_acl_and_group_target_generated_count_drift(tmp_path: Path, field: str) -> None:
    manifest_path = _create_bundle(tmp_path / "capture")
    manifest = _read_json(manifest_path)
    target_generated = manifest["disposition_counts"]["target_generated"]
    target_generated[field] += 1
    _write_json(manifest_path, manifest)
    out_dir = tmp_path / "out"

    with pytest.raises(CiviCRMTargetCanaryError, match="pinned profile"):
        normalize_civicrm_target_canary(manifest_path, out_dir)

    assert not out_dir.exists()


def test_rejects_missing_source_normalization_binding(tmp_path: Path) -> None:
    manifest_path = _create_bundle(tmp_path / "capture")
    manifest = _read_json(manifest_path)
    manifest.pop("source_normalization")
    _write_json(manifest_path, manifest)

    with pytest.raises(CiviCRMTargetCanaryError, match="invalid field set"):
        normalize_civicrm_target_canary(manifest_path, tmp_path / "out")


def test_rejects_manifest_unknown_duplicate_and_bad_nested_fields(tmp_path: Path) -> None:
    manifest_path = _create_bundle(tmp_path / "unknown")
    manifest = _read_json(manifest_path)
    manifest["unexpected"] = True
    _write_json(manifest_path, manifest)
    with pytest.raises(CiviCRMTargetCanaryError, match="invalid field set"):
        normalize_civicrm_target_canary(manifest_path, tmp_path / "unknown-out")

    manifest_path = _create_bundle(tmp_path / "nested")
    manifest = _read_json(manifest_path)
    manifest["sandbox"]["unexpected"] = True
    _write_json(manifest_path, manifest)
    with pytest.raises(CiviCRMTargetCanaryError, match="invalid field set"):
        normalize_civicrm_target_canary(manifest_path, tmp_path / "nested-out")

    manifest_path = _create_bundle(tmp_path / "duplicate")
    document = manifest_path.read_bytes()
    manifest_path.write_bytes(
        document.replace(
            b'{"acquisition_surface"',
            b'{"target_version":"forged","acquisition_surface"',
            1,
        )
    )
    with pytest.raises(CiviCRMTargetCanaryError, match="duplicate JSON"):
        normalize_civicrm_target_canary(manifest_path, tmp_path / "duplicate-out")


@pytest.mark.parametrize("declared_field", ["bytes", "sha256"])
def test_rejects_declared_file_size_or_digest_mismatch(tmp_path: Path, declared_field: str) -> None:
    manifest_path = _create_bundle(tmp_path / "capture")
    manifest = _read_json(manifest_path)
    item = manifest["files"][0]
    item[declared_field] = item[declared_field] + 1 if declared_field == "bytes" else "0" * 64
    manifest["bundle_sha256"] = hashlib.sha256(canonical_json_bytes(manifest["files"])).hexdigest()
    _write_json(manifest_path, manifest)

    with pytest.raises(CiviCRMTargetCanaryError, match="capture manifest"):
        normalize_civicrm_target_canary(manifest_path, tmp_path / "out")


def test_rejects_bundle_digest_path_inventory_and_tamper(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "digest")
    raw = _read_json(manifest)
    raw["bundle_sha256"] = "0" * 64
    _write_json(manifest, raw)
    with pytest.raises(CiviCRMTargetCanaryError, match="bundle digest"):
        normalize_civicrm_target_canary(manifest, tmp_path / "digest-out")

    manifest = _create_bundle(tmp_path / "path")
    raw = _read_json(manifest)
    raw["files"][0]["path"] = "../contacts.json"
    raw["bundle_sha256"] = hashlib.sha256(canonical_json_bytes(raw["files"])).hexdigest()
    _write_json(manifest, raw)
    with pytest.raises(CiviCRMTargetCanaryError, match="file list"):
        normalize_civicrm_target_canary(manifest, tmp_path / "path-out")

    manifest = _create_bundle(tmp_path / "tamper")
    (manifest.parent / "contacts.json").write_bytes(b"{}\n")
    with pytest.raises(CiviCRMTargetCanaryError, match=r"byte size|digest"):
        normalize_civicrm_target_canary(manifest, tmp_path / "tamper-out")


def test_rejects_extra_missing_symlink_and_nonregular_entries(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "extra")
    (manifest.parent / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CiviCRMTargetCanaryError, match="unexpected entry set"):
        normalize_civicrm_target_canary(manifest, tmp_path / "extra-out")

    manifest = _create_bundle(tmp_path / "missing")
    (manifest.parent / "contacts.json").unlink()
    with pytest.raises(CiviCRMTargetCanaryError, match="unexpected entry set"):
        normalize_civicrm_target_canary(manifest, tmp_path / "missing-out")

    manifest = _create_bundle(tmp_path / "symlink")
    contacts = manifest.parent / "contacts.json"
    target = tmp_path / "contacts-target.json"
    contacts.rename(target)
    contacts.symlink_to(target)
    with pytest.raises(CiviCRMTargetCanaryError, match="symbolic links"):
        normalize_civicrm_target_canary(manifest, tmp_path / "symlink-out")

    manifest = _create_bundle(tmp_path / "nonregular")
    contacts = manifest.parent / "contacts.json"
    contacts.unlink()
    contacts.mkdir()
    with pytest.raises(CiviCRMTargetCanaryError, match="unexpected file type"):
        normalize_civicrm_target_canary(manifest, tmp_path / "nonregular-out")


def test_rejects_bad_json_utf8_constants_depth_nodes_and_root_shape(tmp_path: Path) -> None:
    cases: list[tuple[str, bytes, str]] = [
        ("utf8", b"\xff", "UTF-8"),
        ("syntax", b"{", "valid JSON"),
        ("constant", b'{"values":NaN}', "non-finite"),
        ("root", b"[]", "must be an object"),
        ("depth", (b'{"x":' * 35) + b"0" + (b"}" * 35), "nesting"),
        ("nodes", canonical_json_bytes({"values": [0] * 20_100}), "node limit"),
    ]
    for name, document, message in cases:
        manifest = _create_bundle(tmp_path / name)
        (manifest.parent / "contacts.json").write_bytes(document)
        _refresh_manifest(manifest)
        with pytest.raises(CiviCRMTargetCanaryError, match=message):
            normalize_civicrm_target_canary(manifest, tmp_path / f"{name}-out")


@pytest.mark.parametrize(
    ("filename", "mutate", "message"),
    [
        (
            "contacts.json",
            lambda raw: raw["values"][0].update({"unexpected": True}),
            "invalid field set",
        ),
        (
            "contacts.json",
            lambda raw: raw.update({"countFetched": 2}),
            "counts do not match",
        ),
        (
            "contacts.json",
            lambda raw: raw["values"].pop(),
            "item counts",
        ),
        (
            "contacts.json",
            lambda raw: raw["values"][0].update({"id": True}),
            "supported range",
        ),
        (
            "contacts.json",
            lambda raw: raw["values"][0].update({"display_name": "different"}),
            "display names must match",
        ),
        (
            "contacts.json",
            lambda raw: raw["values"][1].update({"exitdrill_person_profile.source_id": "1"}),
            "identifiers must be unique",
        ),
        (
            "cases.json",
            lambda raw: raw["values"][0].update({"case_type_id:name": "other"}),
            "case type",
        ),
        (
            "cases.json",
            lambda raw: raw["values"][0].update({"status_id:name": "Closed"}),
            "target case status",
        ),
        (
            "cases.json",
            lambda raw: raw["values"][1].update(
                {"exitdrill_case_profile.source_document_id": _FILE_IDS[0]}
            ),
            "identifiers must be unique",
        ),
        (
            "relationships.json",
            lambda raw: raw["values"][0].update({"contact_id_b": 999}),
            "unknown source-mapped entity",
        ),
        (
            "relationships.json",
            lambda raw: raw["values"][0].update({"relationship_type_id.name_a_b": "Employee of"}),
            "relationship type",
        ),
        (
            "relationships.json",
            lambda raw: raw["values"][0].update({"is_active": False}),
            "must be active",
        ),
        (
            "relationships.json",
            lambda raw: raw["values"][0].update({"description": "other"}),
            "description",
        ),
        (
            "relationships.json",
            lambda raw: raw["values"][1].update({"contact_id_a": 901}),
            "helper contact",
        ),
        (
            "files.json",
            lambda raw: raw["values"][0].update({"mime_type": "application/json"}),
            "private text/plain",
        ),
        (
            "files.json",
            lambda raw: raw["values"][0].update({"is_public": True}),
            "private text/plain",
        ),
        (
            "files.json",
            lambda raw: raw["values"][0].update({"file_name": "../escape.txt"}),
            "plain .txt",
        ),
        (
            "files.json",
            lambda raw: raw["values"][0].update({"file_name": "safe-but-drifted.txt"}),
            "pinned CiviCRM normalization",
        ),
        (
            "entity-files.json",
            lambda raw: raw["values"][0].update({"entity_table": "civicrm_contact"}),
            "civicrm_case",
        ),
        (
            "entity-files.json",
            lambda raw: raw["values"][0].update({"file_id": 999}),
            "unknown target record",
        ),
        (
            "permission-allow.json",
            lambda raw: raw["values"][0].update({"id": 102}),
            "permission-probe object",
        ),
        (
            "permission-allow.json",
            lambda raw: raw["values"][0].update({"display_name": "Synthetic Person Bravo"}),
            "permission-probe object",
        ),
    ],
)
def test_rejects_closed_shape_and_cross_document_drift(
    tmp_path: Path,
    filename: str,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    manifest = _create_bundle(tmp_path / "capture")
    _mutate_json(manifest, filename, mutate)

    with pytest.raises(CiviCRMTargetCanaryError, match=message):
        normalize_civicrm_target_canary(manifest, tmp_path / "out")


@pytest.mark.parametrize(
    ("filename", "mutate", "message"),
    [
        (
            "contacts.json",
            lambda raw: raw.update({"values": {}}),
            "must be an array",
        ),
        (
            "contacts.json",
            lambda raw: raw.update({"debug": True}),
            "invalid field set",
        ),
        (
            "contacts.json",
            lambda raw: raw["values"][0].update({"display_name": ""}),
            "non-empty trimmed string",
        ),
        (
            "contacts.json",
            lambda raw: raw["values"][0].update({"exitdrill_person_profile.source_id": "bad id"}),
            "stable source identifier",
        ),
        (
            "contacts.json",
            lambda raw: raw["values"][0].update({"exitdrill_person_profile.source_active": 1}),
            "must be a boolean",
        ),
        (
            "contacts.json",
            lambda raw: raw["values"][2].update({"exitdrill_person_profile.source_id": "4"}),
            "source identity inventory",
        ),
        (
            "cases.json",
            lambda raw: raw["values"][0].update(
                {"exitdrill_case_profile.source_document_id": "not-a-uuid"}
            ),
            "lowercase UUID",
        ),
        (
            "cases.json",
            lambda raw: raw["values"][1].update({"exitdrill_case_profile.source_id": "3"}),
            "source identity inventory",
        ),
        (
            "relationships.json",
            lambda raw: raw["values"][1].update({"id": 301}),
            "identifiers and endpoints must be unique",
        ),
        (
            "relationships.json",
            lambda raw: raw["values"][1].update({"contact_id_a": 899}),
            "helper contact",
        ),
        (
            "files.json",
            lambda raw: raw["values"][1].update({"id": 401}),
            "file identifiers must be unique",
        ),
        (
            "files.json",
            lambda raw: raw["values"][1].update(
                {
                    "description": "33333333-3333-4333-8333-333333333333",
                    "file_name": "33333333_3333_4333_8333_333333333333.txt",
                }
            ),
            "attachment inventory",
        ),
        (
            "entity-files.json",
            lambda raw: raw["values"][1].update({"id": 501}),
            "associations must be unique",
        ),
        (
            "identity-reader.json",
            lambda raw: raw.update({"contact_id": 0}),
            "supported range",
        ),
    ],
)
def test_rejects_primitive_inventory_and_uniqueness_drift(
    tmp_path: Path,
    filename: str,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    manifest = _create_bundle(tmp_path / "capture")
    _mutate_json(manifest, filename, mutate)

    with pytest.raises(CiviCRMTargetCanaryError, match=message):
        normalize_civicrm_target_canary(manifest, tmp_path / "out")


def test_rejects_manifest_list_file_list_and_digest_primitive_drift(tmp_path: Path) -> None:
    limitations = _create_bundle(tmp_path / "limitations")
    raw = _read_json(limitations)
    raw["limitations"] = raw["limitations"][:-1]
    _write_json(limitations, raw)
    with pytest.raises(CiviCRMTargetCanaryError, match="pinned profile"):
        normalize_civicrm_target_canary(limitations, tmp_path / "limitations-out")

    file_list = _create_bundle(tmp_path / "file-list")
    raw = _read_json(file_list)
    raw["files"] = {}
    _write_json(file_list, raw)
    with pytest.raises(CiviCRMTargetCanaryError, match="must be an array"):
        normalize_civicrm_target_canary(file_list, tmp_path / "file-list-out")

    file_count = _create_bundle(tmp_path / "file-count")
    raw = _read_json(file_count)
    raw["files"].pop()
    _write_json(file_count, raw)
    with pytest.raises(CiviCRMTargetCanaryError, match="exactly 16"):
        normalize_civicrm_target_canary(file_count, tmp_path / "file-count-out")

    digest = _create_bundle(tmp_path / "digest")
    raw = _read_json(digest)
    raw["bundle_sha256"] = "not-a-digest"
    _write_json(digest, raw)
    with pytest.raises(CiviCRMTargetCanaryError, match="lowercase SHA-256"):
        normalize_civicrm_target_canary(digest, tmp_path / "digest-out")


def test_rejects_identity_collisions_and_authx_drift(tmp_path: Path) -> None:
    duplicate = _create_bundle(tmp_path / "duplicate")
    _mutate_json(
        duplicate,
        "identity-deny.json",
        lambda raw: raw.update({"user_id": 1003}),
    )
    with pytest.raises(CiviCRMTargetCanaryError, match="identities must be distinct"):
        normalize_civicrm_target_canary(duplicate, tmp_path / "duplicate-out")

    collision = _create_bundle(tmp_path / "collision")
    _mutate_json(
        collision,
        "identity-deny.json",
        lambda raw: raw.update({"contact_id": 101}),
    )
    with pytest.raises(CiviCRMTargetCanaryError, match="must not collide"):
        normalize_civicrm_target_canary(collision, tmp_path / "collision-out")

    authx = _create_bundle(tmp_path / "authx")
    _mutate_json(authx, "identity-reader.json", lambda raw: raw.update({"cred": "fail"}))
    with pytest.raises(CiviCRMTargetCanaryError, match="AuthX profile"):
        normalize_civicrm_target_canary(authx, tmp_path / "authx-out")


def test_helper_contact_must_not_be_a_probe_identity(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "capture")

    def use_identity_as_helper(raw: dict[str, Any]) -> None:
        for item in raw["values"]:
            item["contact_id_a"] = 901

    _mutate_json(
        manifest,
        "relationships.json",
        use_identity_as_helper,
    )

    with pytest.raises(CiviCRMTargetCanaryError, match="target-only helper contact"):
        normalize_civicrm_target_canary(manifest, tmp_path / "out")


def test_existing_nested_and_missing_parent_destinations_are_rejected(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "capture")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    sentinel = out_dir / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(CiviCRMTargetCanaryError, match="already exists"):
        normalize_civicrm_target_canary(manifest, out_dir)
    assert sentinel.read_text(encoding="utf-8") == "preserve"

    with pytest.raises(CiviCRMTargetCanaryError, match="outside the capture bundle"):
        normalize_civicrm_target_canary(manifest, manifest.parent / "normalized")

    missing_parent = tmp_path / "missing-parent" / "out"
    with pytest.raises(CiviCRMTargetCanaryError, match="output parent"):
        normalize_civicrm_target_canary(manifest, missing_parent)
    assert not missing_parent.parent.exists()


@pytest.mark.parametrize(
    "result_name",
    [
        "target-result.json",
        "ui-surface-result.json",
        "browser-workflow-result.json",
        "accessibility-result.json",
    ],
)
def test_failed_materialization_removes_temporary_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result_name: str
) -> None:
    manifest = _create_bundle(tmp_path / "capture")
    original = Path.write_bytes

    def fail_on_result(path: Path, data: bytes) -> int:
        if path.name == result_name:
            raise OSError("injected write failure")
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_on_result)

    with pytest.raises(CiviCRMTargetCanaryError, match="could not be materialized"):
        normalize_civicrm_target_canary(manifest, tmp_path / "out")

    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".out.tmp-*"))


def test_manifest_name_root_symlink_and_output_symlink_are_rejected(tmp_path: Path) -> None:
    manifest = _create_bundle(tmp_path / "name")
    renamed = manifest.with_name("manifest.json")
    manifest.rename(renamed)
    with pytest.raises(CiviCRMTargetCanaryError, match="named capture-manifest"):
        normalize_civicrm_target_canary(renamed, tmp_path / "name-out")

    real_root = tmp_path / "real"
    _create_bundle(real_root)
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(CiviCRMTargetCanaryError, match="symbolic links"):
        normalize_civicrm_target_canary(
            linked_root / "capture-manifest.json", tmp_path / "linked-out"
        )

    manifest = _create_bundle(tmp_path / "output-link-capture")
    target = tmp_path / "target"
    target.mkdir()
    output_link = tmp_path / "output-link"
    output_link.symlink_to(target, target_is_directory=True)
    with pytest.raises(CiviCRMTargetCanaryError, match="already exists"):
        normalize_civicrm_target_canary(manifest, output_link)


def test_missing_root_asset_symlink_and_oversized_manifest_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(CiviCRMTargetCanaryError, match="root must be a directory"):
        normalize_civicrm_target_canary(
            tmp_path / "missing" / "capture-manifest.json", tmp_path / "missing-out"
        )

    manifest = _create_bundle(tmp_path / "asset-link")
    asset = manifest.parent / f"assets/{_FILE_IDS[0]}.txt"
    target = tmp_path / "asset-target.txt"
    asset.rename(target)
    asset.symlink_to(target)
    with pytest.raises(CiviCRMTargetCanaryError, match="asset entries"):
        normalize_civicrm_target_canary(manifest, tmp_path / "asset-link-out")

    manifest = _create_bundle(tmp_path / "large-manifest")
    manifest.write_bytes(b" " * (64 * 1024 + 1))
    with pytest.raises(CiviCRMTargetCanaryError, match="byte limit"):
        normalize_civicrm_target_canary(manifest, tmp_path / "large-manifest-out")


def test_module_has_no_evaluator_receipt_report_or_connector_abstraction() -> None:
    source = (Path(__file__).parents[1] / "src/exitdrill/civicrm_target_canary.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "exitdrill.evaluator",
        "exitdrill.receipt",
        "exitdrill.comparison",
        "exitdrill.report",
        "Connector",
        "plugin",
        "mapping_expression",
    ):
        assert forbidden not in source
