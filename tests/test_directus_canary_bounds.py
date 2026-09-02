"""Close the Directus canary's untested trust-boundary rejection branches.

`directus_canary.py` verifies an untrusted capture bundle before anything else
in this project reads it: bounded JSON decoding with its own node, depth, and
byte limits, its own regular-file and directory-entry checks, and a long list
of profile assertions. It carried 69 uncovered statements, almost all of them a
single `raise _fail(...)` with a distinct message. Every one is real rejection
behaviour on the outermost trust boundary, and deleting any of them left the
whole suite green.

This is the same work issue #57 asked for on `strict_json.py`, applied to the
canary's separate copy of that boundary, as `docs/ARCHITECTURE.md` notes it has.

Three groups need something other than a bundle on disk, and each says why:

- The JSON and filesystem primitives are called directly, against their stated
  contracts, the way `matches_field_type` and `_dimension_rows` are (issue #54,
  ADR 0023). Reaching them through `normalize_directus_canary` would mean
  routing every case through a re-manifested bundle for no added signal.
- The schema guards are unreachable through the public path by construction:
  `_validate_schema` compares the document digest against a pinned constant
  before looking inside, so any mutation fails on the first line. They are
  exercised directly, and where the function body is the thing under test the
  pinned digest is repointed at the mutated document so the guard past it can
  run. Each such test says so.
- Three checks are unreachable even directly, because an earlier check in the
  same function already guarantees them. They are named in
  `test_structurally_unreachable_guards_are_named_not_forgotten` rather than
  left as unexplained red lines in a coverage report.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from exitdrill import directus_canary
from exitdrill.directus_canary import (
    DirectusCanaryError,
    _api_data,
    _array,
    _boolean,
    _decode_json,
    _directory_entries,
    _identifier,
    _object,
    _optional_object,
    _parse_activity,
    _parse_cases,
    _parse_files,
    _parse_people,
    _parse_permissions,
    _parse_policy,
    _parse_relationships,
    _read_regular_file,
    _reject_json_constant,
    _require_closed_bundle,
    _schema_collection,
    _schema_field,
    _schema_relation,
    _sha256,
    _string,
    _timestamp,
    _validate_json_bounds,
    _validate_root_entries,
    _validate_schema,
    _write_output,
    normalize_directus_canary,
)

PROJECT = Path(__file__).parents[1]
NATIVE = PROJECT / "examples" / "directus-11.17.4-civic-case" / "native"
FILE_IDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
)


def _native(name: str) -> dict[str, Any]:
    value = json.loads((NATIVE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _mutated(name: str, mutate: Callable[[dict[str, Any]], None]) -> bytes:
    """Return one committed capture response with a single edit applied.

    Starting from the real document rather than a hand-built one keeps every
    unrelated field exactly as captured, so each case fails for the reason it
    names and not because a stub was missing a key.
    """
    document = _native(name)
    mutate(document)
    return json.dumps(document).encode("utf-8")


def _assets() -> dict[str, bytes]:
    return {
        f"assets/{file_id}.txt": (NATIVE / "assets" / f"{file_id}.txt").read_bytes()
        for file_id in FILE_IDS
    }


def _owner_by_file() -> dict[str, int]:
    return {FILE_IDS[0]: 1, FILE_IDS[1]: 2}


# ---------------------------------------------------------------------------
# Bounded JSON primitives.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: _object(["not-an-object"], "w"), "must be an object"),
        (lambda: _array({"not": "an array"}, "w"), "must be an array"),
        (lambda: _string("", "w"), "non-empty trimmed string"),
        (lambda: _string("  padded  ", "w"), "non-empty trimmed string"),
        (lambda: _string(7, "w"), "non-empty trimmed string"),
        (lambda: _string("x" * 300, "w"), "exceeds its length limit"),
        (lambda: _boolean(1, "w"), "must be a boolean"),
        (lambda: _identifier("-leading-punctuation", "w"), "must be a stable identifier"),
        (lambda: _identifier("has space", "w"), "must be a stable identifier"),
        (lambda: _identifier("a" * 129, "w"), "exceeds its length limit"),
        (lambda: _timestamp("not-a-timestamp", "w"), "must be an ISO 8601 timestamp"),
        (lambda: _timestamp("2026-08-02T02:38:28", "w"), "must include a UTC offset"),
        (lambda: _sha256("z" * 64, "w"), "must be a lowercase SHA-256 digest"),
        (lambda: _sha256("AB" * 32, "w"), "must be a lowercase SHA-256 digest"),
        (lambda: _reject_json_constant("NaN"), "non-finite JSON number is not permitted: NaN"),
    ],
)
def test_json_primitive_rejects_its_own_out_of_contract_input(
    call: Callable[[], object], message: str
) -> None:
    with pytest.raises(DirectusCanaryError, match=message):
        call()


def test_optional_object_accepts_none_and_validates_anything_else() -> None:
    """Both arms. Without the `None` case, a helper that always raised would pass."""
    assert _optional_object(None, "w") is None
    assert _optional_object({"a": 1}, "w") == {"a": 1}
    with pytest.raises(DirectusCanaryError, match="must be an object"):
        _optional_object("not-an-object", "w")


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([0] * 20_001, "JSON exceeds the node limit"),
        (float("nan"), "non-finite JSON number is not permitted"),
        (float("inf"), "non-finite JSON number is not permitted"),
    ],
)
def test_json_bounds_reject_oversized_and_non_finite_documents(value: object, message: str) -> None:
    with pytest.raises(DirectusCanaryError, match=message):
        _validate_json_bounds(value)


def test_json_bounds_reject_excessive_nesting() -> None:
    nested: object = "leaf"
    for _index in range(33):
        nested = [nested]

    with pytest.raises(DirectusCanaryError, match="JSON exceeds the nesting limit"):
        _validate_json_bounds(nested)


def test_json_bounds_accept_the_committed_capture_documents() -> None:
    """The positive control for the three rejections above."""
    for path in sorted(NATIVE.glob("*.json")):
        _validate_json_bounds(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (b"\xff", "is not valid UTF-8"),
        (b"{", "is not valid JSON"),
        (b"[" * 20_000 + b"]" * 20_000, "exceeds the parser nesting limit"),
        (b'{"a":1,"a":2}', "duplicate JSON object key is not permitted"),
        (b"[]", "must be an object"),
    ],
)
def test_decode_json_rejects_each_malformed_document_class(document: bytes, message: str) -> None:
    with pytest.raises(DirectusCanaryError, match=message):
        _decode_json(document, "w")


def test_decode_json_names_any_other_value_error_rather_than_leaking_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catch-all arm, which no committed or malformed input reaches.

    `json.loads` raises `JSONDecodeError`, `UnicodeDecodeError`, or
    `RecursionError` for every document class above, and this module's own
    hooks raise `DirectusCanaryError`, which is re-raised unchanged. The arm
    exists so that a future parser change cannot leak a bare `ValueError`
    across the trust boundary, and this is what proves it does that.
    """

    def explode(*_args: object, **_kwargs: object) -> object:
        raise ValueError("something else entirely")

    monkeypatch.setattr(json, "loads", explode)

    with pytest.raises(DirectusCanaryError, match="is not valid JSON"):
        _decode_json(b"{}", "w")


