"""Plain-language narration of one verified receipt, for an outside reader.

A receipt is correct and closed, and it is also a dense JSON document whose
limitation strings are snake_case codes. The next milestone for this project is
not code: it is an outside person running the demo and saying whether the
receipt answers their exit question (issue #51). This module raises the odds
that walkthrough succeeds without changing a single claim.

Every sentence is derived from a receipt field or from `wording.py`, the one
table the HTML report draws its prose from too, so narration cannot say more
than the receipt does and cannot disagree with the report. Nothing here reads
the envelope's claimed time, invents a cause, recommends a remedy, or aggregates
the dimensions into a score.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from exitdrill.models import JsonValue
from exitdrill.receipt import load_receipt, verify_receipt
from exitdrill.wording import (
    COVERAGE_SENTENCES,
    DIMENSION_LABELS,
    DIMENSION_NOUNS,
    DIMENSION_QUESTIONS,
    LIMITATION_SENTENCES,
    OVERALL_SENTENCES,
    STATUS_LABELS,
    counted,
    label,
    were,
)

NARRATION_SCHEMA_VERSION = "exitdrill/receipt-narration/v0.1"

_CONTEXT_SENTENCES = (
    "A baseline is a separately captured record of what the source system held, "
    "with an explicit statement of how much of each kind of evidence it could "
    "account for.",
    "An export is the package the vendor gave you, normalized into a neutral "
    "shape without running any code the export supplied.",
    "The drill loads the export into a neutral reference model and compares it "
    "with the baseline, one kind of evidence at a time. An export cannot prove "
    "its own completeness, which is why the baseline is required.",
)

_NEXT_STEP_SENTENCES = (
    "Replay it: `exitdrill verify RECEIPT --baseline ... --export ... "
    "--attachment-root ...` re-runs the whole drill and requires the same "
    "payload, so you do not have to trust the numbers below.",
    "Compare it: `exitdrill compare REFERENCE CANDIDATE` states what changed "
    "between this receipt and another of the same scope, without ranking them.",
    "Check the digests: the baseline and export SHA-256 values below are of the "
    "files this drill read. Hash the files you were given and compare.",
)


def _fail_sentence(nouns: tuple[str, str], unaccounted: int, expected: int) -> str:
    return (
        f"{unaccounted} of {counted(expected, nouns)} could not be accounted for, "
        "so this dimension fails."
    )


def _indeterminate_sentence(coverage: str) -> str:
    # Deliberately never says "passed", not even to deny it. An indeterminate
    # dimension is one the drill cannot rule on, and a sentence that reaches for
    # the word invites a reader to carry it away.
    return (
        f"Baseline coverage for this dimension is {coverage}, meaning "
        f"{label(COVERAGE_SENTENCES, coverage)}, so this dimension is indeterminate: "
        "the drill cannot say whether the evidence is whole."
    )


def _finding_sentence(nouns: tuple[str, str], extra: int) -> str:
    return (
        f"Nothing was missing or invalid, but the export carried {counted(extra, nouns)} "
        "the baseline did not declare, so this dimension is a finding rather than a "
        "clean result."
    )


def _pass_sentence() -> str:
    return (
        "Nothing declared was missing or invalid, and the export carried nothing the "
        "baseline did not declare, so this dimension passes."
    )


def _conclusion(
    status: str,
    nouns: tuple[str, str],
    coverage: str,
    counts: dict[str, int],
) -> str:
    """One sentence per dimension state, in the order the result algebra decides.

    The order matters and mirrors `models.classify_dimension_status`: missing or
    invalid evidence decides `fail` before coverage is consulted, so a dimension
    that failed is never narrated as a coverage problem.
    """
    if status == "fail":
        return _fail_sentence(
            nouns,
            counts["missing_count"] + counts["invalid_count"],
            counts["expected_count"],
        )
    if status == "indeterminate":
        return _indeterminate_sentence(coverage)
    if status == "finding":
        return _finding_sentence(nouns, counts["extra_count"])
    return _pass_sentence()


def _dimension_narration(raw: dict[str, JsonValue]) -> dict[str, JsonValue]:
    name = cast(str, raw["name"])
    nouns = DIMENSION_NOUNS[name]
    status = cast(str, raw["status"])
    coverage = cast(str, raw["coverage"])
    counts = {
        key: cast(int, raw[key])
        for key in (
            "expected_count",
            "exported_count",
            "restored_count",
            "missing_count",
            "extra_count",
            "invalid_count",
        )
    }
    return {
        "conclusion": _conclusion(status, nouns, coverage, counts),
        "denominator": (
            f"The baseline declared {counted(counts['expected_count'], nouns)}. Its coverage "
            f"for this dimension is {coverage}, meaning "
            f"{label(COVERAGE_SENTENCES, coverage)}."
        ),
        "found": (
            f"The export carried {counted(counts['exported_count'], nouns)}. "
            f"{counts['restored_count']} loaded into the neutral reference model; "
            f"{counts['missing_count']} {were(counts['missing_count'])} missing, "
            f"{counts['invalid_count']} {were(counts['invalid_count'])} invalid, and "
            f"{counts['extra_count']} {were(counts['extra_count'])} not declared by "
            "the baseline."
        ),
        "name": name,
        "question": label(DIMENSION_QUESTIONS, name),
        "status": status,
        "status_label": label(STATUS_LABELS, status),
        "title": label(DIMENSION_LABELS, name),
    }


def narrate_receipt(receipt: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Verify a receipt, then state in sentences exactly what it already says."""
    payload_sha256 = verify_receipt(receipt)
    payload = cast(dict[str, JsonValue], receipt["payload"])
    overall_status = cast(str, payload["overall_status"])
    dimensions = [
        _dimension_narration(cast(dict[str, JsonValue], raw))
        for raw in cast(list[JsonValue], payload["dimensions"])
    ]
    signals = cast(int, payload["observed_remediation_signals"])
    return {
        "context": cast(JsonValue, list(_CONTEXT_SENTENCES)),
        "decision_scope": "verified_aggregate_receipt_narration_only",
        "dimensions": cast(JsonValue, dimensions),
        "next_steps": cast(JsonValue, list(_NEXT_STEP_SENTENCES)),
        "overall": {
            "does_not_mean": cast(
                JsonValue,
                [
                    label(LIMITATION_SENTENCES, cast(str, item))
                    for item in cast(list[JsonValue], payload["trust_limitations"])
                ],
            ),
            "meaning": label(OVERALL_SENTENCES, overall_status),
            "signals": (
                "Across all five dimensions the drill observed "
                f"{counted(signals, ('loss signal', 'loss signals'))}, counting each "
                "missing and each invalid item once."
            ),
            "status": overall_status,
            "status_label": label(STATUS_LABELS, overall_status),
        },
        "schema_version": NARRATION_SCHEMA_VERSION,
        "subject": {
            "baseline_sha256": payload["baseline_sha256"],
            "drill_id": payload["drill_id"],
            "export_sha256": payload["export_sha256"],
            "payload_sha256": payload_sha256,
            "source_system": payload["source_system"],
        },
    }


