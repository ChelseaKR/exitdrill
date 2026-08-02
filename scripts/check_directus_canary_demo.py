#!/usr/bin/env python3
"""Exercise the committed Directus canary through the public CLI."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

PROJECT = Path(__file__).parents[1]
EXAMPLE = PROJECT / "examples" / "directus-11.17.4-civic-case"
BASELINE = EXAMPLE / "baseline.json"
NATIVE = EXAMPLE / "native"

_RAW_SENTINELS = (
    "Synthetic Person Alpha",
    "Synthetic Person Bravo",
    "Synthetic Person Canary",
    "Invented intake note alpha.",
    "Invented intake note bravo.",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _run(*arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository commands
        [sys.executable, "-m", "exitdrill.cli", *arguments],
        cwd=PROJECT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != expected:
        raise RuntimeError(
            f"exitdrill {' '.join(arguments[:1])} returned {completed.returncode}, "
            f"expected {expected}: {completed.stderr.strip()}"
        )
    return completed


def _build_lossy(source: Path, destination: Path, statement: Path) -> None:
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [
            sys.executable,
            str(PROJECT / "scripts" / "build_directus_lossy_canary.py"),
            str(source),
            str(destination),
            "--statement",
            str(statement),
        ],
        cwd=PROJECT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"lossy canary build failed: {completed.stderr.strip()}")


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path.name} must contain an object")
    return cast(dict[str, object], value)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _payload(path: Path) -> dict[str, object]:
    receipt = _json_object(path)
    payload = receipt.get("payload")
    if not isinstance(payload, dict):
        raise AssertionError("receipt payload must be an object")
    return cast(dict[str, object], payload)


def _dimensions(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = payload.get("dimensions")
    if not isinstance(raw, list):
        raise AssertionError("receipt dimensions must be an array")
    result: dict[str, dict[str, object]] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise AssertionError("receipt dimension is malformed")
        result[cast(str, item["name"])] = cast(dict[str, object], item)
    return result


def _assert_clean(payload: dict[str, object]) -> None:
    _require(
        payload["overall_status"] == "structurally_restorable",
        "clean canary was not structurally restorable",
    )
    _require(
        payload["observed_remediation_signals"] == 0,
        "clean canary emitted remediation signals",
    )
    expected_counts = {
        "entities": 7,
        "relationships": 2,
        "attachments": 2,
        "permissions": 2,
        "audit_events": 2,
    }
    for name, expected in expected_counts.items():
        dimension = _dimensions(payload)[name]
        _require(
            dimension
            == {
                "coverage": "complete",
                "expected_count": expected,
                "exported_count": expected,
                "extra_count": 0,
                "invalid_count": 0,
                "missing_count": 0,
                "name": name,
                "restored_count": expected,
                "status": "pass",
            },
            f"clean {name} evidence did not match the exact expected result",
        )


def _assert_lossy(payload: dict[str, object]) -> None:
    _require(
        payload["overall_status"] == "not_structurally_restorable",
        "lossy canary did not fail closed",
    )
    _require(
        payload["observed_remediation_signals"] == 6,
        "lossy canary did not emit the exact expected signal count",
    )
    expected = {
        "entities": (7, 7, 1, 1, 1),
        "relationships": (2, 2, 1, 1, 0),
        "attachments": (2, 2, 0, 0, 1),
        "permissions": (2, 2, 1, 1, 0),
        "audit_events": (2, 2, 1, 1, 0),
    }
    for name, (exported, restored, missing, extra, invalid) in expected.items():
        dimension = _dimensions(payload)[name]
        observed = (
            dimension["expected_count"],
            dimension["exported_count"],
            dimension["restored_count"],
            dimension["missing_count"],
            dimension["extra_count"],
            dimension["invalid_count"],
            dimension["status"],
        )
        _require(
            observed == (exported, exported, restored, missing, extra, invalid, "fail"),
            f"lossy {name} evidence did not match the exact expected result",
        )


def _assert_no_raw_values(paths: tuple[Path, ...], command_output: str) -> None:
    observed = command_output + "".join(path.read_text(encoding="utf-8") for path in paths)
    for sentinel in _RAW_SENTINELS:
        _require(sentinel not in observed, "aggregate output disclosed a raw fixture value")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="exitdrill-directus-canary-") as raw_temp:
        root = Path(raw_temp)
        clean_a = root / "clean-a"
        clean_b = root / "clean-b"
        lossy_native = root / "lossy-native"
        lossy_normalized = root / "lossy-normalized"
        derivative_statement = root / "adversarial-derivative.json"

        command_output = ""
        for output in (clean_a, clean_b):
            completed = _run(
                "normalize-directus-canary",
                str(NATIVE / "capture-manifest.json"),
                "--out-dir",
                str(output),
            )
            command_output += completed.stdout + completed.stderr
        _require(
            _tree_digest(clean_a) == _tree_digest(clean_b),
            "repeated normalization was not byte-deterministic",
        )

        _build_lossy(NATIVE, lossy_native, derivative_statement)
        completed = _run(
            "normalize-directus-canary",
            str(lossy_native / "capture-manifest.json"),
            "--out-dir",
            str(lossy_normalized),
        )
        command_output += completed.stdout + completed.stderr

        clean_export = clean_a / "export.json"
        lossy_export = lossy_normalized / "export.json"
        for export in (clean_export, lossy_export):
            completed = _run("validate", str(BASELINE), str(export))
            command_output += completed.stdout + completed.stderr

        clean_receipt = root / "clean-receipt.json"
        lossy_receipt = root / "lossy-receipt.json"
        completed = _run(
            "drill",
            str(BASELINE),
            str(clean_export),
            "--attachment-root",
            str(clean_a / "export-files"),
            "--out",
            str(clean_receipt),
            "--claimed-generated-at",
            "2026-08-02T02:40:00Z",
        )
        command_output += completed.stdout + completed.stderr
        completed = _run(
            "drill",
            str(BASELINE),
            str(lossy_export),
            "--attachment-root",
            str(lossy_normalized / "export-files"),
            "--out",
            str(lossy_receipt),
            "--claimed-generated-at",
            "2026-08-02T02:41:00Z",
            expected=2,
        )
        command_output += completed.stdout + completed.stderr

        for receipt, normalized in (
            (clean_receipt, clean_a),
            (lossy_receipt, lossy_normalized),
        ):
            completed = _run(
                "verify",
                str(receipt),
                "--baseline",
                str(BASELINE),
                "--export",
                str(normalized / "export.json"),
                "--attachment-root",
                str(normalized / "export-files"),
            )
            command_output += completed.stdout + completed.stderr

        clean_report = root / "clean-report.html"
        lossy_report = root / "lossy-report.html"
        for receipt, report in (
            (clean_receipt, clean_report),
            (lossy_receipt, lossy_report),
        ):
            completed = _run("report", str(receipt), "--out", str(report))
            command_output += completed.stdout + completed.stderr

        completed = _run("compare", str(clean_receipt), str(lossy_receipt))
        command_output += completed.stdout + completed.stderr
        comparison = json.loads(completed.stdout)
        _require(isinstance(comparison, dict), "comparison output was not an object")
        _require(
            comparison["comparability"] == "comparable",
            "clean and lossy receipts were not comparable",
        )
        completed = _run(
            "compare",
            str(clean_receipt),
            str(lossy_receipt),
            "--fail-on-loss-signal-increase",
            expected=3,
        )
        command_output += completed.stdout + completed.stderr

        clean_payload = _payload(clean_receipt)
        lossy_payload = _payload(lossy_receipt)
        _assert_clean(clean_payload)
        _assert_lossy(lossy_payload)
        statement = _json_object(derivative_statement)
        _require(
            statement["row_and_file_counts_preserved"] is True,
            "adversarial derivative did not preserve row and file counts",
        )
        _assert_no_raw_values(
            (clean_receipt, lossy_receipt, clean_report, lossy_report),
            command_output,
        )

        print(
            json.dumps(
                {
                    "clean_overall_status": clean_payload["overall_status"],
                    "lossy_observed_remediation_signals": lossy_payload[
                        "observed_remediation_signals"
                    ],
                    "lossy_overall_status": lossy_payload["overall_status"],
                    "row_and_file_counts_preserved": True,
                    "source_profile": "directus-11.17.4-civic-case/v0.1",
                    "status": "directus_api_capture_canary_verified",
                },
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )


if __name__ == "__main__":
    main()
