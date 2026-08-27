"""Gate: aggregate outputs must never republish a record-level value.

`AGENTS.md` invariant 7 says receipts carry aggregates and hashes, never record
fields or attachment contents. The README repeats it under "Receipts and
trust", and ADR 0003 leans on it: comparison deferred record-identity matching
precisely "because receipts intentionally contain no record-level identifiers".

Both real-process canaries already check this for themselves --
`scripts/check_directus_canary_demo.py` and
`scripts/check_civicrm_target_roundtrip_demo.py` each scan their aggregate
output for a hand-written `_RAW_SENTINELS` tuple. The flagship
`examples/synthetic-crm` path, which the README leads with and which the
usability gate in issue #51 asks outside testers to open in a browser, had no
equivalent. The closest thing was three literals inside
`tests/test_report.py::test_renders_deterministic_aggregate_only_accessible_report`
("Synthetic Person", "person-001", one timestamp), asserted absent from the
rendered report only.

A hand-written needle list is a check that can quietly stop checking. Nothing
ties those literals to the fixtures, so renaming a fixture value leaves the
assertions green while they search for a string that no longer exists anywhere.
This module derives its corpus from the committed fixtures instead, and refuses
to trust a corpus it cannot first prove is real:

1. `record_values` reads the fixture files and returns value -> provenance.
2. `test_record_value_corpus_is_real_and_non_vacuous` asserts every derived
   value literally occurs in the input bytes, so a fixture rename breaks the
   gate loudly rather than emptying it silently.
3. `indistinguishable_values` computes, rather than hardcodes, which values a
   substring scan cannot rule on, by rendering a control whose free text is
   placeholders and treating whatever survives as format vocabulary.
4. `test_aggregate_outputs_disclose_no_record_value` is the gate itself.
5. The final section injects real record values into each output kind and
   proves the gate reports them.

Boundary: this compares whole record values in their literal and HTML-escaped
forms. It does not tokenize, so it would not catch a leak of a fragment of one
value (say the first half of the attachment text). Whole-value republication is
what the invariant is about, and a token corpus would drag common English words
into the indistinguishable set and weaken the exact pin in step 3.
"""

from __future__ import annotations

import html
import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from exitdrill.canonical import canonical_json_bytes, sha256_bytes
from exitdrill.comparison import compare_snapshots, snapshot_receipt
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import JsonValue
from exitdrill.report import render_receipt_report

# Callback that records one record value and where it came from.
Note = Callable[[str, str], None]

PROJECT = Path(__file__).parents[1]
CLEAN = PROJECT / "examples" / "synthetic-crm"
LOSSY = PROJECT / "examples" / "synthetic-crm-lossy"

# The lossy drill runs the *clean* baseline against the lossy export, exactly as
# the `demo-lossy` Makefile target does, so both fixtures share one baseline.
BASELINE = CLEAN / "baseline.json"

_CLAIMED_TIMES = {"clean": "2026-07-22T20:00:00Z", "lossy": "2026-07-22T20:05:00Z"}
_OUTPUT_NAMES = frozenset(
    {"clean-receipt", "lossy-receipt", "clean-report", "lossy-report", "comparison"}
)

# The two free-text payload fields a receipt carries. Replacing both with
# strings that occur in no fixture turns a real receipt into a control that
# still exercises the whole output template while containing no record data.
_CONTROL_TEXT = {
    "source_system": "CONTROL-SOURCE-SYSTEM-PLACEHOLDER",
    "drill_id": "CONTROL-DRILL-ID-PLACEHOLDER",
}

# Record values that ExitDrill's own output vocabulary already contains, so a
# substring scan cannot attribute them to the fixture data. Computed by
# `indistinguishable_values`, pinned here so any change is reviewed rather than
# absorbed. Each entry is proved to be vocabulary by
# `test_every_excluded_value_is_provably_vocabulary`.
EXPECTED_INDISTINGUISHABLE = frozenset(
    {
        # entity type; collides with the report stylesheet's `uppercase`
        "case",
        # lossy audit action; collides with `exported_count` and the report's
        # "Expected, exported, and restored counts" caption
        "exported",
    }
)


def _json_object(path: Path) -> dict[str, JsonValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), f"{path.name} must contain a JSON object"
    return cast(dict[str, JsonValue], value)


