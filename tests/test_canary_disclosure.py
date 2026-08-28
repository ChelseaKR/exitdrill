"""Gate: the two real-process canaries must not republish a record-level value.

`AGENTS.md` invariant 7 says receipts carry aggregates and hashes, never record
fields or attachment contents. ADR 0021 enforced that on the flagship
`examples/synthetic-crm` path in `tests/test_disclosure.py`, and deliberately
left one thing alone: the Directus and CiviCRM canaries keep hand-written
`_RAW_SENTINELS` tuples in `scripts/check_directus_canary_demo.py` and
`scripts/check_civicrm_target_roundtrip_demo.py`. Those tuples have the same
latent defect the synthetic-crm literals had. Nothing binds them to the
fixtures, so renaming a fixture value leaves the canary scanning for a string
that exists nowhere, passing without checking anything. ADR 0022 closes that.

This module does for both canaries what ADR 0021 did for the demo path, and
adds the binding the canaries were missing:

1. `record_values` derives each canary's corpus from its committed native
   capture bundle through a declared field table, mapping value to provenance.
2. `test_*_corpus_is_real_and_non_vacuous` proves every derived value occurs
   verbatim in the bundle bytes, so a fixture rename fails loudly.
3. `test_every_native_bundle_file_is_classified` proves the field table saw
   every file in the bundle, so a new capture file cannot be skipped in silence.
4. `indistinguishable_values` computes, rather than hardcodes, the values a
   substring scan cannot rule on, from a control built out of two derived
   parts: the schemas' declared vocabulary and the aggregates' own digests and
   counts.
5. `test_*_aggregates_disclose_no_record_value` is the gate.
6. `test_script_sentinels_are_bound_to_the_fixtures` proves every hand-written
   sentinel in both canary scripts is still a real fixture value, which is the
   anti-vacuity guard those tuples never had.
7. The final section proves the gate fires: injected record values must be
   reported in every artifact kind, and the corpus and sentinel checks must
   reject the drift they exist to catch.

Boundaries, all stated rather than discovered later:

- Whole values only, in literal and HTML-escaped form. A leaked fragment of a
  value is not caught. ADR 0021 recorded that boundary and it is unchanged.
- The normalized `export.json` and its attachment files are excluded from the
  scan on purpose. They are the evaluator's input contract and record data is
  what they are for. `test_the_excluded_normalized_export_is_where_record_data_lives`
  proves that exclusion is about the right file rather than an empty carve-out.
- `search_forms` and `_found_in` restate two helpers from
  `tests/test_disclosure.py`. Pytest's `--import-mode=importlib` puts no shared
  `tests/` helper module on the import path, and adding one would need both a
  `pythonpath` entry and an `mypy_path` entry to stay type-checked. ADR 0022
  records that trade.
"""

from __future__ import annotations

import html
import json
import re
import tempfile
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path
from typing import cast

import pytest

from exitdrill.canonical import canonical_json_bytes, sha256_bytes
from exitdrill.civicrm_target_canary import (
    normalize_civicrm_target_canary,
    verify_civicrm_evidence_index,
)
from exitdrill.comparison import compare_snapshots, snapshot_receipt
from exitdrill.directus_canary import normalize_directus_canary
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import JsonValue
from exitdrill.report import render_receipt_report

# Callback that records one record value and where it came from.
Note = Callable[[str, str], None]

PROJECT = Path(__file__).parents[1]
SCHEMAS = PROJECT / "schemas"
DIRECTUS = PROJECT / "examples" / "directus-11.17.4-civic-case"
CIVICRM = PROJECT / "examples" / "civicrm-6.16.2-target-roundtrip"
DIRECTUS_NATIVE = DIRECTUS / "native"
CIVICRM_NATIVE = CIVICRM / "native"

# Both canaries evaluate against the one committed Directus baseline, exactly as
# `scripts/check_civicrm_target_roundtrip_demo.py` does.
BASELINE = DIRECTUS / "baseline.json"

_CLAIMED_AT = "2026-08-02T02:40:00Z"
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")