# ---------------------------------------------------------------------------
# Filesystem primitives.
# ---------------------------------------------------------------------------


def test_read_regular_file_rejects_a_path_that_is_not_a_regular_file(tmp_path: Path) -> None:
    """A FIFO opens successfully and is then rejected on its stat mode.

    A directory or a missing path fails at `os.open` instead, so it exercises
    the OSError arm below rather than this one.
    """
    fifo = tmp_path / "pipe.json"
    os.mkfifo(fifo)

    with pytest.raises(DirectusCanaryError, match="is not a regular file"):
        _read_regular_file(fifo, max_bytes=64, where="w")


@pytest.mark.parametrize("name", ["missing.json", ""])
def test_read_regular_file_names_an_os_error(tmp_path: Path, name: str) -> None:
    with pytest.raises(DirectusCanaryError, match="could not be read as a regular file"):
        _read_regular_file(tmp_path / name, max_bytes=64, where="w")


def test_read_regular_file_rejects_a_document_over_its_byte_limit(tmp_path: Path) -> None:
    path = tmp_path / "big.json"
    path.write_bytes(b"x" * 65)

    with pytest.raises(DirectusCanaryError, match="exceeds its byte limit"):
        _read_regular_file(path, max_bytes=64, where="w")

    assert _read_regular_file(path, max_bytes=65, where="w") == b"x" * 65


def test_directory_entries_names_an_os_error(tmp_path: Path) -> None:
    with pytest.raises(DirectusCanaryError, match="could not be inspected"):
        _directory_entries(tmp_path / "missing", "w", frozenset({"a"}))