def _strings(value: object) -> list[str]:
    """Return `value` as a one-item list when it is a string, else nothing.

    Record fields are typed by the fixture, so a non-string field value
    (`active: true`, `priority: 2`) has no substring to search for and is
    skipped here rather than stringified into a false needle.
    """
    return [value] if isinstance(value, str) else []


def _attachment_files(attachment_root: Path) -> list[Path]:
    return sorted(item for item in attachment_root.rglob("*") if item.is_file())


# Which fields of each collection count as record data. Declared as a table so
# the answer is reviewable in one place, and so a collection that gains a field
# is an obvious omission rather than a line buried in a long function.
_BASELINE_FIELDS: dict[str, tuple[str, ...]] = {
    "entities": ("id", "type"),
    "relationships": ("type", "from_id", "to_id"),
    "attachments": ("id", "content_sha256"),
    "permissions": ("principal_id", "role"),
    "audit_events": ("event_id", "action", "occurred_at"),
}
_EXPORT_FIELDS: dict[str, tuple[str, ...]] = {
    "entities": ("id", "type"),
    "relationships": ("type", "from_id", "to_id"),
    "attachments": ("id", "relative_path", "content_sha256"),
    "permissions": ("principal_id", "role"),
    "audit_events": ("event_id", "action", "occurred_at"),
}


def _collect_scalars(
    document: dict[str, JsonValue],
    fields: dict[str, tuple[str, ...]],
    label: str,
    note: Note,
) -> None:
    for collection, names in fields.items():
        for item in cast(list[dict[str, JsonValue]], document[collection]):
            for name in names:
                for text in _strings(item[name]):
                    note(text, f"{label}.{collection}[].{name}")


def _collect_declared_values(baseline: dict[str, JsonValue], note: Note) -> None:
    """Collect the field values the baseline declares an entity must still have."""
    for entity in cast(list[dict[str, JsonValue]], baseline["entities"]):
        for field in cast(list[dict[str, JsonValue]], entity["required_fields"]):
            for text in _strings(field["expected_value"]):
                note(text, "baseline.entities[].required_fields[].expected_value")


def _collect_exported_fields(export: dict[str, JsonValue], note: Note) -> None:
    """Collect the field values the export actually carries, keyed by field name."""
    for entity in cast(list[dict[str, JsonValue]], export["entities"]):
        for name, raw in cast(dict[str, JsonValue], entity["fields"]).items():
            for text in _strings(raw):
                note(text, f"export.entities[].fields.{name}")


def record_values(export_path: Path, attachment_root: Path) -> dict[str, str]:
    """Return every record-level value in one fixture pair, mapped to provenance.

    Reads the documents directly rather than through `load_baseline` /
    `load_export`, so a loader change cannot narrow what this gate treats as
    record data.
    """
    baseline = _json_object(BASELINE)
    export = _json_object(export_path)
    found: dict[str, str] = {}

    def note(value: str, provenance: str) -> None:
        found.setdefault(value, provenance)

    _collect_scalars(baseline, _BASELINE_FIELDS, "baseline", note)
    _collect_declared_values(baseline, note)
    _collect_scalars(export, _EXPORT_FIELDS, "export", note)
    _collect_exported_fields(export, note)
    for path in _attachment_files(attachment_root):
        note(path.read_text(encoding="utf-8").strip(), "attachment file contents")
    return found


def input_text(export_path: Path, attachment_root: Path) -> str:
    """Return every input byte the fixture pair is built from, as one document."""
    parts = [BASELINE.read_text(encoding="utf-8"), export_path.read_text(encoding="utf-8")]
    parts.extend(path.read_text(encoding="utf-8") for path in _attachment_files(attachment_root))
    return "\n".join(parts)


def search_forms(value: str) -> frozenset[str]:
    """Return every form one record value can take in an aggregate output.

    `report.py` escapes payload text before rendering it, so a value containing
    `&`, `<`, `>`, or `"` reaches the HTML in encoded form. Searching only for
    the literal would let escaping act as an accidental bypass: the more
    dangerous the value, the less likely the gate would see it.
    """
    return frozenset({value, html.escape(value, quote=True)})


