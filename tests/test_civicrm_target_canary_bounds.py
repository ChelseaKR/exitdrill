"""Close the CiviCRM target canary's untested rejection branches.

`civicrm_target_canary.py` is the second copy of the outermost trust boundary,
separate from `strict_json.py` and from the Directus canary's, as
`docs/ARCHITECTURE.md` records. It carried 29 uncovered statements: its own
bounded JSON limits, its own regular-file and directory checks, the evidence
index's byte and schema bindings, and the atomic-output paths.

Every one is real rejection behaviour, and deleting any of them left the whole
suite green.

The approach is the one ADR 0023 sets and `tests/test_directus_canary_bounds.py`
follows: where a branch is unreachable through the public entry point it is
exercised directly against the function's stated contract, and the test says
which and why in place.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, SchemaError

from exitdrill import civicrm_target_canary as canary
from exitdrill.civicrm_target_canary import (
    CiviCRMTargetCanaryError,
    _decode_json,
    _directory_entries,
    _evidence_schema_validator,
    _parse_entity_files,
    _read_regular_file,
    _require_closed_bundle,
    _string,
    _validate_json_bounds,
    _write_output,
    normalize_civicrm_target_canary,
    verify_civicrm_evidence_index,
)
from exitdrill.loader import load_export
from exitdrill.models import ExportPackage, JsonValue

PROJECT = Path(__file__).parents[1]
NATIVE = PROJECT / "examples" / "civicrm-6.16.2-target-roundtrip" / "native"
MANIFEST = NATIVE / "capture-manifest.json"


def _normalized(destination: Path) -> Path:
    normalize_civicrm_target_canary(MANIFEST, destination)
    return destination


# ---------------------------------------------------------------------------
# Bounded JSON.
# ---------------------------------------------------------------------------


def test_string_rejects_a_value_over_its_length_limit() -> None:
    with pytest.raises(CiviCRMTargetCanaryError, match="exceeds its length limit"):
        _string("x" * 300, "w")


def test_string_accepts_a_value_inside_its_limit() -> None:
    """Positive control for the rejection above."""
    assert _string("Synthetic", "w") == "Synthetic"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_json_bounds_reject_a_non_finite_number(value: float) -> None:
    with pytest.raises(CiviCRMTargetCanaryError, match="non-finite JSON number"):
        _validate_json_bounds(value)


def test_json_bounds_accept_every_committed_capture_document() -> None:
    """Positive control: the bundle this canary verifies passes its own limits."""
    for path in sorted(NATIVE.glob("*.json")):
        _validate_json_bounds(json.loads(path.read_text(encoding="utf-8")))


def test_decode_json_rejects_nesting_whichever_bound_catches_it() -> None:
    """20,000 levels, rejected on every interpreter `requires-python` admits.

    Which bound rejects it is an interpreter detail: 3.12 and 3.13 give out in
    the decoder, 3.14 walks the document and `_validate_json_bounds` stops it.
    Both name the nesting limit and both raise this canary's own error, which is
    what the trust boundary owes its caller. See issue #90.
    """
    with pytest.raises(CiviCRMTargetCanaryError, match="nesting limit"):
        _decode_json(b"[" * 20_000 + b"]" * 20_000, "w")


def test_decode_json_rejects_nesting_the_parser_cannot_walk(
    parser_defeating_json_depth: int,
) -> None:
    """Deeper than this decoder can recurse, so `json.loads` fails before any bound.

    The depth comes from `parser_defeating_json_depth` rather than a literal
    because CPython 3.14 raised it; the fixture fails the run if no depth in its
    range defeats the decoder, which is what keeps the `RecursionError` arm an
    observable guard rather than an assumed one.
    """
    depth = parser_defeating_json_depth
    with pytest.raises(CiviCRMTargetCanaryError, match="exceeds the parser nesting limit"):
        _decode_json(b"[" * depth + b"]" * depth, "w")


def test_decode_json_names_any_other_value_error_rather_than_leaking_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catch-all arm, which no real document class reaches.

    Every malformed document produces `JSONDecodeError`, `UnicodeDecodeError`,
    or `RecursionError`, and this module's own hooks raise
    `CiviCRMTargetCanaryError`, which is re-raised unchanged. The arm exists so
    a future parser change cannot leak a bare `ValueError` across the boundary.
    """

    def explode(*_args: object, **_kwargs: object) -> object:
        raise ValueError("something else entirely")

    monkeypatch.setattr(json, "loads", explode)

    with pytest.raises(CiviCRMTargetCanaryError, match="is not valid JSON"):
        _decode_json(b"{}", "w")