def _block(heading: str, lines: list[str]) -> list[str]:
    return [heading, *(f"  {line}" for line in lines), ""]


def render_narration_text(narration: dict[str, JsonValue]) -> str:
    """Render one narration as plain text, deterministically and offline."""
    subject = cast(dict[str, JsonValue], narration["subject"])
    overall = cast(dict[str, JsonValue], narration["overall"])
    lines: list[str] = [
        f"ExitDrill receipt for {subject['source_system']} (drill {subject['drill_id']})",
        "",
    ]
    lines += _block("What this is", list(cast(list[str], narration["context"])))
    lines += _block(
        "The result",
        [
            cast(str, overall["status_label"]),
            cast(str, overall["meaning"]),
            cast(str, overall["signals"]),
        ],
    )
    lines += _block("What it does not mean", cast(list[str], overall["does_not_mean"]))
    for raw in cast(list[JsonValue], narration["dimensions"]):
        entry = cast(dict[str, JsonValue], raw)
        lines += _block(
            f"{entry['title']}: {entry['status_label']}",
            [
                cast(str, entry["question"]),
                cast(str, entry["denominator"]),
                cast(str, entry["found"]),
                cast(str, entry["conclusion"]),
            ],
        )
    lines += _block("What you can do next", list(cast(list[str], narration["next_steps"])))
    lines += _block(
        "Digests",
        [
            f"payload   {subject['payload_sha256']}",
            f"baseline  {subject['baseline_sha256']}",
            f"export    {subject['export_sha256']}",
        ],
    )
    return "\n".join(lines).rstrip() + "\n"


def narrate_receipt_file(path: Path) -> dict[str, JsonValue]:
    """Strict-load a bounded receipt and narrate it, or fail without narrating."""
    return narrate_receipt(load_receipt(path))
