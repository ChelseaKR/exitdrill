import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from exitdrill.canonical import canonical_json_bytes, sha256_bytes
from exitdrill.cli import main
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import Dimension, DimensionStatus, JsonValue, classify_overall_status
from exitdrill.receipt import build_receipt, verify_receipt, write_receipt


def _stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    raw = json.loads(capsys.readouterr().out)
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


def _comparison_receipts(
    tmp_path: Path,
    example_root: Path,
) -> tuple[Path, Path]:
    lossy = Path(__file__).parents[1] / "examples" / "synthetic-crm-lossy"
    baseline = load_baseline(example_root / "baseline.json")
    reference_result = run_drill(
        baseline,
        load_export(example_root / "export.json"),
        example_root / "export-files",
    )
    candidate_result = run_drill(
        baseline,
        load_export(lossy / "export.json"),
        lossy / "export-files",
    )
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "candidate.json"
    write_receipt(
        reference,
        build_receipt(reference_result, claimed_generated_at="2030-01-01T00:00:00Z"),
    )
    write_receipt(
        candidate,
        build_receipt(candidate_result, claimed_generated_at="1900-01-01T00:00:00Z"),
    )
    return reference, candidate


def _payload(receipt: dict[str, JsonValue]) -> dict[str, JsonValue]:
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    return payload


def _dimension(receipt: dict[str, JsonValue], name: Dimension) -> dict[str, JsonValue]:
    dimensions = _payload(receipt)["dimensions"]
    assert isinstance(dimensions, list)
    for item in dimensions:
        assert isinstance(item, dict)
        if item["name"] == name.value:
            return item
    raise AssertionError(f"missing dimension {name}")


def _finalize_receipt(receipt: dict[str, JsonValue], export_character: str) -> None:
    payload = _payload(receipt)
    dimensions = payload["dimensions"]
    assert isinstance(dimensions, list)
    statuses: set[DimensionStatus] = set()
    remediation = 0
    for item in dimensions:
        assert isinstance(item, dict)
        statuses.add(DimensionStatus(cast(str, item["status"])))
        remediation += cast(int, item["missing_count"]) + cast(int, item["invalid_count"])
    payload["overall_status"] = classify_overall_status(statuses).value
    payload["observed_remediation_signals"] = remediation
    payload["export_sha256"] = export_character * 64
    receipt["payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    verify_receipt(receipt)


def _good_receipt(example_root: Path) -> dict[str, JsonValue]:
    result = run_drill(
        load_baseline(example_root / "baseline.json"),
        load_export(example_root / "export.json"),
        example_root / "export-files",
    )
    return build_receipt(result, claimed_generated_at="2040-01-01T00:00:00Z")


def test_validate_cli(example_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "validate",
                str(example_root / "baseline.json"),
                str(example_root / "export.json"),
            ]
        )
        == 0
    )
    assert _stdout(capsys)["status"] == "valid"


