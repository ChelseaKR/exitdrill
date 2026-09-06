"""The timeline as a page, held to the same refusals the document is held to.

A table is where a gap is most tempting to fill. A reader scanning columns of
numbers reads a blank as an oversight and a zero as a reading, so the one thing
this page may never do is print a number where no measurement exists. That, and
the rule that nothing renders from a document nobody recomputed, are what these
tests are about.
"""

from __future__ import annotations

import json
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from typing import cast

import pytest

from exitdrill.cli import main
from exitdrill.comparison import snapshot_receipt
from exitdrill.evaluator import run_drill
from exitdrill.history import HistoryError, build_history_from_snapshots, write_history
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import Dimension, JsonValue
from exitdrill.receipt import build_receipt, write_receipt
from exitdrill.report import ReportError, document_kind, render_history_report

PROJECT = Path(__file__).parents[1]
CLEAN = PROJECT / "examples" / "synthetic-crm"
LOSSY = PROJECT / "examples" / "synthetic-crm-lossy"


def receipt_for(export_root: Path, baseline: Path, claimed: str) -> dict[str, JsonValue]:
    result = run_drill(
        load_baseline(baseline),
        load_export(export_root / "export.json"),
        export_root / "export-files",
    )
    return build_receipt(result, claimed_generated_at=claimed)


def clean_receipt() -> dict[str, JsonValue]:
    return receipt_for(CLEAN, CLEAN / "baseline.json", "2026-07-22T20:00:00Z")


def lossy_receipt() -> dict[str, JsonValue]:
    return receipt_for(LOSSY, CLEAN / "baseline.json", "2026-07-22T20:05:00Z")


def out_of_scope_receipt(tmp_path: Path) -> dict[str, JsonValue]:
    """A receipt of the same export against a baseline that is a different file."""
    document = json.loads((CLEAN / "baseline.json").read_text(encoding="utf-8"))
    document["captured_at"] = "2026-07-22T18:30:00Z"
    baseline = tmp_path / "other-baseline.json"
    baseline.write_text(json.dumps(document), encoding="utf-8")
    return receipt_for(CLEAN, baseline, "2026-07-22T20:10:00Z")


def series_of(document: dict[str, JsonValue], name: str) -> list[dict[str, JsonValue]]:
    for raw in cast(list[JsonValue], document["dimensions"]):
        entry = cast(dict[str, JsonValue], raw)
        if entry["name"] == name:
            return [
                cast(dict[str, JsonValue], item) for item in cast(list[JsonValue], entry["series"])
            ]
    raise AssertionError(f"no dimension {name!r} in the document")


