"""Regression tests that keep the offline gate covering every committed artifact."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import tomllib
from pathlib import Path
from shutil import which
from types import ModuleType
from zipfile import ZipFile

import pytest

PROJECT = Path(__file__).parents[1]
PACKAGED_PREFIX = "exitdrill/schemas/"
ACCEPTED_SCHEMA_ID_FORMATS = (
    "https://github.com/ChelseaKR/exitdrill/blob/main/schemas/{name}",
    "https://exitdrill.example/schemas/{name}",
)


def _committed_schemas() -> list[Path]:
    return sorted((PROJECT / "schemas").glob("*.schema.json"))


def _committed_lab_scripts() -> list[Path]:
    return sorted((PROJECT / "scripts").glob("*.mjs"))


def _check_wheel_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "exitdrill_check_wheel", PROJECT / "scripts" / "check_wheel.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wheel_with(entries: dict[str, bytes], path: Path) -> ZipFile:
    with ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return ZipFile(path)


def _packaged_entries() -> dict[str, bytes]:
    return {PACKAGED_PREFIX + schema.name: schema.read_bytes() for schema in _committed_schemas()}


def test_committed_schemas_exist() -> None:
    assert len(_committed_schemas()) >= 1
    assert len(_committed_lab_scripts()) >= 1


def test_wheel_force_include_packages_every_committed_schema() -> None:
    metadata = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    force_include = metadata["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

    assert force_include == {
        f"schemas/{schema.name}": PACKAGED_PREFIX + schema.name for schema in _committed_schemas()
    }


def test_committed_schema_ids_match_an_accepted_published_form() -> None:
    for schema in _committed_schemas():
        document = json.loads(schema.read_bytes())
        accepted = [form.format(name=schema.name) for form in ACCEPTED_SCHEMA_ID_FORMATS]
        assert document["$id"] in accepted, schema.name


def test_wheel_schema_gate_accepts_the_committed_set(tmp_path: Path) -> None:
    module = _check_wheel_module()
    entries = _packaged_entries()
    with _wheel_with(entries, tmp_path / "wheel.zip") as archive:
        checked = module.check_packaged_schemas(archive, set(entries), PROJECT)

    assert checked == len(_committed_schemas())


def test_wheel_schema_gate_rejects_a_dropped_schema(tmp_path: Path) -> None:
    module = _check_wheel_module()
    entries = _packaged_entries()
    dropped = PACKAGED_PREFIX + _committed_schemas()[0].name
    del entries[dropped]
    with (
        _wheel_with(entries, tmp_path / "wheel.zip") as archive,
        pytest.raises(SystemExit) as error,
    ):
        module.check_packaged_schemas(archive, set(entries), PROJECT)

    assert "does not contain committed schemas" in str(error.value)


def test_wheel_schema_gate_rejects_an_unexpected_packaged_schema(tmp_path: Path) -> None:
    module = _check_wheel_module()
    entries = _packaged_entries()
    entries[PACKAGED_PREFIX + "invented-extra-v9.9.schema.json"] = b"{}"
    with (
        _wheel_with(entries, tmp_path / "wheel.zip") as archive,
        pytest.raises(SystemExit) as error,
    ):
        module.check_packaged_schemas(archive, set(entries), PROJECT)

    assert "unexpected packaged schemas" in str(error.value)


def test_wheel_schema_gate_rejects_altered_schema_bytes(tmp_path: Path) -> None:
    module = _check_wheel_module()
    entries = _packaged_entries()
    altered = PACKAGED_PREFIX + _committed_schemas()[0].name
    entries[altered] = entries[altered] + b"\n"
    with (
        _wheel_with(entries, tmp_path / "wheel.zip") as archive,
        pytest.raises(SystemExit) as error,
    ):
        module.check_packaged_schemas(archive, set(entries), PROJECT)

    assert "wheel schema differs from" in str(error.value)


def test_wheel_schema_gate_rejects_a_rewritten_schema_id(tmp_path: Path) -> None:
    module = _check_wheel_module()
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    source = project / "schemas" / "invented-result-v0.1.schema.json"
    source.write_bytes(b'{"$id": "https://attacker.example/schemas/invented-result-v0.1.json"}')
    entries = {PACKAGED_PREFIX + source.name: source.read_bytes()}
    with (
        _wheel_with(entries, tmp_path / "wheel.zip") as archive,
        pytest.raises(SystemExit) as error,
    ):
        module.check_packaged_schemas(archive, set(entries), project)

    assert "unexpected schema id" in str(error.value)


def test_wheel_schema_gate_rejects_an_empty_schema_directory(tmp_path: Path) -> None:
    module = _check_wheel_module()
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    with (
        _wheel_with({}, tmp_path / "wheel.zip") as archive,
        pytest.raises(SystemExit) as error,
    ):
        module.check_packaged_schemas(archive, set(), project)

    assert "no committed JSON Schemas" in str(error.value)


def _makefile_recipe(target: str) -> str:
    makefile = (PROJECT / "Makefile").read_text(encoding="utf-8")
    match = re.search(rf"^{target}:.*\n((?:\t.*\n)+)", makefile, re.MULTILINE)
    assert match is not None, f"Makefile has no {target} target"
    return match.group(1)


def test_lab_syntax_gate_enumerates_scripts_instead_of_naming_them() -> None:
    recipe = _makefile_recipe("lint-lab")
    workflow = (PROJECT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "node --check" in recipe
    assert "scripts/*.mjs" in recipe
    assert not re.search(r"scripts/\S+\.mjs", recipe.replace("scripts/*.mjs", ""))
    assert "make lint-lab" in workflow
    assert not re.search(r"scripts/\S+\.mjs", workflow)


def test_every_committed_lab_script_parses() -> None:
    node = which("node")
    if node is None:  # pragma: no cover - exercised by the Node-enabled CI gate
        pytest.skip("node is required to syntax-check the browser-lab scripts")
    for script in _committed_lab_scripts():
        completed = subprocess.run(  # noqa: S603 - resolved interpreter and repository script
            [node, "--check", str(script)],
            cwd=PROJECT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, f"{script.name}: {completed.stderr}"


def test_strict_type_checking_covers_the_committed_gate_scripts() -> None:
    metadata = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["tool"]["mypy"]["strict"] is True
    assert set(metadata["tool"]["mypy"]["files"]) == {"src", "tests", "scripts"}
