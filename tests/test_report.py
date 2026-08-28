from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from exitdrill.canonical import canonical_json_bytes, sha256_bytes
from exitdrill.cli import main
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import JsonValue
from exitdrill.receipt import ReceiptError, build_receipt, write_receipt
from exitdrill.report import (
    ReportError,
    _dimension_rows,
    render_receipt_report,
    write_report,
)


def _good_receipt(example_root: Path) -> dict[str, JsonValue]:
    result = run_drill(
        load_baseline(example_root / "baseline.json"),
        load_export(example_root / "export.json"),
        example_root / "export-files",
    )
    return build_receipt(result, claimed_generated_at="2026-07-22T20:00:00Z")


def _rehash(receipt: dict[str, JsonValue]) -> None:
    payload = cast(dict[str, JsonValue], receipt["payload"])
    receipt["payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))


def test_renders_deterministic_aggregate_only_accessible_report(example_root: Path) -> None:
    receipt = _good_receipt(example_root)

    first = render_receipt_report(receipt)
    second = render_receipt_report(deepcopy(receipt))

    assert first == second
    assert first.startswith("<!doctype html>")
    assert '<html lang="en">' in first
    assert 'href="#report"' in first
    assert "<caption>Expected, exported, and restored counts" in first
    assert "Structurally restorable" in first
    assert "Does not prove operational equivalence." in first
    assert "Field-value equivalence is limited to baseline-declared required fields." in first
    assert "field_value_equivalence_limited_to_declared_required_fields" not in first
    assert cast(str, receipt["payload_sha256"]) in first
    assert "Synthetic Person" not in first
    assert "person-001" not in first
    assert "2026-07-22T20:00:00Z" not in first
    assert "<script" not in first


def test_escapes_untrusted_verified_receipt_text(example_root: Path) -> None:
    receipt = _good_receipt(example_root)
    payload = cast(dict[str, JsonValue], receipt["payload"])
    payload["source_system"] = '</title><script>alert("source")</script>'
    payload["drill_id"] = '<img src=x onerror="alert(1)">'
    _rehash(receipt)

    document = render_receipt_report(receipt)

    assert '</title><script>alert("source")</script>' not in document
    assert '<img src=x onerror="alert(1)">' not in document
    assert "&lt;/title&gt;&lt;script&gt;alert(&quot;source&quot;)&lt;/script&gt;" in document
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in document


def test_cli_writes_verified_report(
    tmp_path: Path,
    example_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt_path = tmp_path / "receipt.json"
    report_path = tmp_path / "evidence" / "report.html"
    write_receipt(receipt_path, _good_receipt(example_root))

    assert main(["report", str(receipt_path), "--out", str(report_path)]) == 0

    output = capsys.readouterr().out
    assert '"status":"report_written"' in output
    assert '"decision_scope":"verified_aggregate_receipt_report_only"' in output
    assert report_path.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert not list(report_path.parent.glob(".report.html.*.tmp"))


def test_cli_rejects_malformed_receipt_before_output_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt_path = tmp_path / "malformed.json"
    receipt_path.write_text('{"schema_version":', encoding="utf-8")
    report_path = tmp_path / "must-not-exist" / "report.html"

    assert main(["report", str(receipt_path), "--out", str(report_path)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not valid JSON" in captured.err
    assert not report_path.parent.exists()


def test_report_size_limit_precedes_output_mutation(tmp_path: Path) -> None:
    report_path = tmp_path / "must-not-exist" / "report.html"

    with pytest.raises(ReportError, match="2 MiB"):
        write_report(report_path, "x" * (2 * 1024 * 1024 + 1))

    assert not report_path.parent.exists()


@pytest.mark.parametrize("malformed", ["not-a-dimension", [], None, 123, True])
def test_dimension_rows_rejects_a_non_dict_entry(malformed: JsonValue) -> None:
    """The guard `_dimension_rows` enforces on its own parameter type.

    Issue #55 asked whether this guard is reachable. It is not, through either
    public entry point: `render_receipt_report` and `render_receipt_file` both
    run `verify_receipt` first, which routes every dimension through
    `receipt_validation._object`, and `render_receipt_report` then reads that
    same validated list. `test_render_paths_reject_a_malformed_dimension_first`
    below proves that ordering rather than assuming it.

    So the guard is exercised here instead, directly, the way
    `civicrm_target_canary._target_result`'s unreachable `fail` branches are.
    Marking it no-cover would leave a guard in the tree that has never been
    shown to fire, which is the failure mode ADR 0021 and ADR 0022 exist to
    remove. See ADR 0023.
    """
    with pytest.raises(ReportError, match="malformed dimension"):
        _dimension_rows([malformed])


def test_dimension_rows_renders_a_well_formed_dimension() -> None:
    """Pins the positive path, so the guard test cannot pass against a
    function that raised for every input."""
    row = _dimension_rows(
        [
            {
                "name": "entities",
                "coverage": "complete",
                "expected_count": 2,
                "exported_count": 2,
                "restored_count": 2,
                "missing_count": 0,
                "extra_count": 0,
                "invalid_count": 0,
                "status": "pass",
            }
        ]
    )

    assert '<th scope="row">Entities</th>' in row
    assert '<span class="status status-pass">Pass</span>' in row


@pytest.mark.parametrize("position", [0, 5])
def test_render_paths_reject_a_malformed_dimension_first(example_root: Path, position: int) -> None:
    """Verification must run before rendering, or the reachability finding rots.

    If `render_receipt_report` ever stopped verifying first, `_dimension_rows`
    would become reachable and this test would say so by reporting a
    `ReportError` where a `ReceiptError` is required. Position 5 appends a sixth
    entry rather than replacing one, so the dimension-count check cannot be what
    is doing the work.
    """
    receipt = _good_receipt(example_root)
    payload = cast(dict[str, JsonValue], receipt["payload"])
    dimensions = cast(list[JsonValue], payload["dimensions"])
    if position < len(dimensions):
        dimensions[position] = "not-a-dimension"
    else:
        dimensions.append("not-a-dimension")
    _rehash(receipt)

    with pytest.raises(ReceiptError, match=f"dimensions\\[{position}\\] must be an object"):
        render_receipt_report(receipt)