def _receipt(export_path: Path, attachment_root: Path, claimed: str) -> dict[str, JsonValue]:
    result = run_drill(load_baseline(BASELINE), load_export(export_path), attachment_root)
    payload = result.payload()
    return {
        "envelope": {
            "claimed_generated_at": claimed,
            "signature_status": "not_signed",
            "trusted_time": False,
        },
        "payload": payload,
        "payload_sha256": sha256_bytes(canonical_json_bytes(payload)),
        "schema_version": "exitdrill/receipt/v0.3",
    }


def _rehash(receipt: dict[str, JsonValue]) -> None:
    payload = cast(dict[str, JsonValue], receipt["payload"])
    receipt["payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))


def _receipts() -> dict[str, dict[str, JsonValue]]:
    return {
        "clean": _receipt(CLEAN / "export.json", CLEAN / "export-files", _CLAIMED_TIMES["clean"]),
        "lossy": _receipt(LOSSY / "export.json", LOSSY / "export-files", _CLAIMED_TIMES["lossy"]),
    }


def aggregate_outputs(receipts: dict[str, dict[str, JsonValue]]) -> dict[str, str]:
    """Render the aggregate artifacts the synthetic demo puts in front of a reader.

    Given both fixtures these are the five documents `make demo-compare`
    produces: two receipts, two HTML reports, and the comparison document.
    Given one fixture the comparison, which needs two operands, is omitted.
    """
    outputs = {
        f"{name}-receipt": canonical_json_bytes(receipt).decode("utf-8")
        for name, receipt in receipts.items()
    }
    outputs.update(
        {
            f"{name}-report": render_receipt_report(deepcopy(receipt))
            for name, receipt in receipts.items()
        }
    )
    if {"clean", "lossy"} <= set(receipts):
        comparison = compare_snapshots(
            snapshot_receipt(receipts["clean"]),
            snapshot_receipt(receipts["lossy"]),
        )
        outputs["comparison"] = canonical_json_bytes(comparison).decode("utf-8")
    return outputs


def control_outputs() -> dict[str, str]:
    """Render the same five artifacts from receipts that carry no record data.

    Every count, status, digest, JSON key, HTML element, stylesheet rule, and
    fixed caption is still present; only the two free-text payload fields are
    replaced. Whatever text survives in here came from ExitDrill's own output
    format rather than from a fixture, which is what makes it a sound control
    for deciding that a value is vocabulary.

    Both receipts get the same placeholders so they stay comparable and the
    control includes a real comparison document.
    """
    receipts = _receipts()
    for receipt in receipts.values():
        payload = cast(dict[str, JsonValue], receipt["payload"])
        payload.update(cast(dict[str, JsonValue], dict(_CONTROL_TEXT)))
        _rehash(receipt)
    return aggregate_outputs(receipts)


def _found_in(value: str, text: str) -> bool:
    return any(form in text for form in search_forms(value))


def disclosures(
    values: dict[str, str],
    outputs: dict[str, str],
    excluded: frozenset[str],
) -> list[str]:
    """Return one description per record value found in an aggregate output."""
    return sorted(
        f"{output_name} discloses {value!r} (from {provenance})"
        for value, provenance in values.items()
        if value not in excluded
        for output_name, text in outputs.items()
        if _found_in(value, text)
    )


def indistinguishable_values(values: dict[str, str], control: dict[str, str]) -> frozenset[str]:
    """Return the values a substring scan cannot rule on, computed not hardcoded.

    ExitDrill's own aggregate vocabulary is English, snake_case, and CSS, so a
    short record value can collide with it: the entity type `case` occurs inside
    the report stylesheet's `text-transform: uppercase`, and the lossy audit
    action `exported` occurs in `exported_count`. Finding either in real output
    would prove nothing about the fixture data.

    A value already present in `control` -- output rendered with placeholders in
    place of every free-text field -- cannot be attributed to record data, so
    this gate says so instead of reporting a disclosure it cannot substantiate.
    """
    return frozenset(
        value for value in values if any(_found_in(value, text) for text in control.values())
    )


def _fixture_corpora() -> dict[str, dict[str, str]]:
    return {
        "clean": record_values(CLEAN / "export.json", CLEAN / "export-files"),
        "lossy": record_values(LOSSY / "export.json", LOSSY / "export-files"),
    }


def _all_record_values() -> dict[str, str]:
    merged: dict[str, str] = {}
    for values in _fixture_corpora().values():
        for value, provenance in values.items():
            merged.setdefault(value, provenance)
    return merged


# ---------------------------------------------------------------------------
# 1. The corpus is real. A fixture rename must break this gate, not empty it.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["clean", "lossy"])
def test_record_value_corpus_is_real_and_non_vacuous(name: str) -> None:
    """Every derived value must occur verbatim in the bytes it was derived from.

    This is the check the superseded literal lists could not make. A corpus that
    has drifted away from the fixtures fails here, rather than searching output
    for strings that no longer exist and reporting a clean result.
    """
    root = CLEAN if name == "clean" else LOSSY
    values = record_values(root / "export.json", root / "export-files")
    text = input_text(root / "export.json", root / "export-files")

    assert values
    for value, provenance in values.items():
        assert value, f"{provenance} produced an empty needle"
        assert value in text, f"{value!r} from {provenance} is not in the fixture inputs"


def test_record_value_corpus_covers_every_dimension() -> None:
    """A corpus missing a whole dimension would gate four fifths of the invariant."""
    provenances = set(_all_record_values().values())

    for dimension in ("entities", "relationships", "attachments", "permissions", "audit_events"):
        assert any(dimension in item for item in provenances), dimension
    assert "attachment file contents" in provenances
    # Pinned so a corpus that silently shrinks is visible. Raise this
    # deliberately when a fixture gains record data; never lower it to pass.
    assert len(_all_record_values()) >= 24


# ---------------------------------------------------------------------------
# 2. The exclusion is computed, narrow, and provably about vocabulary.
# ---------------------------------------------------------------------------


def test_indistinguishable_values_are_exactly_the_pinned_set() -> None:
    """Only two of the fixtures' record values collide with ExitDrill's vocabulary."""
    excluded = indistinguishable_values(_all_record_values(), control_outputs())

    assert excluded == EXPECTED_INDISTINGUISHABLE


def test_every_excluded_value_is_provably_vocabulary() -> None:
    """Each excluded value must appear in output rendered from no record data.

    This is what makes the carve-out sound rather than convenient: the control
    receipts carry placeholders in every free-text field, so anything found in
    their output came from the format.
    """
    control = control_outputs()

    assert control
    for value in EXPECTED_INDISTINGUISHABLE:
        assert any(_found_in(value, text) for text in control.values()), value


def test_the_exclusion_rule_does_not_swallow_a_genuine_record_value() -> None:
    """Values that carry real identity stay inside the gate.

    Proves the exclusion is a narrow carve-out and not a blanket that would
    quietly exempt whatever the gate happens to find. `person` is included
    deliberately: it is as short as `case` but is not part of the vocabulary,
    so length alone is not what decides this.
    """
    excluded = indistinguishable_values(_all_record_values(), control_outputs())

    for value in (
        "person",
        "person-001",
        "person-002",
        "case_subject",
        "case_manager",
        "Synthetic Person",
        "Replacement Synthetic Person",
        "member",
        "open",
        "event-002",
        "status_changed",
        "attachments/intake.txt",
    ):
        assert value not in excluded, value


def test_the_control_is_not_degenerate() -> None:
    """A control that accidentally contained fixture text would exclude everything.

    Pins the control's own integrity: its placeholders must be present, the
    fixture's real free-text fields must be gone, and it must still render all
    five artifacts rather than collapsing to an empty or partial set.
    """
    control = control_outputs()

    assert set(control) == _OUTPUT_NAMES
    for text in control.values():
        assert "Invented CommunityCase CRM" not in text
        assert "synthetic-crm-exit-001" not in text
    assert all(_CONTROL_TEXT["source_system"] in text for text in control.values())
    # Sanity: each control artifact must still be the real thing, not a stub.
    # A control that rendered as an empty or truncated document would contain
    # no vocabulary and would therefore exclude nothing, silently.
    for name in ("clean-receipt", "lossy-receipt"):
        assert "observed_remediation_signals" in control[name]
    for name in ("clean-report", "lossy-report"):
        assert "Observed loss signals" in control[name]
        assert "<!doctype html>" in control[name]
    assert "comparability" in control["comparison"]


# ---------------------------------------------------------------------------
# 3. The gate.
# ---------------------------------------------------------------------------


def test_aggregate_outputs_disclose_no_record_value() -> None:
    """No receipt, report, or comparison document republishes fixture record data."""
    outputs = aggregate_outputs(_receipts())
    values = _all_record_values()
    excluded = indistinguishable_values(values, control_outputs())

    assert set(outputs) == _OUTPUT_NAMES
    assert disclosures(values, outputs, excluded) == []


# ---------------------------------------------------------------------------
# 4. The gate fires. A drill that cannot fail is not a drill.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "provenance"),
    [
        ("person-001", "export.entities[].id"),
        ("Synthetic Person", "export.entities[].fields.display_name"),
        ("worker-001", "export.permissions[].principal_id"),
        ("case_subject", "export.relationships[].type"),
        ("attachments/intake.txt", "export.attachments[].relative_path"),
        (
            "Synthetic intake attachment for ExitDrill. Contains no real person or case data.",
            "attachment file contents",
        ),
    ],
)
def test_gate_reports_a_record_value_leaked_into_the_receipt_and_report(
    value: str, provenance: str
) -> None:
    """Injecting a real record value into the payload must be reported, twice.

    `source_system` is free payload text carried into both the receipt JSON and
    the rendered report, so one injection exercises both output kinds.
    """
    receipts = _receipts()
    payload = cast(dict[str, JsonValue], receipts["clean"]["payload"])
    payload["source_system"] = value
    _rehash(receipts["clean"])

    outputs = aggregate_outputs({"clean": receipts["clean"]})

    assert disclosures({value: provenance}, outputs, frozenset()) == [
        f"clean-receipt discloses {value!r} (from {provenance})",
        f"clean-report discloses {value!r} (from {provenance})",
    ]