def test_directory_entries_rejects_a_directory_missing_an_expected_entry(
    tmp_path: Path,
) -> None:
    (tmp_path / "a").write_bytes(b"")

    with pytest.raises(DirectusCanaryError, match="has an unexpected entry set"):
        _directory_entries(tmp_path, "w", frozenset({"a", "b"}))


def test_validate_root_entries_rejects_an_entry_set_it_was_handed(tmp_path: Path) -> None:
    """Unreachable through `_require_closed_bundle`, which asks
    `_directory_entries` for exactly this set first. Exercised directly, per
    ADR 0023, so the guard is one that has been shown to fire.
    """
    with pytest.raises(DirectusCanaryError, match="bundle root has an unexpected entry set"):
        _validate_root_entries({})


def _closed_bundle_shape(root: Path, *, fifo_entry: str | None = None) -> Path:
    """Create a directory with the bundle's exact entry names and nothing else.

    The contents are not valid; only the shape matters, because
    `_require_closed_bundle` runs before any file is read.
    """
    root.mkdir()
    assets = root / "assets"
    assets.mkdir()
    for name in directus_canary._ROOT_ENTRIES:
        if name == "assets":
            continue
        (root / name).write_bytes(b"{}")
    for name in directus_canary._ASSET_ENTRIES:
        (assets / name).write_bytes(b"")
    if fifo_entry is not None:
        target = root / fifo_entry
        target.unlink()
        os.mkfifo(target)
    return root / "capture-manifest.json"


def test_closed_bundle_rejects_a_root_entry_that_is_not_a_regular_file(tmp_path: Path) -> None:
    manifest = _closed_bundle_shape(tmp_path / "native", fifo_entry="cases.json")

    with pytest.raises(DirectusCanaryError, match="bundle entry is not a regular file"):
        _require_closed_bundle(manifest.parent, manifest)


def test_closed_bundle_rejects_an_asset_entry_that_is_not_a_regular_file(tmp_path: Path) -> None:
    manifest = _closed_bundle_shape(tmp_path / "native", fifo_entry=f"assets/{FILE_IDS[0]}.txt")

    with pytest.raises(DirectusCanaryError, match="asset entries must be regular files"):
        _require_closed_bundle(manifest.parent, manifest)


def test_closed_bundle_accepts_the_committed_bundle_shape() -> None:
    """The positive control for both shape rejections above."""
    _require_closed_bundle(NATIVE, NATIVE / "capture-manifest.json")


def test_closed_bundle_rejects_an_asset_set_its_helper_reported_wrong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The asset-set recheck, which `_directory_entries` already guarantees.

    Kept as defence in depth for the same reason ADR 0023 keeps
    `_dimension_rows`'s guard, and exercised by making the helper return a set
    it never returns in practice, so the recheck is a check that has been shown
    to fire rather than an unexecuted line.
    """
    manifest = _closed_bundle_shape(tmp_path / "native")
    real = directus_canary._directory_entries

    def wrong(path: Path, where: str, expected: frozenset[str]) -> dict[str, os.DirEntry[str]]:
        entries: dict[str, os.DirEntry[str]] = real(path, where, expected)
        return {} if where == "asset directory" else entries

    monkeypatch.setattr(directus_canary, "_directory_entries", wrong)

    with pytest.raises(DirectusCanaryError, match="asset directory has an unexpected entry set"):
        _require_closed_bundle(manifest.parent, manifest)


def test_bundle_total_byte_limit_rejects_an_oversized_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The committed bundle is far under 32 MiB, so the limit is lowered.

    Writing a 32 MiB fixture to exercise one comparison would trade a slow test
    for the same single bit of information.
    """
    monkeypatch.setattr(directus_canary, "_MAX_BUNDLE_BYTES", 10)

    with pytest.raises(DirectusCanaryError, match="bundle exceeds its total byte limit"):
        normalize_directus_canary(NATIVE / "capture-manifest.json", tmp_path / "out")

    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# Profile assertions over the captured API responses.
# ---------------------------------------------------------------------------


def test_api_data_accepts_the_committed_responses() -> None:
    """Positive control: every mutation below starts from a document that passes."""
    assert len(_api_data((NATIVE / "people.json").read_bytes(), "w", length=3)) == 3


def test_people_ids_must_be_unique() -> None:
    document = _mutated("people.json", lambda raw: raw["data"][1].update({"id": 1}))

    with pytest.raises(DirectusCanaryError, match="people ids must be unique"):
        _parse_people(document)


