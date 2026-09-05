"""Close the last untested rejection branches outside the two canaries.

After the Directus canary's boundary was covered, five modules still carried
rejection branches nothing executed: `paths.py` (the single attachment-root
boundary), `loader.py` (the strict input contract), `exercise.py` (the
synthetic-only plan preflight), `comparison.py` (the packaged-schema and
serialization guards), and `evaluator.py` (the reference-model restore).

Every one is behaviour a caller depends on. Deleting any of them left the whole
suite green, which is the property this file removes.

Where a branch is unreachable through the public entry point, it is exercised
directly against the function's stated contract, per ADR 0023, and the test
says which and why. Two branches in `evaluator.py` are unreachable even
directly without simulating a failure the module is defended against rather
than one it can produce; they are named at the end rather than left as
unexplained red lines.
"""

from __future__ import annotations

import io
import json
import os
import stat
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, SchemaError

from exitdrill import comparison as comparison_module
from exitdrill import paths as paths_module
from exitdrill.comparison import (
    ComparisonError,
    _comparison_schema_validator,
    _verify_comparison_against_snapshots,
    compare_snapshots,
    snapshot_receipt,
)
from exitdrill.evaluator import _invalid_entities, run_drill
from exitdrill.exercise import ExercisePlanError, load_exercise_plan
from exitdrill.loader import (
    PackageError,
    _identifier,
    _items,
    _mapping,
    _string,
    load_baseline,
    load_export,
)
from exitdrill.models import ExportPackage, JsonValue
from exitdrill.paths import (
    BoundedPathError,
    _open_beneath,
    _sha256_stream,
    sha256_bounded_file,
)
from exitdrill.receipt import build_receipt
from exitdrill.strict_json import StrictJsonError, load_strict_json

PROJECT = Path(__file__).parents[1]
EXAMPLE = PROJECT / "examples" / "synthetic-crm"
PLAN = PROJECT / "examples" / "synthetic-exercise" / "plan.json"


# ---------------------------------------------------------------------------
# paths.py: the single attachment-root boundary.
# ---------------------------------------------------------------------------


def test_stream_hash_rejects_a_file_that_shrank_mid_read() -> None:
    """The size the descriptor reported must be the size actually read.

    `sha256_bounded_file` stats and reads through one descriptor precisely so a
    path swap cannot change the bytes being measured. This is the arm that
    fires if the bytes end early anyway.
    """
    with pytest.raises(BoundedPathError, match="changed size while being read"):
        _sha256_stream(io.BytesIO(b"short"), expected_size=64)


def test_stream_hash_rejects_a_file_that_grew_mid_read() -> None:
    with pytest.raises(BoundedPathError, match="changed size while being read"):
        _sha256_stream(io.BytesIO(b"longer than declared"), expected_size=4)


def test_stream_hash_accepts_an_exact_length_read() -> None:
    """Positive control: an always-raising stream reader would pass both above."""
    import hashlib

    assert _sha256_stream(io.BytesIO(b"abc"), expected_size=3) == hashlib.sha256(b"abc").hexdigest()


def test_open_beneath_rejects_a_path_outside_the_root(tmp_path: Path) -> None:
    """Called directly: `resolve_bounded_file` rejects this first in the real path.

    The guard is the contract `_open_beneath` states for its own two arguments,
    and it is what would produce a named error rather than an escape if the
    caller were ever changed.
    """
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside" / "file.txt"
    outside.parent.mkdir()
    outside.write_bytes(b"x")

    with pytest.raises(BoundedPathError, match="escapes its declared root"):
        _open_beneath(root, outside)