def test_gate_reports_a_record_value_leaked_into_the_comparison_document() -> None:
    """The comparison document is gated too, not only the receipts it summarizes."""
    receipts = _receipts()
    for receipt in receipts.values():
        payload = cast(dict[str, JsonValue], receipt["payload"])
        payload["source_system"] = "person-001"
        _rehash(receipt)

    comparison = compare_snapshots(
        snapshot_receipt(receipts["clean"]),
        snapshot_receipt(receipts["lossy"]),
    )
    outputs = {"comparison": canonical_json_bytes(comparison).decode("utf-8")}

    assert disclosures({"person-001": "export.entities[].id"}, outputs, frozenset()) == [
        "comparison discloses 'person-001' (from export.entities[].id)"
    ]


def test_gate_reports_an_html_escaped_record_value() -> None:
    """Escaping must not become a bypass.

    `report.py` escapes payload text, so a record value containing `&` or `<`
    reaches the HTML only in encoded form and a literal-only search would miss
    it. No committed fixture value contains such a character yet, so this pins
    the behaviour before one does.
    """
    receipts = _receipts()
    value = "Synthetic & Partners <person-001>"
    payload = cast(dict[str, JsonValue], receipts["clean"]["payload"])
    payload["source_system"] = value
    _rehash(receipts["clean"])

    outputs = aggregate_outputs({"clean": receipts["clean"]})

    assert value not in outputs["clean-report"]
    assert "Synthetic &amp; Partners &lt;person-001&gt;" in outputs["clean-report"]
    assert disclosures({value: "test"}, outputs, frozenset()) == [
        f"clean-receipt discloses {value!r} (from test)",
        f"clean-report discloses {value!r} (from test)",
    ]


def test_gate_does_not_manufacture_a_finding() -> None:
    """A value in neither the fixtures nor the output must not be reported."""
    outputs = aggregate_outputs(_receipts())

    assert disclosures({"invented-absent-value-001": "test"}, outputs, frozenset()) == []


def test_corpus_reality_check_rejects_a_needle_absent_from_the_inputs() -> None:
    """The anti-vacuity precondition must itself be able to fire.

    Stand-in for the failure the superseded literal lists could not detect: a
    needle nobody notices has stopped matching anything.
    """
    text = input_text(CLEAN / "export.json", CLEAN / "export-files")

    assert "person-999-renamed-and-never-updated" not in text
