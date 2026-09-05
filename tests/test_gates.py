"""Regression tests that keep the offline gate covering every committed artifact."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from shutil import copy2, which
from types import ModuleType
from typing import cast
from zipfile import ZipFile

import pytest

PROJECT = Path(__file__).parents[1]
PACKAGED_PREFIX = "exitdrill/schemas/"

# Several gates below run a real external tool -- `node` for the browser-lab
# syntax check and the binding gate, `uv` for the lockfile-drift probe -- and
# have nothing to run without it. Skipping is the right answer for a local
# checkout that has neither installed. It is the wrong answer for CI, where a
# silent skip is the same "reported success having checked nothing" shape that
# `lint-lab`'s `test "$checked" -gt 0`, `check_wheel.py`'s `if not referenced`,
# and the binding gate's `checked === 0` floor all exist to refuse (issue #89).
#
# So the environment is asserted rather than inferred: set
# EXITDRILL_REQUIRE_GATE_TOOLS=1 and a missing tool fails instead of skipping.
# The flag is deliberate and project-owned rather than keyed off `CI`, which is
# a variable GitHub happens to set and any other runner may not.
REQUIRE_GATE_TOOLS = "EXITDRILL_REQUIRE_GATE_TOOLS"
_REQUIRE_GATE_TOOLS_VALUES = {None, "", "0", "1"}


def _gate_tools_are_required() -> bool:
    return os.environ.get(REQUIRE_GATE_TOOLS) == "1"


def _required_tool(name: str, purpose: str) -> str:
    """Resolve an external tool a gate needs, or decide what its absence means."""
    found = which(name)
    if found is not None:
        return found
    missing = f"{name} is required to {purpose}"
    if _gate_tools_are_required():
        pytest.fail(f"{missing}, and {REQUIRE_GATE_TOOLS}=1 promised this environment provides it")
    pytest.skip(missing)


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
    node = _required_tool("node", "syntax-check the browser-lab scripts")
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
    node = _required_tool("node", "check the browser-capture bindings")
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
    uv = _required_tool("uv", "exercise the lockfile-drift gate")
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


# ---------------------------------------------------------------------------
# What the offline binding gate cannot verify, and whether the README says so.
# ---------------------------------------------------------------------------

README_PATH = PROJECT / "README.md"
_BINDING_GATE = PROJECT / "scripts" / "check_browser_capture_bindings.mjs"

# Every field the binding gate excludes from comparison, mapped to the phrase
# the README must use to disclose it. Pinned rather than derived: the point is
# that adding an exclusion is a review point, not something a later edit can
# do silently. A new exclusion has no phrase here and fails the first test
# below by name; a phrase that stops appearing in the README fails the second.
_LIVE_ONLY_DISCLOSURES = {
    ("browser-accessibility.json", "engine_version"): "its version",
    ("browser-accessibility.json", "incomplete_rule_count"): "rule counts",
    ("browser-accessibility.json", "inapplicable_rule_count"): "rule counts",
    ("browser-accessibility.json", "passes_rule_count"): "rule counts",
    ("browser-accessibility.json", "violations"): "its violation list",
    ("browser-keyboard.json", "tab_steps_to_roles_summary"): "the measured keyboard tab-count",
}


def _flat(text: str) -> str:
    """Collapse whitespace so a hard-wrapped claim can still be matched."""
    return " ".join(text.split())


def _dynamic_field_paths() -> dict[str, list[str]]:
    """Read the binding gate's own exclusion table out of its source.

    Read rather than restated, so this cannot pass against a copy of the table
    that has drifted from the one the gate actually applies.
    """
    source = _BINDING_GATE.read_text(encoding="utf-8")
    match = re.search(
        r"^const DYNAMIC_FIELD_PATHS = (\{.*?^\});$", source, re.DOTALL | re.MULTILINE
    )
    assert match is not None, "the binding gate no longer declares DYNAMIC_FIELD_PATHS"
    literal = re.sub(r",(\s*[}\]])", r"\1", match.group(1))
    return cast("dict[str, list[str]]", json.loads(literal))


def test_every_excluded_field_has_a_disclosure_phrase() -> None:
    """The gate's exclusion table and the disclosure table must name the same fields.

    `blankDynamicFields` replaces each of these with a sentinel on both sides of
    the comparison, so an excluded field is not verified against its capture
    script at all. Growing that table is the one edit that weakens this gate
    without changing its success line, which still reports nine files checked.
    """
    excluded = {
        (output, field) for output, fields in _dynamic_field_paths().items() for field in fields
    }

    assert excluded == set(_LIVE_ONLY_DISCLOSURES), (
        "the binding gate's live-only exclusions changed; re-point the disclosure "
        "table and the README sentence rather than leaving a field silently unverified"
    )


def test_the_readme_discloses_every_field_the_binding_gate_cannot_verify() -> None:
    """Issue: the README named three of the four excluded field groups.

    `violations` carries the two serious accessibility findings that
    `docs/ARCHITECTURE.md` publishes, and the offline check never compares it
    against the capture script's declared output. The README's parenthetical
    listed axe-core's rule counts, its version, and the keyboard tab-count, and
    stopped there, while pointing the reader at the script "for exactly which
    fields that is".
    """
    readme = _flat(README_PATH.read_text(encoding="utf-8"))
    excluded = {
        (output, field) for output, fields in _dynamic_field_paths().items() for field in fields
    }

    undisclosed = sorted(
        f"{output}:{field}"
        for output, field in excluded
        if _LIVE_ONLY_DISCLOSURES.get((output, field), "\0") not in readme
    )

    assert not undisclosed, f"the README does not disclose: {undisclosed}"


def test_the_readme_points_at_the_gate_that_holds_the_exclusion_table() -> None:
    """The disclosure is only checkable if the pointer still resolves."""
    readme = _flat(README_PATH.read_text(encoding="utf-8"))

    assert "scripts/check_browser_capture_bindings.mjs" in readme
    assert _BINDING_GATE.is_file()


def test_the_binding_gate_fails_when_it_has_nothing_to_check() -> None:
    """A gate that reports success having compared zero files is not a gate.

    `lint-lab` floors its own count with `test "$checked" -gt 0` and
    `check_wheel.py` floors its with `if not referenced`. This one did not, so
    an emptied binding table printed "verified 0 committed browser-*.json
    files" and exited 0 through `make demo-civicrm-target-canary`.
    """
    node = _required_tool("node", "exercise the binding gate")
    source = _BINDING_GATE.read_text(encoding="utf-8")
    emptied, substitutions = re.subn(
        r"^const BINDINGS = \[.*?^\];$",
        "const BINDINGS = [];",
        source,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert substitutions == 1, "could not locate the binding table to empty"
    assert emptied != source, "emptying the binding table changed nothing"

    with tempfile.TemporaryDirectory(prefix="exitdrill-binding-floor-") as raw:
        probe = Path(raw) / "check_browser_capture_bindings.mjs"
        probe.write_text(emptied, encoding="utf-8")
        completed = subprocess.run(  # noqa: S603 - resolved interpreter and generated script
            [node, str(probe)],
            cwd=PROJECT,
            check=False,
            capture_output=True,
            text=True,
        )

    assert completed.returncode != 0, completed.stdout
    assert "verified 0" not in completed.stdout


# ---------------------------------------------------------------------------
# The fabricated `pageErrors` stub, and the two facts that make it safe.
# ---------------------------------------------------------------------------

_CASE_SEARCH_CAPTURE = PROJECT / "scripts" / "civicrm_browser_case_search_workflow.mjs"
_PAGE_ERRORS_STUB_OWNER = _CASE_SEARCH_CAPTURE.name
_PAGE_ERRORS_GUARD = re.compile(r"pageErrors\.length\s*!==\s*2")
_PAGE_ERRORS_REFERENCE = re.compile(r"\bpageErrors\b")

# Every capture script the binding gate reads. Pinned so that a script dropped
# from BINDINGS cannot be mistaken below for one whose literal was checked and
# found clean.
_BOUND_CAPTURE_SCRIPTS = {
    "civicrm_browser_access_allow_control.mjs",
    "civicrm_browser_access_denial.mjs",
    "civicrm_browser_case_search_workflow.mjs",
    "civicrm_browser_workflow.mjs",
}


def _declared_literals() -> dict[str, str]:
    """The exact literal source the binding gate extracts from each capture script.

    Read out of the gate itself rather than re-derived here: the gate takes the
    first `process.stdout.write(` and the first `JSON.stringify(` after it, and
    a second copy of those rules in Python could drift from the ones actually
    applied. Grepping whole files is not an option either -- all four scripts
    collect `pageErrors` for their own assertions, so a file-wide search reports
    every one of them and proves nothing about what they declare as output.
    """
    node = _required_tool("node", "read the binding gate's declared literals")
    completed = subprocess.run(  # noqa: S603 - resolved interpreter and repository script
        [node, str(_BINDING_GATE), "--print-declared-literals"],
        cwd=PROJECT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return cast("dict[str, str]", json.loads(completed.stdout))


def test_the_case_search_capture_still_proves_the_page_errors_stub() -> None:
    """`evaluateLiteral` fabricates `pageErrors = { length: 2 }` for every literal.

    That is not a SENTINEL. A SENTINEL reaching a field the gate does compare
    fails loudly; a plausible `2` can quietly satisfy the comparison instead. It
    is safe only because this script cannot reach its declared literal unless
    `pageErrors.length === 2`, which is what turns the fabricated value into a
    proven one. Nothing pinned that guard until this test (issue #87).
    """
    source = _CASE_SEARCH_CAPTURE.read_text(encoding="utf-8")

    assert _PAGE_ERRORS_GUARD.search(source), (
        f"{_PAGE_ERRORS_STUB_OWNER} no longer requires pageErrors.length === 2 before reaching "
        "its declared literal, but scripts/check_browser_capture_bindings.mjs still stubs "
        "pageErrors as a fabricated { length: 2 } when it evaluates that literal; without the "
        "guard the gate compares a committed capture against a number nothing establishes"
    )


def test_only_the_script_that_proves_it_reads_page_errors_in_its_declared_literal() -> None:
    """The other half of the same stub's justification (issue #87).

    `browser-contact-summary-workflow.json` and `browser-workflow.json` both
    record an occurrence_count of 2, so a literal in `civicrm_browser_workflow.mjs`
    that started emitting `pageErrors.length` would be compared against the
    fabricated 2, match, and leave the success line reading "verified 9".
    """
    literals = _declared_literals()

    assert set(literals) == _BOUND_CAPTURE_SCRIPTS
    reading_page_errors = sorted(
        name for name, literal in literals.items() if _PAGE_ERRORS_REFERENCE.search(literal)
    )

    assert reading_page_errors == [_PAGE_ERRORS_STUB_OWNER], (
        "only the script that proves pageErrors.length === 2 may read pageErrors inside the "
        "literal the binding gate evaluates with a fabricated { length: 2 } stub"
    )


# ---------------------------------------------------------------------------
# Proof that each binding-gate floor can fail, run against a copied tree.
# ---------------------------------------------------------------------------

_NATIVE_DIR = PROJECT / "examples" / "civicrm-6.16.2-target-roundtrip" / "native"


def _binding_gate_probe_tree(root: Path) -> Path:
    """Copy the gate, its four capture scripts, and the nine captures into `root`.

    The gate resolves its own ROOT from `import.meta.url`, so a probe placed at
    `root/scripts/` reads these copies rather than the committed originals.
    Every break below therefore mutates a copy: the nine `browser-*.json` files
    are pinned evidence from a lab run that cannot be reproduced offline, and a
    capture script edited in place would invalidate its committed capture.
    """
    (root / "scripts").mkdir(parents=True)
    native = root / "examples" / "civicrm-6.16.2-target-roundtrip" / "native"
    native.mkdir(parents=True)
    copy2(_BINDING_GATE, root / "scripts" / _BINDING_GATE.name)
    for script in sorted((PROJECT / "scripts").glob("civicrm_browser_*.mjs")):
        copy2(script, root / "scripts" / script.name)
    for capture in sorted(_NATIVE_DIR.glob("browser-*.json")):
        copy2(capture, native / capture.name)
    return root / "scripts" / _BINDING_GATE.name


def _run_binding_gate_probe(
    tmp_path: Path, edits: dict[str, tuple[str, str]]
) -> subprocess.CompletedProcess[str]:
    """Run the gate over a copied tree in which `edits` replaced one string per file."""
    node = _required_tool("node", "exercise the binding gate")
    probe = _binding_gate_probe_tree(tmp_path / "probe")
    for name, (before, after) in edits.items():
        target = probe.parent / name
        source = target.read_text(encoding="utf-8")
        assert source.count(before) == 1, f"{name}: expected exactly one {before!r} to replace"
        target.write_text(source.replace(before, after), encoding="utf-8")
    return subprocess.run(  # noqa: S603 - resolved interpreter and generated script
        [node, str(probe)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )


def test_the_binding_gate_probe_tree_reproduces_the_committed_verdict(tmp_path: Path) -> None:
    """The control for every break below: unedited, the copied tree still verifies nine.

    Without this, a probe that failed for an unrelated reason -- a file the copy
    forgot, a path the gate could not resolve -- would look like proof that the
    floor under test had fired.
    """
    completed = _run_binding_gate_probe(tmp_path, {})

    assert completed.returncode == 0, completed.stderr
    assert "verified 9 committed browser-*.json files" in completed.stdout


@pytest.mark.parametrize(
    ("label", "replacement", "found"),
    [
        (
            "a plain progress line",
            'process.stdout.write("step: done\\n");\n  process.stdout.write(',
            2,
        ),
        (
            "an earlier JSON-shaped write, the quiet case",
            "process.stdout.write(`${JSON.stringify({ progress: 1 })}\\n`);\n  "
            "process.stdout.write(",
            2,
        ),
        ("the only write removed", "void (", 0),
    ],
)
def test_the_binding_gate_requires_exactly_one_stdout_write(
    label: str, replacement: str, found: int, tmp_path: Path
) -> None:
    """Issue #88: the gate binds to whichever literal follows the FIRST write.

    A capture script that gains an earlier write rebinds this gate to a
    different literal. The loud outcome is an evaluation failure; the quiet one
    is an earlier write that is itself JSON-shaped, which gets compared against
    the committed capture while the success line still reads "verified 9".
    """
    completed = _run_binding_gate_probe(
        tmp_path,
        {"civicrm_browser_access_denial.mjs": ("process.stdout.write(", replacement)},
    )

    assert completed.returncode != 0, f"{label}: {completed.stdout}"
    assert "verified" not in completed.stdout
    assert f"expected exactly one process.stdout.write( call, found {found}" in completed.stderr, (
        completed.stderr
    )


def test_the_binding_gate_rejects_page_errors_in_another_scripts_literal(tmp_path: Path) -> None:
    """Issue #87: the fabricated stub is only safe for the script that proves it.

    `browser-contact-summary-workflow.json` records an occurrence_count of 2, so
    this edit -- a second capture script emitting `pageErrors.length`, with no
    `pageErrors.length === 2` guard behind it -- is the silent case: the stub
    supplies a 2, the comparison matches, and the gate reports "verified 9"
    having compared a committed capture against a fabricated number.
    """
    # Anchored on the contact-summary block's own schema_version, because two
    # blocks in this script declare an occurrence_count of 2.
    tail = (
        "\n          },\n        ],\n        retained_artifacts: [],\n"
        '        schema_version: "exitdrill/civicrm-contact-summary-workflow-observation/v0.1",'
    )
    completed = _run_binding_gate_probe(
        tmp_path,
        {
            "civicrm_browser_workflow.mjs": (
                f"occurrence_count: 2,{tail}",
                f"occurrence_count: pageErrors.length,{tail}",
            )
        },
    )

    assert completed.returncode != 0, completed.stdout
    assert "verified" not in completed.stdout
    assert "its declared literal reads pageErrors" in completed.stderr, completed.stderr


def test_the_binding_gate_rejects_a_stub_whose_guard_is_gone(tmp_path: Path) -> None:
    """The guard the stub rests on, broken in the copy rather than assumed about."""
    completed = _run_binding_gate_probe(
        tmp_path,
        {"civicrm_browser_case_search_workflow.mjs": ("pageErrors.length !== 2 ||", "false ||")},
    )

    assert completed.returncode != 0, completed.stdout
    assert "nothing here requires pageErrors.length === 2" in completed.stderr, completed.stderr


def test_the_binding_gate_rejects_a_stub_nothing_reads_any_more(tmp_path: Path) -> None:
    """A fabrication that outlives its one literal must be deleted, not left live."""
    completed = _run_binding_gate_probe(
        tmp_path,
        {
            "civicrm_browser_case_search_workflow.mjs": (
                "occurrence_count: pageErrors.length",
                "occurrence_count: 2",
            )
        },
    )

    assert completed.returncode != 0, completed.stdout
    assert "no longer reads pageErrors" in completed.stderr, completed.stderr


def test_the_binding_gate_rejects_a_nested_exclusion_path(tmp_path: Path) -> None:
    """`DYNAMIC_FIELD_PATHS` is named for paths but holds top-level keys (issue #87).

    A nested exclusion cannot be expressed, and before this said so it failed as
    `expected live-only field "..." is missing`, which reads as a broken capture
    rather than as an unsupported exclusion.
    """
    completed = _run_binding_gate_probe(
        tmp_path,
        {
            _BINDING_GATE.name: (
                '"browser-keyboard.json": ["tab_steps_to_roles_summary"],',
                '"browser-keyboard.json": ["tab_steps_to_roles_summary"],\n'
                '  "browser-workflow.json": ["known_runtime_errors.0.occurrence_count"],',
            )
        },
    )

    assert completed.returncode != 0, completed.stdout
    assert "reads as a nested path" in completed.stderr, completed.stderr


def test_the_binding_gate_refuses_an_argument_it_does_not_recognize() -> None:
    """The introspection flag must not turn a typo into a run that checks nothing."""
    node = _required_tool("node", "exercise the binding gate")
    completed = subprocess.run(  # noqa: S603 - resolved interpreter and repository script
        [node, str(_BINDING_GATE), "--print-declared-literal"],
        cwd=PROJECT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "unrecognized argument(s): --print-declared-literal" in completed.stderr


# ---------------------------------------------------------------------------
# The suite's own environment: a gate that skips itself is not a gate.
# ---------------------------------------------------------------------------


def test_the_gate_tool_requirement_is_set_to_a_value_this_suite_understands() -> None:
    """A misspelled value must not silently disable the requirement it was set for.

    This runs whether or not the tools are present, so
    `EXITDRILL_REQUIRE_GATE_TOOLS: "true"` in a workflow fails here instead of
    quietly restoring the skips it was added to remove.
    """
    raw = os.environ.get(REQUIRE_GATE_TOOLS)

    assert raw in _REQUIRE_GATE_TOOLS_VALUES, (
        f"{REQUIRE_GATE_TOOLS}={raw!r} is not understood: set it to 1 to require the gate tools, "
        "or unset it to let a local checkout without them skip"
    )


def test_a_missing_gate_tool_fails_when_the_environment_promised_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #89: under the flag, an absent tool is a failure, not a skip.

    The outcome is captured and then asserted on, rather than wrapped in
    `pytest.raises(pytest.fail.Exception)`. A `pytest.raises` that went unmet
    because `_required_tool` skipped instead would skip this test too, and a
    proof that turns itself into a skip when the thing it proves stops holding
    is the exact defect this test exists to close. Measured: with the fail arm
    deleted, the `pytest.raises` form reported green.
    """
    monkeypatch.setenv(REQUIRE_GATE_TOOLS, "1")
    monkeypatch.setattr(sys.modules[__name__], "which", lambda _name: None)

    outcome: BaseException | None = None
    try:
        _required_tool("node", "check the browser-capture bindings")
    except (pytest.fail.Exception, pytest.skip.Exception) as raised:
        outcome = raised

    assert isinstance(outcome, pytest.fail.Exception), (
        f"under {REQUIRE_GATE_TOOLS}=1 a missing gate tool must fail the suite, but "
        f"_required_tool produced {type(outcome).__name__}, which is how CI loses a gate quietly"
    )
    assert "node is required to check the browser-capture bindings" in str(outcome)
    assert f"{REQUIRE_GATE_TOOLS}=1" in str(outcome)


@pytest.mark.parametrize("value", [None, "", "0"])
def test_a_missing_gate_tool_skips_when_nothing_promised_it(
    value: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A local checkout without node or uv still skips rather than fails."""
    monkeypatch.delenv(REQUIRE_GATE_TOOLS, raising=False)
    if value is not None:
        monkeypatch.setenv(REQUIRE_GATE_TOOLS, value)
    monkeypatch.setattr(sys.modules[__name__], "which", lambda _name: None)

    with pytest.raises(pytest.skip.Exception) as error:
        _required_tool("uv", "exercise the lockfile-drift gate")

    assert "uv is required to exercise the lockfile-drift gate" in str(error.value)


@pytest.mark.parametrize("value", [None, "1"])
def test_a_present_gate_tool_is_returned_under_either_setting(
    value: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The requirement only changes what absence means, never what presence means."""
    monkeypatch.delenv(REQUIRE_GATE_TOOLS, raising=False)
    if value is not None:
        monkeypatch.setenv(REQUIRE_GATE_TOOLS, value)

    resolved = _required_tool("git", "enumerate the committed browser-lab scripts")

    assert Path(resolved).name.startswith("git")
