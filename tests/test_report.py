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
from exitdrill.receipt import build_receipt, write_receipt
from exitdrill.report import ReportError, render_receipt_report, write_report


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
