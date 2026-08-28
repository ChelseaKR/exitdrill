import json
from collections.abc import Callable
from pathlib import Path

import pytest

from exitdrill.loader import PackageError, load_baseline, load_export
from exitdrill.models import Coverage, Dimension


def _json(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _write(path: Path, raw: object) -> None:
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_loads_strict_baseline_and_export(example_root: Path) -> None:
    baseline = load_baseline(example_root / "baseline.json")
    package = load_export(example_root / "export.json")
    assert baseline.drill_id == package.drill_id
    assert baseline.coverage[Dimension.ENTITIES] is Coverage.COMPLETE
    assert baseline.entities[0].required_fields[0].expected_value == "Synthetic Person"
    assert len(package.entities) == 2


@pytest.mark.parametrize(
    ("document", "mutation", "message"),
    [
        ("baseline", lambda raw: raw.update({"unexpected": True}), "unknown field"),
        ("baseline", lambda raw: raw.pop("entities"), "missing field"),
        (
            "baseline",
            lambda raw: raw.update({"schema_version": "wrong"}),
            "unsupported baseline",
        ),
        (
            "export",
            lambda raw: raw.update({"schema_version": "wrong"}),
            "unsupported export",
        ),
        (
            "baseline",
            lambda raw: raw["coverage"].update({"entities": "optimistic"}),
            "coverage value",
        ),
        (
            "export",
            lambda raw: raw["entities"][0]["fields"].update({"nested": {}}),
            "JSON scalar",
        ),
        (
            "baseline",
            lambda raw: raw["entities"][0]["required_fields"][0].update({"type": "object"}),
            "unsupported",
        ),
        (
            "baseline",
            lambda raw: raw["entities"][0]["required_fields"][0].update({"expected_value": 42}),
            "does not match",
        ),
        (
            "baseline",
            lambda raw: raw["entities"][0]["required_fields"][0].pop("expected_value"),
            "missing field",
        ),
        (
            "baseline",
            lambda raw: raw["entities"][0]["required_fields"][0].update({"comparison": "casefold"}),
            "unknown field",
        ),
        (
            "export",
            lambda raw: raw["attachments"][0].update({"content_sha256": "bad"}),
            "SHA-256",
        ),
    ],
)
def test_rejects_invalid_documents(
    copied_example: Path,
    document: str,
    mutation: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    path = copied_example / f"{document}.json"
    raw = _json(path)
    mutation(raw)
    _write(path, raw)
    loader = load_baseline if document == "baseline" else load_export
    with pytest.raises(PackageError, match=message):
        loader(path)


def test_rejects_duplicate_keys(copied_example: Path) -> None:
    path = copied_example / "export.json"
    raw = _json(path)
    entities = raw["entities"]
    assert isinstance(entities, list)
    entities.append(entities[0])
    _write(path, raw)
    with pytest.raises(PackageError, match="unique"):
        load_export(path)


@pytest.mark.parametrize(
    ("entity_index", "field_index", "expected_value"),
    [
        (0, 0, " "),
        (0, 1, 1),
        (1, 1, True),
        (1, 1, None),
        (1, 1, {"nested": "value"}),
    ],
)
def test_rejects_expected_values_outside_declared_scalar_type(
    copied_example: Path,
    entity_index: int,
    field_index: int,
    expected_value: object,
) -> None:
    path = copied_example / "baseline.json"
    raw = _json(path)
    raw["entities"][entity_index]["required_fields"][field_index][  # type: ignore[index]
        "expected_value"
    ] = expected_value
    _write(path, raw)

    with pytest.raises(PackageError, match="expected_value does not match"):
        load_baseline(path)


@pytest.mark.parametrize(
    ("document", "collection"), [("baseline", "attachments"), ("export", "audit_events")]
)
def test_rejects_duplicate_primary_identity_with_changed_semantics(
    copied_example: Path,
    document: str,
    collection: str,
) -> None:
    path = copied_example / f"{document}.json"
    raw = _json(path)
    items = raw[collection]
    assert isinstance(items, list)
    duplicate = dict(items[0])
    if collection == "attachments":
        duplicate["owner_type"] = "person"
        duplicate["owner_id"] = "person-001"
    else:
        duplicate["action"] = "different_synthetic_action"
    items.append(duplicate)
    _write(path, raw)
    loader = load_baseline if document == "baseline" else load_export
    with pytest.raises(PackageError, match="keys must be unique"):
        loader(path)


@pytest.mark.parametrize("document", ["baseline", "export"])
def test_rejects_duplicate_json_object_keys(copied_example: Path, document: str) -> None:
    path = copied_example / f"{document}.json"
    content = path.read_text(encoding="utf-8")
    duplicate = '"drill_id": "synthetic-crm-exit-001",\n  "drill_id": "synthetic-crm-exit-001",'
    path.write_text(
        content.replace('"drill_id": "synthetic-crm-exit-001",', duplicate, 1),
        encoding="utf-8",
    )
    loader = load_baseline if document == "baseline" else load_export
    with pytest.raises(PackageError, match="duplicate object key"):
        loader(path)


@pytest.mark.parametrize("document", ["baseline", "export"])
@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_rejects_non_finite_json_numbers(
    copied_example: Path,
    document: str,
    token: str,
) -> None:
    path = copied_example / f"{document}.json"
    content = path.read_text(encoding="utf-8")
    path.write_text(
        content.replace(
            '"source_system": "Invented CommunityCase CRM"', f'"source_system": {token}'
        ),
        encoding="utf-8",
    )
    loader = load_baseline if document == "baseline" else load_export
    with pytest.raises(PackageError, match="non-finite"):
        loader(path)


def test_rejects_float_overflow_to_infinity(copied_example: Path) -> None:
    path = copied_example / "export.json"
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace('"priority": 2', '"priority": 1e400'), encoding="utf-8")
    with pytest.raises(PackageError, match="non-finite"):
        load_export(path)


@pytest.mark.parametrize("timestamp", ["not-a-time", "2026-07-22T18:00:00"])
def test_rejects_invalid_or_naive_timestamp(copied_example: Path, timestamp: str) -> None:
    path = copied_example / "baseline.json"
    raw = _json(path)
    raw["captured_at"] = timestamp
    _write(path, raw)
    with pytest.raises(PackageError, match=r"timestamp|UTC offset"):
        load_baseline(path)


def test_rejects_excessive_json_nesting(copied_example: Path) -> None:
    path = copied_example / "export.json"
    raw = _json(path)
    nested: object = "leaf"
    for _index in range(65):
        nested = [nested]
    raw["entities"][0]["fields"]["deep"] = nested  # type: ignore[index]
    _write(path, raw)
    with pytest.raises(PackageError, match="depth limit"):
        load_export(path)


def test_rejects_excessive_dict_nesting(copied_example: Path) -> None:
    """The dict arm of the depth limit, which the list test above never reaches.

    `validate_json_value` checks depth separately for dicts and for lists.
    `test_rejects_excessive_json_nesting` builds a list chain, so it only ever
    exercises the list arm; deleting the dict one left every test green.
    """
    path = copied_example / "export.json"
    raw = _json(path)
    nested: object = "leaf"
    for _index in range(65):
        nested = {"x": nested}
    raw["entities"][0]["fields"]["deep"] = nested  # type: ignore[index]
    _write(path, raw)
    with pytest.raises(PackageError, match="depth limit"):
        load_export(path)


def test_rejects_a_document_that_is_not_valid_utf8(tmp_path: Path) -> None:
    """Bytes that never become text at all, before any JSON shape is considered.

    The neighbouring malformed-JSON cases are both valid UTF-8, so they take the
    JSONDecodeError path. A lone 0xff byte is the one input that reaches the
    UnicodeDecodeError branch, which is the first thing standing between a raw
    file and every command that loads one.
    """
    path = tmp_path / "not-utf8.json"
    path.write_bytes(b"\xff")
    with pytest.raises(PackageError, match="UTF-8"):
        load_export(path)


def test_rejects_nesting_the_json_parser_itself_cannot_walk(tmp_path: Path) -> None:
    """Nesting deep enough to exhaust the parser before any bound is consulted.

    `validate_json_value` runs after `json.loads` returns, so a document nested
    far past CPython's recursion limit never reaches the depth check at all. The
    RecursionError arm is what stops that raw interpreter error from escaping
    the trust boundary as itself. Found while closing issue #57; it was the last
    uncovered branch left in the module.
    """
    path = tmp_path / "unparseable.json"
    path.write_text("[" * 20000 + "]" * 20000, encoding="utf-8")
    with pytest.raises(PackageError, match="parser limit"):
        load_export(path)


@pytest.mark.parametrize(("content", "message"), [("[]", "JSON object"), ("{", "valid JSON")])
def test_rejects_non_object_or_malformed_json(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(PackageError, match=message):
        load_export(path)


def test_rejects_oversized_document(tmp_path: Path) -> None:
    path = tmp_path / "large.json"
    path.write_bytes(b" " * (4 * 1024 * 1024 + 1))
    with pytest.raises(PackageError, match="4 MiB"):
        load_export(path)
