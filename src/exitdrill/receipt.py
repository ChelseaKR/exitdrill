"""Receipt construction and checksum/replay verification."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from exitdrill.canonical import canonical_json_bytes, sha256_bytes
from exitdrill.models import DrillResult, JsonValue
from exitdrill.receipt_validation import PayloadError, validate_payload
from exitdrill.strict_json import StrictJsonError, load_strict_json, validate_json_value

_RECEIPT_KEYS = {"envelope", "payload", "payload_sha256", "schema_version"}
_ENVELOPE_KEYS = {"claimed_generated_at", "signature_status", "trusted_time"}


class ReceiptError(ValueError):
    """Raised when a receipt is malformed or fails verification."""


def build_receipt(
    result: DrillResult,
    *,
    claimed_generated_at: str | None = None,
) -> dict[str, JsonValue]:
    """Create a deterministic payload inside an explicitly untrusted envelope."""
    payload = result.payload()
    return {
        "envelope": {
            "claimed_generated_at": claimed_generated_at
            or datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
            "signature_status": "not_signed",
            "trusted_time": False,
        },
        "payload": payload,
        "payload_sha256": sha256_bytes(canonical_json_bytes(payload)),
        "schema_version": "exitdrill/receipt/v0.2",
    }


def write_receipt(path: Path, receipt: dict[str, JsonValue]) -> None:
    """Atomically write a receipt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = canonical_json_bytes(receipt) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_receipt(path: Path) -> dict[str, JsonValue]:
    """Load a bounded receipt."""
    try:
        raw, _source_sha256 = load_strict_json(
            path,
            max_bytes=2 * 1024 * 1024,
            size_label="2 MiB",
        )
    except StrictJsonError as exc:
        message = str(exc).replace("document exceeds", "receipt exceeds", 1)
        raise ReceiptError(message) from exc
    if not isinstance(raw, dict):
        raise ReceiptError("receipt must be a JSON object")
    return cast(dict[str, JsonValue], raw)


def _require_exact_fields(value: dict[str, object], expected: set[str], context: str) -> None:
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise ReceiptError(f"{context} has unknown field(s): {', '.join(unknown)}")
    if missing:
        raise ReceiptError(f"{context} is missing field(s): {', '.join(missing)}")


def verify_receipt(receipt: dict[str, JsonValue]) -> str:
    """Verify receipt self-consistency without claiming authenticity."""
    try:
        validate_json_value(receipt)
    except StrictJsonError as exc:
        raise ReceiptError(str(exc)) from exc
    _require_exact_fields(cast(dict[str, object], receipt), _RECEIPT_KEYS, "receipt")
    if receipt.get("schema_version") != "exitdrill/receipt/v0.2":
        raise ReceiptError("unsupported receipt schema")
    payload = receipt.get("payload")
    claimed_hash = receipt.get("payload_sha256")
    envelope = receipt.get("envelope")
    if not isinstance(payload, dict) or not isinstance(claimed_hash, str):
        raise ReceiptError("receipt payload or payload checksum is missing")
    if not isinstance(envelope, dict):
        raise ReceiptError("receipt envelope is missing")
    _require_exact_fields(cast(dict[str, object], envelope), _ENVELOPE_KEYS, "receipt envelope")
    claimed_time = envelope.get("claimed_generated_at")
    if not isinstance(claimed_time, str) or not claimed_time.strip():
        raise ReceiptError("receipt envelope claimed time must be a non-empty string")
    if (
        envelope.get("signature_status") != "not_signed"
        or envelope.get("trusted_time") is not False
    ):
        raise ReceiptError("receipt envelope overstates its trust status")
    try:
        validate_payload(payload)
    except PayloadError as exc:
        raise ReceiptError(str(exc)) from exc
    if not _is_sha256(claimed_hash):
        raise ReceiptError("receipt payload checksum must be a lowercase SHA-256 digest")
    actual_hash = sha256_bytes(canonical_json_bytes(payload))
    if actual_hash != claimed_hash:
        raise ReceiptError("receipt payload checksum mismatch")
    return actual_hash


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