# ---------------------------------------------------------------------------
# Which fields of each captured file carry record data.
#
# Declared as tables so the answer is reviewable in one place, and so a capture
# file that gains a field is an obvious omission rather than a line buried in a
# long function. Every file in each bundle appears in exactly one of the two
# tables below; `test_every_native_bundle_file_is_classified` proves it.
# ---------------------------------------------------------------------------

_DIRECTUS_RECORD_FIELDS: dict[str, tuple[str, ...]] = {
    "activity.json": ("action", "collection", "item", "timestamp"),
    "case-people.json": ("relation_type",),
    "cases.json": ("document", "status"),
    "files.json": ("filename_download", "id", "type"),
    "people.json": ("display_name",),
    "permissions.json": ("action", "collection", "policy"),
    "policies.json": ("id", "name"),
}
_DIRECTUS_NON_RECORD: dict[str, str] = {
    "capture-manifest.json": "aggregate capture assertions, byte lengths, and digests",
    "schema.json": "Directus collection and field definitions, not row data",
}

_CIVICRM_RECORD_FIELDS: dict[str, tuple[str, ...]] = {
    "cases.json": (
        "case_type_id:name",
        "exitdrill_case_profile.source_document_id",
        "exitdrill_case_profile.source_id",
        "exitdrill_case_profile.source_status",
        "start_date",
        "status_id:name",
        "subject",
    ),
    "contacts.json": (
        "display_name",
        "exitdrill_person_profile.source_display_name",
        "exitdrill_person_profile.source_id",
    ),
    "entity-files.json": ("entity_table",),
    "files.json": ("description", "file_name", "mime_type"),
    "permission-allow.json": ("display_name",),
    "permission-deny.json": ("display_name",),
    "relationships.json": ("description", "relationship_type_id.name_a_b"),
}
_CIVICRM_NON_RECORD: dict[str, str] = {
    "browser-access-allow-control.json": "browser observation projection, already record-free",
    "browser-access-denial.json": "browser observation projection, already record-free",
    "browser-accessibility.json": "axe-core rule aggregates, already record-free",
    "browser-activity-view.json": "browser observation projection, already record-free",
    "browser-case-client-workflow.json": "browser observation projection, already record-free",
    "browser-case-search-workflow.json": "browser observation projection, already record-free",
    "browser-contact-summary-workflow.json": "browser observation projection, already record-free",
    "browser-keyboard.json": "keyboard observation projection, already record-free",
    "browser-workflow.json": "browser observation projection, already record-free",
    "capture-manifest.json": "aggregate capture assertions, byte lengths, and digests",
    "identity-allow.json": "sandbox identity assertion; secret-shaped keys are gated separately",
    "identity-deny.json": "sandbox identity assertion; secret-shaped keys are gated separately",
    "identity-reader.json": "sandbox identity assertion; secret-shaped keys are gated separately",
    "identity-writer.json": "sandbox identity assertion; secret-shaped keys are gated separately",
    # Read below through `_collect_observed_labels` rather than the field table,
    # because its record data is a bare array of rendered page labels.
    "ui-contact-summary.json": "read separately: observed_labels carries the rendered name",
}

# The artifacts each canary puts in front of a reader. Pinned so that a canary
# which starts emitting a new aggregate document is a review point rather than
# an untested one.
_DIRECTUS_ARTIFACTS = frozenset(
    {
        "normalization-aggregate",
        "normalization-manifest",
        "receipt",
        "report",
        "comparison",
    }
)
_CIVICRM_ARTIFACTS = frozenset(
    {
        "normalization-aggregate",
        "structural-payload",
        "evidence-index-verification",
        "accessibility-result.json",
        "activity-view-result.json",
        "browser-access-allow-control-result.json",
        "browser-access-denial-result.json",
        "browser-workflow-result.json",
        "case-client-workflow-result.json",
        "case-search-workflow-result.json",
        "contact-summary-workflow-result.json",
        "evidence-index.json",
        "keyboard-result.json",
        "target-result.json",
        "ui-surface-result.json",
    }
)

