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
from exitdrill.explain import narrate_receipt_file, render_narration_text
from exitdrill.history import (
    HistoryError,
    history_from_files,
    history_last_pair_has_observed_loss_signal_increase,
    last_transition,
    receipt_paths_in_directory,
    verify_history_files,
    write_history,
)
from exitdrill.loader import PackageError, load_baseline, load_export
from exitdrill.models import JsonValue, OverallStatus
from exitdrill.receipt import (
    ReceiptError,
    build_receipt,
    load_receipt,
    verify_receipt,
    write_receipt,
)
from exitdrill.report import (
    ReportError,
    document_kind,
    render_comparison_file,
    render_history_file,
    render_receipt_file,
    write_report,
)
from exitdrill.schemas import (
    PUBLIC_SCHEMA_NAMES,
    SchemaResourceError,
    read_schema_bytes,
)


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
    explain = commands.add_parser(
        "explain",
        help="narrate a verified receipt in plain language for an outside reader",
    )
    explain.add_argument("receipt", type=Path)
    explain.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit the same narration as a canonical JSON document",
    )
    history = commands.add_parser(
        "history",
        help="line up a series of same-scope receipts as a timeline",
    )
    history.add_argument("receipts", type=Path, nargs="*")
    history.add_argument(
        "--dir",
        dest="directory",
        type=Path,
        help="read every *.json receipt in this directory, in filename order",
    )
    history.add_argument(
        "--fail-on-loss-signal-increase",
        action="store_true",
        help="return 3 for an observed aggregate missing/invalid increase in the last pair",
    )
    history.add_argument(
        "--out",
        type=Path,
        help="atomically write the history document here instead of stdout",
    )
    verify_history = commands.add_parser(
        "verify-history",
        help="recompute a history document from its source receipts",
    )
    verify_history.add_argument("history", type=Path)
    verify_history.add_argument(
        "--receipt",
        dest="receipts",
        type=Path,
        action="append",
        help="one source receipt, repeated in the order the history was built from",
    )
    report = commands.add_parser(
        "report",
        help="render an accessible offline report from a verified receipt or comparison",
    )
    report.add_argument("document", type=Path)
    report.add_argument("--out", type=Path, required=True)
    report.add_argument(
        "--reference",
        type=Path,
        help="reference receipt, required when the document is a comparison",
    )
    report.add_argument(
        "--candidate",
        type=Path,
        help="candidate receipt, required when the document is a comparison",
    )
    report.add_argument(
        "--receipt",
        dest="receipts",
        type=Path,
        action="append",
        help="one source receipt, repeated in series order when the document is a history",
    )
    schema = commands.add_parser(
        "schema",
        help="list or print the public JSON Schemas this package publishes",
    )
    schema.add_argument("action", choices=("list", "show"))
    schema.add_argument(
        "name",
        nargs="?",
        help="schema to print, with or without the '.schema.json' suffix",
    )
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


def _explain(receipt_path: Path, as_json: bool) -> int:
    """Narrate a verified receipt, or fail without narrating part of one.

    Verification happens inside `narrate_receipt_file` before any sentence is
    built, so an invalid receipt produces the validation error and exit 2
    rather than a partial narration a reader could mistake for a result.
    """
    narration = narrate_receipt_file(receipt_path)
    if as_json:
        _print_json(narration)
    else:
        sys.stdout.write(render_narration_text(narration))
    return 0


def _history_paths(receipts: list[Path], directory: Path | None) -> tuple[Path, ...]:
    """Resolve the series, refusing the two ways an order could be invented.

    Naming files and naming a directory together would leave the order half
    caller-supplied and half filename-derived, which is neither of the two
    things the document says its ordering basis is.
    """
    if directory is not None and receipts:
        raise HistoryError("give receipt paths or --dir, not both")
    if directory is not None:
        return receipt_paths_in_directory(directory)
    return tuple(receipts)


def _history(
    receipts: list[Path],
    directory: Path | None,
    *,
    fail_on_loss_signal_increase: bool,
    out: Path | None,
) -> int:
    document = history_from_files(_history_paths(receipts, directory))
    summary = cast(dict[str, JsonValue], document["summary"])
    if out is None:
        _print_json(document)
    else:
        write_history(out, document)
        _print_json(
            {
                "decision_scope": "offline_aggregate_receipt_series_only",
                "gap_positions": summary["gap_positions"],
                "history": str(out),
                "receipt_count": summary["receipt_count"],
                "status": "history_written",
            }
        )
    if not fail_on_loss_signal_increase:
        return 0
    final = last_transition(document)
    if final["comparable"] is not True:
        # The policy has nothing to read. Returning 0 here would publish "the
        # last pair could not be compared" as "nothing increased", which is
        # the one thing this document exists to avoid.
        raise HistoryError(
            "the last adjacent pair is not comparable, so --fail-on-loss-signal-increase "
            "has nothing to decide"
        )
    return 3 if history_last_pair_has_observed_loss_signal_increase(document) else 0


def _verify_history(history_path: Path, receipts: list[Path] | None) -> int:
    document = verify_history_files(history_path, tuple(receipts or ()))
    summary = cast(dict[str, JsonValue], document["summary"])
    _print_json(
        {
            "decision_scope": "offline_aggregate_receipt_series_only",
            "gap_positions": summary["gap_positions"],
            "in_scope_count": summary["in_scope_count"],
            "receipt_count": summary["receipt_count"],
            "status": "recomputation_verified",
        }
    )
    return 0


