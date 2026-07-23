import json
from pathlib import Path
from typing import cast

import pytest

from exitdrill.cli import main


def _stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    raw = json.loads(capsys.readouterr().out)
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


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


def test_validate_exercise_cli(capsys: pytest.CaptureFixture[str]) -> None:
    plan = Path(__file__).parents[1] / "examples" / "synthetic-exercise" / "plan.json"
    assert main(["validate-exercise", str(plan)]) == 0
    result = _stdout(capsys)
    assert result["status"] == "synthetic_protocol_valid"
    assert result["decision_scope"] == "plan_only_no_target_execution"


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
