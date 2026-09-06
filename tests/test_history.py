"""A series of receipts, reduced without inventing anything the receipts do not say.

`compare` answers one question about two receipts. A timeline answers the same
question repeatedly, and the ways it could go wrong are new: it could order the
series by something the caller did not choose, it could fill a receipt it cannot
compare with zeros, it could give an adjacent pair a direction computed from one
side, or it could let a policy that had nothing to read return the code that
means "nothing was wrong".

Each of those is checked here against the document rather than against prose.
The gap tests are the centre: this project's dominant defect is a value nobody
measured published where a measurement goes, and a timeline is the shape that
invites it, because a table with a hole in it looks unfinished and a table of
zeros looks complete.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator, ValidationError

from exitdrill.canonical import canonical_json_bytes
from exitdrill.cli import main
from exitdrill.comparison import load_receipt_snapshot, snapshot_receipt
from exitdrill.evaluator import run_drill
from exitdrill.history import (
    HISTORY_SCHEMA_VERSION,
    HistoryError,
    build_history_from_snapshots,
    history_from_files,
    receipt_paths_in_directory,
    verify_history_document,
    write_history,
)
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import Dimension, JsonValue
from exitdrill.receipt import build_receipt, write_receipt

PROJECT = Path(__file__).parents[1]
CLEAN = PROJECT / "examples" / "synthetic-crm"
LOSSY = PROJECT / "examples" / "synthetic-crm-lossy"

_OBSERVED_KEYS = {
    "exported_count",
    "extra_count",
    "invalid_count",
    "missing_count",
    "observed",
    "position",
    "restored_count",
    "status",
}


def receipt_for(export_root: Path, baseline: Path, claimed: str) -> dict[str, JsonValue]:
    result = run_drill(
        load_baseline(baseline),
        load_export(export_root / "export.json"),
        export_root / "export-files",
    )
    return build_receipt(result, claimed_generated_at=claimed)


def clean_receipt(claimed: str = "2026-07-22T20:00:00Z") -> dict[str, JsonValue]:
    return receipt_for(CLEAN, CLEAN / "baseline.json", claimed)


def lossy_receipt(claimed: str = "2026-07-22T20:05:00Z") -> dict[str, JsonValue]:
    return receipt_for(LOSSY, CLEAN / "baseline.json", claimed)


def out_of_scope_receipt(tmp_path: Path) -> dict[str, JsonValue]:
    """A receipt of the same export against a baseline that is a different file."""
    document = json.loads((CLEAN / "baseline.json").read_text(encoding="utf-8"))
    document["captured_at"] = "2026-07-22T18:30:00Z"
    baseline = tmp_path / "other-baseline.json"
    baseline.write_text(json.dumps(document), encoding="utf-8")
    return receipt_for(CLEAN, baseline, "2026-07-22T20:10:00Z")


def history_of(*receipts: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return build_history_from_snapshots(
        tuple(snapshot_receipt(deepcopy(receipt)) for receipt in receipts)
    )


def written(tmp_path: Path, *receipts: dict[str, JsonValue]) -> tuple[Path, list[Path]]:
    paths = []
    for index, receipt in enumerate(receipts):
        path = tmp_path / f"receipt-{index}.json"
        write_receipt(path, receipt)
        paths.append(path)
    document = tmp_path / "history.json"
    write_history(document, history_of(*receipts))
    return document, paths


def series_of(document: dict[str, JsonValue], name: str) -> list[dict[str, JsonValue]]:
    dimensions = cast(list[JsonValue], document["dimensions"])
    for raw in dimensions:
        entry = cast(dict[str, JsonValue], raw)
        if entry["name"] == name:
            return [
                cast(dict[str, JsonValue], item) for item in cast(list[JsonValue], entry["series"])
            ]
    raise AssertionError(f"no dimension {name!r} in the document")


def directions(document: dict[str, JsonValue]) -> list[str | None]:
    return [
        cast(str, cast(dict[str, JsonValue], item).get("direction"))
        for item in cast(list[JsonValue], document["transitions"])
    ]


# ---------------------------------------------------------------------------
# The timeline states what the receipts state, in the order it was given.
# ---------------------------------------------------------------------------


def test_a_clean_lossy_clean_series_reads_increase_then_decrease() -> None:
    document = history_of(clean_receipt(), lossy_receipt(), clean_receipt())

    assert document["schema_version"] == HISTORY_SCHEMA_VERSION
    assert directions(document) == [
        "observed_loss_signals_increased",
        "observed_loss_signals_decreased",
    ]
    assert cast(dict[str, JsonValue], document["summary"])["receipt_count"] == 3
    assert cast(dict[str, JsonValue], document["summary"])["gap_positions"] == []


def test_every_count_in_the_timeline_is_the_count_in_that_receipt() -> None:
    receipts = [clean_receipt(), lossy_receipt(), clean_receipt()]
    document = history_of(*receipts)

    for name in Dimension:
        series = series_of(document, name.value)
        assert len(series) == len(receipts)
        for observation, receipt in zip(series, receipts, strict=True):
            payload = cast(dict[str, JsonValue], receipt["payload"])
            dimension = next(
                cast(dict[str, JsonValue], raw)
                for raw in cast(list[JsonValue], payload["dimensions"])
                if cast(dict[str, JsonValue], raw)["name"] == name.value
            )
            for key in ("missing_count", "invalid_count", "extra_count", "restored_count"):
                assert observation[key] == dimension[key], (name.value, key)
            assert observation["status"] == dimension["status"]


def test_the_order_is_the_callers_and_not_the_envelopes() -> None:
    """The same two receipts in the other order is a different document.

    Both receipts carry a claimed generation time, and the later one is passed
    first here. If anything read the envelope, the document would be the same
    either way and the ordering basis it declares would be a lie.
    """
    later = lossy_receipt("2026-07-22T23:00:00Z")
    earlier = clean_receipt("2026-07-22T01:00:00Z")

    forwards = history_of(later, earlier)
    backwards = history_of(earlier, later)

    assert forwards["ordering_basis"] == "caller_supplied_unverified"
    assert directions(forwards) == ["observed_loss_signals_decreased"]
    assert directions(backwards) == ["observed_loss_signals_increased"]


def test_the_document_is_byte_stable() -> None:
    receipts = [clean_receipt(), lossy_receipt()]

    first = canonical_json_bytes(history_of(*receipts))
    second = canonical_json_bytes(history_of(*receipts))

    assert first == second


# ---------------------------------------------------------------------------
# A receipt outside the series scope is a gap, and a gap carries no numbers.
# ---------------------------------------------------------------------------


def test_an_out_of_scope_receipt_is_a_gap_with_reason_codes(tmp_path: Path) -> None:
    document = history_of(clean_receipt(), out_of_scope_receipt(tmp_path), lossy_receipt())
    summary = cast(dict[str, JsonValue], document["summary"])
    entries = [
        cast(dict[str, JsonValue], item) for item in cast(list[JsonValue], document["receipts"])
    ]

    assert summary["gap_positions"] == [1]
    assert summary["gap_reasons"] == ["baseline_sha256_changed"]
    assert summary["in_scope_count"] == 2
    assert entries[1]["in_scope"] is False
    assert entries[1]["out_of_scope_reasons"] == ["baseline_sha256_changed"]
    assert entries[0]["in_scope"] is True
    assert entries[2]["in_scope"] is True


def test_a_gap_carries_no_counts_at_all(tmp_path: Path) -> None:
    """The whole point. A zero here is a measurement nobody took."""
    document = history_of(clean_receipt(), out_of_scope_receipt(tmp_path), lossy_receipt())

    for name in Dimension:
        series = series_of(document, name.value)
        assert set(series[1]) == {"observed", "position"}, name.value
        assert series[1]["observed"] is False
        assert set(series[0]) == _OBSERVED_KEYS
        assert set(series[2]) == _OBSERVED_KEYS


def test_a_gap_does_not_abort_the_rest_of_the_series(tmp_path: Path) -> None:
    """The receipts around the gap are still measured, and still say so."""
    with_gap = history_of(clean_receipt(), out_of_scope_receipt(tmp_path), lossy_receipt())
    without_gap = history_of(clean_receipt(), lossy_receipt())

    entities = series_of(with_gap, "entities")
    plain = series_of(without_gap, "entities")

    assert entities[0]["missing_count"] == plain[0]["missing_count"]
    assert entities[2]["missing_count"] == plain[1]["missing_count"]
    assert entities[2]["status"] == "fail"


def test_a_pair_touching_a_gap_carries_no_direction(tmp_path: Path) -> None:
    document = history_of(clean_receipt(), out_of_scope_receipt(tmp_path), lossy_receipt())
    transitions = [
        cast(dict[str, JsonValue], item) for item in cast(list[JsonValue], document["transitions"])
    ]

    for transition in transitions:
        assert transition["comparable"] is False
        assert "direction" not in transition
        assert "observed_loss_signal_increases" not in transition
        assert transition["not_comparable_reasons"] == ["baseline_sha256_changed"]


def test_a_comparable_pair_does_carry_one() -> None:
    """Pins the other side, so the checks above cannot pass on a document that
    never carries a direction at all."""
    document = history_of(clean_receipt(), lossy_receipt())
    transition = cast(dict[str, JsonValue], cast(list[JsonValue], document["transitions"])[0])

    assert transition["comparable"] is True
    assert transition["direction"] == "observed_loss_signals_increased"
    assert transition["observed_loss_signal_increases"] == [name.value for name in Dimension]


def test_the_scope_is_the_first_receipts(tmp_path: Path) -> None:
    """Position 0 defines the series, so it is never itself a gap."""
    document = history_of(out_of_scope_receipt(tmp_path), clean_receipt())
    scope = cast(dict[str, JsonValue], document["scope"])
    entries = [
        cast(dict[str, JsonValue], item) for item in cast(list[JsonValue], document["receipts"])
    ]

    assert entries[0]["in_scope"] is True
    assert entries[1]["in_scope"] is False
    assert cast(dict[str, JsonValue], document["summary"])["gap_positions"] == [1]
    assert scope["drill_id"] == "synthetic-crm-exit-001"


# ---------------------------------------------------------------------------
# Verification recomputes, and a single receipt is a usage error.
# ---------------------------------------------------------------------------


def test_verification_rejects_an_edited_count_sequence() -> None:
    receipts = [clean_receipt(), lossy_receipt()]
    document = history_of(*receipts)
    series = series_of(document, "entities")
    series[1]["missing_count"] = 0

    with pytest.raises(HistoryError, match="does not match its source receipts"):
        verify_history_document(document, tuple(receipts))


def test_verification_rejects_a_document_paired_with_the_wrong_receipts() -> None:
    document = history_of(clean_receipt(), lossy_receipt())

    with pytest.raises(HistoryError, match="does not match its source receipts"):
        verify_history_document(document, (clean_receipt(), clean_receipt()))


def test_verification_accepts_the_document_it_was_built_from() -> None:
    receipts = [clean_receipt(), lossy_receipt(), clean_receipt()]

    verify_history_document(history_of(*receipts), tuple(receipts))


@pytest.mark.parametrize("count", [0, 1])
def test_a_series_shorter_than_two_receipts_is_a_usage_error(count: int) -> None:
    receipts = [clean_receipt()][:count]

    with pytest.raises(HistoryError, match="at least two receipts"):
        history_of(*receipts)
    with pytest.raises(HistoryError, match="at least two receipts"):
        verify_history_document(history_of(clean_receipt(), lossy_receipt()), tuple(receipts))


def test_recomputation_reports_a_forged_document_before_the_schema_does() -> None:
    """The precise, source-bound error wins, as it does for a comparison.

    The schema check runs after as a structural net; it only has anything left
    to catch when a document passes byte-for-byte recomputation and still is
    not well-formed, which recomputation alone cannot promise for arbitrary
    caller-supplied JSON.
    """
    document = history_of(clean_receipt(), lossy_receipt())
    document["invented_key"] = True

    with pytest.raises(HistoryError, match="does not match its source receipts"):
        verify_history_document(document, (clean_receipt(), lossy_receipt()))


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda document: document.update({"invented_key": True}), id="extra-key"),
        pytest.param(lambda document: document.pop("summary"), id="missing-summary"),
        pytest.param(
            lambda document: document.update({"ordering_basis": "envelope_timestamp"}),
            id="invented-ordering-basis",
        ),
        pytest.param(
            lambda document: series_of(document, "entities")[0].update({"observed": False}),
            id="a-measurement-claiming-to-be-a-gap",
        ),
        pytest.param(
            lambda document: series_of(document, "entities")[0].pop("missing_count"),
            id="a-gap-claiming-to-be-a-measurement",
        ),
    ],
)
def test_the_public_schema_rejects_a_malformed_document(
    mutate: Callable[[dict[str, JsonValue]], object],
) -> None:
    """The schema is maintained apart from `_build_history` and can genuinely differ.

    Exercised against the committed file directly, because a document that
    fails the schema and passes recomputation cannot be constructed: these are
    the shapes the schema is the only thing standing between a reader and.
    """
    schema = json.loads(
        (PROJECT / "schemas" / "receipt-history-v0.1.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    document = history_of(clean_receipt(), lossy_receipt())
    validator.validate(document)

    mutate(document)

    with pytest.raises(ValidationError):
        validator.validate(document)


def test_the_committed_schema_is_the_one_the_package_loads() -> None:
    """A schema the package never opens is a check nobody runs (issue #33)."""
    source = (PROJECT / "src" / "exitdrill" / "history.py").read_text(encoding="utf-8")

    assert "receipt-history-v0.1.schema.json" in source


# ---------------------------------------------------------------------------
# Reading a directory, in filename order and nothing else.
# ---------------------------------------------------------------------------


def test_a_directory_is_read_in_filename_order(tmp_path: Path) -> None:
    write_receipt(tmp_path / "b-lossy.json", lossy_receipt())
    write_receipt(tmp_path / "a-clean.json", clean_receipt())

    paths = receipt_paths_in_directory(tmp_path)
    document = history_from_files(paths)

    assert [path.name for path in paths] == ["a-clean.json", "b-lossy.json"]
    assert directions(document) == ["observed_loss_signals_increased"]


def test_an_empty_or_missing_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HistoryError, match="receipt directory not found"):
        receipt_paths_in_directory(tmp_path / "nowhere")
    with pytest.raises(HistoryError, match=r"no \*.json receipts"):
        receipt_paths_in_directory(tmp_path)