# Record values that a substring scan cannot attribute to the fixtures.
# Computed by `indistinguishable_values`, pinned here so a change is reviewed
# rather than absorbed, and proved to be one or the other by
# `test_every_excluded_value_is_provably_undecidable`.
EXPECTED_DIRECTUS_INDISTINGUISHABLE = frozenset(
    {
        # activity item, a stringified row id; occurs inside every digest
        "1",
        "2",
        # activity and permission actions; declared schema vocabulary
        "create",
        "read",
        # case status; declared schema vocabulary
        "open",
    }
)
EXPECTED_CIVICRM_INDISTINGUISHABLE = frozenset(
    {
        # source row ids carried as strings; occur inside every digest
        "1",
        "2",
        "3",
        # source case status; declared schema vocabulary
        "open",
    }
)


def _json_object(path: Path) -> dict[str, JsonValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), f"{path.name} must contain a JSON object"
    return cast(dict[str, JsonValue], value)


def _strings(value: object) -> list[str]:
    """Return `value` as a one-item list when it is a string, else nothing.

    A non-string field value (`active: 1`, `is_public: false`) has no substring
    to search for and is skipped rather than stringified into a false needle.
    This matches `tests/test_disclosure.py`, which made the same call.
    """
    return [value] if isinstance(value, str) else []


def _attachment_files(root: Path) -> list[Path]:
    return sorted(item for item in root.rglob("*") if item.is_file())


def _collect_rows(
    native: Path,
    fields: dict[str, tuple[str, ...]],
    rows_key: str,
    note: Note,
) -> None:
    for filename, names in fields.items():
        document = _json_object(native / filename)
        for row in cast(list[dict[str, JsonValue]], document[rows_key]):
            for name in names:
                for text in _strings(row.get(name)):
                    note(text, f"{filename}.{rows_key}[].{name}")


def _collect_observed_labels(native: Path, note: Note) -> None:
    """Collect the page labels the CiviCRM UI capture recorded verbatim.

    `ui-contact-summary.json` is the one native file whose record data is a bare
    array rather than a row field, and it is the input the verifier turns into
    `ui-surface-result.json`, so leaving it out would leave that artifact ungated.
    """
    document = _json_object(native / "ui-contact-summary.json")
    for label in cast(list[JsonValue], document["observed_labels"]):
        for text in _strings(label):
            note(text, "ui-contact-summary.json.observed_labels[]")


def _collect_attachments(native: Path, note: Note) -> None:
    for path in _attachment_files(native / "assets"):
        note(path.read_text(encoding="utf-8").strip(), "attachment file contents")


def directus_record_values() -> dict[str, str]:
    """Return every record-level value in the Directus capture, with provenance."""
    found: dict[str, str] = {}

    def note(value: str, provenance: str) -> None:
        found.setdefault(value, provenance)

    _collect_rows(DIRECTUS_NATIVE, _DIRECTUS_RECORD_FIELDS, "data", note)
    _collect_attachments(DIRECTUS_NATIVE, note)
    return found


def civicrm_record_values() -> dict[str, str]:
    """Return every record-level value in the CiviCRM capture, with provenance."""
    found: dict[str, str] = {}

    def note(value: str, provenance: str) -> None:
        found.setdefault(value, provenance)

    _collect_rows(CIVICRM_NATIVE, _CIVICRM_RECORD_FIELDS, "values", note)
    _collect_observed_labels(CIVICRM_NATIVE, note)
    _collect_attachments(CIVICRM_NATIVE, note)
    return found


def input_text(native: Path) -> str:
    """Return every byte of one native capture bundle, as one document."""
    return "\n".join(path.read_text(encoding="utf-8") for path in _attachment_files(native))


def search_forms(value: str) -> frozenset[str]:
    """Return every form one record value can take in an aggregate output.

    `report.py` escapes payload text before rendering it, so searching only for
    the literal would let escaping act as an accidental bypass: the more
    dangerous the value, the less likely the gate would see it.
    """
    return frozenset({value, html.escape(value, quote=True)})


def _found_in(value: str, text: str) -> bool:
    return any(form in text for form in search_forms(value))


