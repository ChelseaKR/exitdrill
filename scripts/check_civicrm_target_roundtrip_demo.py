#!/usr/bin/env python3
"""Verify the pinned CiviCRM target read-back and its adversarial controls offline."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from exitdrill.civicrm_target_canary import (
    CiviCRMTargetCanaryError,
    normalize_civicrm_target_canary,
    verify_civicrm_evidence_index,
)
from exitdrill.directus_canary import normalize_directus_canary
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export

PROJECT = Path(__file__).parents[1]
DIRECTUS = PROJECT / "examples" / "directus-11.17.4-civic-case"
TARGET = PROJECT / "examples" / "civicrm-6.16.2-target-roundtrip"
BASELINE = DIRECTUS / "baseline.json"
DIRECTUS_NATIVE = DIRECTUS / "native"
TARGET_NATIVE = TARGET / "native"

TARGET_PROFILE = "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1"
SOURCE_PROFILE = "directus-11.17.4-civic-case/v0.1"
TARGET_RESULT_NAME = "target-result.json"
UI_RESULT_NAME = "ui-surface-result.json"
BROWSER_RESULT_NAME = "browser-workflow-result.json"
ACCESSIBILITY_RESULT_NAME = "accessibility-result.json"
KEYBOARD_RESULT_NAME = "keyboard-result.json"
ACTIVITY_VIEW_RESULT_NAME = "activity-view-result.json"
EVIDENCE_INDEX_NAME = "evidence-index.json"
PROBE_IDS = (
    "record_lookup",
    "relationship_traversal",
    "attachment_retrieval",
    "authorized_access",
    "unauthorized_denial",
)
PROBE_EVIDENCE = {
    "record_lookup": "independent_api_v4_readback",
    "relationship_traversal": "independent_api_v4_relationship_readback",
    "attachment_retrieval": "authenticated_private_file_bytes",
    "authorized_access": "permission_enforced_api_v4_contact_get",
    "unauthorized_denial": "permission_enforced_api_v4_contact_get",
}
VARIANTS = (
    "scalar-substitution",
    "relationship-rewire",
    "attachment-corruption",
    "permission-escalation",
    "nonempty-precondition",
)

_RAW_SENTINELS = (
    "Synthetic Person Alpha",
    "Synthetic Person Bravo",
    "Synthetic Person Canary",
    "Invented intake note alpha.",
    "Invented intake note bravo.",
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
)
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "credential",
        "credentials",
        "password",
        "api_key",
        "site_key",
        "token",
    }
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return cast(dict[str, object], value)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _build_adversaries(source: Path, destination: Path) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [
            sys.executable,
            str(PROJECT / "scripts" / "build_civicrm_target_adversaries.py"),
            str(source),
            str(destination),
        ],
        cwd=PROJECT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"CiviCRM adversary build failed: {completed.stderr.strip()}")
    _require(completed.stdout == "", "adversary builder wrote unexpected stdout")
    return completed.stderr


def _structural_payload(normalized: Path) -> dict[str, object]:
    baseline = load_baseline(BASELINE)
    package = load_export(normalized / "export.json")
    result = run_drill(baseline, package, normalized / "export-files")
    return cast(dict[str, object], result.payload())


def _dimensions(payload: Mapping[str, object]) -> dict[str, dict[str, object]]:
    raw = payload.get("dimensions")
    if not isinstance(raw, list):
        raise RuntimeError("structural dimensions must be an array")
    dimensions: dict[str, dict[str, object]] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise RuntimeError("structural dimension is malformed")
        dimensions[cast(str, item["name"])] = cast(dict[str, object], item)
    return dimensions


def _assert_clean_structural(payload: Mapping[str, object]) -> None:
    _require(
        payload.get("overall_status") == "not_structurally_restorable",
        "clean target read-back did not preserve the intentional structural failure",
    )
    _require(
        payload.get("observed_remediation_signals") == 6,
        "clean target read-back did not preserve exactly six structural gaps",
    )
    expected = {
        "entities": (7, 5, 5, 2, 0, 0, "fail"),
        "relationships": (2, 2, 2, 0, 0, 0, "pass"),
        "attachments": (2, 2, 2, 0, 0, 0, "pass"),
        "permissions": (2, 0, 0, 2, 0, 0, "fail"),
        "audit_events": (2, 0, 0, 2, 0, 0, "fail"),
    }
    for name, values in expected.items():
        item = _dimensions(payload)[name]
        observed = (
            item["expected_count"],
            item["exported_count"],
            item["restored_count"],
            item["missing_count"],
            item["extra_count"],
            item["invalid_count"],
            item["status"],
        )
        _require(observed == values, f"clean target {name} evidence is not exact")


def _assert_adversarial_structural(
    payload: Mapping[str, object],
    clean_payload: Mapping[str, object],
    dimension_name: str,
    *,
    missing: int,
    extra: int,
    invalid: int,
) -> None:
    _require(
        payload.get("overall_status") == "not_structurally_restorable",
        "adversarial target read-back did not fail structurally",
    )
    _require(
        payload.get("observed_remediation_signals") == 7,
        "adversarial target read-back did not add exactly one detected loss signal",
    )
    dimensions = _dimensions(payload)
    clean_dimensions = _dimensions(clean_payload)
    item = dimensions[dimension_name]
    _require(item["missing_count"] == missing, "adversarial missing count was not exact")
    _require(item["extra_count"] == extra, "adversarial extra count was not exact")
    _require(item["invalid_count"] == invalid, "adversarial invalid count was not exact")
    _require(item["status"] == "fail", "adversarial dimension did not fail")
    for name, clean in clean_dimensions.items():
        if name != dimension_name:
            _require(dimensions[name] == clean, "adversary changed an unrelated dimension")


def _probe_results(document: Mapping[str, object]) -> dict[str, str]:
    raw = document.get("probe_results")
    if not isinstance(raw, list):
        raise RuntimeError("target probe results must be an array")
    probes: dict[str, str] = {}
    observed_order: list[str] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"id", "state", "evidence_kind"}:
            raise RuntimeError("target probe result has an invalid field set")
        probe_id = item.get("id")
        state = item.get("state")
        evidence_kind = item.get("evidence_kind")
        if (
            not isinstance(probe_id, str)
            or probe_id in probes
            or state not in {"pass", "fail"}
            or not isinstance(evidence_kind, str)
            or not evidence_kind
        ):
            raise RuntimeError("target probe result is malformed")
        _require(
            evidence_kind == PROBE_EVIDENCE.get(probe_id),
            "target probe evidence kind was not exact",
        )
        probes[probe_id] = cast(str, state)
        observed_order.append(probe_id)
    _require(set(probes) == set(PROBE_IDS), "target probe ids were not exact")
    _require(tuple(observed_order) == PROBE_IDS, "target probe order was not exact")
    return probes


def _assert_clean_target_result(document: Mapping[str, object]) -> None:
    _require(
        set(document)
        == {
            "schema_version",
            "target_profile",
            "source_profile",
            "decision_scope",
            "probe_results",
            "represented_counts",
            "unmapped_counts",
            "target_generated_counts",
            "limitations",
        },
        "target result field set was not exact",
    )
    _require(
        document.get("schema_version") == "exitdrill/civicrm-target-roundtrip-result/v0.1",
        "target result schema was not exact",
    )
    _require(document.get("target_profile") == TARGET_PROFILE, "target profile was not exact")
    _require(document.get("source_profile") == SOURCE_PROFILE, "source profile was not exact")
    _require(
        document.get("decision_scope") == "pinned_synthetic_target_roundtrip_only",
        "target decision scope was not bounded",
    )
    _require(
        _probe_results(document) == {probe_id: "pass" for probe_id in PROBE_IDS},
        "clean target did not pass all five probes",
    )
    _require(
        document.get("represented_counts")
        == {
            "entities": 5,
            "relationships": 2,
            "attachments": 2,
            "permissions": 0,
            "audit_events": 0,
        },
        "target represented counts were not exact",
    )
    _require(
        document.get("unmapped_counts")
        == {
            "entities": 2,
            "relationships": 0,
            "attachments": 0,
            "permissions": 2,
            "audit_events": 2,
        },
        "target unmapped counts were not exact",
    )
    _require(
        document.get("target_generated_counts")
        == {
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
        },
        "target-generated counts were not exact",
    )
    _require(
        document.get("limitations")
        == [
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
        ],
        "target limitations were not exact",
    )


def _assert_clean_ui_result(document: Mapping[str, object]) -> None:
    _require(
        document
        == {
            "decision_scope": "pinned_synthetic_ui_surface_only",
            "limitations": [
                "synthetic_fixture_only",
                "target_evidence_is_unsigned_and_unauthenticated",
                "server_rendered_html_projection_only",
                "does_not_prove_browser_interaction_or_javascript_behavior",
                "does_not_prove_accessibility_or_end_to_end_task_completion",
                "manage_case_and_case_workflow_not_observed",
                "does_not_prove_operational_equivalence",
                "target_version_and_execution_context_are_operator_asserted",
            ],
            "schema_version": "exitdrill/civicrm-ui-surface-result/v0.1",
            "surface_results": [
                {
                    "evidence_kind": "authenticated_server_rendered_html_projection",
                    "id": "contact_summary",
                    "state": "observed",
                }
            ],
            "target_profile": TARGET_PROFILE,
        },
        "clean UI-surface result was not exact",
    )


def _assert_clean_browser_result(document: Mapping[str, object]) -> None:
    _require(
        document
        == {
            "decision_scope": "pinned_synthetic_browser_workflow_only",
            "known_runtime_errors": [
                {
                    "error_key": "jquery_notify_unavailable",
                    "occurrence_count": 2,
                }
            ],
            "limitations": [
                "synthetic_fixture_only",
                "target_evidence_is_unsigned_and_unauthenticated",
                "single_case_browser_workflow_only",
                "browser_workflow_observed_with_known_jquery_notify_runtime_errors",
                "does_not_prove_accessibility",
                "does_not_prove_operational_equivalence",
                "target_version_and_execution_context_are_operator_asserted",
            ],
            "schema_version": "exitdrill/civicrm-browser-workflow-result/v0.1",
            "target_profile": TARGET_PROFILE,
            "workflow_results": [
                {
                    "evidence_kind": "isolated_headless_chromium_interaction",
                    "id": "case_dashboard_to_manage_case",
                    "state": "observed",
                }
            ],
        },
        "clean browser-workflow result was not exact",
    )


def _assert_clean_accessibility_result(document: Mapping[str, object]) -> None:
    _require(
        document
        == {
            "decision_scope": "pinned_synthetic_manage_case_automated_scan_only",
            "limitations": [
                "synthetic_fixture_only",
                "target_evidence_is_unsigned_and_unauthenticated",
                "single_manage_case_document_only",
                "automated_rules_only",
                "does_not_cover_keyboard_navigation",
                "does_not_cover_screen_reader_behavior",
                "does_not_cover_zoom_reflow",
                "does_not_establish_wcag_conformance",
                "target_version_and_execution_context_are_operator_asserted",
            ],
            "scan_result": {
                "engine": "axe-core",
                "engine_version": "4.12.1",
                "inapplicable_rule_count": 29,
                "incomplete_rule_count": 0,
                "page_scope": "manage_case_document",
                "passes_rule_count": 32,
                "rule_tags": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
                "violations": [
                    {"impact": "serious", "node_count": 4, "rule_id": "color-contrast"},
                    {
                        "impact": "serious",
                        "node_count": 2,
                        "rule_id": "link-in-text-block",
                    },
                ],
            },
            "schema_version": "exitdrill/civicrm-accessibility-result/v0.1",
            "target_profile": TARGET_PROFILE,
        },
        "clean accessibility result was not exact",
    )


def _assert_clean_keyboard_result(document: Mapping[str, object]) -> None:
    _require(
        document
        == {
            "decision_scope": "pinned_synthetic_manage_case_keyboard_interaction_only",
            "limitations": [
                "synthetic_fixture_only",
                "target_evidence_is_unsigned_and_unauthenticated",
                "single_manage_case_roles_disclosure_only",
                "programmatic_keyboard_events_only",
                "does_not_cover_complete_tab_order",
                "does_not_assess_visible_focus_indicator",
                "does_not_cover_screen_reader_behavior",
                "does_not_establish_keyboard_accessibility",
                "does_not_establish_wcag_conformance",
                "target_version_and_execution_context_are_operator_asserted",
            ],
            "observation": {
                "browser_engine": "chromium",
                "steps": [
                    "roles_summary_reached_by_tab",
                    "roles_summary_closed_by_enter",
                    "roles_summary_reopened_by_space",
                ],
                "tab_steps_to_roles_summary": 69,
            },
            "schema_version": "exitdrill/civicrm-keyboard-result/v0.1",
            "target_profile": TARGET_PROFILE,
        },
        "clean keyboard result was not exact",
    )


def _assert_clean_activity_view_result(document: Mapping[str, object]) -> None:
    _require(
        document
        == {
            "decision_scope": "pinned_synthetic_generated_activity_view_only",
            "known_runtime_errors": [
                {"error_key": "jquery_notify_unavailable", "occurrence_count": 1}
            ],
            "limitations": [
                "synthetic_fixture_only",
                "target_evidence_is_unsigned_and_unauthenticated",
                "single_generated_open_case_activity_only",
                "activity_view_observed_with_known_jquery_notify_runtime_error",
                "read_only_activity_view_only",
                "does_not_prove_activity_editing_or_creation",
                "does_not_prove_operational_equivalence",
                "target_version_and_execution_context_are_operator_asserted",
            ],
            "schema_version": "exitdrill/civicrm-activity-view-result/v0.1",
            "target_profile": TARGET_PROFILE,
            "workflow_results": [
                {
                    "evidence_kind": "isolated_headless_chromium_read_only_interaction",
                    "id": "generated_open_case_activity_view",
                    "state": "observed",
                }
            ],
        },
        "clean activity-view result was not exact",
    )


def _assert_clean_evidence_index(document: Mapping[str, object], root: Path) -> None:
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError("clean evidence index entries were not an array")
    _require(
        [item.get("artifact_id") for item in entries if isinstance(item, dict)]
        == [
            "normalized_target_readback",
            "target_interface",
            "ui_surface",
            "browser_workflow",
            "automated_accessibility",
            "keyboard_interaction",
            "activity_view",
        ],
        "clean evidence index artifact order was not exact",
    )
    for item in entries:
        if not isinstance(item, dict):
            raise RuntimeError("clean evidence index entry was not an object")
        raw_filename = item.get("filename")
        _require(isinstance(raw_filename, str), "clean evidence index filename was not a string")
        filename = cast("str", raw_filename)
        content = (root / filename).read_bytes()
        _require(item.get("bytes") == len(content), "clean evidence index size was not exact")
        _require(
            item.get("sha256") == hashlib.sha256(content).hexdigest(),
            "clean evidence index digest was not exact",
        )
    _require(
        document.get("decision_scope") == "separate_non_composite_evidence_families",
        "clean evidence index scope was not exact",
    )
    _require(
        document.get("limitations")
        == [
            "index_is_unsigned_and_unauthenticated",
            "index_is_not_a_composite_assessment",
            "entries_have_independent_decision_scopes",
            "normalized_export_requires_separate_baseline_evaluation",
            "each_result_must_be_interpreted_with_its_own_limitations",
            "digests_prove_internal_consistency_not_authenticity",
            "target_version_and_execution_context_are_operator_asserted",
        ],
        "clean evidence index limitations were not exact",
    )
    _require(
        document.get("schema_version") == "exitdrill/civicrm-evidence-index/v0.2"
        and document.get("target_profile") == TARGET_PROFILE,
        "clean evidence index profile was not exact",
    )


def _assert_aggregate_privacy(value: object, roots: tuple[Path, ...]) -> None:
    def walk(item: object) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                _require(
                    key.lower() not in _SENSITIVE_KEYS, "aggregate evidence exposed a secret field"
                )
                walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)

    walk(value)
    serialized = json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))
    for sentinel in _RAW_SENTINELS:
        _require(sentinel not in serialized, "aggregate evidence disclosed a raw fixture sentinel")
    for root in roots:
        _require(str(root) not in serialized, "aggregate evidence disclosed a filesystem path")


def _assert_builder_statement(path: Path) -> None:
    statement = _json_object(path)
    _require(
        statement.get("schema_version") == "exitdrill/civicrm-target-adversaries/v0.1",
        "adversarial statement schema was not exact",
    )
    _require(
        statement.get("mutations") == list(VARIANTS),
        "adversarial statement mutations were not exact",
    )
    _require(
        statement.get("target_data_row_counts_preserved") is True,
        "adversarial target row counts were not preserved",
    )
    _require(
        statement.get("attachment_file_counts_and_sizes_preserved") is True,
        "adversarial attachment counts or sizes were not preserved",
    )


def _assert_source_normalization_binding(
    target_manifest: Mapping[str, object],
    directus_result: Mapping[str, object],
) -> None:
    binding = target_manifest.get("source_normalization")
    _require(isinstance(binding, dict), "target manifest omitted its source normalization binding")
    expected = {
        "adapter_profile": directus_result.get("adapter_profile"),
        "attachment_bundle_sha256": directus_result.get("attachment_bundle_sha256"),
        "export_sha256": directus_result.get("export_sha256"),
        "schema_version": directus_result.get("schema_version"),
        "source_bundle_sha256": directus_result.get("source_bundle_sha256"),
    }
    _require(binding == expected, "target manifest did not bind the verified source normalization")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="exitdrill-civicrm-target-") as raw_temp:
        root = Path(raw_temp)
        directus_normalized = root / "directus-normalized"
        clean_a = root / "clean-a"
        clean_b = root / "clean-b"
        adversaries = root / "adversaries"

        directus_result = normalize_directus_canary(
            DIRECTUS_NATIVE / "capture-manifest.json",
            directus_normalized,
        )
        _assert_source_normalization_binding(
            _json_object(TARGET_NATIVE / "capture-manifest.json"),
            directus_result,
        )
        clean_result_a = normalize_civicrm_target_canary(
            TARGET_NATIVE / "capture-manifest.json",
            clean_a,
        )
        clean_result_b = normalize_civicrm_target_canary(
            TARGET_NATIVE / "capture-manifest.json",
            clean_b,
        )
        _require(
            clean_result_a == clean_result_b, "clean normalization aggregate was not deterministic"
        )
        _require(
            _tree_digest(clean_a) == _tree_digest(clean_b), "clean normalization was not byte exact"
        )

        clean_payload = _structural_payload(clean_a)
        _assert_clean_structural(clean_payload)
        clean_target_result = _json_object(clean_a / TARGET_RESULT_NAME)
        _require(
            clean_target_result == clean_result_a,
            "returned clean aggregate did not match target-result.json",
        )
        _assert_clean_target_result(clean_target_result)
        clean_ui_result = _json_object(clean_a / UI_RESULT_NAME)
        _assert_clean_ui_result(clean_ui_result)
        clean_browser_result = _json_object(clean_a / BROWSER_RESULT_NAME)
        _assert_clean_browser_result(clean_browser_result)
        clean_accessibility_result = _json_object(clean_a / ACCESSIBILITY_RESULT_NAME)
        _assert_clean_accessibility_result(clean_accessibility_result)
        clean_keyboard_result = _json_object(clean_a / KEYBOARD_RESULT_NAME)
        _assert_clean_keyboard_result(clean_keyboard_result)
        clean_activity_view_result = _json_object(clean_a / ACTIVITY_VIEW_RESULT_NAME)
        _assert_clean_activity_view_result(clean_activity_view_result)
        clean_evidence_index = _json_object(clean_a / EVIDENCE_INDEX_NAME)
        _assert_clean_evidence_index(clean_evidence_index, clean_a)
        clean_evidence_index_verification = verify_civicrm_evidence_index(
            clean_a / EVIDENCE_INDEX_NAME
        )
        _require(
            clean_evidence_index_verification.get("status") == "evidence_index_bindings_verified",
            "clean evidence index binding verification was not exact",
        )

        committed_target_digest = _tree_digest(TARGET_NATIVE)
        builder_stderr = _build_adversaries(TARGET_NATIVE, adversaries)
        _require(builder_stderr == "", "adversary builder wrote unexpected stderr")
        _require(
            _tree_digest(TARGET_NATIVE) == committed_target_digest,
            "adversary builder changed the committed target bundle",
        )
        _assert_builder_statement(adversaries / "adversarial-derivatives.json")

        adversarial_outputs: dict[str, dict[str, object]] = {}
        for variant in (
            "scalar-substitution",
            "relationship-rewire",
            "attachment-corruption",
            "permission-escalation",
        ):
            output = root / f"normalized-{variant}"
            aggregate = normalize_civicrm_target_canary(
                adversaries / variant / "capture-manifest.json",
                output,
            )
            target_result = _json_object(output / TARGET_RESULT_NAME)
            _require(
                target_result == aggregate,
                "returned adversarial aggregate did not match target-result.json",
            )
            adversarial_outputs[variant] = {
                "aggregate": aggregate,
                "payload": _structural_payload(output),
                "target_result": target_result,
            }

        _assert_adversarial_structural(
            cast(dict[str, object], adversarial_outputs["scalar-substitution"]["payload"]),
            clean_payload,
            "entities",
            missing=2,
            extra=0,
            invalid=1,
        )
        _assert_adversarial_structural(
            cast(dict[str, object], adversarial_outputs["relationship-rewire"]["payload"]),
            clean_payload,
            "relationships",
            missing=1,
            extra=1,
            invalid=0,
        )
        _assert_adversarial_structural(
            cast(dict[str, object], adversarial_outputs["attachment-corruption"]["payload"]),
            clean_payload,
            "attachments",
            missing=0,
            extra=0,
            invalid=1,
        )

        permission_result = cast(
            dict[str, object],
            adversarial_outputs["permission-escalation"]["target_result"],
        )
        permission_probes = _probe_results(permission_result)
        _require(
            permission_probes["unauthorized_denial"] == "fail",
            "permission escalation did not fail the deny probe",
        )
        _require(
            all(
                status == "pass"
                for probe_id, status in permission_probes.items()
                if probe_id != "unauthorized_denial"
            ),
            "permission escalation changed an unrelated probe",
        )
        _assert_clean_structural(
            cast(dict[str, object], adversarial_outputs["permission-escalation"]["payload"])
        )

        rejected_output = root / "normalized-nonempty"
        try:
            normalize_civicrm_target_canary(
                adversaries / "nonempty-precondition" / "capture-manifest.json",
                rejected_output,
            )
        except CiviCRMTargetCanaryError:
            pass
        else:
            raise RuntimeError("nonempty target precondition was not rejected")
        _require(not rejected_output.exists(), "nonempty rejection created an output directory")

        aggregate_evidence = {
            "clean_normalization": clean_result_a,
            "clean_structural": clean_payload,
            "clean_target": clean_target_result,
            "clean_ui_surface": clean_ui_result,
            "clean_browser_workflow": clean_browser_result,
            "clean_accessibility": clean_accessibility_result,
            "clean_keyboard": clean_keyboard_result,
            "clean_activity_view": clean_activity_view_result,
            "clean_evidence_index": clean_evidence_index,
            "clean_evidence_index_verification": clean_evidence_index_verification,
            "directus_normalization": directus_result,
            "permission_escalation_target": permission_result,
        }
        _assert_aggregate_privacy(aggregate_evidence, (PROJECT, root))

        print(
            json.dumps(
                {
                    "adversarial_controls_detected": 5,
                    "clean_observed_remediation_signals": 6,
                    "clean_overall_status": "not_structurally_restorable",
                    "clean_target_probe_passes": 5,
                    "clean_browser_workflow_observations": 1,
                    "clean_accessibility_serious_violations": 2,
                    "clean_keyboard_tab_steps_to_roles_summary": 69,
                    "clean_activity_view_observations": 1,
                    "clean_evidence_index_entries": 7,
                    "clean_ui_surface_observations": 1,
                    "source_profile": SOURCE_PROFILE,
                    "status": "civicrm_target_roundtrip_canary_verified",
                    "target_profile": TARGET_PROFILE,
                },
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