# ---------------------------------------------------------------------------
# The CLI, including the policy that must not read absence as a pass.
# ---------------------------------------------------------------------------


def test_cli_writes_and_verifies_a_timeline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document, paths = written(tmp_path, clean_receipt(), lossy_receipt(), clean_receipt())
    out = tmp_path / "written" / "history.json"

    assert main(["history", *[str(path) for path in paths], "--out", str(out)]) == 0
    output = capsys.readouterr().out
    assert '"status":"history_written"' in output
    assert '"receipt_count":3' in output

    assert (
        main(
            [
                "verify-history",
                str(out),
                *[flag for path in paths for flag in ("--receipt", str(path))],
            ]
        )
        == 0
    )
    assert '"status":"recomputation_verified"' in capsys.readouterr().out
    assert out.read_bytes() == document.read_bytes()


def test_cli_refuses_a_single_receipt_series(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _document, paths = written(tmp_path, clean_receipt(), lossy_receipt())
    out = tmp_path / "must-not-exist" / "history.json"

    assert main(["history", str(paths[0]), "--out", str(out)]) == 2

    assert "at least two receipts" in capsys.readouterr().err
    assert not out.parent.exists()


def test_cli_refuses_paths_and_dir_together(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _document, paths = written(tmp_path, clean_receipt(), lossy_receipt())

    assert main(["history", str(paths[0]), str(paths[1]), "--dir", str(tmp_path)]) == 2

    assert "not both" in capsys.readouterr().err


def test_cli_policy_returns_three_on_a_last_pair_increase(tmp_path: Path) -> None:
    _document, paths = written(tmp_path, clean_receipt(), lossy_receipt())

    assert main(["history", *[str(path) for path in paths], "--fail-on-loss-signal-increase"]) == 3


def test_cli_policy_returns_zero_on_a_last_pair_decrease(tmp_path: Path) -> None:
    _document, paths = written(tmp_path, lossy_receipt(), clean_receipt())

    assert main(["history", *[str(path) for path in paths], "--fail-on-loss-signal-increase"]) == 0


def test_cli_policy_reads_only_the_last_pair(tmp_path: Path) -> None:
    """An increase earlier in the series does not decide the exit code."""
    _document, paths = written(tmp_path, clean_receipt(), lossy_receipt(), clean_receipt())

    assert main(["history", *[str(path) for path in paths], "--fail-on-loss-signal-increase"]) == 0


def test_cli_policy_refuses_rather_than_passing_when_it_cannot_look(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 0 here would report "the policy could not look" as "nothing increased".

    `compare` already exits 2 before its policy runs on an incomparable pair.
    This is the same rule for the last adjacent pair of a series.
    """
    _document, paths = written(tmp_path, clean_receipt(), out_of_scope_receipt(tmp_path))

    code = main(["history", *[str(path) for path in paths], "--fail-on-loss-signal-increase"])

    assert code == 2
    assert code != 0
    assert "has nothing to decide" in capsys.readouterr().err


def test_cli_writes_the_document_before_the_policy_decides(tmp_path: Path) -> None:
    """A nonzero exit still leaves the evidence on disk, as `compare` guarantees."""
    _document, paths = written(tmp_path, clean_receipt(), lossy_receipt())
    out = tmp_path / "policy" / "history.json"

    assert (
        main(
            [
                "history",
                *[str(path) for path in paths],
                "--out",
                str(out),
                "--fail-on-loss-signal-increase",
            ]
        )
        == 3
    )

    assert out.is_file()


def test_cli_reads_a_directory(tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    write_receipt(receipts / "1-clean.json", clean_receipt())
    write_receipt(receipts / "2-lossy.json", lossy_receipt())
    out = tmp_path / "history.json"

    assert main(["history", "--dir", str(receipts), "--out", str(out)]) == 0

    document = json.loads(out.read_text(encoding="utf-8"))
    assert cast(dict[str, JsonValue], document["summary"])["receipt_count"] == 2


def test_cli_verify_history_refuses_a_forged_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document, paths = written(tmp_path, clean_receipt(), lossy_receipt())
    forged = json.loads(document.read_text(encoding="utf-8"))
    forged["dimensions"][0]["series"][1]["missing_count"] = 0
    document.write_text(json.dumps(forged), encoding="utf-8")

    assert (
        main(
            [
                "verify-history",
                str(document),
                *[flag for path in paths for flag in ("--receipt", str(path))],
            ]
        )
        == 2
    )

    assert "does not match its source receipts" in capsys.readouterr().err


def test_loading_one_receipt_snapshot_is_what_the_series_is_built_from(tmp_path: Path) -> None:
    """The series verifies each receipt itself; it does not trust the file."""
    path = tmp_path / "receipt.json"
    write_receipt(path, clean_receipt())
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["payload"]["observed_remediation_signals"] = 99
    path.write_text(json.dumps(forged), encoding="utf-8")

    with pytest.raises(ValueError, match="remediation signals contradict"):
        load_receipt_snapshot(path)
