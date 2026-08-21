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
from typing import cast
from zipfile import ZipFile

import pytest

PROJECT = Path(__file__).parents[1]
PACKAGED_PREFIX = "exitdrill/schemas/"


def _committed_schemas() -> list[Path]:
    """Every schema.json committed under schemas/, referenced by code or not."""
    return sorted((PROJECT / "schemas").glob("*.schema.json"))


def _expected_wheel_schemas() -> list[Path]:
    """The schemas the wheel is required to carry: those `src/exitdrill/` references."""
    return sorted(_check_wheel_module().committed_schemas(PROJECT))


def _force_include_table() -> dict[str, str]:
    metadata = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    return cast(
        dict[str, str],
        metadata["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"],
    )


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
    return {
        PACKAGED_PREFIX + schema.name: schema.read_bytes() for schema in _expected_wheel_schemas()
    }


def test_committed_schemas_exist() -> None:
    assert len(_committed_schemas()) >= 1
    assert len(_committed_lab_scripts()) >= 1


def test_wheel_force_include_packages_exactly_the_referenced_schemas() -> None:
    """pyproject.toml's force-include must match what `src/exitdrill/` references --
    no more (issue #33: 12 superseded schemas were force-included and never
    opened by any code) and no less (a schema real code needs must ship).
    """
    module = _check_wheel_module()
    referenced = module.schemas_referenced_by_source(PROJECT)
    assert referenced, "src/exitdrill/ must reference at least one schema"

    assert _force_include_table() == {
        f"schemas/{name}": PACKAGED_PREFIX + name for name in referenced
    }


def test_wheel_excludes_a_superseded_schema_nothing_references() -> None:
    """At least one committed schema stays unshipped because nothing loads it --
    proves the previous test can actually fail, not just pass vacuously, and
    pins the concrete regression from issue #33.
    """
    module = _check_wheel_module()
    referenced = module.schemas_referenced_by_source(PROJECT)
    committed_names = {schema.name for schema in _committed_schemas()}
    unreferenced = committed_names - referenced

    assert "civicrm-evidence-index-v0.1.schema.json" in unreferenced
    assert "civicrm-evidence-verification-v0.1.schema.json" in unreferenced
    force_include = _force_include_table()
    for name in unreferenced:
        assert f"schemas/{name}" not in force_include


def test_committed_schema_ids_match_their_pinned_form() -> None:
    module = _check_wheel_module()
    for schema in _committed_schemas():
        document = json.loads(schema.read_bytes())
        assert document["$id"] == module.expected_schema_id(schema.name), schema.name


def test_wheel_schema_gate_accepts_the_expected_set(tmp_path: Path) -> None:
    module = _check_wheel_module()
    entries = _packaged_entries()
    expected_schemas = _expected_wheel_schemas()
    with _wheel_with(entries, tmp_path / "wheel.zip") as archive:
        checked = module.check_packaged_schemas(archive, set(entries), expected_schemas)

    assert checked == len(expected_schemas)


def test_wheel_schema_gate_rejects_a_dropped_schema(tmp_path: Path) -> None:
    module = _check_wheel_module()
    entries = _packaged_entries()
    expected_schemas = _expected_wheel_schemas()
    dropped = PACKAGED_PREFIX + expected_schemas[0].name
    del entries[dropped]
    with (
        _wheel_with(entries, tmp_path / "wheel.zip") as archive,
        pytest.raises(SystemExit) as error,
    ):
        module.check_packaged_schemas(archive, set(entries), expected_schemas)

    assert "does not contain committed schemas" in str(error.value)


def test_wheel_schema_gate_rejects_an_unexpected_packaged_schema(tmp_path: Path) -> None:
    module = _check_wheel_module()
    entries = _packaged_entries()
    entries[PACKAGED_PREFIX + "invented-extra-v9.9.schema.json"] = b"{}"
    with (
        _wheel_with(entries, tmp_path / "wheel.zip") as archive,
        pytest.raises(SystemExit) as error,
    ):
        module.check_packaged_schemas(archive, set(entries), _expected_wheel_schemas())

    assert "unexpected packaged schemas" in str(error.value)


def test_wheel_schema_gate_rejects_a_superseded_schema_that_is_not_referenced(
    tmp_path: Path,
) -> None:
    """Concrete regression test for issue #33: civicrm-evidence-index-v0.1.schema.json
    is a real, committed file, but no code under `src/exitdrill/` references
    it (only v0.7 is loaded), so it must not ship even though it exists.
    """
    module = _check_wheel_module()
    superseded = PROJECT / "schemas" / "civicrm-evidence-index-v0.1.schema.json"
    assert superseded.is_file()
    assert superseded.name not in module.schemas_referenced_by_source(PROJECT)

    entries = _packaged_entries()
    entries[PACKAGED_PREFIX + superseded.name] = superseded.read_bytes()
    with (
        _wheel_with(entries, tmp_path / "wheel.zip") as archive,
        pytest.raises(SystemExit) as error,
    ):
        module.check_packaged_schemas(archive, set(entries), _expected_wheel_schemas())

    assert "unexpected packaged schemas" in str(error.value)


def test_wheel_schema_gate_rejects_altered_schema_bytes(tmp_path: Path) -> None:
    module = _check_wheel_module()
    entries = _packaged_entries()
    expected_schemas = _expected_wheel_schemas()
    altered = PACKAGED_PREFIX + expected_schemas[0].name
    entries[altered] = entries[altered] + b"\n"
    with (
        _wheel_with(entries, tmp_path / "wheel.zip") as archive,
        pytest.raises(SystemExit) as error,
    ):
        module.check_packaged_schemas(archive, set(entries), expected_schemas)

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
        module.check_packaged_schemas(archive, set(entries), (source,))

    assert "unexpected schema id" in str(error.value)