def test_case_document_must_be_a_pinned_attachment() -> None:
    document = _mutated(
        "cases.json",
        lambda raw: raw["data"][0].update({"document": "44444444-4444-4444-8444-444444444444"}),
    )

    with pytest.raises(DirectusCanaryError, match="outside the pinned attachment inventory"):
        _parse_cases(document)


def test_cases_must_cover_every_pinned_attachment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The final coverage recheck in `_parse_cases`.

    With two cases, two unique document ids, and a two-item pinned inventory,
    this cannot fail: any id outside the inventory is rejected earlier. Adding a
    third pinned id makes the two-case capture genuinely incomplete, which is
    the condition the guard describes.
    """
    monkeypatch.setattr(
        directus_canary, "_FILE_IDS", (*FILE_IDS, "33333333-3333-4333-8333-333333333333")
    )

    with pytest.raises(DirectusCanaryError, match="both pinned attachments exactly once"):
        _parse_cases((NATIVE / "cases.json").read_bytes())


def test_relationship_identifiers_and_keys_must_be_unique() -> None:
    document = _mutated(
        "case-people.json",
        lambda raw: raw["data"][1].update(
            {"case_id": 1, "person_id": 1, "relation_type": "assigned_to"}
        ),
    )

    with pytest.raises(DirectusCanaryError, match="unique identifiers and keys"):
        _parse_relationships(document, {1, 2}, {1, 2, 3})


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda raw: raw["data"][1].update({"id": FILE_IDS[0]}),
            "duplicated or outside the pinned attachment inventory",
        ),
        (
            lambda raw: raw["data"][0].update({"type": "text/html"}),
            "must have text/plain media type",
        ),
        (
            lambda raw: raw["data"][0].update({"filename_download": "intake.md"}),
            "must be a plain .txt filename",
        ),
        (
            lambda raw: raw["data"][0].update({"filename_download": "nested/intake.txt"}),
            "must be a plain .txt filename",
        ),
        (
            lambda raw: raw["data"][0].update({"filename_download": "nested\\intake.txt"}),
            "must be a plain .txt filename",
        ),
    ],
)
def test_files_response_rejects_each_out_of_profile_attachment(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    with pytest.raises(DirectusCanaryError, match=message):
        _parse_files(_mutated("files.json", mutate), _assets(), _owner_by_file())


def test_files_response_must_contain_every_pinned_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final inventory recheck, unreachable for the same structural reason
    as the case one above, and exercised the same way."""
    assets = _assets()
    assets["assets/33333333-3333-4333-8333-333333333333.txt"] = b""
    monkeypatch.setattr(
        directus_canary, "_FILE_IDS", (*FILE_IDS, "33333333-3333-4333-8333-333333333333")
    )

    with pytest.raises(DirectusCanaryError, match="does not contain the pinned attachment"):
        _parse_files((NATIVE / "files.json").read_bytes(), assets, _owner_by_file())


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda raw: raw["data"][0].update({"id": "44444444-4444-4444-8444-444444444444"}),
            "policy id does not match the pinned profile",
        ),
        (
            lambda raw: raw["data"][0].update({"app_access": False}),
            "must allow application access",
        ),
    ],
)
def test_policy_response_rejects_an_out_of_profile_policy(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    with pytest.raises(DirectusCanaryError, match=message):
        _parse_policy(_mutated("policies.json", mutate))


POLICY_ID = "33333333-3333-4333-8333-333333333333"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda raw: raw["data"][0].update({"fields": []}),
            "permission fields must be a non-empty unique list",
        ),
        (
            lambda raw: raw["data"][0].update({"fields": ["id", "id"]}),
            "permission fields must be a non-empty unique list",
        ),
        (
            lambda raw: raw["data"][1].update({"id": 1}),
            "permission ids and collection scopes must be unique",
        ),
        (
            lambda raw: raw["data"][1].update({"collection": "exitdrill_cases"}),
            "permission ids and collection scopes must be unique",
        ),
        (
            lambda raw: raw["data"][0].update({"collection": "directus_users"}),
            "permission collection is outside the pinned profile",
        ),
    ],
)
def test_permissions_response_rejects_each_out_of_profile_grant(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    with pytest.raises(DirectusCanaryError, match=message):
        _parse_permissions(_mutated("permissions.json", mutate), POLICY_ID)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda raw: raw["data"][0].update({"item": "notanumber"}),
            "activity item must identify a case integer",
        ),
        (
            lambda raw: raw["data"][1].update({"id": raw["data"][0]["id"]}),
            "activity event and object identifiers must be unique",
        ),
        (
            lambda raw: raw["data"][1].update({"item": raw["data"][0]["item"]}),
            "activity event and object identifiers must be unique",
        ),
    ],
)
def test_activity_response_rejects_each_out_of_profile_event(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    with pytest.raises(DirectusCanaryError, match=message):
        _parse_activity(_mutated("activity.json", mutate), {1, 2})


# ---------------------------------------------------------------------------
# Schema guards, all unreachable through the public path by construction.
# ---------------------------------------------------------------------------


def _schema_data() -> dict[str, Any]:
    return cast(dict[str, Any], _native("schema.json")["data"])


def test_schema_digest_is_checked_before_anything_inside_the_document() -> None:
    """Why every test below calls a helper directly or repoints the digest.

    `_validate_schema` compares the document's SHA-256 against a pinned
    constant on its first line, so no mutation of the schema can reach the
    guards that follow through `normalize_directus_canary`.
    """
    with pytest.raises(DirectusCanaryError, match="schema snapshot does not match"):
        _validate_schema(b'{"data":{}}')


def test_schema_collection_metadata_must_agree_with_its_name() -> None:
    entry = _schema_data()["collections"][0]
    entry["meta"]["collection"] = "exitdrill_renamed"

    with pytest.raises(DirectusCanaryError, match="schema collection metadata is inconsistent"):
        _schema_collection(entry, 0)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda entry: entry["meta"].update({"field": "renamed"}),
            "schema field metadata is inconsistent",
        ),
        (
            lambda entry: entry["meta"].update({"collection": "renamed"}),
            "schema field metadata is inconsistent",
        ),
        (
            lambda entry: entry["schema"].update({"table": "renamed"}),
            "schema field storage metadata is inconsistent",
        ),
        (
            lambda entry: entry["schema"].update({"name": "renamed"}),
            "schema field storage metadata is inconsistent",
        ),
    ],
)
def test_schema_field_metadata_must_agree_with_its_identity(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    entry = _schema_data()["fields"][0]
    mutate(entry)

    with pytest.raises(DirectusCanaryError, match=message):
        _schema_field(entry, 0)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda entry: entry["meta"].update({"many_field": "renamed"}),
            "schema relation metadata is inconsistent",
        ),
        (
            lambda entry: entry["schema"].update({"column": "renamed"}),
            "schema relation storage metadata is inconsistent",
        ),
    ],
)
def test_schema_relation_metadata_must_agree_with_its_identity(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    entry = _schema_data()["relations"][0]
    mutate(entry)

    with pytest.raises(DirectusCanaryError, match=message):
        _schema_relation(entry, 0)


def _repointed_schema(
    monkeypatch: pytest.MonkeyPatch, mutate: Callable[[dict[str, Any]], None]
) -> bytes:
    """Return mutated schema bytes with the pinned digest moved onto them.

    The digest pin is the outer guard and is already tested above. Repointing
    it is the only way to run the guards behind it, which are the ones that
    would have to hold if the pinned profile were ever re-captured.
    """
    document = _native("schema.json")
    mutate(document["data"])
    encoded = json.dumps(document).encode("utf-8")
    monkeypatch.setattr(directus_canary, "_SCHEMA_SHA256", hashlib.sha256(encoded).hexdigest())
    return encoded


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data.update({"version": 2}), "schema snapshot version"),
        (lambda data: data.update({"version": True}), "schema snapshot version"),
        (lambda data: data.update({"directus": "11.17.5"}), "schema source version"),
        (lambda data: data.update({"vendor": "postgres"}), "database vendor"),
        (
            lambda data: data["collections"][0].update(
                {
                    "collection": "exitdrill_renamed",
                    "meta": {**data["collections"][0]["meta"], "collection": "exitdrill_renamed"},
                    "schema": {"name": "exitdrill_renamed"},
                }
            ),
            "schema collections do not match the pinned profile",
        ),
        (
            lambda data: data["fields"][0].update(
                {"type": "string", "field": data["fields"][0]["field"]}
            ),
            "schema fields do not match the pinned profile",
        ),
        (
            lambda data: data["relations"][0].update(
                {
                    "related_collection": "exitdrill_people",
                    "meta": {**data["relations"][0]["meta"], "one_collection": "exitdrill_people"},
                    "schema": {
                        **data["relations"][0]["schema"],
                        "foreign_key_table": "exitdrill_people",
                    },
                }
            ),
            "schema relations do not match the pinned profile",
        ),
    ],
)
def test_schema_body_rejects_each_out_of_profile_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    document = _repointed_schema(monkeypatch, mutate)

    with pytest.raises(DirectusCanaryError, match=message):
        _validate_schema(document)