def test_normalize_directus_canary_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = Path(__file__).parents[1]
    native = project / "examples" / "directus-11.17.4-civic-case" / "native"
    out_dir = tmp_path / "normalized"

    assert (
        main(
            [
                "normalize-directus-canary",
                str(native / "capture-manifest.json"),
                "--out-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    raw_output = capsys.readouterr().out
    output = json.loads(raw_output)
    assert output["adapter_profile"] == "directus-11.17.4-civic-case/v0.1"
    assert output["counts"] == {
        "attachment_bytes": 56,
        "attachments": 2,
        "audit_events": 2,
        "entities": 7,
        "permissions": 2,
        "relationships": 2,
    }
    assert (out_dir / "export.json").is_file()
    assert (out_dir / "normalization-manifest.json").is_file()
    assert str(native) not in raw_output
    assert str(out_dir) not in raw_output
    assert "Synthetic Person Alpha" not in raw_output
    assert "11111111-1111-4111-8111-111111111111" not in raw_output


def test_normalize_directus_canary_cli_error_does_not_disclose_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = "private-native-source-location"
    manifest = tmp_path / marker / "capture-manifest.json"
    out_dir = tmp_path / "normalized"

    assert (
        main(
            [
                "normalize-directus-canary",
                str(manifest),
                "--out-dir",
                str(out_dir),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert marker not in captured.err
    assert str(tmp_path) not in captured.err
    assert not out_dir.exists()


def test_normalize_civicrm_target_canary_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = Path(__file__).parents[1]
    native = project / "examples" / "civicrm-6.16.2-target-roundtrip" / "native"
    out_dir = tmp_path / "normalized-target"

    assert (
        main(
            [
                "normalize-civicrm-target-canary",
                str(native / "capture-manifest.json"),
                "--out-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    raw_output = capsys.readouterr().out
    output = json.loads(raw_output)
    assert output["target_profile"] == (
        "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1"
    )
    assert [item["state"] for item in output["probe_results"]] == ["pass"] * 5
    assert (out_dir / "export.json").is_file()
    assert (out_dir / "target-result.json").is_file()
    assert (out_dir / "ui-surface-result.json").is_file()
    assert (out_dir / "browser-workflow-result.json").is_file()
    assert str(native) not in raw_output
    assert str(out_dir) not in raw_output
    assert "Synthetic Person Alpha" not in raw_output
    assert "11111111-1111-4111-8111-111111111111" not in raw_output


def test_verify_civicrm_evidence_index_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = Path(__file__).parents[1]
    native = project / "examples" / "civicrm-6.16.2-target-roundtrip" / "native"
    out_dir = tmp_path / "normalized-target"
    assert (
        main(
            [
                "normalize-civicrm-target-canary",
                str(native / "capture-manifest.json"),
                "--out-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["verify-civicrm-evidence-index", str(out_dir / "evidence-index.json")]) == 0
    assert _stdout(capsys) == {
        "artifact_count": 9,
        "attachment_count": 2,
        "decision_scope": "catalog_bindings_artifact_schemas_and_export_attachments_only",
        "index_schema_version": "exitdrill/civicrm-evidence-index/v0.4",
        "limitations": [
            "verification_is_unsigned_and_unauthenticated",
            "does_not_interpret_or_compose_artifact_results",
            "does_not_run_structural_evaluator",
            "does_not_prove_live_execution_or_completeness",
            "digests_prove_internal_consistency_not_authenticity",
        ],
        "schema_version": "exitdrill/civicrm-evidence-verification/v0.3",
        "status": "evidence_artifact_contracts_verified",
        "target_profile": ("directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1"),
    }


def test_normalize_civicrm_target_canary_cli_error_does_not_disclose_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = "private-target-capture-location"
    manifest = tmp_path / marker / "capture-manifest.json"
    out_dir = tmp_path / "normalized-target"

    assert (
        main(
            [
                "normalize-civicrm-target-canary",
                str(manifest),
                "--out-dir",
                str(out_dir),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert marker not in captured.err
    assert str(tmp_path) not in captured.err
    assert not out_dir.exists()


def test_validate_exercise_cli(capsys: pytest.CaptureFixture[str]) -> None:
    plan = Path(__file__).parents[1] / "examples" / "synthetic-exercise" / "plan.json"
    assert main(["validate-exercise", str(plan)]) == 0
    result = _stdout(capsys)
    assert result["status"] == "synthetic_protocol_valid"
    assert result["decision_scope"] == "plan_only_no_target_execution"


def test_compare_cli_reports_comparable_loss_signals(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reference, candidate = _comparison_receipts(tmp_path, example_root)
    assert main(["compare", str(reference), str(candidate)]) == 0
    unflagged = capsys.readouterr().out
    output = json.loads(unflagged)
    assert isinstance(output, dict)
    assert output["comparability"] == "comparable"
    assert output["ordering_basis"] == "caller_supplied_unverified"
    assert str(reference) not in unflagged
    assert str(candidate) not in unflagged
    assert "2030-01-01T00:00:00Z" not in unflagged
    assert "1900-01-01T00:00:00Z" not in unflagged

    assert (
        main(
            [
                "compare",
                str(reference),
                str(candidate),
                "--fail-on-loss-signal-increase",
            ]
        )
        == 3
    )
    assert capsys.readouterr().out == unflagged


def test_compare_cli_policy_allows_unchanged_and_decreased_signals(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    good, lossy = _comparison_receipts(tmp_path, example_root)
    for reference, candidate in ((good, good), (lossy, good)):
        assert (
            main(
                [
                    "compare",
                    str(reference),
                    str(candidate),
                    "--fail-on-loss-signal-increase",
                ]
            )
            == 0
        )
        assert _stdout(capsys)["comparability"] == "comparable"


def test_compare_cli_policy_ignores_status_and_extra_only_change(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reference_receipt = _good_receipt(example_root)
    candidate_receipt = deepcopy(reference_receipt)
    _dimension(candidate_receipt, Dimension.ENTITIES).update(
        {
            "exported_count": 3,
            "extra_count": 1,
            "restored_count": 3,
            "status": "finding",
        }
    )
    _finalize_receipt(candidate_receipt, "a")
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "candidate.json"
    write_receipt(reference, reference_receipt)
    write_receipt(candidate, candidate_receipt)

    assert (
        main(
            [
                "compare",
                str(reference),
                str(candidate),
                "--fail-on-loss-signal-increase",
            ]
        )
        == 0
    )
    output = _stdout(capsys)
    dimensions = cast(list[dict[str, object]], output["dimensions"])
    assert dimensions[0]["status_transition"] == "changed"
    assert dimensions[0]["extra_count_transition"] == "changed_from_zero"
    assert dimensions[0]["observed_loss_signal_increases"] == []


def test_compare_cli_policy_trips_on_mixed_observed_movement(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reference_receipt = _good_receipt(example_root)
    candidate_receipt = deepcopy(reference_receipt)
    _dimension(reference_receipt, Dimension.ENTITIES).update(
        {
            "exported_count": 1,
            "missing_count": 1,
            "restored_count": 1,
            "status": "fail",
        }
    )
    _dimension(candidate_receipt, Dimension.ENTITIES).update(
        {
            "invalid_count": 1,
            "status": "fail",
        }
    )
    _finalize_receipt(reference_receipt, "b")
    _finalize_receipt(candidate_receipt, "c")
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "candidate.json"
    write_receipt(reference, reference_receipt)
    write_receipt(candidate, candidate_receipt)

    assert (
        main(
            [
                "compare",
                str(reference),
                str(candidate),
                "--fail-on-loss-signal-increase",
            ]
        )
        == 3
    )
    output = _stdout(capsys)
    dimensions = cast(list[dict[str, object]], output["dimensions"])
    assert dimensions[0]["assessment"] == "mixed_loss_signal_change"
    assert dimensions[0]["observed_loss_signal_increases"] == ["invalid_count_increased"]
    assert dimensions[0]["observed_loss_signal_decreases"] == ["missing_count_decreased"]


@pytest.mark.parametrize("coverage", ["partial", "unavailable"])
def test_compare_cli_policy_can_trip_while_assessment_stays_uncertain(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
    coverage: str,
) -> None:
    reference_receipt = _good_receipt(example_root)
    candidate_receipt = deepcopy(reference_receipt)
    for receipt in (reference_receipt, candidate_receipt):
        _dimension(receipt, Dimension.ENTITIES).update(
            {"coverage": coverage, "status": "indeterminate"}
        )
    _dimension(candidate_receipt, Dimension.ENTITIES).update(
        {
            "exported_count": 1,
            "missing_count": 1,
            "restored_count": 1,
            "status": "fail",
        }
    )
    _finalize_receipt(reference_receipt, "d")
    _finalize_receipt(candidate_receipt, "e")
    reference = tmp_path / f"{coverage}-reference.json"
    candidate = tmp_path / f"{coverage}-candidate.json"
    write_receipt(reference, reference_receipt)
    write_receipt(candidate, candidate_receipt)

    assert (
        main(
            [
                "compare",
                str(reference),
                str(candidate),
                "--fail-on-loss-signal-increase",
            ]
        )
        == 3
    )
    output = _stdout(capsys)
    dimensions = cast(list[dict[str, object]], output["dimensions"])
    assert dimensions[0]["coverage"] == coverage
    assert dimensions[0]["assessment"] == "uncertain"
    assert dimensions[0]["observed_loss_signal_increases"] == ["missing_count_increased"]


def test_compare_module_process_returns_actual_policy_exit_three(
    tmp_path: Path,
    example_root: Path,
) -> None:
    reference, candidate = _comparison_receipts(tmp_path, example_root)
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and local test fixtures
        [
            sys.executable,
            "-m",
            "exitdrill.cli",
            "compare",
            str(reference),
            str(candidate),
            "--fail-on-loss-signal-increase",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 3
    assert completed.stderr == ""
    output = json.loads(completed.stdout)
    assert output["comparability"] == "comparable"


def test_compare_cli_usage_error_is_exit_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["compare"])
    assert raised.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage:" in captured.err


def test_compare_cli_rejects_malformed_receipt_without_stdout(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = run_drill(
        load_baseline(example_root / "baseline.json"),
        load_export(example_root / "export.json"),
        example_root / "export-files",
    )
    reference = tmp_path / "reference.json"
    malformed = tmp_path / "malformed.json"
    write_receipt(reference, build_receipt(result))
    malformed.write_text('{"schema_version":', encoding="utf-8")

    assert (
        main(
            [
                "compare",
                str(reference),
                str(malformed),
                "--fail-on-loss-signal-increase",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not valid JSON" in captured.err


def test_compare_cli_read_error_does_not_disclose_operand_path(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reference = tmp_path / "reference.json"
    write_receipt(reference, _good_receipt(example_root))
    marker = "invented-private-missing-receipt"
    missing = tmp_path / f"{marker}.json"

    assert main(["compare", str(reference), str(missing)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "comparison input could not be read" in captured.err
    assert marker not in captured.err
    assert str(tmp_path) not in captured.err


def test_compare_cli_accepts_option_like_filenames_after_separator(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = tmp_path / "-reference.json"
    candidate = tmp_path / "--candidate.json"
    write_receipt(reference, _good_receipt(example_root))
    write_receipt(candidate, _good_receipt(example_root))
    monkeypatch.chdir(tmp_path)

    assert main(["compare", "--", reference.name, candidate.name]) == 0
    output = _stdout(capsys)
    assert output["comparability"] == "comparable"
    assert reference.name not in canonical_json_bytes(cast(dict[str, JsonValue], output)).decode()
    assert candidate.name not in canonical_json_bytes(cast(dict[str, JsonValue], output)).decode()


def test_compare_cli_duplicate_key_error_does_not_echo_key_or_path(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "invented-private-candidate.json"
    write_receipt(reference, _good_receipt(example_root))
    marker = "invented-sensitive-duplicate"
    candidate.write_text(f'{{"{marker}": 1, "{marker}": 2}}', encoding="utf-8")

    assert main(["compare", str(reference), str(candidate)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "duplicate object key" in captured.err
    assert marker not in captured.err
    assert str(candidate) not in captured.err


def test_compare_cli_returns_two_for_incomparable_scope(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = run_drill(
        load_baseline(example_root / "baseline.json"),
        load_export(example_root / "export.json"),
        example_root / "export-files",
    )
    reference_receipt = build_receipt(result, claimed_generated_at="2026-07-22T20:00:00Z")
    candidate_receipt = build_receipt(result, claimed_generated_at="2026-07-22T21:00:00Z")
    payload = candidate_receipt["payload"]
    assert isinstance(payload, dict)
    payload["baseline_sha256"] = "0" * 64
    candidate_receipt["payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    reference = tmp_path / "reference.json"
    candidate = tmp_path / "candidate.json"
    write_receipt(reference, reference_receipt)
    write_receipt(candidate, candidate_receipt)

    assert (
        main(
            [
                "compare",
                str(reference),
                str(candidate),
                "--fail-on-loss-signal-increase",
            ]
        )
        == 2
    )
    output = _stdout(capsys)
    assert output["comparability"] == "incomparable"
    assert output["dimensions"] == []


def test_drill_and_replay_cli(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = tmp_path / "receipt.json"
    common = [
        str(example_root / "baseline.json"),
        str(example_root / "export.json"),
    ]
    assert (
        main(
            [
                "drill",
                *common,
                "--attachment-root",
                str(example_root / "export-files"),
                "--out",
                str(receipt),
                "--claimed-generated-at",
                "2026-07-22T20:00:00Z",
            ]
        )
        == 0
    )
    assert _stdout(capsys)["overall_status"] == "structurally_restorable"
    assert (
        main(
            [
                "verify",
                str(receipt),
                "--baseline",
                common[0],
                "--export",
                common[1],
                "--attachment-root",
                str(example_root / "export-files"),
            ]
        )
        == 0
    )
    assert _stdout(capsys)["replayed"] is True


def test_same_type_value_loss_fails_drill_and_clean_receipt_replay(
    copied_example: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = copied_example / "baseline.json"
    export = copied_example / "export.json"
    attachment_root = copied_example / "export-files"
    clean_receipt = tmp_path / "clean-receipt.json"
    common = [str(baseline), str(export)]
    assert (
        main(
            [
                "drill",
                *common,
                "--attachment-root",
                str(attachment_root),
                "--out",
                str(clean_receipt),
            ]
        )
        == 0
    )
    _stdout(capsys)

    raw = json.loads(export.read_text(encoding="utf-8"))
    raw["entities"][0]["fields"]["display_name"] = "Different synthetic string"
    export.write_text(json.dumps(raw), encoding="utf-8")

    assert (
        main(
            [
                "verify",
                str(clean_receipt),
                "--baseline",
                common[0],
                "--export",
                common[1],
                "--attachment-root",
                str(attachment_root),
            ]
        )
        == 2
    )
    assert "does not match a fresh drill replay" in capsys.readouterr().err

    failed_receipt = tmp_path / "failed-receipt.json"
    assert (
        main(
            [
                "drill",
                *common,
                "--attachment-root",
                str(attachment_root),
                "--out",
                str(failed_receipt),
            ]
        )
        == 2
    )
    output = _stdout(capsys)
    assert output["overall_status"] == "not_structurally_restorable"
    encoded = failed_receipt.read_text(encoding="utf-8")
    assert "Synthetic Person" not in encoded
    assert "Different synthetic string" not in encoded


def test_verify_without_replay(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = tmp_path / "receipt.json"
    main(
        [
            "drill",
            str(example_root / "baseline.json"),
            str(example_root / "export.json"),
            "--attachment-root",
            str(example_root / "export-files"),
            "--out",
            str(receipt),
        ]
    )
    _stdout(capsys)
    assert main(["verify", str(receipt)]) == 0
    assert _stdout(capsys)["status"] == "checksum_self_consistent"


def test_cli_errors_on_partial_replay_arguments(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = tmp_path / "receipt.json"
    main(
        [
            "drill",
            str(example_root / "baseline.json"),
            str(example_root / "export.json"),
            "--attachment-root",
            str(example_root / "export-files"),
            "--out",
            str(receipt),
        ]
    )
    _stdout(capsys)
    assert (
        main(
            [
                "verify",
                str(receipt),
                "--baseline",
                str(example_root / "baseline.json"),
            ]
        )
        == 2
    )
    assert "must be supplied together" in capsys.readouterr().err


def test_failed_drill_returns_nonzero(
    copied_example: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (copied_example / "export-files" / "attachments" / "intake.txt").unlink()
    assert (
        main(
            [
                "drill",
                str(copied_example / "baseline.json"),
                str(copied_example / "export.json"),
                "--attachment-root",
                str(copied_example / "export-files"),
                "--out",
                str(tmp_path / "receipt.json"),
            ]
        )
        == 2
    )
    assert _stdout(capsys)["overall_status"] == "not_structurally_restorable"