def disclosures(
    values: dict[str, str],
    artifacts: dict[str, str],
    excluded: frozenset[str],
) -> list[str]:
    """Return one description per record value found in an aggregate artifact."""
    return sorted(
        f"{name} discloses {value!r} (from {provenance})"
        for value, provenance in values.items()
        if value not in excluded
        for name, text in artifacts.items()
        if _found_in(value, text)
    )


# ---------------------------------------------------------------------------
# The control: what an aggregate artifact may contain with no record data.
# ---------------------------------------------------------------------------


def _walk_schema(node: JsonValue, out: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "description":
                continue
            if key in {"properties", "patternProperties", "$defs"} and isinstance(value, dict):
                out.update(value)
            if key in {"const", "title", "$id", "format", "pattern"} and isinstance(value, str):
                out.add(value)
            if key in {"enum", "required"} and isinstance(value, list):
                out.update(item for item in value if isinstance(item, str))
            _walk_schema(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk_schema(item, out)


@lru_cache(maxsize=1)
def declared_vocabulary() -> str:
    """Return the strings the packaged schemas declare these documents may contain.

    Property names, `const` values, `enum` members, `required` entries, titles,
    ids, formats, and patterns: everything a conforming document can carry
    without any record data being present. Prose `description` text is left out,
    so an unrelated English word in a schema comment cannot widen the carve-out.
    """
    vocabulary: set[str] = set()
    for schema in sorted(SCHEMAS.glob("*.schema.json")):
        _walk_schema(cast(JsonValue, json.loads(schema.read_text(encoding="utf-8"))), vocabulary)
    return "\n".join(sorted(vocabulary))


def _walk_scalars(node: JsonValue, out: set[str]) -> None:
    if isinstance(node, dict):
        for value in node.values():
            _walk_scalars(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk_scalars(item, out)
    elif isinstance(node, bool) or node is None:
        return
    elif isinstance(node, int | float):
        out.add(str(node))
    elif _DIGEST.match(node):
        out.add(node)


def computed_scalars(documents: Iterable[JsonValue]) -> str:
    """Return every count and SHA-256 digest the aggregate documents carry.

    A digest is a function of bytes, not a republication of them, and a count is
    a number. Neither can be a deliberate leak of a record string, but both are
    full of decimal digits, so a record value that is itself a bare integer is
    undecidable by substring search. Deriving this from the artifacts rather
    than writing down which values are short keeps the reason explicit.
    """
    scalars: set[str] = set()
    for document in documents:
        _walk_scalars(document, scalars)
    return "\n".join(sorted(scalars))


def control_text(documents: Iterable[JsonValue]) -> str:
    return declared_vocabulary() + "\n" + computed_scalars(documents)


def indistinguishable_values(values: dict[str, str], control: str) -> frozenset[str]:
    """Return the record values a substring scan cannot rule on."""
    return frozenset(value for value in values if _found_in(value, control))


# ---------------------------------------------------------------------------
# Producing the artifacts. Both canaries run in process; nothing here needs
# Docker, a network, or a browser.
# ---------------------------------------------------------------------------


def _receipt(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "envelope": {
            "claimed_generated_at": _CLAIMED_AT,
            "signature_status": "not_signed",
            "trusted_time": False,
        },
        "payload": payload,
        "payload_sha256": sha256_bytes(canonical_json_bytes(payload)),
        "schema_version": "exitdrill/receipt/v0.3",
    }


def _structural_payload(normalized: Path) -> dict[str, JsonValue]:
    result = run_drill(
        load_baseline(BASELINE),
        load_export(normalized / "export.json"),
        normalized / "export-files",
    )
    return result.payload()


@lru_cache(maxsize=1)
def directus_artifacts() -> dict[str, str]:
    """Render every aggregate artifact the Directus canary path produces.

    `export.json` and `export-files/` are excluded deliberately: they are the
    evaluator's record-level input contract, not aggregate output. The comparison
    document is built from the clean receipt against itself, which is the
    cheapest comparable pair and exercises the same rendering.
    """
    with tempfile.TemporaryDirectory(prefix="exitdrill-directus-disclosure-") as raw:
        out = Path(raw) / "normalized"
        aggregate = normalize_directus_canary(DIRECTUS_NATIVE / "capture-manifest.json", out)
        receipt = _receipt(_structural_payload(out))
        comparison = compare_snapshots(snapshot_receipt(receipt), snapshot_receipt(receipt))
        return {
            "normalization-aggregate": canonical_json_bytes(cast(JsonValue, aggregate)).decode(
                "utf-8"
            ),
            "normalization-manifest": (out / "normalization-manifest.json").read_text(
                encoding="utf-8"
            ),
            "receipt": canonical_json_bytes(cast(JsonValue, receipt)).decode("utf-8"),
            "report": render_receipt_report(json.loads(json.dumps(receipt))),
            "comparison": canonical_json_bytes(cast(JsonValue, comparison)).decode("utf-8"),
        }


@lru_cache(maxsize=1)
def civicrm_artifacts() -> dict[str, str]:
    """Render every aggregate artifact the CiviCRM target canary produces.

    That is the twelve documents the normalizer writes beside the normalized
    export, the aggregate it returns, the evidence-index verification document,
    and the structural payload the unchanged evaluator produces from the
    normalized target export.
    """
    with tempfile.TemporaryDirectory(prefix="exitdrill-civicrm-disclosure-") as raw:
        out = Path(raw) / "normalized"
        aggregate = normalize_civicrm_target_canary(CIVICRM_NATIVE / "capture-manifest.json", out)
        verification = verify_civicrm_evidence_index(out / "evidence-index.json")
        artifacts = {
            "normalization-aggregate": canonical_json_bytes(cast(JsonValue, aggregate)).decode(
                "utf-8"
            ),
            "evidence-index-verification": canonical_json_bytes(
                cast(JsonValue, verification)
            ).decode("utf-8"),
            "structural-payload": canonical_json_bytes(
                cast(JsonValue, _structural_payload(out))
            ).decode("utf-8"),
        }
        for path in sorted(out.glob("*.json")):
            if path.name != "export.json":
                artifacts[path.name] = path.read_text(encoding="utf-8")
        return artifacts


def _json_documents(artifacts: dict[str, str]) -> list[JsonValue]:
    documents: list[JsonValue] = []
    for name, text in artifacts.items():
        if name != "report":
            documents.append(cast(JsonValue, json.loads(text)))
    return documents


def _directus_excluded() -> frozenset[str]:
    return indistinguishable_values(
        directus_record_values(), control_text(_json_documents(directus_artifacts()))
    )


def _civicrm_excluded() -> frozenset[str]:
    return indistinguishable_values(
        civicrm_record_values(), control_text(_json_documents(civicrm_artifacts()))
    )


# ---------------------------------------------------------------------------
# 1. The corpus is real, and it saw the whole bundle.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "values", "native"),
    [
        ("directus", directus_record_values, DIRECTUS_NATIVE),
        ("civicrm", civicrm_record_values, CIVICRM_NATIVE),
    ],
)
def test_canary_corpus_is_real_and_non_vacuous(
    name: str, values: Callable[[], dict[str, str]], native: Path
) -> None:
    """Every derived value must occur verbatim in the bytes it was derived from.

    This is the check the hand-written `_RAW_SENTINELS` tuples cannot make. A
    corpus that has drifted away from the capture bundle fails here instead of
    searching output for strings that no longer exist and reporting success.
    """
    corpus = values()
    text = input_text(native)

    assert corpus, name
    for value, provenance in corpus.items():
        assert value, f"{provenance} produced an empty needle"
        assert value in text, f"{value!r} from {provenance} is not in the {name} capture bytes"


@pytest.mark.parametrize(
    ("native", "fields", "non_record"),
    [
        (DIRECTUS_NATIVE, _DIRECTUS_RECORD_FIELDS, _DIRECTUS_NON_RECORD),
        (CIVICRM_NATIVE, _CIVICRM_RECORD_FIELDS, _CIVICRM_NON_RECORD),
    ],
)
def test_every_native_bundle_file_is_classified(
    native: Path, fields: dict[str, tuple[str, ...]], non_record: dict[str, str]
) -> None:
    """A capture file added later must be classified, not silently skipped.

    Without this, a new file full of record values would simply never enter the
    corpus, and the gate would keep reporting a clean result over a smaller
    question than the one it claims to answer.
    """
    captured = {path.name for path in native.glob("*.json")}

    assert captured == set(fields) | set(non_record)
    assert not set(fields) & set(non_record)
    for reason in non_record.values():
        assert reason, "every non-record classification must state its reason"


def test_canary_corpora_cover_the_dimensions_each_capture_carries() -> None:
    """A corpus missing a whole file would gate a fraction of the invariant."""
    directus = set(directus_record_values().values())
    civicrm = set(civicrm_record_values().values())

    for filename in _DIRECTUS_RECORD_FIELDS:
        assert any(item.startswith(filename) for item in directus), filename
    assert "attachment file contents" in directus
    assert "ui-contact-summary.json.observed_labels[]" in civicrm
    assert "attachment file contents" in civicrm
    # Pinned so a corpus that silently shrinks is visible. Raise these
    # deliberately when a capture gains record data; never lower one to pass.
    assert len(directus_record_values()) >= 22
    assert len(civicrm_record_values()) >= 23


def test_the_excluded_normalized_export_is_where_record_data_lives() -> None:
    """The one excluded output must be excluded because it is the input contract.

    Proves the scan target list is drawn in the right place. If the normalized
    export stopped carrying record values, excluding it would be pointless and
    something about the normalizer would have changed unnoticed.
    """
    with tempfile.TemporaryDirectory(prefix="exitdrill-export-check-") as raw:
        out = Path(raw) / "normalized"
        normalize_civicrm_target_canary(CIVICRM_NATIVE / "capture-manifest.json", out)
        export = (out / "export.json").read_text(encoding="utf-8")

    corpus = civicrm_record_values()
    excluded = _civicrm_excluded()
    present = sorted(
        value for value in corpus if value not in excluded and _found_in(value, export)
    )

    assert "export.json" not in civicrm_artifacts()
    assert "Synthetic Person Alpha" in present
    # Pinned so that an export which stopped carrying record data is visible.
    assert len(present) >= 6


# ---------------------------------------------------------------------------
# 2. The exclusion is computed, narrow, and provably about undecidability.
# ---------------------------------------------------------------------------


def test_indistinguishable_values_are_exactly_the_pinned_sets() -> None:
    assert _directus_excluded() == EXPECTED_DIRECTUS_INDISTINGUISHABLE
    assert _civicrm_excluded() == EXPECTED_CIVICRM_INDISTINGUISHABLE


def test_every_excluded_value_is_provably_undecidable() -> None:
    """Each excluded value must be declared schema vocabulary or digit noise.

    This is what makes the carve-out sound rather than convenient. Both control
    halves are derived: the vocabulary from the packaged schemas, the digits
    from the artifacts' own counts and digests. A value in neither would be a
    genuine record value being quietly waved through, and would fail here.
    """
    vocabulary = declared_vocabulary()
    directus_digits = computed_scalars(_json_documents(directus_artifacts()))
    civicrm_digits = computed_scalars(_json_documents(civicrm_artifacts()))

    for value in EXPECTED_DIRECTUS_INDISTINGUISHABLE:
        assert _found_in(value, vocabulary) or _found_in(value, directus_digits), value
    for value in EXPECTED_CIVICRM_INDISTINGUISHABLE:
        assert _found_in(value, vocabulary) or _found_in(value, civicrm_digits), value


def test_the_exclusion_rule_does_not_swallow_a_genuine_record_value() -> None:
    """Values that carry real identity stay inside the gate.

    Proves the exclusion is a narrow carve-out and not a blanket. `Cases` and
    `Open` are included deliberately: both are ordinary English words that the
    format could plausibly have contained, and neither is excluded, so the rule
    is about what the control actually holds rather than about word shape.
    """
    excluded = _directus_excluded() | _civicrm_excluded()

    for value in (
        "Synthetic Person Alpha",
        "Synthetic Person Bravo",
        "Synthetic Person Canary",
        "Synthetic Case Worker",
        "Synthetic ExitDrill Case Alpha",
        "Synthetic ExitDrill Case Bravo",
        "Invented intake note alpha.",
        "Invented intake note bravo.",
        "Case Coordinator is",
        "ExitDrill assigned_to",
        "Cases",
        "Open",
        "assigned_to",
        "civicrm_case",
        "exitdrill_cases",
        "exitdrill_civic_case",
        "exitdrill_people",
        "synthetic-intake-a.txt",
        "text/plain",
        "11111111-1111-4111-8111-111111111111",
        "11111111_1111_4111_8111_111111111111.txt",
        "33333333-3333-4333-8333-333333333333",
    ):
        assert value not in excluded, value


def test_the_control_is_not_degenerate() -> None:
    """A control that swallowed the corpus would exclude everything, silently."""
    directus = directus_record_values()
    civicrm = civicrm_record_values()

    assert declared_vocabulary()
    assert computed_scalars(_json_documents(directus_artifacts()))
    assert computed_scalars(_json_documents(civicrm_artifacts()))
    assert len(_directus_excluded()) < len(directus)
    assert len(_civicrm_excluded()) < len(civicrm)
    # A control built from nothing must exclude nothing, or the rule is inverted.
    assert indistinguishable_values(directus, "") == frozenset()
    assert indistinguishable_values(civicrm, "") == frozenset()


# ---------------------------------------------------------------------------
# 3. The gate.
# ---------------------------------------------------------------------------


def test_directus_aggregates_disclose_no_record_value() -> None:
    artifacts = directus_artifacts()

    assert set(artifacts) == _DIRECTUS_ARTIFACTS
    assert disclosures(directus_record_values(), artifacts, _directus_excluded()) == []


def test_civicrm_aggregates_disclose_no_record_value() -> None:
    artifacts = civicrm_artifacts()

    assert set(artifacts) == _CIVICRM_ARTIFACTS
    assert disclosures(civicrm_record_values(), artifacts, _civicrm_excluded()) == []


def test_script_sentinels_are_bound_to_the_fixtures() -> None:
    """Every hand-written canary sentinel must still be a real fixture value.

    This is the guard ADR 0021 recorded as missing. The tuples in
    `scripts/check_directus_canary_demo.py` and
    `scripts/check_civicrm_target_roundtrip_demo.py` are searched for in
    aggregate output; nothing there notices when one stops matching anything.
    Requiring each to be in a corpus that was itself proved against the capture
    bytes makes a fixture rename break the tuple loudly.
    """
    directus = directus_record_values()
    civicrm = civicrm_record_values()
    combined = {**directus, **civicrm}

    for sentinel in _script_sentinels("check_directus_canary_demo"):
        assert sentinel in directus, sentinel
    for sentinel in _script_sentinels("check_civicrm_target_roundtrip_demo"):
        assert sentinel in combined, sentinel


def _script_sentinels(name: str) -> tuple[str, ...]:
    """Read one canary script's `_RAW_SENTINELS` without importing the script.

    The scripts run subprocesses and normalizers at import time is not a risk
    here, but parsing keeps this gate independent of anything a script does on
    import, and fails loudly if the tuple is renamed or removed.
    """
    source = (PROJECT / "scripts" / f"{name}.py").read_text(encoding="utf-8")
    match = re.search(r"^_RAW_SENTINELS = \(\n(.*?)^\)$", source, re.MULTILINE | re.DOTALL)
    assert match is not None, f"{name}.py no longer declares a _RAW_SENTINELS tuple"
    sentinels = tuple(json.loads(line.strip().rstrip(",")) for line in match.group(1).splitlines())
    assert sentinels, f"{name}.py declares an empty _RAW_SENTINELS tuple"
    return sentinels


# ---------------------------------------------------------------------------
# 4. The gate fires. A drill that cannot fail is not a drill.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("artifact", sorted(_DIRECTUS_ARTIFACTS))
def test_gate_reports_a_directus_record_value_in_every_artifact(artifact: str) -> None:
    """A leak into any one Directus artifact must be reported, naming that artifact."""
    value = "Synthetic Person Alpha"
    leaked = dict(directus_artifacts())
    leaked[artifact] = leaked[artifact] + value

    assert disclosures({value: "people.json"}, leaked, frozenset()) == [
        f"{artifact} discloses {value!r} (from people.json)"
    ]


@pytest.mark.parametrize("artifact", sorted(_CIVICRM_ARTIFACTS))
def test_gate_reports_a_civicrm_record_value_in_every_artifact(artifact: str) -> None:
    """A leak into any one CiviCRM artifact must be reported, naming that artifact."""
    value = "Synthetic ExitDrill Case Alpha"
    leaked = dict(civicrm_artifacts())
    leaked[artifact] = leaked[artifact] + value

    assert disclosures({value: "cases.json"}, leaked, frozenset()) == [
        f"{artifact} discloses {value!r} (from cases.json)"
    ]


def test_gate_reports_every_checkable_corpus_value_when_it_is_leaked() -> None:
    """Not one representative value: every value the gate claims to check.

    A gate that only fires for the value someone thought to test is the defect
    this module exists to remove, one level up.
    """
    for corpus, artifacts, excluded in (
        (directus_record_values(), directus_artifacts(), _directus_excluded()),
        (civicrm_record_values(), civicrm_artifacts(), _civicrm_excluded()),
    ):
        checkable = {value: prov for value, prov in corpus.items() if value not in excluded}
        assert checkable
        for value, provenance in checkable.items():
            leaked = {"normalization-aggregate": artifacts["normalization-aggregate"] + value}
            assert disclosures({value: provenance}, leaked, excluded) == [
                f"normalization-aggregate discloses {value!r} (from {provenance})"
            ]


def test_gate_reports_an_html_escaped_record_value() -> None:
    """Escaping must not become a bypass for exactly the dangerous characters."""
    value = "Synthetic & Partners <Alpha>"
    leaked = {"report": directus_artifacts()["report"] + html.escape(value, quote=True)}

    assert value not in leaked["report"]
    assert disclosures({value: "test"}, leaked, frozenset()) == [
        f"report discloses {value!r} (from test)"
    ]


def test_gate_does_not_manufacture_a_finding() -> None:
    """A value in neither the captures nor the artifacts must not be reported."""
    assert (
        disclosures({"invented-absent-value-001": "test"}, directus_artifacts(), frozenset()) == []
    )
    assert (
        disclosures({"invented-absent-value-001": "test"}, civicrm_artifacts(), frozenset()) == []
    )


@pytest.mark.parametrize("native", [DIRECTUS_NATIVE, CIVICRM_NATIVE])
def test_corpus_reality_check_rejects_a_needle_absent_from_the_capture(native: Path) -> None:
    """The anti-vacuity precondition must itself be able to fire.

    Stand-in for the failure the `_RAW_SENTINELS` tuples cannot detect: a needle
    nobody notices has stopped matching anything.
    """
    assert "Synthetic Person Delta-renamed-and-never-updated" not in input_text(native)


def test_sentinel_binding_rejects_a_sentinel_that_left_the_fixtures() -> None:
    """The binding check must fire for a stale sentinel, not just pass today.

    Runs the same membership rule `test_script_sentinels_are_bound_to_the_fixtures`
    uses against a tuple containing one value that is no longer in either capture.
    """
    combined = {**directus_record_values(), **civicrm_record_values()}
    stale = ("Synthetic Person Alpha", "Synthetic Person Delta")

    assert [sentinel for sentinel in stale if sentinel not in combined] == [
        "Synthetic Person Delta"
    ]


def test_sentinel_parser_reads_both_committed_tuples() -> None:
    """The parser must return real sentinels, or the binding check is vacuous too."""
    directus = _script_sentinels("check_directus_canary_demo")
    civicrm = _script_sentinels("check_civicrm_target_roundtrip_demo")

    assert len(directus) >= 5
    assert len(civicrm) >= 7
    assert "Synthetic Person Alpha" in directus
    assert "11111111-1111-4111-8111-111111111111" in civicrm