def _report_operands(
    kind: str,
    reference_path: Path | None,
    candidate_path: Path | None,
    receipt_paths: list[Path] | None,
) -> None:
    """Refuse operands that do not belong to the kind the document declares.

    Checked rather than ignored: supplying a comparison's operands for a
    receipt, or omitting a history's, is a usage error and never a silent skip
    of the recomputation each report is required to run first.
    """
    pair = reference_path is not None or candidate_path is not None
    series = bool(receipt_paths)
    if kind == "receipt" and (pair or series):
        raise ReportError(
            "--reference, --candidate and --receipt apply only to a comparison or history"
        )
    if kind == "comparison":
        if series:
            raise ReportError("--receipt applies only to a history document")
        if reference_path is None or candidate_path is None:
            raise ReportError("a comparison report requires --reference and --candidate receipts")
    if kind == "history":
        if pair:
            raise ReportError("--reference and --candidate apply only to a comparison document")
        if len(receipt_paths or ()) < 2:
            raise ReportError("a history report requires --receipt for every receipt in the series")


def _report(
    document_path: Path,
    out: Path,
    reference_path: Path | None,
    candidate_path: Path | None,
    receipt_paths: list[Path] | None,
) -> int:
    """Render whichever document kind the file declares itself to be.

    The operand flags are checked against that kind rather than ignored when
    they do not apply: supplying receipts for a receipt report, or omitting
    them for a comparison report, is a usage error and never a silent skip of
    the recomputation a comparison report is required to run first.
    """
    kind = document_kind(document_path)
    _report_operands(kind, reference_path, candidate_path, receipt_paths)
    if kind == "receipt":
        rendered = render_receipt_file(document_path)
        decision_scope = "verified_aggregate_receipt_report_only"
    elif kind == "history":
        rendered = render_history_file(document_path, tuple(receipt_paths or ()))
        decision_scope = "verified_aggregate_history_report_only"
    else:
        rendered = render_comparison_file(
            document_path, cast(Path, reference_path), cast(Path, candidate_path)
        )
        decision_scope = "verified_aggregate_comparison_report_only"
    write_report(out, rendered)
    _print_json(
        {
            "decision_scope": decision_scope,
            "report": str(out),
            "status": "report_written",
        }
    )
    return 0


def _resolve_schema_name(name: str) -> str:
    """Accept `receipt-v0.3`, `receipt-v0.3.schema.json`, or a plain `receipt`.

    An integrator reading `docs/DATA-CONTRACTS.md` types the contract's name,
    not its filename, and a command that refuses that is a command they stop
    using. Ambiguity is refused rather than resolved to the first match.
    """
    if name in PUBLIC_SCHEMA_NAMES:
        return name
    suffixed = f"{name}.schema.json"
    if suffixed in PUBLIC_SCHEMA_NAMES:
        return suffixed
    matches = [item for item in PUBLIC_SCHEMA_NAMES if item.startswith(f"{name}-v")]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise SchemaResourceError(f"{name} names more than one schema: {', '.join(matches)}")
    raise SchemaResourceError(f"{name} is not a published schema")


def _schema(action: str, name: str | None) -> int:
    """List the published schemas, or print one schema's exact committed bytes."""
    if action == "list":
        if name is not None:
            raise SchemaResourceError("schema list takes no name")
        sys.stdout.write("".join(f"{item}\n" for item in PUBLIC_SCHEMA_NAMES))
        return 0
    if name is None:
        raise SchemaResourceError("schema show needs the name of a published schema")
    sys.stdout.buffer.write(read_schema_bytes(_resolve_schema_name(name)))
    return 0


def _run_printing_command(args: argparse.Namespace) -> int | None:
    """Route the two commands that print to stdout and write no file.

    Grouped for the same reason the verification and canary commands are:
    `main`'s dispatch is a flat list, and one branch per verb stops being
    readable long before it stops working. `None` means this was not one of
    them.
    """
    if args.command == "explain":
        return _explain(args.receipt, args.as_json)
    if args.command == "schema":
        return _schema(args.action, args.name)
    return None


def _run_verification_command(args: argparse.Namespace) -> int | None:
    """Route the three commands that recompute an existing artifact from its sources.

    Grouped for the same reason the canary commands are: `main`'s dispatch is a
    flat list of subcommands, and a router that keeps growing one branch per
    verb stops being readable long before it stops working. `None` means this
    was not one of them.
    """
    if args.command == "verify":
        return _verify(args.receipt, args.baseline, args.export, args.attachment_root)
    if args.command == "verify-comparison":
        return _verify_comparison(args.comparison, args.reference, args.candidate)
    if args.command == "verify-history":
        return _verify_history(args.history, args.receipts)
    return None


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
        verified = _run_verification_command(args)
        if verified is not None:
            return verified
        if args.command == "compare":
            return _compare(
                args.reference,
                args.candidate,
                fail_on_loss_signal_increase=args.fail_on_loss_signal_increase,
                out=args.out,
            )
        printed = _run_printing_command(args)
        if printed is not None:
            return printed
        if args.command == "history":
            return _history(
                args.receipts,
                args.directory,
                fail_on_loss_signal_increase=args.fail_on_loss_signal_increase,
                out=args.out,
            )
        if args.command == "report":
            return _report(args.document, args.out, args.reference, args.candidate, args.receipts)
        return _run_canary_command(args)
    except (
        CiviCRMTargetCanaryError,
        ComparisonError,
        DirectusCanaryError,
        DrillError,
        ExercisePlanError,
        HistoryError,
        PackageError,
        SchemaResourceError,
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
