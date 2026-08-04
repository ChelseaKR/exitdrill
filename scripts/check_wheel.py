"""Fail if the local wheel omits typing metadata, drops a schema, or leaks fixtures."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from zipfile import ZipFile

PROJECT = Path(__file__).resolve().parents[1]
SCHEMA_SOURCE_DIR = "schemas"
SCHEMA_SUFFIX = ".schema.json"
PACKAGED_SCHEMA_PREFIX = "exitdrill/schemas/"
CANONICAL_SCHEMA_ID_FORMAT = "https://exitdrill.example/schemas/{name}"
LEGACY_SCHEMA_ID_FORMAT = "https://github.com/ChelseaKR/exitdrill/blob/main/schemas/{name}"
LEGACY_SCHEMA_ID_NAMES = frozenset(
    {
        "receipt-comparison-v0.1.schema.json",
        "civicrm-target-roundtrip-result-v0.1.schema.json",
    }
)


def expected_schema_id(name: str) -> str:
    """Return the single `$id` this schema name is pinned to.

    Every schema is pinned to exactly one accepted `$id`, so a schema cannot
    silently adopt another schema's published form. Two schemas predate the
    canonical form and stay pinned to their legacy one; anything added later
    must use the canonical form without touching this gate.
    """
    form = LEGACY_SCHEMA_ID_FORMAT if name in LEGACY_SCHEMA_ID_NAMES else CANONICAL_SCHEMA_ID_FORMAT
    return form.format(name=name)


def committed_schemas(project: Path) -> tuple[Path, ...]:
    """Return every committed JSON Schema the wheel is required to carry."""
    schemas = tuple(sorted((project / SCHEMA_SOURCE_DIR).glob(f"*{SCHEMA_SUFFIX}")))
    if not schemas:
        raise SystemExit("no committed JSON Schemas were found")
    return schemas


def _check_schema(archive: ZipFile, packaged_path: str, source_path: Path) -> None:
    packaged = archive.read(packaged_path)
    if packaged != source_path.read_bytes():
        raise SystemExit(f"wheel schema differs from {source_path}")
    document = json.loads(packaged)
    expected = expected_schema_id(source_path.name)
    if not isinstance(document, dict) or document.get("$id") != expected:
        raise SystemExit(f"wheel contains an unexpected schema id for {packaged_path}")


def check_packaged_schemas(archive: ZipFile, names: set[str], project: Path) -> int:
    """Require the wheel to carry exactly the committed schema set, byte for byte."""
    expected = {
        PACKAGED_SCHEMA_PREFIX + source.name: source for source in committed_schemas(project)
    }
    packaged = {name for name in names if name.startswith(PACKAGED_SCHEMA_PREFIX)}
    missing = sorted(set(expected) - packaged)
    if missing:
        raise SystemExit(f"wheel does not contain committed schemas: {missing}")
    unexpected = sorted(packaged - set(expected))
    if unexpected:
        raise SystemExit(f"wheel contains unexpected packaged schemas: {unexpected}")
    for packaged_path, source_path in sorted(expected.items()):
        _check_schema(archive, packaged_path, source_path)
    return len(expected)


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


def _check_civicrm_evidence_verifier(uv: str, wheel: Path) -> None:
    manifest = Path(
        "examples/civicrm-6.16.2-target-roundtrip/native/capture-manifest.json"
    ).resolve()
    with TemporaryDirectory(prefix="exitdrill-wheel-civicrm-") as temporary:
        out_dir = Path(temporary) / "out"
        base = [uv, "run", "--isolated", "--no-project", "--with", str(wheel), "exitdrill"]
        subprocess.run(  # noqa: S603 - fixed uv arguments, local wheel, and committed fixture
            [
                *base,
                "normalize-civicrm-target-canary",
                str(manifest),
                "--out-dir",
                str(out_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        completed = subprocess.run(  # noqa: S603 - fixed uv arguments and generated output
            [*base, "verify-civicrm-evidence-index", str(out_dir / "evidence-index.json")],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        if result.get("status") != "evidence_artifact_contracts_verified":
            raise SystemExit("wheel CiviCRM evidence verification was not exact")


def main() -> None:
    wheels = list(Path("dist").glob("exitdrill-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one ExitDrill wheel, found {len(wheels)}")
    with ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        schema_count = check_packaged_schemas(archive, names, PROJECT)
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
    _check_civicrm_evidence_verifier(uv, wheels[0])
    print(f"verified {schema_count} packaged schemas in {wheels[0].name}")


if __name__ == "__main__":
    main()
