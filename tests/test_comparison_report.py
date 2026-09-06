"""The comparison document gets the same offline report the receipt already had.

`compare` and `verify-comparison` closed the comparison round trip in #102, but
its only output was JSON: a reader who is not the operator was handed a
document and left to read `count_deltas` by eye. This module binds the second
renderer to the same discipline the receipt report is held to -- no aggregate
score, no ordinal reading of a status change, extras kept apart from losses,
and nothing rendered from a document that has not first been recomputed from
both of its source receipts.

The four properties issue #129 asks for are each checked here against the
document rather than against prose: the delta table equals the JSON's deltas,
`uncertain` appears on the page only when a dimension's assessment is
`uncertain`, an incomparable document renders its reason codes and no dimension
table, and a forged delta stops `report` before anything is written.
"""

from __future__ import annotations

import json
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from typing import cast

import pytest

from exitdrill.canonical import canonical_json_bytes
from exitdrill.cli import main
from exitdrill.comparison import ComparisonError, compare_snapshots, snapshot_receipt
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import JsonValue
from exitdrill.receipt import build_receipt, write_receipt
from exitdrill.report import (
    _ASSESSMENT_LABELS,
    _TRANSITION_LABELS,
    ReportError,
    _objects,
    document_kind,
    render_comparison_report,
)

PROJECT = Path(__file__).parents[1]
CLEAN = PROJECT / "examples" / "synthetic-crm"
LOSSY = PROJECT / "examples" / "synthetic-crm-lossy"


