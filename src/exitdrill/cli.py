"""ExitDrill command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from exitdrill import __version__
from exitdrill.canonical import canonical_json_bytes
from exitdrill.civicrm_target_canary import (
    CiviCRMTargetCanaryError,
    normalize_civicrm_target_canary,
    verify_civicrm_evidence_index,
)
from exitdrill.comparison import (
    ComparisonError,
    compare_receipt_files,
    comparison_has_observed_loss_signal_increase,
    verify_comparison_files,
    write_comparison,
)
from exitdrill.directus_canary import DirectusCanaryError, normalize_directus_canary
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
from exitdrill.report import ReportError, render_receipt_file, write_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exitdrill",
        description="Run structural recovery drills for leaving SaaS systems.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
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
    compare.add_argument(
        "--out",
        type=Path,
        help="atomically write the comparison document here instead of stdout",
    )
    verify_comparison = commands.add_parser(
        "verify-comparison",
        help="recompute a comparison document from both source receipts",
    )
    verify_comparison.add_argument("comparison", type=Path)
    verify_comparison.add_argument("--reference", type=Path, required=True)
    verify_comparison.add_argument("--candidate", type=Path, required=True)
    report = commands.add_parser(
        "report",
        help="render an accessible offline report from a verified receipt",
    )
    report.add_argument("receipt", type=Path)
    report.add_argument("--out", type=Path, required=True)
    normalize_directus = commands.add_parser(
        "normalize-directus-canary",
        help="verify and normalize the bounded Directus 11.17.4 canary bundle",
    )
    normalize_directus.add_argument("manifest", type=Path)
    normalize_directus.add_argument("--out-dir", type=Path, required=True)
    normalize_civicrm = commands.add_parser(
        "normalize-civicrm-target-canary",
        help="verify and normalize the bounded CiviCRM 6.16.2 target read-back bundle",
    )
    normalize_civicrm.add_argument("manifest", type=Path)
    normalize_civicrm.add_argument("--out-dir", type=Path, required=True)
    verify_civicrm_index = commands.add_parser(
        "verify-civicrm-evidence-index",
        help="verify the bounded CiviCRM evidence catalog and artifact bindings",
    )
    verify_civicrm_index.add_argument("index", type=Path)
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
    out: Path | None,
) -> int:
    result = compare_receipt_files(reference_path, candidate_path)
    if out is None:
        _print_json(result)
    else:
        write_comparison(out, result)
        _print_json(
            {
                "comparability": result["comparability"],
                "comparison": str(out),
                "decision_scope": "offline_aggregate_receipt_change_only",
                "status": "comparison_written",
            }
        )
    if result["comparability"] != "comparable":
        return 2
    if fail_on_loss_signal_increase and comparison_has_observed_loss_signal_increase(result):
        return 3
    return 0


def _verify_comparison(
    comparison_path: Path,
    reference_path: Path,
    candidate_path: Path,
) -> int:
    comparison = verify_comparison_files(comparison_path, reference_path, candidate_path)
    reference = cast(dict[str, JsonValue], comparison["reference"])
    candidate = cast(dict[str, JsonValue], comparison["candidate"])
    _print_json(
        {
            "candidate_payload_sha256": candidate["payload_sha256"],
            "comparability": comparison["comparability"],
            "decision_scope": "offline_aggregate_receipt_change_only",
            "reference_payload_sha256": reference["payload_sha256"],
            "status": "recomputation_verified",
        }
    )
    return 0


def _report(receipt_path: Path, out: Path) -> int:
    document = render_receipt_file(receipt_path)
    write_report(out, document)
    _print_json(
        {
            "decision_scope": "verified_aggregate_receipt_report_only",
            "report": str(out),
            "status": "report_written",
        }
    )
    return 0


def _run_canary_command(args: argparse.Namespace) -> int:
    if args.command == "normalize-directus-canary":
        _print_json(normalize_directus_canary(args.manifest, args.out_dir))
        return 0
    if args.command == "normalize-civicrm-target-canary":
        _print_json(normalize_civicrm_target_canary(args.manifest, args.out_dir))
        return 0
    if args.command == "verify-civicrm-evidence-index":
        _print_json(verify_civicrm_evidence_index(args.index))
        return 0
    return 2


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
                out=args.out,
            )
        if args.command == "verify-comparison":
            return _verify_comparison(args.comparison, args.reference, args.candidate)
        if args.command == "report":
            return _report(args.receipt, args.out)
        return _run_canary_command(args)
    except (
        CiviCRMTargetCanaryError,
        ComparisonError,
        DirectusCanaryError,
        DrillError,
        ExercisePlanError,
        PackageError,
        ReceiptError,
        ReportError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"exitdrill: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
