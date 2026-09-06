"""A timeline over a series of same-scope receipts, reduced and never smoothed.

`compare` answers "did this export lose more than that one?" for exactly two
receipts. An organisation rehearsing an exit repeats the drill: after each
vendor fix, each schema change, each quarter. Reading that as N-1 hand-chained
comparisons is work, and work nobody does is evidence nobody has.

This is a pure reduction over verified receipts. Nothing here averages, trends,
forecasts, scores, or attributes a cause, and nothing reads an envelope
timestamp: the order is the caller's argument order, and the document says so.

The one thing it adds beyond `comparison.py` is a series scope. The first
receipt sets it, under exactly the comparability rules `compare` enforces, and
every later receipt either belongs to that scope or does not. One that does not
is rendered as a gap carrying its reason codes -- never as zero counts, which
would publish "we could not measure this" as "we measured nothing missing".
For the same reason an adjacent pair touching a gap carries no direction at
all, rather than a direction computed from one side.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from exitdrill.atomic_write import write_bounded_file
from exitdrill.canonical import canonical_json_bytes
from exitdrill.comparison import (
    DimensionSnapshot,
    ReceiptSnapshot,
    load_receipt_snapshot,
    snapshot_receipt,
)
from exitdrill.models import Coverage, Dimension, JsonValue
from exitdrill.strict_json import StrictJsonError, load_strict_json

_HISTORY_SCHEMA_RESOURCE = "receipt-history-v0.1.schema.json"
_MAX_HISTORY_BYTES = 2 * 1024 * 1024

HISTORY_SCHEMA_VERSION = "exitdrill/history/v0.1"

_HISTORY_LIMITATIONS = (
    "inputs_are_unsigned_and_unauthenticated",
    "history_output_is_unsigned_and_unauthenticated",
    "aggregate_only_cannot_observe_record_identity_churn",
    "series_order_is_caller_supplied_unverified",
    "does_not_bind_export_generation_or_evaluator_version",
    "does_not_prove_operational_equivalence",
    "adjacent_directions_are_observations_not_a_trend",
)


class HistoryError(ValueError):
    """Raised when a receipt series cannot be reduced, or a document cannot be trusted."""


def _scope_of(snapshot: ReceiptSnapshot) -> dict[str, JsonValue]:
    """The fields every receipt in one series must agree on, taken from the first."""
    return {
        "baseline_sha256": snapshot.baseline_sha256,
        "decision_scope": snapshot.decision_scope,
        "drill_id": snapshot.drill_id,
        "receipt_schema_version": snapshot.receipt_schema_version,
        "result_schema_version": snapshot.result_schema_version,
        "source_system": snapshot.source_system,
        "trust_limitations": cast(JsonValue, list(snapshot.trust_limitations)),
    }


def _scope_reasons(reference: ReceiptSnapshot, candidate: ReceiptSnapshot) -> list[str]:
    """Why `candidate` is not in `reference`'s series, in the reason codes `compare` uses.

    Deliberately the same predicates and the same code strings as
    `comparison._scope`, so "in this series" and "comparable with the first
    receipt" cannot drift apart into two different questions.
    """
    reference_dimensions = reference.dimensions_by_name
    candidate_dimensions = candidate.dimensions_by_name
    checks = (
        (reference.baseline_sha256 == candidate.baseline_sha256, "baseline_sha256_changed"),
        (reference.drill_id == candidate.drill_id, "drill_id_changed"),
        (reference.source_system == candidate.source_system, "source_system_changed"),
        (
            reference.receipt_schema_version == candidate.receipt_schema_version,
            "receipt_schema_version_changed",
        ),
        (
            reference.result_schema_version == candidate.result_schema_version,
            "result_schema_version_changed",
        ),
        (reference.decision_scope == candidate.decision_scope, "decision_scope_changed"),
        (
            all(
                reference_dimensions[item].coverage is candidate_dimensions[item].coverage
                for item in Dimension
            ),
            "dimension_coverage_changed",
        ),
        (
            all(
                reference_dimensions[item].expected_count
                == candidate_dimensions[item].expected_count
                for item in Dimension
            ),
            "dimension_expected_counts_changed",
        ),
        (reference.trust_limitations == candidate.trust_limitations, "trust_limitations_changed"),
    )
    return [reason for holds, reason in checks if not holds]


def _series_entry(
    position: int, snapshot: ReceiptSnapshot, reasons: list[str]
) -> dict[str, JsonValue]:
    return {
        "export_sha256": snapshot.export_sha256,
        "in_scope": not reasons,
        "out_of_scope_reasons": cast(list[JsonValue], reasons),
        "payload_sha256": snapshot.payload_sha256,
        "position": position,
    }


def _observation(position: int, dimension: DimensionSnapshot | None) -> dict[str, JsonValue]:
    """One cell of the timeline: a measurement, or an explicit gap.

    A gap carries no counts at all. Emitting zeros here is the failure this
    project names first: a value nobody measured, published in the column a
    reader reads as a measurement.
    """
    if dimension is None:
        return {"observed": False, "position": position}
    return {
        "exported_count": dimension.exported_count,
        "extra_count": dimension.extra_count,
        "invalid_count": dimension.invalid_count,
        "missing_count": dimension.missing_count,
        "observed": True,
        "position": position,
        "restored_count": dimension.restored_count,
        "status": dimension.status.value,
    }


def _dimension_series(
    name: Dimension,
    scope_dimension: DimensionSnapshot,
    entries: list[ReceiptSnapshot | None],
) -> dict[str, JsonValue]:
    return {
        "coverage": scope_dimension.coverage.value,
        "expected_count": scope_dimension.expected_count,
        "name": name.value,
        "series": cast(
            list[JsonValue],
            [
                _observation(
                    position,
                    None if snapshot is None else snapshot.dimensions_by_name[name],
                )
                for position, snapshot in enumerate(entries)
            ],
        ),
    }


def _loss_signal_total(snapshot: ReceiptSnapshot, name: Dimension) -> int:
    dimension = snapshot.dimensions_by_name[name]
    return dimension.missing_count + dimension.invalid_count


def _direction(increases: list[str], decreases: list[str], uncertain: bool) -> str:
    if uncertain:
        return "uncertain"
    if increases and decreases:
        return "mixed_loss_signal_change"
    if increases:
        return "observed_loss_signals_increased"
    if decreases:
        return "observed_loss_signals_decreased"
    return "no_observed_loss_signal_change"


def _transition(
    position: int,
    earlier: ReceiptSnapshot | None,
    later: ReceiptSnapshot | None,
    reasons: list[str],
) -> dict[str, JsonValue]:
    """One adjacent pair. A pair touching a gap carries no direction, not a neutral one."""
    if earlier is None or later is None:
        return {
            "comparable": False,
            "from_position": position,
            "not_comparable_reasons": cast(list[JsonValue], reasons),
            "to_position": position + 1,
        }
    increases: list[str] = []
    decreases: list[str] = []
    uncertain = False
    for name in Dimension:
        if earlier.dimensions_by_name[name].coverage is not Coverage.COMPLETE:
            uncertain = True
        delta = _loss_signal_total(later, name) - _loss_signal_total(earlier, name)
        if delta > 0:
            increases.append(name.value)
        elif delta < 0:
            decreases.append(name.value)
    return {
        "comparable": True,
        "direction": _direction(increases, decreases, uncertain),
        "from_position": position,
        "observed_loss_signal_decreases": cast(list[JsonValue], decreases),
        "observed_loss_signal_increases": cast(list[JsonValue], increases),
        "to_position": position + 1,
    }


def _gap_reasons(entries: list[ReceiptSnapshot | None], all_reasons: list[list[str]]) -> list[str]:
    return sorted({reason for reasons in all_reasons for reason in reasons})


def _build_history(snapshots: tuple[ReceiptSnapshot, ...]) -> dict[str, JsonValue]:
    """Reduce a verified series to a closed timeline document. Pure and total."""
    first = snapshots[0]
    reasons_by_position = [_scope_reasons(first, snapshot) for snapshot in snapshots]
    in_scope: list[ReceiptSnapshot | None] = [
        snapshot if not reasons else None
        for snapshot, reasons in zip(snapshots, reasons_by_position, strict=True)
    ]
    scope_dimensions = first.dimensions_by_name
    transitions = [
        _transition(
            position,
            in_scope[position],
            in_scope[position + 1],
            sorted(set(reasons_by_position[position]) | set(reasons_by_position[position + 1])),
        )
        for position in range(len(snapshots) - 1)
    ]
    return {
        "decision_scope": "offline_aggregate_receipt_series_only",
        "dimensions": cast(
            list[JsonValue],
            [_dimension_series(name, scope_dimensions[name], in_scope) for name in Dimension],
        ),
        "limitations": cast(list[JsonValue], list(_HISTORY_LIMITATIONS)),
        "receipts": cast(
            list[JsonValue],
            [
                _series_entry(position, snapshot, reasons)
                for position, (snapshot, reasons) in enumerate(
                    zip(snapshots, reasons_by_position, strict=True)
                )
            ],
        ),
        "ordering_basis": "caller_supplied_unverified",
        "schema_version": HISTORY_SCHEMA_VERSION,
        "scope": _scope_of(first),
        "summary": {
            "gap_positions": cast(
                list[JsonValue],
                [position for position, item in enumerate(in_scope) if item is None],
            ),
            "gap_reasons": cast(list[JsonValue], _gap_reasons(in_scope, reasons_by_position)),
            "in_scope_count": sum(1 for item in in_scope if item is not None),
            "receipt_count": len(snapshots),
        },
        "transitions": cast(list[JsonValue], transitions),
    }


@lru_cache(maxsize=1)
def _history_schema_validator() -> Draft202012Validator:
    """Load and compile the packaged public history schema, wheel or checkout."""
    packaged = files("exitdrill").joinpath("schemas", _HISTORY_SCHEMA_RESOURCE)
    try:
        schema_bytes = packaged.read_bytes()
    except FileNotFoundError:
        schema_bytes = (
            Path(__file__).parents[2] / "schemas" / _HISTORY_SCHEMA_RESOURCE
        ).read_bytes()
    schema = json.loads(schema_bytes)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise HistoryError("packaged history schema is invalid") from exc
    return Draft202012Validator(schema)


def _validate_history_schema(document: dict[str, JsonValue]) -> None:
    """Require closed-structure conformance to the public history schema.

    Independently maintained from `_build_history`, exactly as the comparison
    schema is from `_build_comparison`, so the two can genuinely disagree and
    the check is not a value compared with itself.
    """
    try:
        _history_schema_validator().validate(document)
    except ValidationError as exc:
        raise HistoryError("history document does not satisfy the public history schema") from exc


def build_history_from_snapshots(
    snapshots: tuple[ReceiptSnapshot, ...],
) -> dict[str, JsonValue]:
    """Reduce two or more verified receipts to a timeline, in the order given."""
    if len(snapshots) < 2:
        raise HistoryError("a history needs at least two receipts, in the order to read them")
    document = _build_history(snapshots)
    _validate_history_schema(document)
    return document


def history_from_files(paths: tuple[Path, ...]) -> dict[str, JsonValue]:
    """Strict-load and verify each receipt file, then reduce them in the order given."""
    return build_history_from_snapshots(tuple(load_receipt_snapshot(path) for path in paths))


def receipt_paths_in_directory(directory: Path) -> tuple[Path, ...]:
    """Every `*.json` in one directory, in filename order.

    Filename order, not modification time and not an envelope timestamp: the
    caller controls it by naming the files, and the same directory always
    reduces to the same document.
    """
    if not directory.is_dir():
        raise HistoryError("receipt directory not found")
    paths = tuple(sorted(item for item in directory.glob("*.json") if item.is_file()))
    if not paths:
        raise HistoryError("no *.json receipts in the directory")
    return paths


def verify_history_document(
    document: dict[str, JsonValue],
    receipts: tuple[dict[str, JsonValue], ...],
) -> None:
    """Verify every field by recomputing the timeline from the source receipts.

    The semantic recomputation runs first, because it gives the precise error
    for an edited count sequence; the schema check runs after as a structural
    net over a document that arrived from outside.
    """
    if len(receipts) < 2:
        raise HistoryError("a history needs at least two receipts, in the order to read them")
    expected = _build_history(tuple(snapshot_receipt(receipt) for receipt in receipts))
    try:
        matches = canonical_json_bytes(document) == canonical_json_bytes(expected)
    except (TypeError, ValueError) as exc:
        raise HistoryError("history document is not valid JSON data") from exc
    if not matches:
        raise HistoryError("history document does not match its source receipts")
    _validate_history_schema(document)


def load_history(path: Path) -> dict[str, JsonValue]:
    """Strict-load one bounded history document without echoing its path."""
    try:
        raw, _source_sha256 = load_strict_json(
            path,
            max_bytes=_MAX_HISTORY_BYTES,
            size_label="2 MiB",
            document_label="history",
        )
    except StrictJsonError as exc:
        raise HistoryError(str(exc)) from exc
    except OSError as exc:
        raise HistoryError("history input could not be read") from exc
    if not isinstance(raw, dict):
        raise HistoryError("history document must be a JSON object")
    return cast(dict[str, JsonValue], raw)


def verify_history_files(
    document_path: Path,
    receipt_paths: tuple[Path, ...],
) -> dict[str, JsonValue]:
    """Strict-load a history document and recompute it from the receipt files."""
    document = load_history(document_path)
    snapshots = tuple(load_receipt_snapshot(path) for path in receipt_paths)
    if len(snapshots) < 2:
        raise HistoryError("a history needs at least two receipts, in the order to read them")
    expected = _build_history(snapshots)
    if canonical_json_bytes(document) != canonical_json_bytes(expected):
        raise HistoryError("history document does not match its source receipts")
    _validate_history_schema(document)
    return document


def write_history(path: Path, document: dict[str, JsonValue]) -> None:
    """Atomically write a bounded canonical history document."""
    write_bounded_file(
        path,
        canonical_json_bytes(document) + b"\n",
        max_bytes=_MAX_HISTORY_BYTES,
        size_message="history exceeds the 2 MiB limit",
        error=HistoryError,
    )


def last_transition(document: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """The final adjacent pair, which is the only one any policy reads."""
    transitions = cast(list[JsonValue], document["transitions"])
    return cast(dict[str, JsonValue], transitions[-1])


def history_last_pair_has_observed_loss_signal_increase(
    document: dict[str, JsonValue],
) -> bool:
    """Whether the last adjacent pair directly observed a missing/invalid increase.

    Only the last pair, and only a directly observed increase, exactly as
    `comparison_has_observed_loss_signal_increase` decides it for two receipts.
    Callers must first establish that the last pair is comparable at all: a
    pair that could not be compared has no answer here, and returning False
    would report "we could not look" as "nothing increased".
    """
    final = last_transition(document)
    return bool(cast(list[JsonValue], final["observed_loss_signal_increases"]))