class _Tables(HTMLParser):
    """Collect every table as a list of rows of cell texts, in document order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tr":
            self._row = []
        elif tag in {"td", "th"}:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def tables(document: str) -> list[list[list[str]]]:
    parser = _Tables()
    parser.feed(document)
    parser.close()
    return parser.tables


def table_with_header(document: str, first_cell: str, second_cell: str) -> list[list[str]]:
    """Return the one table whose header row starts with these two columns."""
    matches = [
        table for table in tables(document) if table and table[0][:2] == [first_cell, second_cell]
    ]
    assert len(matches) == 1, f"expected exactly one {first_cell}/{second_cell} table"
    return matches[0]


def receipt_for(export_root: Path, baseline: Path, claimed: str) -> dict[str, JsonValue]:
    result = run_drill(
        load_baseline(baseline),
        load_export(export_root / "export.json"),
        export_root / "export-files",
    )
    return build_receipt(result, claimed_generated_at=claimed)


def receipt_pair(baseline: Path) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """One clean and one lossy receipt against the same baseline, as `demo-lossy` runs."""
    return (
        receipt_for(CLEAN, baseline, "2026-07-22T20:00:00Z"),
        receipt_for(LOSSY, baseline, "2026-07-22T20:05:00Z"),
    )


def rendered_pair(
    reference: dict[str, JsonValue],
    candidate: dict[str, JsonValue],
) -> tuple[dict[str, JsonValue], str]:
    comparison = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    return comparison, render_comparison_report(
        comparison, deepcopy(reference), deepcopy(candidate)
    )


def edited_baseline(tmp_path: Path, **changes: JsonValue) -> Path:
    """Write a copy of the demo baseline with the named top-level fields replaced."""
    document = json.loads((CLEAN / "baseline.json").read_text(encoding="utf-8"))
    document.update(changes)
    destination = tmp_path / f"baseline-{'-'.join(sorted(changes))}.json"
    destination.write_text(json.dumps(document), encoding="utf-8")
    return destination


def written_comparison(tmp_path: Path, baseline: Path) -> tuple[Path, Path, Path]:
    """Write both receipts and their comparison document to disk, for the CLI."""
    reference, candidate = receipt_pair(baseline)
    reference_path = tmp_path / "reference.json"
    candidate_path = tmp_path / "candidate.json"
    comparison_path = tmp_path / "comparison.json"
    write_receipt(reference_path, reference)
    write_receipt(candidate_path, candidate)
    comparison = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    comparison_path.write_bytes(canonical_json_bytes(comparison) + b"\n")
    return comparison_path, reference_path, candidate_path


# ---------------------------------------------------------------------------
# The page equals the document it was rendered from.
# ---------------------------------------------------------------------------


def test_the_delta_table_equals_the_documents_deltas() -> None:
    """Every signed delta on the page is the delta in the JSON, sign included."""
    comparison, document = rendered_pair(*receipt_pair(CLEAN / "baseline.json"))
    table = table_with_header(document, "Dimension", "Coverage")
    columns = [
        "expected_count",
        "exported_count",
        "restored_count",
        "missing_count",
        "extra_count",
        "invalid_count",
    ]
    dimensions = cast(list[JsonValue], comparison["dimensions"])

    assert len(table) == len(dimensions) + 1
    for row, raw in zip(table[1:], dimensions, strict=True):
        entry = cast(dict[str, JsonValue], raw)
        deltas = cast(dict[str, JsonValue], entry["count_deltas"])
        expected = [
            f"{cast(int, deltas[column]):+d}" if deltas[column] else "0" for column in columns
        ]
        assert row[2:] == expected, entry["name"]
        assert row[1] == cast(str, entry["coverage"]).capitalize()


def test_the_delta_table_would_report_a_page_that_disagreed_with_the_document() -> None:
    """The comparison above is only worth running if a mismatch could fail it.

    A renderer that dropped signs, or printed the reference's counts instead of
    the deltas, would produce a table this assertion rejects.
    """
    comparison, document = rendered_pair(*receipt_pair(CLEAN / "baseline.json"))
    table = table_with_header(document, "Dimension", "Coverage")
    entities = cast(dict[str, JsonValue], cast(list[JsonValue], comparison["dimensions"])[0])
    deltas = cast(dict[str, JsonValue], entities["count_deltas"])

    assert deltas["missing_count"] == 1
    assert table[1][5] == "+1"
    assert table[1][5] != "1"


def test_status_transitions_are_rendered_as_facts_for_both_receipts() -> None:
    comparison, document = rendered_pair(*receipt_pair(CLEAN / "baseline.json"))
    table = table_with_header(document, "Dimension", "Reference status")
    dimensions = cast(list[JsonValue], comparison["dimensions"])

    for row, raw in zip(table[1:], dimensions, strict=True):
        entry = cast(dict[str, JsonValue], raw)
        assert row[1] == "Pass"
        assert row[2] == "Fail"
        assert row[3] == "Changed"
        assert cast(str, entry["reference_status"]) == "pass"
        assert cast(str, entry["candidate_status"]) == "fail"


def test_the_page_adds_no_verdict_vocabulary_of_its_own() -> None:
    """Every transition and assessment cell is a label for a document value.

    The project's rule is that a status change is a fact, never a ranking, so
    the page may not introduce a word the document does not support. Checking
    the rendered cells against the two closed label sets is what makes that
    enforceable: a renderer that added "improved" or "regressed" to a row would
    produce a cell outside these sets.
    """
    _comparison, document = rendered_pair(*receipt_pair(CLEAN / "baseline.json"))
    table = table_with_header(document, "Dimension", "Reference status")
    transitions = set(_TRANSITION_LABELS.values())
    assessments = set(_ASSESSMENT_LABELS.values())

    assert len(table) == 6
    for row in table[1:]:
        assert row[3] in transitions, row[3]
        assert row[4] in transitions, row[4]
        assert row[6] in assessments, row[6]
    assert {row[6] for row in table[1:]} == {"Observed loss signals increased"}


def test_the_page_is_byte_stable() -> None:
    reference, candidate = receipt_pair(CLEAN / "baseline.json")
    _first_document, first = rendered_pair(reference, candidate)
    _second_document, second = rendered_pair(deepcopy(reference), deepcopy(candidate))

    assert first == second


# ---------------------------------------------------------------------------
# `uncertain` is a coverage fact, printed only when it is one.
# ---------------------------------------------------------------------------


def test_the_word_uncertain_is_absent_when_no_dimension_is_uncertain() -> None:
    comparison, document = rendered_pair(*receipt_pair(CLEAN / "baseline.json"))
    summary = cast(dict[str, JsonValue], comparison["summary"])

    assert summary["uncertain"] == []
    assert "uncertain" not in document.lower()


def test_the_word_uncertain_appears_when_a_dimension_is_uncertain(tmp_path: Path) -> None:
    """Partial baseline coverage makes one dimension's assessment `uncertain`.

    Both receipts are drilled against the same edited baseline, so the pair
    stays comparable and the only thing that changed is what the baseline can
    account for.
    """
    coverage = {
        "entities": "complete",
        "relationships": "complete",
        "attachments": "complete",
        "permissions": "partial",
        "audit_events": "complete",
    }
    baseline = edited_baseline(tmp_path, coverage=cast(JsonValue, coverage))
    comparison, document = rendered_pair(*receipt_pair(baseline))
    summary = cast(dict[str, JsonValue], comparison["summary"])

    assert summary["uncertain"] == ["permissions"]
    assert "Uncertain: baseline coverage is not complete" in document
    assert document.lower().count("uncertain") == 2


# ---------------------------------------------------------------------------
# An incomparable document renders its reasons and no dimension table.
# ---------------------------------------------------------------------------


def test_an_incomparable_document_renders_reason_codes_and_no_dimension_table(
    tmp_path: Path,
) -> None:
    reference = receipt_for(CLEAN, CLEAN / "baseline.json", "2026-07-22T20:00:00Z")
    candidate = receipt_for(
        CLEAN,
        edited_baseline(tmp_path, captured_at="2026-07-22T18:30:00Z"),
        "2026-07-22T20:05:00Z",
    )
    comparison, document = rendered_pair(reference, candidate)

    assert comparison["comparability"] == "incomparable"
    assert comparison["incomparable_reasons"] == ["baseline_sha256_changed"]
    assert "Incomparable" in document
    assert "<code>baseline_sha256_changed</code>" in document
    assert "The baseline digest differs between the two receipts." in document
    assert "No dimension table is rendered." in document
    # The comparability-check table is still rendered; the two dimension tables
    # are not, and neither is the summary of an empty comparison.
    assert len(tables(document)) == 1
    assert "Signed count deltas" not in document
    assert "Dimensions by observation" not in document


def test_a_comparable_document_renders_the_tables_the_incomparable_one_omits() -> None:
    """Pins the other half of the branch, so the test above cannot pass on a
    renderer that emits no dimension table for anything."""
    _comparison, document = rendered_pair(*receipt_pair(CLEAN / "baseline.json"))

    assert len(tables(document)) == 3
    assert "Signed count deltas" in document
    assert "Dimensions by observation" in document
    assert "No dimension table is rendered." not in document


# ---------------------------------------------------------------------------
# Nothing is rendered from a document that does not match its receipts.
# ---------------------------------------------------------------------------


def test_a_forged_delta_is_refused_before_rendering() -> None:
    reference, candidate = receipt_pair(CLEAN / "baseline.json")
    comparison = compare_snapshots(snapshot_receipt(reference), snapshot_receipt(candidate))
    entities = cast(dict[str, JsonValue], cast(list[JsonValue], comparison["dimensions"])[0])
    cast(dict[str, JsonValue], entities["count_deltas"])["missing_count"] = 0

    with pytest.raises(ComparisonError, match="does not match its source receipts"):
        render_comparison_report(comparison, reference, candidate)


def test_cli_refuses_a_forged_delta_before_touching_the_output_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    comparison_path, reference_path, candidate_path = written_comparison(
        tmp_path, CLEAN / "baseline.json"
    )
    document = json.loads(comparison_path.read_text(encoding="utf-8"))
    document["dimensions"][0]["count_deltas"]["missing_count"] = 0
    comparison_path.write_text(json.dumps(document), encoding="utf-8")
    out = tmp_path / "must-not-exist" / "comparison.html"

    assert (
        main(
            [
                "report",
                str(comparison_path),
                "--reference",
                str(reference_path),
                "--candidate",
                str(candidate_path),
                "--out",
                str(out),
            ]
        )
        == 2
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "does not match its source receipts" in captured.err
    assert not out.parent.exists()


def test_cli_writes_a_comparison_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    comparison_path, reference_path, candidate_path = written_comparison(
        tmp_path, CLEAN / "baseline.json"
    )
    out = tmp_path / "evidence" / "comparison.html"

    assert (
        main(
            [
                "report",
                str(comparison_path),
                "--reference",
                str(reference_path),
                "--candidate",
                str(candidate_path),
                "--out",
                str(out),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert '"status":"report_written"' in output
    assert '"decision_scope":"verified_aggregate_comparison_report_only"' in output
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert not list(out.parent.glob(".comparison.html.*.tmp"))


# ---------------------------------------------------------------------------
# Routing: the document says what it is, and the operand flags must match it.
# ---------------------------------------------------------------------------


def test_document_kind_reads_the_declared_schema_version(
    tmp_path: Path,
    example_root: Path,
) -> None:
    comparison_path, reference_path, _candidate_path = written_comparison(
        tmp_path, example_root / "baseline.json"
    )

    assert document_kind(reference_path) == "receipt"
    assert document_kind(comparison_path) == "comparison"


@pytest.mark.parametrize(
    "document",
    [
        '{"schema_version":"exitdrill/receipt/v0.2"}',
        '{"schema_version":42}',
        "{}",
        "[]",
    ],
)
def test_document_kind_refuses_a_document_it_cannot_route(tmp_path: Path, document: str) -> None:
    path = tmp_path / "unknown.json"
    path.write_text(document, encoding="utf-8")

    with pytest.raises(ReportError, match=r"supported schema version|must be a JSON object"):
        document_kind(path)


def test_document_kind_reports_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "malformed.json"
    path.write_text('{"schema_version":', encoding="utf-8")

    with pytest.raises(ReportError, match="not valid JSON"):
        document_kind(path)


def test_cli_requires_both_receipts_for_a_comparison_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A comparison report without its receipts is a usage error, not a page.

    Rendering one anyway would publish a delta table nothing had recomputed,
    which is the precise thing the comparison round trip exists to prevent.
    """
    comparison_path, reference_path, _candidate_path = written_comparison(
        tmp_path, CLEAN / "baseline.json"
    )
    out = tmp_path / "must-not-exist" / "comparison.html"

    assert (
        main(
            ["report", str(comparison_path), "--reference", str(reference_path), "--out", str(out)]
        )
        == 2
    )

    assert "requires --reference and --candidate" in capsys.readouterr().err
    assert not out.parent.exists()