def test_open_beneath_rejects_the_root_itself(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(BoundedPathError, match="is not a regular file"):
        _open_beneath(root, root.resolve())


def test_bounded_hash_works_where_the_platform_lacks_directory_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback open, taken on platforms without `dir_fd` or `O_NOFOLLOW`.

    CI and development both run on platforms that have them, so the fallback is
    never taken here. It is still the code every other platform would run.
    """
    root = tmp_path / "root"
    (root / "attachments").mkdir(parents=True)
    (root / "attachments" / "intake.txt").write_bytes(b"synthetic")
    monkeypatch.setattr(paths_module, "_OPEN_SUPPORTS_DIR_FD", False)

    digest = sha256_bounded_file(root, "attachments/intake.txt", max_bytes=1024)

    import hashlib

    assert digest == hashlib.sha256(b"synthetic").hexdigest()


def test_bounded_hash_rejects_a_descriptor_that_is_not_a_regular_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recheck after the open, which exists for a swap between the two.

    `resolve_bounded_file` has already required a regular file, so reaching
    this in a test means simulating the swap the check is for. `S_ISREG` is
    made to answer False, which is what a swapped descriptor would report.
    """
    root = tmp_path / "root"
    (root / "attachments").mkdir(parents=True)
    (root / "attachments" / "intake.txt").write_bytes(b"synthetic")
    monkeypatch.setattr(stat, "S_ISREG", lambda _mode: False)

    with pytest.raises(BoundedPathError, match="is not a regular file"):
        sha256_bounded_file(root, "attachments/intake.txt", max_bytes=1024)


# ---------------------------------------------------------------------------
# loader.py: the strict input contract.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: _mapping(["not-a-mapping"], "c"), "must be an object"),
        (lambda: _items({"not": "a list"}, "c"), "must be an array"),
        (lambda: _string({"k": 1}, "k", "c"), "must be a non-empty string"),
        (lambda: _string({"k": "   "}, "k", "c"), "must be a non-empty string"),
        (lambda: _string({}, "k", "c"), "must be a non-empty string"),
        (lambda: _identifier({"k": "has space"}, "k", "c"), "must be a stable identifier"),
    ],
)
def test_loader_primitive_rejects_its_own_out_of_contract_input(
    call: Callable[[], object], message: str
) -> None:
    with pytest.raises(PackageError, match=message):
        call()


def _copied(tmp_path: Path) -> Path:
    from shutil import copytree

    destination = tmp_path / "synthetic-crm"
    copytree(EXAMPLE, destination)
    return destination