class _Cells(HTMLParser):
    """Every table row as a list of cell texts, in document order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"}:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def rows(document: str) -> list[list[str]]:
    parser = _Cells()
    parser.feed(document)
    parser.close()
    return parser.rows


def row_starting(document: str, heading: str) -> list[str]:
    matches = [row for row in rows(document) if row and row[0] == heading]
    assert len(matches) == 1, f"expected exactly one row headed {heading!r}"
    return matches[0]


def history_of(*receipts: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return build_history_from_snapshots(
        tuple(snapshot_receipt(deepcopy(receipt)) for receipt in receipts)
    )


def rendered(*receipts: dict[str, JsonValue]) -> tuple[dict[str, JsonValue], str]:
    document = history_of(*receipts)
    return document, render_history_report(
        document, tuple(deepcopy(receipt) for receipt in receipts)
    )


# ---------------------------------------------------------------------------
# The page equals the document.
# ---------------------------------------------------------------------------


def test_every_timeline_cell_carries_that_receipts_counts() -> None:
    document, page = rendered(clean_receipt(), lossy_receipt(), clean_receipt())

    dimensions = {
        cast(str, cast(dict[str, JsonValue], raw)["name"]): cast(dict[str, JsonValue], raw)
        for raw in cast(list[JsonValue], document["dimensions"])
    }
    for name in Dimension:
        entry = dimensions[name.value]
        row = row_starting(page, name.value.replace("_", " ").capitalize())
        assert row[1] == cast(str, entry["coverage"]).capitalize()
        assert row[2] == str(entry["expected_count"])
        for index, observation in enumerate(series_of(document, name.value)):
            cell = row[3 + index]
            assert f"{observation['missing_count']} missing" in cell
            assert f"{observation['invalid_count']} invalid" in cell
            assert f"{observation['extra_count']} extra" in cell


def test_the_page_is_byte_stable() -> None:
    receipts = (clean_receipt(), lossy_receipt())

    _first_document, first = rendered(*receipts)
    _second_document, second = rendered(*receipts)

    assert first == second


def test_the_adjacent_pairs_table_states_each_direction_once() -> None:
    document, page = rendered(clean_receipt(), lossy_receipt(), clean_receipt())
    transitions = cast(list[JsonValue], document["transitions"])

    assert len(transitions) == 2
    assert page.count("Observed loss signals increased") == 1
    assert page.count("Observed loss signals decreased") == 1


# ---------------------------------------------------------------------------
# A gap prints words, never numbers.
# ---------------------------------------------------------------------------


def test_a_gap_cell_carries_no_number(tmp_path: Path) -> None:
    document, page = rendered(clean_receipt(), out_of_scope_receipt(tmp_path), lossy_receipt())

    assert cast(dict[str, JsonValue], document["summary"])["gap_positions"] == [1]
    for name in Dimension:
        row = row_starting(page, name.value.replace("_", " ").capitalize())
        gap_cell = row[4]
        assert gap_cell == "No measurement"
        assert not any(character.isdigit() for character in gap_cell), gap_cell
        # The receipts either side still read as measurements.
        assert "missing" in row[3]
        assert "missing" in row[5]


def test_the_gap_is_named_with_its_reason_code(tmp_path: Path) -> None:
    _document, page = rendered(clean_receipt(), out_of_scope_receipt(tmp_path), lossy_receipt())

    assert "baseline_sha256_changed" in page
    assert "One receipt does not share the series scope" in page
    assert "never as zero counts" in page


def test_a_pair_touching_a_gap_shows_no_direction(tmp_path: Path) -> None:
    _document, page = rendered(clean_receipt(), out_of_scope_receipt(tmp_path), lossy_receipt())

    assert "Not comparable" in page
    assert "Observed loss signals increased" not in page
    assert "Observed loss signals decreased" not in page


def test_a_clean_series_says_so_instead(tmp_path: Path) -> None:
    """Pins the other side of the gap sentence, so it cannot be always-on."""
    _document, page = rendered(clean_receipt(), lossy_receipt())

    assert "Every receipt in this series shares one scope." in page
    assert "No measurement" not in page


# ---------------------------------------------------------------------------
# Nothing renders from a document nobody recomputed.
# ---------------------------------------------------------------------------


def test_a_forged_count_is_refused_before_rendering() -> None:
    receipts = (clean_receipt(), lossy_receipt())
    document = history_of(*receipts)
    series_of(document, "entities")[1]["missing_count"] = 0

    with pytest.raises(HistoryError, match="does not match its source receipts"):
        render_history_report(document, receipts)


def test_cli_refuses_a_forged_timeline_before_touching_the_output_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = tmp_path / "r0.json"
    second = tmp_path / "r1.json"
    write_receipt(first, clean_receipt())
    write_receipt(second, lossy_receipt())
    history = tmp_path / "history.json"
    write_history(history, history_of(clean_receipt(), lossy_receipt()))
    forged = json.loads(history.read_text(encoding="utf-8"))
    forged["dimensions"][0]["series"][1]["missing_count"] = 0
    history.write_text(json.dumps(forged), encoding="utf-8")
    out = tmp_path / "must-not-exist" / "history.html"

    code = main(
        [
            "report",
            str(history),
            "--receipt",
            str(first),
            "--receipt",
            str(second),
            "--out",
            str(out),
        ]
    )

    assert code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "does not match its source receipts" in captured.err
    assert not out.parent.exists()


def test_cli_writes_a_timeline_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = tmp_path / "r0.json"
    second = tmp_path / "r1.json"
    write_receipt(first, clean_receipt())
    write_receipt(second, lossy_receipt())
    history = tmp_path / "history.json"
    write_history(history, history_of(clean_receipt(), lossy_receipt()))
    out = tmp_path / "evidence" / "history.html"

    assert (
        main(
            [
                "report",
                str(history),
                "--receipt",
                str(first),
                "--receipt",
                str(second),
                "--out",
                str(out),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert '"decision_scope":"verified_aggregate_history_report_only"' in output
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


# ---------------------------------------------------------------------------
# Routing: the document says what it is, and the operands must match it.
# ---------------------------------------------------------------------------


def test_document_kind_reads_a_history(tmp_path: Path) -> None:
    history = tmp_path / "history.json"
    write_history(history, history_of(clean_receipt(), lossy_receipt()))

    assert document_kind(history) == "history"


@pytest.mark.parametrize(
    ("arguments", "fragment"),
    [
        ([], "requires --receipt for every receipt"),
        (["--receipt", "one"], "requires --receipt for every receipt"),
        (["--reference", "a", "--candidate", "b"], "apply only to a comparison document"),
    ],
)
def test_cli_refuses_a_timeline_with_the_wrong_operands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    fragment: str,
) -> None:
    history = tmp_path / "history.json"
    write_history(history, history_of(clean_receipt(), lossy_receipt()))
    out = tmp_path / "must-not-exist" / "history.html"

    assert main(["report", str(history), *arguments, "--out", str(out)]) == 2

    assert fragment in capsys.readouterr().err
    assert not out.parent.exists()


def test_cli_refuses_series_receipts_on_a_comparison_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from exitdrill.comparison import compare_snapshots, write_comparison

    first = tmp_path / "r0.json"
    second = tmp_path / "r1.json"
    write_receipt(first, clean_receipt())
    write_receipt(second, lossy_receipt())
    comparison = tmp_path / "comparison.json"
    write_comparison(
        comparison,
        compare_snapshots(snapshot_receipt(clean_receipt()), snapshot_receipt(lossy_receipt())),
    )
    out = tmp_path / "must-not-exist" / "comparison.html"

    assert (
        main(
            [
                "report",
                str(comparison),
                "--reference",
                str(first),
                "--candidate",
                str(second),
                "--receipt",
                str(first),
                "--out",
                str(out),
            ]
        )
        == 2
    )

    assert "--receipt applies only to a history document" in capsys.readouterr().err


def test_the_row_guard_names_the_malformed_history_part() -> None:
    """The three history row builders enforce their own parameter type.

    Unreachable through the renderer, which verifies first; exercised directly
    for the same reason `_dimension_rows`'s guard is (ADR 0023, issue #55).
    """
    from exitdrill.report import _objects

    for message in (
        "verified history contains a malformed series entry",
        "verified history contains a malformed observation",
        "verified history contains a malformed transition",
    ):
        with pytest.raises(ReportError, match="malformed"):
            _objects(["not-an-object"], message)
