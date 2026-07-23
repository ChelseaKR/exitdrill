"""Bounded timestamp parsing for drill chronology checks."""

from __future__ import annotations

from datetime import datetime


class TimestampError(ValueError):
    """Raised when a timestamp is not an offset-aware ISO 8601 value."""


def parse_timestamp(value: str, context: str) -> datetime:
    """Parse an ISO 8601 timestamp and require an explicit UTC offset."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TimestampError(f"{context} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TimestampError(f"{context} must include a UTC offset")
    return parsed
