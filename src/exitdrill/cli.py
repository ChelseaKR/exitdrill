"""ExitDrill command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from exitdrill.canonical import canonical_json_bytes
from exitdrill.comparison import (
    _comparison_has_observed_loss_signal_increase,
    compare_receipt_files,
)
from exitdrill.evaluator import DrillError, run_drill
from exitdrill.exercise import ExercisePlanError, load_exercise_plan
from exitdrill.loader import PackageError, load_baseline, load_export
from exitdrill.models import JsonValue, OverallStatus
from exitdrill.receipt import (
    ReceiptError,
    build_receipt,
    load_receipt,
    verify_receipt,
    write_receipt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exitdrill",
        description="Run structural recovery drills for leaving SaaS systems.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate a baseline and export package")
    validate.add_argument("baseline", type=Path)
    validate.add_argument("export", type=Path)
    validate_exercise = commands.add_parser(
        "validate-exercise",
        help="validate a synthetic-only future target exercise plan",
    )
    validate_exercise.add_argument("plan", type=Path)
    drill = commands.add_parser("drill", help="compare, restore, and issue a receipt")
    drill.add_argument("baseline", type=Path)
    drill.add_argument("export", type=Path)
    drill.add_argument("--attachment-root", type=Path, required=True)
    drill.add_argument("--out", type=Path, required=True)
    drill.add_argument("--claimed-generated-at")
    verify = commands.add_parser("verify", help="verify a receipt, optionally by replay")
    verify.add_argument("receipt", type=Path)
    verify.add_argument("--baseline", type=Path)
    verify.add_argument("--export", type=Path)
    verify.add_argument("--attachment-root", type=Path)
    compare = commands.add_parser(
        "compare",
        help="compare aggregate evidence in two verified receipts",
    )
    compare.add_argument("reference", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument(
        "--fail-on-loss-signal-increase",
        action="store_true",
        help="return 3 for a comparable observed aggregate missing/invalid increase",
    )
    return parser


def _print_json(value: dict[str, JsonValue]) -> None:
    sys.stdout.buffer.write(canonical_json_bytes(value) + b"\n")


def _validate(baseline_path: Path, export_path: Path) -> int:
    baseline = load_baseline(baseline_path)
    package = load_export(export_path)
    if baseline.drill_id != package.drill_id or baseline.source_system != package.source_system:
        raise DrillError("baseline and export identities do not match")
    _print_json(
        {
            "baseline_sha256": baseline.source_sha256,
            "drill_id": baseline.drill_id,
            "export_sha256": package.source_sha256,
            "status": "valid",
        }
    )
    return 0


def _drill(
    baseline_path: Path,
    export_path: Path,
    attachment_root: Path,
    out: Path,
    claimed_generated_at: str | None,
) -> int:
    result = run_drill(
        load_baseline(baseline_path),
        load_export(export_path),
        attachment_root,
    )
    receipt = build_receipt(result, claimed_generated_at=claimed_generated_at)
    write_receipt(out, receipt)
    _print_json(
        {
            "observed_remediation_signals": result.payload()["observed_remediation_signals"],
            "overall_status": result.overall_status.value,
            "payload_sha256": receipt["payload_sha256"],
            "receipt": str(out),
        }
    )
    return (
        0
        if result.overall_status
        in {
            OverallStatus.STRUCTURALLY_RESTORABLE,
            OverallStatus.STRUCTURALLY_RESTORABLE_WITH_FINDINGS,
        }
        else 2
    )


def _validate_exercise(path: Path) -> int:
    plan = load_exercise_plan(path)
    _print_json(
        {
            "decision_scope": "plan_only_no_target_execution",
            "exercise_id": plan.exercise_id,
            "source_system": plan.source_system,
            "status": "synthetic_protocol_valid",
            "target_system": plan.target_system,
        }
    )
    return 0


def _verify(
    receipt_path: Path,
    baseline_path: Path | None,
    export_path: Path | None,
    attachment_root: Path | None,
) -> int:
    receipt = load_receipt(receipt_path)
    payload_sha256 = verify_receipt(receipt)
    replayed = False
    replay_args = (baseline_path, export_path, attachment_root)
    if any(item is not None for item in replay_args) and not all(
        item is not None for item in replay_args
    ):
        raise ReceiptError("--baseline, --export, and --attachment-root must be supplied together")
    if baseline_path is not None and export_path is not None and attachment_root is not None:
        fresh = run_drill(
            load_baseline(baseline_path),
            load_export(export_path),
            attachment_root,
        )
        if receipt["payload"] != fresh.payload():
            raise ReceiptError("receipt payload does not match a fresh drill replay")
        replayed = True
    _print_json(
        {
            "payload_sha256": payload_sha256,
            "replayed": replayed,
            "status": "replay_verified" if replayed else "checksum_self_consistent",
        }
    )
    return 0


def _compare(
    reference_path: Path,
    candidate_path: Path,
    *,
    fail_on_loss_signal_increase: bool,
) -> int:
    result = compare_receipt_files(reference_path, candidate_path)
    _print_json(result)
    if result["comparability"] != "comparable":
        return 2
    if fail_on_loss_signal_increase and _comparison_has_observed_loss_signal_increase(result):
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI with bounded failures."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            return _validate(args.baseline, args.export)
        if args.command == "drill":
            return _drill(
                args.baseline,
                args.export,
                args.attachment_root,
                args.out,
                args.claimed_generated_at,
            )
        if args.command == "validate-exercise":
            return _validate_exercise(args.plan)
        if args.command == "verify":
            return _verify(
                args.receipt,
                args.baseline,
                args.export,
                args.attachment_root,
            )
        if args.command == "compare":
            return _compare(
                args.reference,
                args.candidate,
                fail_on_loss_signal_increase=args.fail_on_loss_signal_increase,
            )
    except (
        DrillError,
        ExercisePlanError,
        PackageError,
        ReceiptError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"exitdrill: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
