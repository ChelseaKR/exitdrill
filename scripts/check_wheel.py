"""Fail if the local wheel omits typing metadata or leaks repository fixtures."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from shutil import which
from zipfile import ZipFile

COMPARISON_SCHEMA = "exitdrill/schemas/receipt-comparison-v0.1.schema.json"


def main() -> None:
    wheels = list(Path("dist").glob("exitdrill-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one ExitDrill wheel, found {len(wheels)}")
    with ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        if COMPARISON_SCHEMA not in names:
            raise SystemExit(f"wheel does not contain {COMPARISON_SCHEMA}")
        packaged_schema = archive.read(COMPARISON_SCHEMA)
        comparison_schema = json.loads(packaged_schema)
    source_schema = Path("schemas/receipt-comparison-v0.1.schema.json").read_bytes()
    if packaged_schema != source_schema:
        raise SystemExit("wheel comparison schema differs from the public source schema")
    if "exitdrill/py.typed" not in names:
        raise SystemExit("wheel does not contain exitdrill/py.typed")
    if comparison_schema.get("$id") != (
        "https://github.com/ChelseaKR/exitdrill/blob/main/"
        "schemas/receipt-comparison-v0.1.schema.json"
    ):
        raise SystemExit("wheel contains an unexpected comparison schema")
    forbidden = tuple(name for name in names if name.startswith(("tests/", "examples/")))
    if forbidden:
        raise SystemExit(f"wheel contains repository-only fixtures: {forbidden}")
    uv = which("uv")
    if uv is None:
        raise SystemExit("uv is required for the isolated wheel smoke test")
    completed = subprocess.run(  # noqa: S603 - fixed executable and locally built wheel
        [
            uv,
            "run",
            "--isolated",
            "--no-project",
            "--with",
            str(wheels[0]),
            "exitdrill",
            "compare",
            "--help",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    if "--fail-on-loss-signal-increase" not in completed.stdout:
        raise SystemExit("wheel CLI does not expose the comparison policy flag")


if __name__ == "__main__":
    main()