def _rewrite(path: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    mutate(cast(dict[str, Any], raw))
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_baseline_rejects_duplicate_required_field_names(tmp_path: Path) -> None:
    copied = _copied(tmp_path)
    _rewrite(
        copied / "baseline.json",
        lambda raw: raw["entities"][0]["required_fields"].append(
            dict(raw["entities"][0]["required_fields"][0])
        ),
    )

    with pytest.raises(PackageError, match="required_fields names must be unique"):
        load_baseline(copied / "baseline.json")


def test_export_rejects_an_entity_field_name_that_is_not_an_identifier(
    tmp_path: Path,
) -> None:
    copied = _copied(tmp_path)
    _rewrite(
        copied / "export.json",
        lambda raw: raw["entities"][0]["fields"].update({"not a name": "x"}),
    )

    with pytest.raises(PackageError, match="fields has an invalid field name"):
        load_export(copied / "export.json")


def test_the_committed_fixtures_still_load(tmp_path: Path) -> None:
    """Positive control for both mutations above."""
    copied = _copied(tmp_path)

    assert load_baseline(copied / "baseline.json").entities
    assert load_export(copied / "export.json").entities


# ---------------------------------------------------------------------------
# exercise.py: the synthetic-only plan preflight.
# ---------------------------------------------------------------------------


def _plan_at(tmp_path: Path, mutate: Callable[[dict[str, Any]], None] | None = None) -> Path:
    raw = json.loads(PLAN.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    if mutate is not None:
        mutate(cast(dict[str, Any], raw))
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_the_committed_exercise_plan_validates(tmp_path: Path) -> None:
    """Positive control: every rejection below starts from a plan that passes."""
    load_exercise_plan(_plan_at(tmp_path))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda raw: raw.update({"schema_version": "exitdrill/exercise-plan/v0.2"}),
            "unsupported exercise plan schema",
        ),
        (
            lambda raw: raw.update({"source": ["not", "an", "object"]}),
            "exercise source must be an object",
        ),
        (
            lambda raw: raw["source"].update({"system": "   "}),
            "exercise source.system must be a non-empty string",
        ),
        (
            lambda raw: raw["source"].pop("version"),
            "exercise source is missing field",
        ),
        (
            lambda raw: raw.update({"workflow_probes": {"not": "an array"}}),
            "workflow_probes must be an array",
        ),
        (
            lambda raw: raw["baseline"].update({"source_descriptions": []}),
            "source_descriptions must contain non-empty strings",
        ),
    ],
)
def test_exercise_plan_rejects_each_out_of_contract_document(
    tmp_path: Path, mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    with pytest.raises(ExercisePlanError, match=message):
        load_exercise_plan(_plan_at(tmp_path, mutate))


# ---------------------------------------------------------------------------
# comparison.py: the packaged schema and the serialization guard.
# ---------------------------------------------------------------------------


def test_an_invalid_packaged_schema_is_reported_rather_than_raised_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The packaged schema is loaded at runtime, so a bad one must be named.

    `tests/test_gates.py` already pins that the wheel ships exactly the schemas
    the source references and that their bytes are unaltered, so a genuinely
    invalid packaged schema cannot ship. This arm is what turns one into a
    `ComparisonError` instead of a `jsonschema` traceback if it ever did.
    """

    def explode(_schema: object) -> None:
        raise SchemaError("invalid packaged schema")

    monkeypatch.setattr(Draft202012Validator, "check_schema", staticmethod(explode))
    _comparison_schema_validator.cache_clear()
    try:
        with pytest.raises(ComparisonError, match="packaged comparison schema is invalid"):
            _comparison_schema_validator()
    finally:
        # The cache must not keep a validator built under the patch, or every
        # later comparison in this session would inherit it.
        _comparison_schema_validator.cache_clear()


def test_the_packaged_comparison_schema_is_actually_valid() -> None:
    """Positive control for the arm above, and for the cache being cleared."""
    assert _comparison_schema_validator() is not None
    assert comparison_module._COMPARISON_SCHEMA_RESOURCE.endswith(".schema.json")


def _snapshots() -> tuple[Any, Any]:
    lossy = PROJECT / "examples" / "synthetic-crm-lossy"
    baseline = load_baseline(EXAMPLE / "baseline.json")
    reference = build_receipt(
        run_drill(baseline, load_export(EXAMPLE / "export.json"), EXAMPLE / "export-files"),
        claimed_generated_at="2026-07-22T20:00:00Z",
    )
    candidate = build_receipt(
        run_drill(baseline, load_export(lossy / "export.json"), lossy / "export-files"),
        claimed_generated_at="2026-07-22T20:05:00Z",
    )
    return snapshot_receipt(reference), snapshot_receipt(candidate)


def test_a_comparison_document_that_cannot_be_serialized_is_reported() -> None:
    """The verifier canonicalizes both documents to compare them byte for byte.

    A caller-supplied document holding a value canonical JSON cannot express
    must produce a named error rather than a `TypeError` from the serializer.
    """
    reference, candidate = _snapshots()
    unserializable = cast("dict[str, JsonValue]", {"comparability": {1, 2, 3}})

    with pytest.raises(ComparisonError, match="not valid JSON data"):
        _verify_comparison_against_snapshots(unserializable, reference, candidate)


def test_a_real_comparison_document_verifies_against_its_snapshots() -> None:
    """Positive control for the guard above."""
    reference, candidate = _snapshots()

    _verify_comparison_against_snapshots(
        compare_snapshots(reference, candidate), reference, candidate
    )


# ---------------------------------------------------------------------------
# evaluator.py: the reference-model restore.
# ---------------------------------------------------------------------------


def test_restore_reports_nothing_when_the_entity_load_violates_integrity() -> None:
    """A package the loader would have rejected must still fail closed here.

    `load_export` rejects duplicate entity keys, so this cannot arrive through
    the CLI. `run_drill` accepts an `ExportPackage` from any caller, and the
    entity insert is the one bulk statement in the restore: if it violates the
    primary key the reference model is abandoned rather than partially counted.
    Constructing the package directly is the only way to state that.

    What this pins is the outcome, not the short circuit. Measured: deleting
    the early return leaves this test passing, because with no entities loaded
    the reference model's foreign keys reject every dependent insert too, so
    continuing arrives at the same zeros. Two independent mechanisms produce
    the same fail-closed answer, and that is worth knowing rather than
    papering over: the early return saves work, and the foreign keys are what
    make the answer correct either way.
    """
    baseline = load_baseline(EXAMPLE / "baseline.json")
    package = load_export(EXAMPLE / "export.json")
    duplicated = ExportPackage(
        drill_id=package.drill_id,
        source_system=package.source_system,
        exported_at=package.exported_at,
        entities=(*package.entities, replace(package.entities[0])),
        relationships=package.relationships,
        attachments=package.attachments,
        permissions=package.permissions,
        audit_events=package.audit_events,
        source_sha256=package.source_sha256,
    )

    result = run_drill(baseline, duplicated, EXAMPLE / "export-files")
    payload = result.payload()

    assert payload["overall_status"] == "not_structurally_restorable"
    for dimension in cast("list[dict[str, JsonValue]]", payload["dimensions"]):
        assert dimension["restored_count"] == 0


def test_entity_validation_skips_an_expectation_without_the_shape_it_needs() -> None:
    """The defensive `continue` in `_invalid_entities`.

    Its parameter is `tuple[object, ...]`, so the guard is the contract that
    type states: an expectation lacking `key` or `required_fields` contributes
    nothing rather than raising an `AttributeError` mid-count.
    """
    assert _invalid_entities(("not-an-expectation", 7, None), {}) == 0


def test_structurally_unreachable_restore_branches_are_named_not_forgotten() -> None:
    """Two branches in `evaluator.py` stay uncovered, and this records why.

    - `_table_count`'s `row is None` arm. `SELECT COUNT(*)` always returns one
      row, so `fetchone()` cannot return `None`. It is the contract sqlite3's
      `Cursor.fetchone` signature states (`Any | None`), not a state this query
      can produce.
    - the post-insert `PRAGMA foreign_key_check` arm. Every per-row insert that
      would violate a foreign key is already caught and rolled back one row at
      a time, so the check finds nothing left to report. Reaching it would mean
      inserting a violating row successfully, which the same connection's
      enforced foreign keys prevent.

    Neither is deleted, for the reason ADR 0023 gives: each is a fail-closed
    floor that would produce a correct zero rather than a wrong count if an
    earlier guarantee were ever narrowed. This test asserts the two facts it
    depends on, so it fails if either stops being true.
    """
    source = (PROJECT / "src" / "exitdrill" / "evaluator.py").read_text(encoding="utf-8")

    assert "SELECT COUNT(*) FROM {table}" in source
    assert "PRAGMA foreign_key_check" in source
    assert source.count("except sqlite3.IntegrityError:") == 2
    assert "PRAGMA foreign_keys = ON" in source or "foreign_keys" in source


def test_the_json_recursion_arms_are_named_with_the_depth_that_still_reaches_them(
    tmp_path: Path, parser_defeating_json_depth: int
) -> None:
    """Three `except RecursionError` arms, and what it now takes to observe each.

    `strict_json.py`, `directus_canary.py` and `civicrm_target_canary.py` each
    turn a decoder recursion failure into their own boundary error rather than
    letting a raw interpreter error escape as itself. Issue #57 reached all
    three with a 20,000-level document. CPython 3.14 parses that document, so on
    that interpreter the same literal reaches each module's own depth bound
    instead and the arm goes uncovered without anything going red -- the exact
    shape of the defect ADR 0023 exists to remove, arriving through an
    interpreter upgrade rather than a code edit (issue #90).

    The arms are not unreachable on any interpreter `requires-python` admits.
    The depth moved; it did not disappear. `parser_defeating_json_depth` finds
    it and fails the run when it cannot, and the three bounds tests use it. This
    records the reason and asserts the facts it rests on:

    - a depth that defeats this decoder exists, and is at least the one #57 used;
    - all three arms are still present, so none was quietly deleted once the
      literal stopped reaching it;
    - the 20,000-level document is still rejected by this module's own boundary,
      whichever floor catches it, which is the property that made the 3.14 red
      an expectation failure and not a security regression. The two canaries
      assert the same property against their own copies of the boundary, in
      `test_directus_canary_bounds.py` and `test_civicrm_target_canary_bounds.py`.
    """
    assert parser_defeating_json_depth >= 20_000

    for module in ("strict_json.py", "directus_canary.py", "civicrm_target_canary.py"):
        source = (PROJECT / "src" / "exitdrill" / module).read_text(encoding="utf-8")
        assert "except RecursionError as exc:" in source

    document = tmp_path / "deeply-nested.json"
    document.write_text("[" * 20_000 + "]" * 20_000, encoding="utf-8")
    with pytest.raises(StrictJsonError, match="JSON nesting exceeds"):
        load_strict_json(document, max_bytes=1 << 20, size_label="test")


def test_attachment_root_is_still_the_only_way_in(tmp_path: Path) -> None:
    """Regression net: the boundary rejects an absolute path and an escape.

    Already covered elsewhere, restated here so this module fails loudly if the
    boundary it spends its first section on is ever bypassed entirely.
    """
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"not yours")

    for relative in (str(outside), "../outside.txt"):
        with pytest.raises(BoundedPathError):
            sha256_bounded_file(root, relative, max_bytes=1024)

    assert os.path.isdir(root)
    assert outside.read_bytes() == b"not yours"
