"""Fail if the local wheel omits typing metadata or leaks repository fixtures."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from shutil import which
from zipfile import ZipFile

COMPARISON_SCHEMA = "exitdrill/schemas/receipt-comparison-v0.1.schema.json"
TARGET_RESULT_SCHEMA = "exitdrill/schemas/civicrm-target-roundtrip-result-v0.1.schema.json"
UI_RESULT_SCHEMA = "exitdrill/schemas/civicrm-ui-surface-result-v0.1.schema.json"
BROWSER_RESULT_SCHEMA = "exitdrill/schemas/civicrm-browser-workflow-result-v0.1.schema.json"


def _check_schema(
    archive: ZipFile,
    names: set[str],
    packaged_path: str,
    source_path: Path,
    expected_id: str,
) -> None:
    if packaged_path not in names:
        raise SystemExit(f"wheel does not contain {packaged_path}")
    packaged = archive.read(packaged_path)
    if packaged != source_path.read_bytes():
        raise SystemExit(f"wheel schema differs from {source_path}")
    document = json.loads(packaged)
    if document.get("$id") != expected_id:
        raise SystemExit(f"wheel contains an unexpected schema id for {packaged_path}")


def _command_help(uv: str, wheel: Path, command: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed uv arguments and locally built wheel
        [
            uv,
            "run",
            "--isolated",
            "--no-project",
            "--with",
            str(wheel),
            "exitdrill",
            command,
            "--help",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def main() -> None:
    wheels = list(Path("dist").glob("exitdrill-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one ExitDrill wheel, found {len(wheels)}")
    with ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        _check_schema(
            archive,
            names,
            COMPARISON_SCHEMA,
            Path("schemas/receipt-comparison-v0.1.schema.json"),
            (
                "https://github.com/ChelseaKR/exitdrill/blob/main/"
                "schemas/receipt-comparison-v0.1.schema.json"
            ),
        )
        _check_schema(
            archive,
            names,
            UI_RESULT_SCHEMA,
            Path("schemas/civicrm-ui-surface-result-v0.1.schema.json"),
            "https://exitdrill.example/schemas/civicrm-ui-surface-result-v0.1.schema.json",
        )
        _check_schema(
            archive,
            names,
            BROWSER_RESULT_SCHEMA,
            Path("schemas/civicrm-browser-workflow-result-v0.1.schema.json"),
            "https://exitdrill.example/schemas/civicrm-browser-workflow-result-v0.1.schema.json",
        )
        _check_schema(
            archive,
            names,
            TARGET_RESULT_SCHEMA,
            Path("schemas/civicrm-target-roundtrip-result-v0.1.schema.json"),
            (
                "https://github.com/ChelseaKR/exitdrill/blob/main/"
                "schemas/civicrm-target-roundtrip-result-v0.1.schema.json"
            ),
        )
    if "exitdrill/py.typed" not in names:
        raise SystemExit("wheel does not contain exitdrill/py.typed")
    forbidden = tuple(name for name in names if name.startswith(("tests/", "examples/")))
    if forbidden:
        raise SystemExit(f"wheel contains repository-only fixtures: {forbidden}")
    uv = which("uv")
    if uv is None:
        raise SystemExit("uv is required for the isolated wheel smoke test")
    if "--fail-on-loss-signal-increase" not in _command_help(uv, wheels[0], "compare"):
        raise SystemExit("wheel CLI does not expose the comparison policy flag")
    if "--out-dir" not in _command_help(uv, wheels[0], "normalize-directus-canary"):
        raise SystemExit("wheel CLI does not expose the Directus canary normalizer")
    if "--out-dir" not in _command_help(uv, wheels[0], "normalize-civicrm-target-canary"):
        raise SystemExit("wheel CLI does not expose the CiviCRM target canary normalizer")


if __name__ == "__main__":
    main()