def test_cli_rejects_receipt_operands_on_a_receipt_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _comparison_path, reference_path, candidate_path = written_comparison(
        tmp_path, CLEAN / "baseline.json"
    )
    out = tmp_path / "must-not-exist" / "report.html"

    assert (
        main(
            [
                "report",
                str(reference_path),
                "--reference",
                str(reference_path),
                "--candidate",
                str(candidate_path),
                "--out",
                str(out),
            ]
        )
        == 2
    )

    assert "apply only to a comparison document" in capsys.readouterr().err
    assert not out.parent.exists()


# ---------------------------------------------------------------------------
# The shared row guard, exercised directly as ADR 0023 requires.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("malformed", ["not-a-dimension", [], None, 123, True])
def test_objects_rejects_a_non_object_entry(malformed: JsonValue) -> None:
    """The guard both row builders enforce on their own parameter type.

    Unreachable through either renderer: each verifies its document first, and
    both verifiers reject a non-object dimension before rendering begins. It is
    exercised directly rather than marked no-cover, so it stays a guard that has
    been shown to fire. See ADR 0023 and issue #55.
    """
    with pytest.raises(ReportError, match="malformed dimension"):
        _objects([malformed], "verified comparison contains a malformed dimension")


def test_objects_returns_the_well_formed_entries() -> None:
    """Pins the positive path, so the guard test cannot pass against a
    function that raised for every input."""
    assert _objects([{"name": "entities"}], "unused") == [{"name": "entities"}]