def test_repointing_the_digest_alone_still_validates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive control for the repointing technique.

    Without it, every case above could be passing because repointing itself
    breaks the document rather than because the mutation is out of profile.
    """
    document = _repointed_schema(monkeypatch, lambda data: None)

    _validate_schema(document)


# ---------------------------------------------------------------------------
# Atomic output.
# ---------------------------------------------------------------------------


def test_output_reports_a_temporary_directory_that_cannot_be_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> str:
        raise OSError("no space left on device")

    monkeypatch.setattr(tempfile, "mkdtemp", explode)

    with pytest.raises(DirectusCanaryError, match="could not be materialized"):
        _write_output(tmp_path / "out", b"{}", (), {})


def test_output_refuses_to_replace_a_directory_that_appeared_during_the_write(
    tmp_path: Path,
) -> None:
    """The last-moment recheck before `rename`, and the cleanup behind it.

    `normalize_directus_canary` checks the same thing much earlier, so reaching
    this through the public entry point would need a real race. Calling
    `_write_output` directly states the condition the guard is for, and pins
    that a refusal leaves no temporary directory behind.
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with pytest.raises(DirectusCanaryError, match="output directory already exists"):
        _write_output(out_dir, b"{}", (), {})

    assert list(out_dir.iterdir()) == []
    assert not list(tmp_path.glob(".out.tmp-*"))


