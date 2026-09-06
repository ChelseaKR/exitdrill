import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from exitdrill.canonical import canonical_json_bytes, sha256_bytes
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.receipt import (
    ReceiptError,
    build_receipt,
    load_receipt,
    verify_receipt,
    write_receipt,
)


def _receipt(example_root: Path) -> dict[str, object]:
    result = run_drill(
        load_baseline(example_root / "baseline.json"),
        load_export(example_root / "export.json"),
        example_root / "export-files",
    )
    return build_receipt(
        result,
        claimed_generated_at="2026-07-22T20:00:00Z",
    )  # type: ignore[return-value]


def _rehash(receipt: dict[str, object]) -> None:
    receipt["payload_sha256"] = sha256_bytes(canonical_json_bytes(receipt["payload"]))


def _dimensions(payload: dict[str, object]) -> list[object]:
    value = payload["dimensions"]
    assert isinstance(value, list)
    return cast(list[object], value)


def _first_dimension(payload: dict[str, object]) -> dict[str, object]:
    value = _dimensions(payload)[0]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _replace_first_dimension(payload: dict[str, object]) -> None:
    _dimensions(payload)[0] = "not-an-object"


def test_receipt_checksum_and_untrusted_envelope(example_root: Path) -> None:
    receipt = _receipt(example_root)
    assert verify_receipt(receipt) == receipt["payload_sha256"]  # type: ignore[arg-type]
    assert receipt["schema_version"] == "exitdrill/receipt/v0.3"
    assert receipt["payload"]["schema_version"] == "exitdrill/drill-result/v0.3"  # type: ignore[index]
    assert receipt["envelope"]["trusted_time"] is False  # type: ignore[index]