def _wheel_for_schema_id(module: ModuleType, name: str, schema_id: str, tmp_path: Path) -> None:
    """Run the wheel schema gate over a lone schema carrying `schema_id`."""
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    source = project / "schemas" / name
    source.write_bytes(json.dumps({"$id": schema_id}).encode("utf-8"))
    entries = {PACKAGED_PREFIX + name: source.read_bytes()}
    with _wheel_with(entries, tmp_path / "wheel.zip") as archive:
        module.check_packaged_schemas(archive, set(entries), (source,))


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
        module.check_packaged_schemas(archive, set(entries), (source,))

    assert "unexpected schema id" in str(error.value)


def test_committed_schemas_rejects_a_project_with_no_schema_references(tmp_path: Path) -> None:
    """`committed_schemas` -- not `check_packaged_schemas` -- now owns discovery,
    so this exercises it directly: a tree with no schema references at all
    (an empty or absent `src/exitdrill/`) must fail loudly rather than ship
    nothing silently.
    """
    module = _check_wheel_module()
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "src" / "exitdrill").mkdir(parents=True)
    (project / "src" / "exitdrill" / "empty.py").write_text("", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        module.committed_schemas(project)

    assert "no schema references were found" in str(error.value)


def test_committed_schemas_rejects_a_reference_to_a_missing_schema(tmp_path: Path) -> None:
    """A schema `src/exitdrill/` names but `schemas/` does not contain is a
    broken build, not a trim -- `committed_schemas` must fail, not skip it.
    """
    module = _check_wheel_module()
    project = tmp_path / "project"
    (project / "schemas").mkdir(parents=True)
    (project / "src" / "exitdrill").mkdir(parents=True)
    (project / "src" / "exitdrill" / "loader.py").write_text(
        'SCHEMA = "ghost-v0.1.schema.json"\n', encoding="utf-8"
    )

    with pytest.raises(SystemExit) as error:
        module.committed_schemas(project)

    assert "references a schema that does not exist" in str(error.value)


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


def test_committed_browser_captures_bind_to_their_scripts_declared_output() -> None:
    """Regression test for issue #31: a committed browser-*.json must match the
    literal its capture script declares, offline, without a live CiviCRM,
    Playwright, or Docker. See scripts/check_browser_capture_bindings.mjs
    for exactly which fields this can and cannot verify.
    """
    node = which("node")
    if node is None:  # pragma: no cover - exercised by the Node-enabled CI gate
        pytest.skip("node is required to check the browser-capture bindings")
    completed = subprocess.run(  # noqa: S603 - resolved interpreter and repository script
        [node, str(PROJECT / "scripts" / "check_browser_capture_bindings.mjs")],
        cwd=PROJECT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "verified 9 committed browser-*.json files" in completed.stdout


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


def _uv_or_skip() -> str:
    uv = which("uv")
    if uv is None:  # pragma: no cover - exercised by the uv-provisioned CI gate
        pytest.skip("uv is required to exercise the lockfile-drift gate")
    return uv


def _uv(uv: str, *arguments: str, cwd: Path) -> int:
    completed = subprocess.run(  # noqa: S603 - resolved interpreter and fixed arguments
        [uv, *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode


def test_frozen_lockfile_flag_cannot_observe_declared_dependency_drift(tmp_path: Path) -> None:
    """`--frozen` exits 0 on a drifted lockfile; only `--locked` can observe the drift.

    This is the property the repository's own lockfile gate depends on, so it is
    asserted against real `uv` behaviour rather than assumed. The probe project
    declares no dependencies, so both commands resolve offline.
    """
    uv = _uv_or_skip()
    project = tmp_path / "drift-probe"
    project.mkdir()
    manifest = project / "pyproject.toml"
    manifest.write_text(
        '[project]\nname = "drift-probe"\nversion = "0.0.0"\n'
        'requires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )
    assert _uv(uv, "lock", "--offline", cwd=project) == 0

    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "dependencies = []", 'dependencies = ["exitdrill-drift-probe-absent"]'
        ),
        encoding="utf-8",
    )

    assert _uv(uv, "sync", "--frozen", "--offline", "--no-install-project", cwd=project) == 0
    assert _uv(uv, "sync", "--locked", "--offline", "--no-install-project", cwd=project) != 0


def test_every_lockfile_consuming_command_observes_lockfile_drift() -> None:
    """No committed command may read `uv.lock` with a flag that ignores drift.

    `uv sync --frozen` and `uv export --frozen` install and export whatever the
    lockfile already says and exit 0 even when `pyproject.toml` has moved on. A
    dependency added to the project but never relocked would then be absent from
    the installed environment and absent from the audited requirement set, while
    every gate stayed green. `--locked` fails closed instead.
    """
    sources = {
        "Makefile": (PROJECT / "Makefile").read_text(encoding="utf-8"),
        "ci.yml": (PROJECT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        "release.yml": (PROJECT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        ),
    }
    drift_blind = re.compile(r"uv (?:sync|export)[^\n]*--frozen")

    for name, text in sources.items():
        assert not drift_blind.search(text), f"{name} reads uv.lock without observing drift"

    assert "uv sync --locked" in sources["Makefile"]
    assert "uv sync --locked" in sources["ci.yml"]
    assert "uv export --locked" in sources["ci.yml"]
    assert "uv sync --locked" in sources["release.yml"]
