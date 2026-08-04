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


def _committed_schemas() -> list[Path]:
    return sorted((PROJECT / "schemas").glob("*.schema.json"))


def _committed_lab_scripts() -> list[Path]:
    """Return every committed browser-lab script, from the same source the gate uses."""
    git = which("git")
    assert git is not None, "git is required to enumerate the committed browser-lab scripts"
    completed = subprocess.run(  # noqa: S603 - resolved interpreter and fixed arguments
        [git, "ls-files", "*.mjs"],
        cwd=PROJECT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(PROJECT / line for line in completed.stdout.splitlines() if line)


def _script_module(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"exitdrill_gate_{name}", PROJECT / "scripts" / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_wheel_module() -> ModuleType:
    return _script_module("check_wheel")


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


def test_committed_schema_ids_match_their_pinned_form() -> None:
    module = _check_wheel_module()
    for schema in _committed_schemas():
        document = json.loads(schema.read_bytes())
        assert document["$id"] == module.expected_schema_id(schema.name), schema.name


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


def _wheel_for_schema_id(module: ModuleType, name: str, schema_id: str, tmp_path: Path) -> None:
    """Run the wheel schema gate over a lone schema carrying `schema_id`."""
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    source = project / "schemas" / name
    source.write_bytes(json.dumps({"$id": schema_id}).encode("utf-8"))
    entries = {PACKAGED_PREFIX + name: source.read_bytes()}
    with _wheel_with(entries, tmp_path / "wheel.zip") as archive:
        module.check_packaged_schemas(archive, set(entries), project)


def test_wheel_schema_gate_pins_each_schema_to_one_published_form(tmp_path: Path) -> None:
    """A schema may not adopt the other published `$id` form: each name has one pin."""
    module = _check_wheel_module()
    legacy = "receipt-comparison-v0.1.schema.json"
    canonical = "civicrm-evidence-index-v0.7.schema.json"
    assert legacy in module.LEGACY_SCHEMA_ID_NAMES
    assert canonical not in module.LEGACY_SCHEMA_ID_NAMES

    _wheel_for_schema_id(module, legacy, module.expected_schema_id(legacy), tmp_path / "ok-legacy")
    _wheel_for_schema_id(
        module, canonical, module.expected_schema_id(canonical), tmp_path / "ok-canonical"
    )

    for name, wrong_form in (
        (legacy, module.CANONICAL_SCHEMA_ID_FORMAT),
        (canonical, module.LEGACY_SCHEMA_ID_FORMAT),
    ):
        wrong = wrong_form.format(name=name)
        assert wrong != module.expected_schema_id(name)
        with pytest.raises(SystemExit) as error:
            _wheel_for_schema_id(module, name, wrong, tmp_path / f"swapped-{name}")
        assert "unexpected schema id" in str(error.value)


def test_wheel_schema_gate_rejects_an_id_outside_every_published_form(tmp_path: Path) -> None:
    module = _check_wheel_module()
    name = "civicrm-evidence-index-v0.7.schema.json"
    for outside in (
        "https://attacker.example/schemas/" + name,
        "https://exitdrill.example/schemas/some-other-name.schema.json",
        "urn:exitdrill:" + name,
        "",
    ):
        with pytest.raises(SystemExit) as error:
            _wheel_for_schema_id(module, name, outside, tmp_path / f"outside-{hash(outside)}")
        assert "unexpected schema id" in str(error.value)


def test_wheel_schema_gate_rejects_a_non_object_schema_document(tmp_path: Path) -> None:
    module = _check_wheel_module()
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    source = project / "schemas" / "civicrm-evidence-index-v0.7.schema.json"
    source.write_bytes(b"[]")
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
    assert "git ls-files '*.mjs'" in recipe
    assert not re.search(r"[\w/-]\.mjs", recipe)
    assert "make lint-lab" in workflow
    assert not re.search(r"\.mjs", workflow)


def test_lab_syntax_gate_covers_every_committed_lab_script_anywhere_in_the_tree() -> None:
    """The gate enumerates committed `.mjs` files by tracking status, not by directory.

    The recipe and this suite share one source of truth, `git ls-files '*.mjs'`,
    which matches at any depth rather than under a fixed directory. Every lab
    script currently lives in a subdirectory, so an empty enumeration would mean
    the pattern had been narrowed or anchored and scripts could escape the gate.
    """
    recipe = _makefile_recipe("lint-lab")
    scripts = _committed_lab_scripts()

    assert "git ls-files '*.mjs'" in recipe
    assert scripts
    for script in scripts:
        assert script.is_file(), script
        assert script.parent != PROJECT, f"{script.name} would need a root-anchored pattern"


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


def _summary_module_rooted_at(
    root: Path, document: str, monkeypatch: pytest.MonkeyPatch
) -> ModuleType:
    module = _script_module("summarize_synthetic_demo")
    (root / "out").mkdir()
    (root / "out" / "receipt.json").write_text(document, encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", root)
    return module


def test_synthetic_demo_summary_reads_a_json_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _summary_module_rooted_at(tmp_path, '{"payload": {"ok": true}}', monkeypatch)

    assert module._read("out/receipt.json") == {"payload": {"ok": True}}


@pytest.mark.parametrize("document", ["[]", '"a string"', "12", "null", "true"])
def test_synthetic_demo_summary_rejects_a_non_object_document(
    document: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A demo receipt that parses as JSON but is not an object must stop the summary."""
    module = _summary_module_rooted_at(tmp_path, document, monkeypatch)

    with pytest.raises(SystemExit) as error:
        module._read("out/receipt.json")

    assert "is not a JSON object" in str(error.value)


def test_strict_type_checking_covers_the_committed_gate_scripts() -> None:
    metadata = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["tool"]["mypy"]["strict"] is True
    assert set(metadata["tool"]["mypy"]["files"]) == {"src", "tests", "scripts"}