def test_payload_is_deterministic_outside_envelope(example_root: Path) -> None:
    first = _receipt(example_root)
    result = run_drill(
        load_baseline(example_root / "baseline.json"),
        load_export(example_root / "export.json"),
        example_root / "export-files",
    )
    second = build_receipt(result, claimed_generated_at="2030-01-01T00:00:00Z")
    assert first["payload"] == second["payload"]
    assert first["payload_sha256"] == second["payload_sha256"]
    assert first["envelope"] != second["envelope"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "wrong", "unsupported"),
        ("payload", None, "payload or payload checksum"),
        ("payload_sha256", None, "payload or payload checksum"),
        ("envelope", None, "envelope is missing"),
        (
            "envelope",
            {
                "claimed_generated_at": "2026-07-22T20:00:00Z",
                "signature_status": "signed",
                "trusted_time": False,
            },
            "overstates",
        ),
    ],
)
def test_malformed_receipt_is_rejected(
    example_root: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    receipt = _receipt(example_root)
    receipt[field] = value
    with pytest.raises(ReceiptError, match=message):
        verify_receipt(receipt)  # type: ignore[arg-type]


@pytest.mark.parametrize("receipt", [None, 5, [1, 2, 3], "not a receipt", True])
def test_verify_receipt_rejects_a_non_object_cleanly(receipt: object) -> None:
    # verify_receipt's type hint promises a dict, but it is a public entry
    # point that arbitrary JSON can reach (directly, or via
    # verify_comparison_document's reference/candidate receipts) before
    # anything else has checked its shape. Each of these used to raise an
    # unhandled TypeError from set(value) deep inside _require_exact_fields
    # instead of a clean ReceiptError.
    with pytest.raises(ReceiptError, match="receipt must be a JSON object"):
        verify_receipt(receipt)  # type: ignore[arg-type]


def test_changed_payload_is_rejected(example_root: Path) -> None:
    receipt = _receipt(example_root)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    payload["source_system"] = "Changed synthetic source"
    with pytest.raises(ReceiptError, match="checksum mismatch"):
        verify_receipt(receipt)  # type: ignore[arg-type]


def test_write_and_load_receipt(tmp_path: Path, example_root: Path) -> None:
    receipt = _receipt(example_root)
    path = tmp_path / "nested" / "receipt.json"
    write_receipt(path, receipt)  # type: ignore[arg-type]
    assert load_receipt(path) == receipt


def test_write_rejects_invalid_receipt_before_filesystem_mutation(tmp_path: Path) -> None:
    parent = tmp_path / "not-created"
    path = parent / "receipt.json"
    forged = {"schema_version": "exitdrill/receipt/v0.3"}

    with pytest.raises(ReceiptError, match="missing field"):
        write_receipt(path, forged)  # type: ignore[arg-type]
    assert not parent.exists()
    assert not path.exists()


def test_write_rejects_oversized_valid_receipt_before_filesystem_mutation(
    tmp_path: Path,
    example_root: Path,
) -> None:
    # `drill_id`, not the envelope's claimed time, is the padding site: the
    # claimed time is now required to be offset-aware ISO 8601, and `drill_id`
    # is the remaining unbounded free-text field a valid payload carries.
    receipt = _receipt(example_root)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    payload["drill_id"] = "x" * (2 * 1024 * 1024)
    _rehash(receipt)
    assert verify_receipt(receipt) == receipt["payload_sha256"]  # type: ignore[arg-type]
    parent = tmp_path / "not-created"
    path = parent / "receipt.json"

    with pytest.raises(ReceiptError, match="receipt exceeds the 2 MiB limit"):
        write_receipt(path, receipt)  # type: ignore[arg-type]
    assert not parent.exists()
    assert not path.exists()


def test_write_replaces_output_symlink_without_following_it(
    tmp_path: Path,
    example_root: Path,
) -> None:
    receipt = _receipt(example_root)
    outside = tmp_path / "outside.json"
    outside.write_text("do not overwrite", encoding="utf-8")
    path = tmp_path / "receipt.json"
    path.symlink_to(outside)
    write_receipt(path, receipt)  # type: ignore[arg-type]
    assert outside.read_text(encoding="utf-8") == "do not overwrite"
    assert not path.is_symlink()
    assert load_receipt(path) == receipt


def test_write_cleans_temporary_file_after_replace_failure(
    tmp_path: Path,
    example_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt(example_root)

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr("exitdrill.atomic_write.os.replace", fail_replace)
    with pytest.raises(OSError, match="synthetic"):
        write_receipt(tmp_path / "receipt.json", receipt)  # type: ignore[arg-type]
    assert not list(tmp_path.glob(".receipt.json.*.tmp"))


def test_load_rejects_nonobject_and_oversized(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ReceiptError, match="JSON object"):
        load_receipt(path)
    path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    # The full message, not just "2 MiB": `strict_json` composes it from the
    # noun `load_receipt` supplies, and "2 MiB" alone matched the generic
    # wording too, so nothing observed which noun came out (issue #85).
    with pytest.raises(ReceiptError, match="receipt exceeds the 2 MiB limit"):
        load_receipt(path)


def test_load_accepts_valid_receipt_at_exact_byte_limit(
    tmp_path: Path,
    example_root: Path,
) -> None:
    receipt = _receipt(example_root)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    # Padded through `drill_id` for the reason given on the oversized case:
    # the envelope's claimed time no longer accepts arbitrary text. The
    # rehashed digest is a fixed 64 characters, so growing `drill_id` by one
    # character grows the document by exactly one byte.
    payload["drill_id"] = "x"
    _rehash(receipt)
    max_bytes = 2 * 1024 * 1024
    padding = max_bytes - len(canonical_json_bytes(receipt))
    assert padding > 0
    payload["drill_id"] = "x" * (padding + 1)
    _rehash(receipt)
    document = canonical_json_bytes(receipt)
    assert len(document) == max_bytes
    path = tmp_path / "exact-limit-receipt.json"
    path.write_bytes(document)

    loaded = load_receipt(path)
    assert verify_receipt(loaded) == receipt["payload_sha256"]


def test_load_rejects_non_regular_document_without_blocking(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is unavailable on this platform")
    path = tmp_path / "receipt.fifo"
    os.mkfifo(path)
    with pytest.raises(ReceiptError, match="receipt path is not a regular file"):
        load_receipt(path)


@pytest.mark.parametrize("wrapper", ["trailing_document", "utf8_bom"])
def test_load_rejects_ambiguous_document_wrappers(
    tmp_path: Path,
    example_root: Path,
    wrapper: str,
) -> None:
    document = canonical_json_bytes(_receipt(example_root))
    if wrapper == "trailing_document":
        document += b"{}"
    else:
        document = b"\xef\xbb\xbf" + document
    path = tmp_path / "wrapped-receipt.json"
    path.write_bytes(document)
    with pytest.raises(ReceiptError, match="receipt is not valid JSON"):
        load_receipt(path)


def test_load_rejects_invalid_utf8_receipt_bytes(tmp_path: Path, example_root: Path) -> None:
    """`strict_json`'s UTF-8 rejection is already covered from the loader side.
    This covers it from the receipt side, which is what observes that the
    message names the receipt rather than the generic noun (issue #85)."""
    path = tmp_path / "invalid-utf8-receipt.json"
    path.write_bytes(canonical_json_bytes(_receipt(example_root)) + b"\xff")
    with pytest.raises(ReceiptError, match="receipt is not valid UTF-8"):
        load_receipt(path)


def test_load_rejects_integer_beyond_parser_digit_budget(
    tmp_path: Path,
    example_root: Path,
) -> None:
    document = canonical_json_bytes(_receipt(example_root)).replace(
        b'"observed_remediation_signals":0',
        b'"observed_remediation_signals":' + b"9" * 5000,
    )
    path = tmp_path / "huge-integer-receipt.json"
    path.write_bytes(document)
    with pytest.raises(ReceiptError, match="receipt is not valid JSON"):
        load_receipt(path)


def test_load_rejects_maximally_wide_json_before_semantic_validation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wide-receipt.json"
    path.write_text("[" + ",".join("0" for _ in range(200_000)) + "]", encoding="utf-8")
    with pytest.raises(ReceiptError, match="node limit"):
        load_receipt(path)


def test_load_rejects_duplicate_receipt_key(tmp_path: Path, example_root: Path) -> None:
    receipt = _receipt(example_root)
    content = json.dumps(receipt)
    content = content.replace(
        '"schema_version": "exitdrill/receipt/v0.3"',
        ('"schema_version": "exitdrill/receipt/v0.3", "schema_version": "exitdrill/receipt/v0.3"'),
        1,
    )
    path = tmp_path / "receipt.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ReceiptError, match="duplicate object key"):
        load_receipt(path)


def test_duplicate_key_error_does_not_echo_attacker_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / "receipt.json"
    path.write_text('{"invented-sensitive-key": 1, "invented-sensitive-key": 2}', encoding="utf-8")
    with pytest.raises(ReceiptError) as raised:
        load_receipt(path)
    assert "duplicate object key" in str(raised.value)
    assert "invented-sensitive-key" not in str(raised.value)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_load_rejects_non_finite_receipt_number(
    tmp_path: Path,
    example_root: Path,
    token: str,
) -> None:
    receipt = _receipt(example_root)
    content = json.dumps(receipt).replace(
        '"observed_remediation_signals": 0',
        f'"observed_remediation_signals": {token}',
    )
    path = tmp_path / "receipt.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ReceiptError, match="non-finite"):
        load_receipt(path)


@pytest.mark.parametrize(("context", "mode"), [("receipt", "unknown"), ("receipt", "missing")])
def test_verify_rejects_nonexact_receipt_fields(
    example_root: Path,
    context: str,
    mode: str,
) -> None:
    receipt = _receipt(example_root)
    if mode == "unknown":
        receipt["attacker_extension"] = False
    else:
        receipt.pop("payload_sha256")
    with pytest.raises(ReceiptError, match=f"{context} (has unknown|is missing)"):
        verify_receipt(receipt)  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", ["unknown", "missing"])
def test_verify_rejects_nonexact_envelope_fields(example_root: Path, mode: str) -> None:
    receipt = _receipt(example_root)
    envelope = receipt["envelope"]
    assert isinstance(envelope, dict)
    if mode == "unknown":
        envelope["key_id"] = "misleading"
    else:
        envelope.pop("claimed_generated_at")
    with pytest.raises(ReceiptError, match=r"receipt envelope (has unknown|is missing)"):
        verify_receipt(receipt)  # type: ignore[arg-type]


def test_verify_rejects_non_string_claimed_time(example_root: Path) -> None:
    receipt = _receipt(example_root)
    envelope = receipt["envelope"]
    assert isinstance(envelope, dict)
    envelope["claimed_generated_at"] = None
    with pytest.raises(ReceiptError, match="claimed time"):
        verify_receipt(receipt)  # type: ignore[arg-type]


def test_verify_rejects_empty_claimed_time(example_root: Path) -> None:
    receipt = _receipt(example_root)
    envelope = receipt["envelope"]
    assert isinstance(envelope, dict)
    envelope["claimed_generated_at"] = " "
    with pytest.raises(ReceiptError, match="non-empty"):
        verify_receipt(receipt)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("claimed", "message"),
    [
        ("not a timestamp at all", "must be an ISO 8601 timestamp"),
        # Offset-naive: parseable, but it does not say when.
        ("2026-07-22T20:00:00", "must include a UTC offset"),
        # Surrounding whitespace. `build_receipt` never emits it, so the value
        # is parsed unstripped and this is a rejection, not a normalization.
        (" 2026-07-22T20:00:00Z ", "must be an ISO 8601 timestamp"),
    ],
)
def test_verify_rejects_a_claimed_time_outside_the_shape_build_receipt_emits(
    example_root: Path,
    claimed: str,
    message: str,
) -> None:
    """Issue #83. `--claimed-generated-at "sometime last spring"` used to
    produce a receipt that verified and rendered. Requiring the shape is not a
    trust claim: `signature_status` and `trusted_time` still carry the
    disclaimer, and both are checked separately below."""
    receipt = _receipt(example_root)
    envelope = receipt["envelope"]
    assert isinstance(envelope, dict)
    envelope["claimed_generated_at"] = claimed
    with pytest.raises(ReceiptError, match=f"receipt envelope claimed time {message}"):
        verify_receipt(receipt)  # type: ignore[arg-type]


def test_verify_accepts_a_non_utc_offset_claimed_time(example_root: Path) -> None:
    """Positive control for the case above, and the boundary the parser draws:
    an explicit offset is required, not specifically `Z`."""
    receipt = _receipt(example_root)
    envelope = receipt["envelope"]
    assert isinstance(envelope, dict)
    envelope["claimed_generated_at"] = "2026-07-22T20:00:00+05:30"
    assert verify_receipt(receipt) == receipt["payload_sha256"]  # type: ignore[arg-type]


def test_verify_rejects_a_dimension_below_the_restoration_floor(example_root: Path) -> None:
    """Issue #81. The receipt every dimension of which claims that the export
    was complete, nothing restored, and nothing invalid.

    `evaluator._dimension_result` cannot emit this: it floors `invalid_count`
    at `exported_count - restored_count`, so a dimension the reference model
    refused entirely is a `fail`. Before the floor was re-derived here, this
    receipt verified as `pass` and `render_receipt_report` rendered
    "Structurally restorable" with a Restored column of 0 beside an Exported
    column of 2.
    """
    receipt = _receipt(example_root)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    for raw in _dimensions(payload):
        assert isinstance(raw, dict)
        dimension = cast(dict[str, object], raw)
        assert dimension["exported_count"] != 0
        assert dimension["status"] == "pass"
        dimension["restored_count"] = 0
    _rehash(receipt)

    with pytest.raises(ReceiptError, match=r"dimensions\[0\].invalid_count is below"):
        verify_receipt(receipt)  # type: ignore[arg-type]


def test_verify_accepts_a_dimension_exactly_at_the_restoration_floor(example_root: Path) -> None:
    """Positive control for the case above, and the boundary the floor draws:
    `invalid_count` equal to the shortfall is what the evaluator emits, so it
    has to verify. Written the way the evaluator would write it -- one refused
    row makes the dimension `fail`, which makes the drill not structurally
    restorable and adds one remediation signal."""
    receipt = _receipt(example_root)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    dimension = _first_dimension(payload)
    assert dimension["exported_count"] == 2
    dimension.update({"restored_count": 1, "invalid_count": 1, "status": "fail"})
    payload["overall_status"] = "not_structurally_restorable"
    payload["observed_remediation_signals"] = 1
    _rehash(receipt)

    assert verify_receipt(receipt) == receipt["payload_sha256"]  # type: ignore[arg-type]


def test_verify_rejects_non_finite_in_memory_value(example_root: Path) -> None:
    receipt = _receipt(example_root)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    payload["observed_remediation_signals"] = float("nan")
    with pytest.raises(ReceiptError, match="non-finite"):
        verify_receipt(receipt)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("empty_payload", "missing field"),
        ("unknown_payload_field", "unknown field"),
        ("missing_dimension", "every dimension exactly once"),
        ("duplicate_dimension", "every dimension exactly once"),
        ("invalid_count", "exceeds exported_count"),
        ("contradictory_status", "contradicts its counts"),
        ("contradictory_overall", "overall_status contradicts"),
        ("contradictory_remediation", "remediation signals contradict"),
        ("incomplete_limitations", "trust limitations"),
    ],
)
def test_recomputed_checksum_cannot_hide_invalid_payload(
    example_root: Path,
    mutation: str,
    message: str,
) -> None:
    receipt = _receipt(example_root)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    dimensions = payload["dimensions"]
    assert isinstance(dimensions, list)
    if mutation == "empty_payload":
        receipt["payload"] = {}
    elif mutation == "unknown_payload_field":
        payload["operator_is_trusted"] = True
    elif mutation == "missing_dimension":
        dimensions.pop()
    elif mutation == "duplicate_dimension":
        dimensions[-1] = dimensions[0]
    elif mutation == "invalid_count":
        assert isinstance(dimensions[0], dict)
        dimensions[0]["invalid_count"] = 3
    elif mutation == "contradictory_status":
        assert isinstance(dimensions[0], dict)
        dimensions[0]["status"] = "finding"
    elif mutation == "contradictory_overall":
        payload["overall_status"] = "not_structurally_restorable"
    elif mutation == "contradictory_remediation":
        payload["observed_remediation_signals"] = 4
    else:
        payload["trust_limitations"] = []
    _rehash(receipt)
    with pytest.raises(ReceiptError, match=message):
        verify_receipt(receipt)  # type: ignore[arg-type]