def test_output_cleans_up_after_an_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A BaseException must not leave a partial output directory behind.

    KeyboardInterrupt is not an `Exception`, so only the bare `BaseException`
    arm can clean up after it. Without that arm the temporary tree survives.
    """

    def explode(_value: object) -> bytes:
        raise KeyboardInterrupt

    monkeypatch.setattr(directus_canary, "canonical_json_bytes", explode)

    with pytest.raises(KeyboardInterrupt):
        _write_output(tmp_path / "out", b"{}", (), {})

    assert not list(tmp_path.glob(".out.tmp-*"))
    assert not (tmp_path / "out").exists()


def test_output_reports_a_location_that_cannot_be_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> Path:
        raise OSError("too many levels of symbolic links")

    monkeypatch.setattr(Path, "resolve", explode)

    with pytest.raises(DirectusCanaryError, match="could not be resolved"):
        normalize_directus_canary(NATIVE / "capture-manifest.json", tmp_path / "out")


def test_output_succeeds_and_writes_the_expected_tree(tmp_path: Path) -> None:
    """The positive control for every output rejection above."""
    out_dir = tmp_path / "out"

    normalize_directus_canary(NATIVE / "capture-manifest.json", out_dir)

    assert (out_dir / "export.json").is_file()
    assert (out_dir / "normalization-manifest.json").is_file()
    assert not list(tmp_path.glob(".out.tmp-*"))


# ---------------------------------------------------------------------------
# What is left, named rather than forgotten.
# ---------------------------------------------------------------------------


def test_structurally_unreachable_guards_are_named_not_forgotten() -> None:
    """Two guards in this module cannot fail, and this records why.

    Neither is deleted, for the reason ADR 0023 gives: each is the contract its
    surrounding function states, and each would produce a named error rather
    than a confusing one if an earlier check were ever narrowed.

    - `_parse_permissions`'s closing `collections != {...}` check. Two grants,
      required unique collections, each required to be one of exactly two
      allowed values, means the set always ends up equal. Unlike the case and
      file inventories, the allowed set is an inline literal rather than a
      module constant, so there is nothing to repoint in a test.
    - `normalize_directus_canary`'s second `resolved_out.exists()` check, after
      resolution. The first check already rejects any `out_dir` that exists or
      is a symlink, and `resolve(strict=False)` cannot make a non-existent path
      exist.

    This test is documentation with a home in the suite rather than a comment
    in a coverage report nobody reads. It asserts the two facts it depends on,
    so it fails if either stops being true.
    """
    source = (PROJECT / "src" / "exitdrill" / "directus_canary.py").read_text(encoding="utf-8")

    assert 'if collection not in {"exitdrill_cases", "exitdrill_people"}:' in source
    assert source.count('raise _fail("output directory already exists")') == 3