# ---------------------------------------------------------------------------
# Filesystem.
# ---------------------------------------------------------------------------


def test_read_regular_file_rejects_a_path_that_is_not_a_regular_file(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe.json"
    os.mkfifo(fifo)

    with pytest.raises(CiviCRMTargetCanaryError, match="is not a regular file"):
        _read_regular_file(fifo, max_bytes=64, where="w")


def test_read_regular_file_names_an_os_error(tmp_path: Path) -> None:
    with pytest.raises(CiviCRMTargetCanaryError, match="could not be read as a regular file"):
        _read_regular_file(tmp_path / "missing.json", max_bytes=64, where="w")


def test_read_regular_file_accepts_a_committed_capture_file() -> None:
    """Positive control for both rejections above."""
    assert _read_regular_file(NATIVE / "contacts.json", max_bytes=4096, where="w")


def test_directory_entries_names_an_os_error(tmp_path: Path) -> None:
    with pytest.raises(CiviCRMTargetCanaryError, match="could not be inspected"):
        _directory_entries(tmp_path / "missing", "w", frozenset({"a"}))


def _bundle_shape(root: Path, *, fifo_entry: str | None = None) -> Path:
    """Create a directory with the bundle's exact entry names and nothing else.

    Contents do not matter: `_require_closed_bundle` runs before any file is
    read, so only the entry set and file types are under test.
    """
    root.mkdir(parents=True)
    (root / "assets").mkdir()
    for name in canary._ROOT_ENTRIES:
        if name == "assets":
            continue
        (root / name).write_bytes(b"{}")
    for name in canary._ASSET_ENTRIES:
        (root / "assets" / name).write_bytes(b"")
    if fifo_entry is not None:
        target = root / fifo_entry
        target.unlink()
        os.mkfifo(target)
    return root / "capture-manifest.json"


def test_closed_bundle_rejects_a_root_entry_that_is_not_a_regular_file(tmp_path: Path) -> None:
    manifest = _bundle_shape(tmp_path / "native", fifo_entry="contacts.json")

    with pytest.raises(CiviCRMTargetCanaryError, match="bundle entry is not a regular file"):
        _require_closed_bundle(manifest.parent, manifest)


def test_closed_bundle_accepts_the_committed_bundle_shape() -> None:
    """Positive control for the rejection above."""
    _require_closed_bundle(NATIVE, MANIFEST)


def test_bundle_total_byte_limit_rejects_an_oversized_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The committed bundle is far under the limit, so the limit is lowered.

    Writing a fixture large enough to exercise one comparison would trade a
    slow test for the same single bit of information.
    """
    monkeypatch.setattr(canary, "_MAX_BUNDLE_BYTES", 10)

    with pytest.raises(CiviCRMTargetCanaryError, match="bundle exceeds its total byte limit"):
        normalize_civicrm_target_canary(MANIFEST, tmp_path / "out")

    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# Target read-back parsing.
# ---------------------------------------------------------------------------


def test_entity_files_must_cover_every_pinned_target_file() -> None:
    """The closing inventory recheck in `_parse_entity_files`.

    With two associations and a two-file inventory it cannot fail: an
    association to an unknown file is rejected earlier. The function takes the
    inventory as a parameter, so passing a three-file one states the condition
    the guard describes without touching the committed capture.
    """
    documents = {
        f"assets/{name}": (NATIVE / "assets" / name).read_bytes()
        for name in os.listdir(NATIVE / "assets")
    }
    file_by_target = {
        1: "11111111-1111-4111-8111-111111111111",
        2: "22222222-2222-4222-8222-222222222222",
        3: "33333333-3333-4333-8333-333333333333",
    }

    with pytest.raises(CiviCRMTargetCanaryError, match="do not cover the pinned target file"):
        _parse_entity_files(
            (NATIVE / "entity-files.json").read_bytes(),
            file_by_target,
            {1: "1", 2: "2"},
            documents,
        )


def test_entity_files_accept_the_committed_two_file_inventory() -> None:
    """Positive control: the same call with the real inventory succeeds."""
    documents = {
        f"assets/{name}": (NATIVE / "assets" / name).read_bytes()
        for name in os.listdir(NATIVE / "assets")
    }
    attachments, copies = _parse_entity_files(
        (NATIVE / "entity-files.json").read_bytes(),
        {
            1: "11111111-1111-4111-8111-111111111111",
            2: "22222222-2222-4222-8222-222222222222",
        },
        {1: "1", 2: "2"},
        documents,
    )

    assert len(attachments) == 2
    assert len(copies) == 2


# ---------------------------------------------------------------------------
# The evidence index and its packaged schemas.
# ---------------------------------------------------------------------------


def _index_dir(tmp_path: Path) -> Path:
    return _normalized(tmp_path / "normalized")


def _rewrite_index(directory: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    path = directory / "evidence-index.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    mutate(cast(dict[str, Any], raw))
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_index_verification_accepts_the_emitted_index(tmp_path: Path) -> None:
    """Positive control for every index rejection below."""
    result = verify_civicrm_evidence_index(_index_dir(tmp_path) / "evidence-index.json")

    assert result["status"] == "evidence_artifact_contracts_verified"


def test_index_rejects_an_entry_claiming_more_bytes_than_the_limit(tmp_path: Path) -> None:
    directory = _index_dir(tmp_path)
    _rewrite_index(directory, lambda raw: raw["entries"][0].update({"bytes": 10_485_761}))

    with pytest.raises(CiviCRMTargetCanaryError, match=r"bytes exceeds its byte limit"):
        verify_civicrm_evidence_index(directory / "evidence-index.json")


def test_an_invalid_packaged_schema_is_reported_rather_than_raised_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The packaged schemas are loaded at runtime, so a bad one must be named.

    `tests/test_gates.py` already pins that the wheel ships exactly the schemas
    the source references, with unaltered bytes, so an invalid one cannot ship.
    This arm is what turns one into a named canary error rather than a
    `jsonschema` traceback if it ever did.
    """

    def explode(_schema: object) -> None:
        raise SchemaError("invalid packaged schema")

    monkeypatch.setattr(Draft202012Validator, "check_schema", staticmethod(explode))
    _evidence_schema_validator.cache_clear()
    try:
        with pytest.raises(CiviCRMTargetCanaryError, match="is invalid"):
            _evidence_schema_validator(canary._EVIDENCE_INDEX_SCHEMA)
    finally:
        # Must not leave a validator built under the patch in the cache.
        _evidence_schema_validator.cache_clear()


def test_every_packaged_evidence_schema_is_actually_valid() -> None:
    """Positive control for the arm above, and for the cache being cleared."""
    for schema_version in canary._EVIDENCE_SCHEMA_RESOURCES:
        assert _evidence_schema_validator(schema_version) is not None


def test_index_rejects_an_export_that_changed_between_the_two_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recheck after `load_export` re-reads the file from disk.

    The bytes were already digest-checked once, so the two can only disagree if
    the file changed in between. `load_export` is made to report a different
    digest, which is what a swap would produce.
    """
    directory = _index_dir(tmp_path)

    def swapped(path: Path) -> ExportPackage:
        return replace(load_export(path), source_sha256="0" * 64)

    monkeypatch.setattr(canary, "load_export", swapped)

    with pytest.raises(CiviCRMTargetCanaryError, match="changed during validation"):
        verify_civicrm_evidence_index(directory / "evidence-index.json")


def test_index_reports_an_attachment_that_cannot_be_read(tmp_path: Path) -> None:
    """A declared attachment whose bytes are gone must be named, not raised raw.

    The export document still matches its binding, so verification reaches the
    per-attachment read and fails there rather than earlier.
    """
    directory = _index_dir(tmp_path)
    attachments = sorted((directory / "export-files").rglob("*.txt"))
    assert attachments
    attachments[0].unlink()

    with pytest.raises(CiviCRMTargetCanaryError, match="could not be verified"):
        verify_civicrm_evidence_index(directory / "evidence-index.json")


# ---------------------------------------------------------------------------
# Atomic output.
# ---------------------------------------------------------------------------


_RESULT_PARAMETERS = (
    "result",
    "ui_result",
    "browser_result",
    "accessibility_result",
    "keyboard_result",
    "activity_view_result",
    "contact_summary_workflow_result",
    "case_client_workflow_result",
    "browser_access_denial_result",
    "browser_access_allow_control_result",
    "case_search_workflow_result",
)


def test_the_write_signature_is_the_one_these_tests_call() -> None:
    """Pins the parameter list the helper below fills in.

    Every output test writes empty result documents, because none of them cares
    what a document says: each fails before or during the write for an
    unrelated reason. An added result document would otherwise turn those calls
    into a `TypeError` that reads like an unrelated breakage.
    """
    from inspect import signature

    parameters = tuple(signature(canary._write_output).parameters)

    assert parameters == ("out_dir", "export_document", "copies", *_RESULT_PARAMETERS)


def _write_empty_output(out_dir: Path) -> None:
    """Call `_write_output` with the smallest arguments it accepts."""
    empty: dict[str, JsonValue] = {}
    _write_output(
        out_dir,
        b"{}",
        (),
        empty,
        empty,
        empty,
        empty,
        empty,
        empty,
        empty,
        empty,
        empty,
        empty,
        empty,
    )


def test_output_reports_a_temporary_directory_that_cannot_be_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> str:
        raise OSError("no space left on device")

    monkeypatch.setattr(tempfile, "mkdtemp", explode)

    with pytest.raises(CiviCRMTargetCanaryError, match="could not be materialized"):
        _write_empty_output(tmp_path / "out")


def test_output_refuses_to_replace_a_directory_that_appeared_during_the_write(
    tmp_path: Path,
) -> None:
    """The last-moment recheck before `rename`, and the cleanup behind it.

    `normalize_civicrm_target_canary` checks the same thing much earlier, so
    reaching this through the public entry point would need a real race.
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with pytest.raises(CiviCRMTargetCanaryError, match="output directory already exists"):
        _write_empty_output(out_dir)

    assert list(out_dir.iterdir()) == []
    assert not list(tmp_path.glob(".out.tmp-*"))


def test_output_cleans_up_after_an_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A BaseException must not leave a partial output directory behind.

    KeyboardInterrupt is not an `Exception`, so only the bare `BaseException`
    arm can clean up after it.
    """

    def explode(_value: object) -> bytes:
        raise KeyboardInterrupt

    monkeypatch.setattr(canary, "canonical_json_bytes", explode)

    with pytest.raises(KeyboardInterrupt):
        _write_empty_output(tmp_path / "out")

    assert not list(tmp_path.glob(".out.tmp-*"))
    assert not (tmp_path / "out").exists()


def test_output_reports_a_location_that_cannot_be_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> Path:
        raise OSError("too many levels of symbolic links")

    monkeypatch.setattr(Path, "resolve", explode)

    with pytest.raises(CiviCRMTargetCanaryError, match="could not be resolved"):
        normalize_civicrm_target_canary(MANIFEST, tmp_path / "out")


def test_output_succeeds_and_writes_the_expected_tree(tmp_path: Path) -> None:
    """Positive control for every output rejection above."""
    out_dir = _normalized(tmp_path / "out")

    assert (out_dir / "export.json").is_file()
    assert (out_dir / "evidence-index.json").is_file()
    assert not list(tmp_path.glob(".out.tmp-*"))


def test_normalizer_refuses_an_existing_output_directory(tmp_path: Path) -> None:
    """The public pre-check, so the private recheck above is not the only guard."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with pytest.raises(CiviCRMTargetCanaryError, match="output directory already exists"):
        normalize_civicrm_target_canary(MANIFEST, out_dir)

    assert list(out_dir.iterdir()) == []


def test_no_temporary_output_survives_a_rejected_run(tmp_path: Path) -> None:
    """Whatever the rejection, the parent directory must be left clean."""
    out_dir = tmp_path / "out"
    shutil.copytree(NATIVE, tmp_path / "native")
    (tmp_path / "native" / "contacts.json").write_bytes(b"{}")

    with pytest.raises(CiviCRMTargetCanaryError):
        normalize_civicrm_target_canary(tmp_path / "native" / "capture-manifest.json", out_dir)

    assert not out_dir.exists()
    assert not list(tmp_path.glob(".out.tmp-*"))


def test_the_structurally_unreachable_guard_is_named_not_forgotten() -> None:
    """One statement in this module cannot be reached, and this records why.

    `normalize_civicrm_target_canary` checks `out_dir.exists() or
    out_dir.is_symlink()` before resolving, and checks the resolved path again
    afterwards. The first check already rejects anything that exists or is a
    symlink, and `resolve(strict=False)` cannot make a non-existent path exist,
    so the second can only fire under a race between the two.

    It is not deleted, for the reason ADR 0023 gives: it is the last thing
    standing between a racing writer and an overwritten output directory, and
    it would produce a named error rather than a silent replacement.
    `test_normalizer_refuses_an_existing_output_directory` covers the
    pre-resolution check, so the guard is not the only one of its kind here.

    The assertion below fails if the pair ever stops existing.
    """
    source = (PROJECT / "src" / "exitdrill" / "civicrm_target_canary.py").read_text(
        encoding="utf-8"
    )

    assert source.count('raise _fail("output directory already exists")') == 3