def test_verify_rejects_non_digest_checksum(example_root: Path) -> None:
    receipt = _receipt(example_root)
    receipt["payload_sha256"] = "not-a-digest"
    with pytest.raises(ReceiptError, match="lowercase SHA-256"):
        verify_receipt(receipt)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload.update({"schema_version": "unsupported"}),
            "payload schema",
        ),
        (
            lambda payload: payload.update({"decision_scope": "universal_portability"}),
            "decision scope",
        ),
        (
            lambda payload: payload.update({"baseline_sha256": "wrong"}),
            "lowercase SHA-256",
        ),
        (
            lambda payload: payload.update({"source_system": " "}),
            "non-empty string",
        ),
        (
            lambda payload: payload.update({"dimensions": {}}),
            "dimensions must be an array",
        ),
        (_replace_first_dimension, r"dimensions\[0\] must be an object"),
        (
            lambda payload: _first_dimension(payload).update({"name": "unknown"}),
            "name is unsupported",
        ),
        (
            # Non-string counterpart. All four _enum_value call sites share one
            # isinstance guard, so covering it at only one call site would let a
            # regression specific to any of the other three ship undetected.
            lambda payload: _first_dimension(payload).update({"name": 123}),
            "name is unsupported: expected a string",
        ),
        (
            lambda payload: _first_dimension(payload).update({"coverage": "assumed"}),
            "coverage is unsupported",
        ),
        (
            lambda payload: _first_dimension(payload).update({"coverage": None}),
            "coverage is unsupported: expected a string",
        ),
        (
            lambda payload: _first_dimension(payload).update({"status": "portable"}),
            "status is unsupported",
        ),
        (
            # The more specific match text pins this to the isinstance
            # guard in _enum_value specifically, not just "some exception
            # with 'status is unsupported' in it": the ValueError-catch
            # branch a few lines below raises a shorter message that
            # wouldn't satisfy this match if the guard were removed and
            # DimensionStatus(123) fell through to it instead.
            #
            # The two `status` rows must keep distinct match text. Pytest
            # generates this table's node ids from the message string, so two
            # byte-identical messages would silently renumber each other's node
            # id whenever one is added or removed. Nothing else enforces that,
            # which is the second half of issue #61.
            lambda payload: _first_dimension(payload).update({"status": 123}),
            "status is unsupported: expected a string",
        ),
        (
            lambda payload: _first_dimension(payload).update({"expected_count": -1}),
            "non-negative integer",
        ),
        (
            lambda payload: _first_dimension(payload).update({"missing_count": 3}),
            "exceeds expected_count",
        ),
        (
            lambda payload: _first_dimension(payload).update({"extra_count": 3}),
            "exceeds exported_count",
        ),
        (
            lambda payload: _first_dimension(payload).update({"restored_count": 3}),
            "exceeds exported_count",
        ),
        (
            # A partial shortfall, distinct from the whole-receipt case above:
            # one of the two exported rows was refused by the reference model
            # and the dimension still claims nothing invalid.
            lambda payload: _first_dimension(payload).update({"restored_count": 1}),
            "invalid_count is below the restoration shortfall",
        ),
        (
            lambda payload: _first_dimension(payload).update({"expected_count": 3}),
            "intersection is inconsistent",
        ),
        (
            lambda payload: payload.update({"overall_status": "portable"}),
            "overall_status is unsupported",
        ),
        (
            lambda payload: payload.update({"overall_status": ["not_structurally_restorable"]}),
            "overall_status is unsupported: expected a string",
        ),
        (
            lambda payload: payload.update({"observed_remediation_signals": True}),
            "non-negative integer",
        ),
    ],
)
def test_closed_payload_rejects_each_invalid_semantic_class(
    example_root: Path,
    mutation: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    receipt = _receipt(example_root)
    payload = receipt["payload"]
    assert isinstance(payload, dict)
    mutation(payload)
    _rehash(receipt)
    with pytest.raises(ReceiptError, match=message):
        verify_receipt(receipt)  # type: ignore[arg-type]
