"""Accessible offline evidence reports for verified structural documents."""

from __future__ import annotations

import html
from pathlib import Path
from typing import cast

from exitdrill.atomic_write import write_bounded_file
from exitdrill.comparison import verify_comparison_document, verify_comparison_files
from exitdrill.models import JsonValue
from exitdrill.receipt import load_receipt, verify_receipt
from exitdrill.strict_json import StrictJsonError, load_strict_json
from exitdrill.wording import DIMENSION_LABELS, LIMITATION_SENTENCES, STATUS_LABELS, label

_MAX_REPORT_BYTES = 2 * 1024 * 1024
_MAX_DOCUMENT_BYTES = 2 * 1024 * 1024

RECEIPT_SCHEMA_VERSION = "exitdrill/receipt/v0.3"
COMPARISON_SCHEMA_VERSION = "exitdrill/receipt-comparison/v0.1"

# Which renderer a document routes to, keyed by the version it declares about
# itself. Kept as a table so an unknown version is a named refusal rather than
# a renderer guessing from the keys it happens to find.
_DOCUMENT_KINDS = {
    RECEIPT_SCHEMA_VERSION: "receipt",
    COMPARISON_SCHEMA_VERSION: "comparison",
}


# One sentence per comparability reason code. The code itself is rendered
# beside its sentence, so a reader can match the page against the JSON.
_REASON_LABELS = {
    "baseline_sha256_changed": "The baseline digest differs between the two receipts.",
    "decision_scope_changed": "The declared decision scope differs.",
    "dimension_coverage_changed": "Baseline coverage differs for at least one dimension.",
    "dimension_expected_counts_changed": "The expected count differs for at least one dimension.",
    "drill_id_changed": "The drill identifier differs.",
    "receipt_schema_version_changed": "The receipt schema version differs.",
    "result_schema_version_changed": "The drill-result schema version differs.",
    "source_system_changed": "The declared source system differs.",
    "trust_limitations_changed": "The two receipts declare different trust limitations.",
}

# Neutral wording on purpose. A comparison reports what differs between two
# measurements; it never ranks them, so no label here reads as better or worse.
_ASSESSMENT_LABELS = {
    "mixed_loss_signal_change": "Mixed loss-signal change",
    "no_observed_loss_signal_change": "No observed loss-signal change",
    "observed_loss_signals_decreased": "Observed loss signals decreased",
    "observed_loss_signals_increased": "Observed loss signals increased",
    "uncertain": "Uncertain: baseline coverage is not complete",
}
_SUMMARY_LABELS = {
    "mixed_loss_signal_changes": "Mixed loss-signal change",
    "no_observed_loss_signal_change": "No observed loss-signal change",
    "observed_loss_signal_decreases": "Observed loss signals decreased",
    "observed_loss_signal_increases": "Observed loss signals increased",
    "uncertain": "Uncertain: baseline coverage is not complete",
}
_TRANSITION_LABELS = {
    "changed": "Changed",
    "changed_from_zero": "Changed from zero",
    "decreased": "Decreased",
    "increased": "Increased",
    "returned_to_zero": "Returned to zero",
    "unchanged": "Unchanged",
}
_LOSS_SIGNAL_LABELS = {
    "invalid_count_decreased": "Invalid count decreased",
    "invalid_count_increased": "Invalid count increased",
    "missing_count_decreased": "Missing count decreased",
    "missing_count_increased": "Missing count increased",
}

_COMPARABILITY_LABELS = {
    "comparable": "Comparable",
    "incomparable": "Incomparable",
}
_ORDERING_LABELS = {
    "caller_supplied_unverified": "Caller-supplied, unverified",
}
_RELATIONSHIP_LABELS = {
    "distinct_payloads": "Distinct payloads",
    "duplicate_payload": "Duplicate payload",
}

_DELTA_COLUMNS = (
    "expected_count",
    "exported_count",
    "restored_count",
    "missing_count",
    "extra_count",
    "invalid_count",
)

_CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"

_STYLE = """    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; --ink: #17211b; --muted: #526159; --paper: #f5f7f3; --card: #ffffff; --line: #cbd5cd; --accent: #145c3b; --pass: #17643d; --fail: #a52a2a; --finding: #8a5800; --unknown: #5b4b8a; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--paper); color: var(--ink); line-height: 1.5; }
    a { color: var(--accent); }
    .skip { position: absolute; left: -9999px; }
    .skip:focus { left: 1rem; top: 1rem; background: white; padding: .75rem; z-index: 2; }
    header, main, footer { width: min(70rem, calc(100% - 2rem)); margin-inline: auto; }
    header { padding: 3rem 0 1.5rem; }
    .eyebrow { color: var(--accent); font-size: .82rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
    h1 { max-width: 18ch; margin: .35rem 0 .5rem; font-size: clamp(2rem, 6vw, 4.5rem); line-height: .98; letter-spacing: -.04em; }
    .scope { max-width: 58rem; color: var(--muted); font-size: 1.05rem; }
    .result { margin: 1.5rem 0; border-left: .55rem solid var(--accent); background: var(--card); padding: 1.25rem 1.5rem; box-shadow: 0 .2rem 1.2rem rgb(28 44 34 / 8%); }
    .result strong { display: block; font-size: clamp(1.35rem, 3vw, 2rem); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: 1rem; margin: 1rem 0 2rem; }
    .card, section { background: var(--card); border: 1px solid var(--line); border-radius: .5rem; padding: 1rem 1.2rem; }
    .card span { color: var(--muted); display: block; font-size: .8rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
    .card strong { display: block; font-size: 1.35rem; overflow-wrap: anywhere; }
    section { margin: 1rem 0; overflow-x: auto; }
    h2 { margin-top: 0; font-size: 1.25rem; }
    table { border-collapse: collapse; min-width: 58rem; width: 100%; }
    caption { color: var(--muted); padding: 0 0 .75rem; text-align: left; }
    th, td { border-bottom: 1px solid var(--line); padding: .7rem .55rem; text-align: right; vertical-align: top; }
    th:first-child, td:first-child { text-align: left; }
    thead th { color: var(--muted); font-size: .76rem; letter-spacing: .03em; text-transform: uppercase; }
    .status { border: 1px solid currentColor; border-radius: 999px; display: inline-block; font-size: .78rem; font-weight: 800; padding: .15rem .5rem; white-space: nowrap; }
    .status-pass, .status-structurally_restorable { color: var(--pass); }
    .status-fail, .status-not_structurally_restorable { color: var(--fail); }
    .status-finding, .status-structurally_restorable_with_findings { color: var(--finding); }
    .status-indeterminate { color: var(--unknown); }
    code { font-size: .82rem; overflow-wrap: anywhere; }
    footer { color: var(--muted); padding: 1rem 0 3rem; }"""

_FOOTER_CLAIM = "No external assets, scripts, or network requests are used."


class ReportError(ValueError):
    """Raised when an evidence report cannot be safely rendered or written."""


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _statuslabel(value: object) -> str:
    return label(STATUS_LABELS, str(value))


def _status_pill(status: object) -> str:
    return f'<span class="status status-{_escape(status)}">{_escape(_statuslabel(status))}</span>'


def _plain_pill(text: str) -> str:
    """A pill with no colour modifier.

    Transitions and assessments are facts about a difference, not verdicts on
    it, so they carry no colour: the report states what changed and refuses to
    say whether that is good news.
    """
    return f'<span class="status">{_escape(text)}</span>'


def _objects(items: list[JsonValue], message: str) -> list[dict[str, JsonValue]]:
    """Narrow a verified list to objects, naming the document if it is not.

    Not reachable through either public entry point today: every renderer here
    verifies its document first, and both verifiers reject a non-object entry
    before rendering begins. The guard stays because these row builders take a
    list as their contract, so a caller that renders rows from a list this
    module did not verify gets a named error instead of a KeyError or a
    silently malformed table. It is exercised directly by tests rather than
    marked no-cover, so it stays a check that has been shown to fire. See
    ADR 0023 and issue #55.
    """
    result: list[dict[str, JsonValue]] = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ReportError(message)
        result.append(raw)
    return result


def _dimension_rows(dimensions: list[JsonValue]) -> str:
    rows: list[str] = []
    for raw in _objects(dimensions, "verified receipt contains a malformed dimension"):
        name = cast(str, raw["name"])
        status = cast(str, raw["status"])
        cells = (
            label(DIMENSION_LABELS, name),
            cast(str, raw["coverage"]).capitalize(),
            raw["expected_count"],
            raw["exported_count"],
            raw["restored_count"],
            raw["missing_count"],
            raw["extra_count"],
            raw["invalid_count"],
        )
        row_heading = _escape(cells[0])
        row_cells = "".join(f"<td>{_escape(item)}</td>" for item in cells[1:])
        rows.append(
            f'<tr><th scope="row">{row_heading}</th>{row_cells}<td>{_status_pill(status)}</td></tr>'
        )
    return "".join(rows)


def _limitation_items(limitations: list[JsonValue]) -> str:
    return "".join(
        f"<li>{_escape(label(LIMITATION_SENTENCES, cast(str, item)))}</li>" for item in limitations
    )


def _page(*, title: str, headline: str, scope: str, main: str, provenance: str) -> str:
    """Wrap one report body in the shared offline, script-free page shell.

    Both reports render through here so the escaping, the content-security
    policy, the stylesheet, and the footer claim cannot drift apart between
    them: `tests/test_report_offline_safety.py` binds the properties of this
    shell, and a second shell would be a second thing to bind.
    """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="{_CSP}">
  <title>{title}</title>
  <style>
{_STYLE}
  </style>
</head>
<body>
  <a class="skip" href="#report">Skip to report</a>
  <header>
    <div class="eyebrow">ExitDrill evidence report</div>
    <h1>{headline}</h1>
    <p class="scope">{scope}</p>
  </header>
  <main id="report">
{main}  </main>
  <footer>Generated locally by ExitDrill from {provenance}. {_FOOTER_CLAIM}</footer>
</body>
</html>
"""


def render_receipt_report(receipt: dict[str, JsonValue]) -> str:
    """Render a deterministic, aggregate-only HTML report from a verified receipt."""
    payload_sha256 = verify_receipt(receipt)
    payload = cast(dict[str, JsonValue], receipt["payload"])
    dimensions = cast(list[JsonValue], payload["dimensions"])
    limitations = cast(list[JsonValue], payload["trust_limitations"])
    overall_status = cast(str, payload["overall_status"])
    status_label = _statuslabel(overall_status)
    source_system = cast(str, payload["source_system"])
    drill_id = cast(str, payload["drill_id"])
    remediation_signals = cast(int, payload["observed_remediation_signals"])
    main = f"""    <div class="result">
      <span>Structural result</span>
      <strong>{_escape(status_label)}</strong>
      <span>Status is determined independently for five dimensions; there is no composite portability score.</span>
    </div>
    <div class="grid" aria-label="Receipt summary">
      <div class="card"><span>Source system</span><strong>{_escape(source_system)}</strong></div>
      <div class="card"><span>Drill ID</span><strong>{_escape(drill_id)}</strong></div>
      <div class="card"><span>Observed loss signals</span><strong>{remediation_signals}</strong></div>
      <div class="card"><span>Decision scope</span><strong>Offline structural drill only</strong></div>
    </div>
    <section aria-labelledby="dimensions-heading">
      <h2 id="dimensions-heading">Dimension evidence</h2>
      <table>
        <caption>Expected, exported, and restored counts remain separate from missing, extra, and invalid observations.</caption>
        <thead><tr><th scope="col">Dimension</th><th scope="col">Coverage</th><th scope="col">Expected</th><th scope="col">Exported</th><th scope="col">Restored</th><th scope="col">Missing</th><th scope="col">Extra</th><th scope="col">Invalid</th><th scope="col">Status</th></tr></thead>
        <tbody>{_dimension_rows(dimensions)}</tbody>
      </table>
    </section>
    <section aria-labelledby="integrity-heading">
      <h2 id="integrity-heading">Integrity and provenance</h2>
      <p>The receipt passed ExitDrill's closed semantic validation and its payload checksum is internally self-consistent. The checksum is not a signature and does not authenticate the operator or inputs.</p>
      <dl>
        <dt>Payload SHA-256</dt><dd><code>{_escape(payload_sha256)}</code></dd>
        <dt>Baseline SHA-256</dt><dd><code>{_escape(payload["baseline_sha256"])}</code></dd>
        <dt>Export SHA-256</dt><dd><code>{_escape(payload["export_sha256"])}</code></dd>
      </dl>
    </section>
    <section aria-labelledby="limitations-heading">
      <h2 id="limitations-heading">Required limitations</h2>
      <ul>{_limitation_items(limitations)}</ul>
    </section>
"""
    return _page(
        title=f"ExitDrill structural receipt — {_escape(source_system)}",
        headline="Structural recovery, without the victory lap.",
        scope=(
            "This report summarizes a verified, aggregate-only offline structural exit drill. "
            "It does not establish operational equivalence, a successful cutover, or vendor "
            "deletion."
        ),
        main=main,
        provenance="a verified receipt",
    )


def _signed(value: object) -> str:
    """Render a signed count delta so its direction is never inferred.

    Zero is rendered bare rather than as `+0`, which would give a direction to
    a difference that has none.
    """
    number = cast(int, value)
    return f"{number:+d}" if number else "0"


def _delta_rows(dimensions: list[dict[str, JsonValue]]) -> str:
    rows: list[str] = []
    for raw in dimensions:
        name = cast(str, raw["name"])
        deltas = cast(dict[str, JsonValue], raw["count_deltas"])
        heading = _escape(label(DIMENSION_LABELS, name))
        cells = "".join(f"<td>{_escape(_signed(deltas[column]))}</td>" for column in _DELTA_COLUMNS)
        coverage = _escape(cast(str, raw["coverage"]).capitalize())
        rows.append(f'<tr><th scope="row">{heading}</th><td>{coverage}</td>{cells}</tr>')
    return "".join(rows)


def _observation_rows(dimensions: list[dict[str, JsonValue]]) -> str:
    rows: list[str] = []
    for raw in dimensions:
        name = cast(str, raw["name"])
        heading = _escape(label(DIMENSION_LABELS, name))
        signals = [
            *cast(list[JsonValue], raw["observed_loss_signal_increases"]),
            *cast(list[JsonValue], raw["observed_loss_signal_decreases"]),
        ]
        observed = (
            "".join(
                f"<li>{_escape(label(_LOSS_SIGNAL_LABELS, cast(str, item)))}</li>"
                for item in signals
            )
            if signals
            else "<li>None observed</li>"
        )
        rows.append(
            f'<tr><th scope="row">{heading}</th>'
            f"<td>{_status_pill(raw['reference_status'])}</td>"
            f"<td>{_status_pill(raw['candidate_status'])}</td>"
            f"<td>{_plain_pill(label(_TRANSITION_LABELS, cast(str, raw['status_transition'])))}</td>"
            f"<td>{_plain_pill(label(_TRANSITION_LABELS, cast(str, raw['extra_count_transition'])))}</td>"
            f"<td><ul>{observed}</ul></td>"
            f"<td>{_plain_pill(label(_ASSESSMENT_LABELS, cast(str, raw['assessment'])))}</td></tr>"
        )
    return "".join(rows)


def _scope_check_rows(checks: dict[str, JsonValue]) -> str:
    return "".join(
        f'<tr><th scope="row"><code>{_escape(name)}</code></th>'
        f"<td>{_escape('Equal' if value is True else 'Different')}</td></tr>"
        for name, value in sorted(checks.items())
    )


def _reason_items(reasons: list[JsonValue]) -> str:
    return "".join(
        f"<li><code>{_escape(cast(str, item))}</code> — {_escape(label(_REASON_LABELS, cast(str, item)))}</li>"
        for item in reasons
    )


def _summary_items(summary: dict[str, JsonValue]) -> str:
    """List only the buckets that hold a dimension.

    An empty bucket is not a finding, and printing every bucket name would put
    words on the page -- `uncertain` above all -- that describe nothing this
    document observed.
    """
    items: list[str] = []
    for key in sorted(summary):
        names = cast(list[JsonValue], summary[key])
        if not names:
            continue
        # Document order, not alphabetical: the page must read back against the
        # JSON it was rendered from.
        rendered = ", ".join(_escape(label(DIMENSION_LABELS, cast(str, item))) for item in names)
        items.append(f"<dt>{_escape(label(_SUMMARY_LABELS, key))}</dt><dd>{rendered}</dd>")
    return "".join(items)


def _operand_card(title: str, operand: dict[str, JsonValue]) -> str:
    return (
        f'<div class="card"><span>{_escape(title)}</span>'
        f"<strong>{_escape(operand['source_system'])}</strong>"
        f"<span>Drill ID {_escape(operand['drill_id'])}</span>"
        f"<span>Payload <code>{_escape(operand['payload_sha256'])}</code></span></div>"
    )


def _comparison_dimension_sections(dimensions: list[JsonValue]) -> str:
    """Render both dimension tables, or the sentence that says there are none."""
    entries = _objects(dimensions, "verified comparison contains a malformed dimension")
    if not entries:
        return """    <section aria-labelledby="dimensions-heading">
      <h2 id="dimensions-heading">Dimension evidence</h2>
      <p>No dimension table is rendered. The two receipts did not pass the comparability checks above, so their counts do not measure the same thing and differencing them would state something this evidence cannot support.</p>
    </section>
"""
    return f"""    <section aria-labelledby="dimensions-heading">
      <h2 id="dimensions-heading">Signed count deltas</h2>
      <table>
        <caption>Candidate minus reference, per dimension. Expected, exported, and restored deltas stay separate from missing, extra, and invalid ones, and no delta is combined into a score.</caption>
        <thead><tr><th scope="col">Dimension</th><th scope="col">Coverage</th><th scope="col">Expected</th><th scope="col">Exported</th><th scope="col">Restored</th><th scope="col">Missing</th><th scope="col">Extra</th><th scope="col">Invalid</th></tr></thead>
        <tbody>{_delta_rows(entries)}</tbody>
      </table>
    </section>
    <section aria-labelledby="observations-heading">
      <h2 id="observations-heading">Status and loss-signal observations</h2>
      <table>
        <caption>Status transitions are stated as facts. Neither receipt is ranked above the other, and no cause is attributed to any difference.</caption>
        <thead><tr><th scope="col">Dimension</th><th scope="col">Reference status</th><th scope="col">Candidate status</th><th scope="col">Status transition</th><th scope="col">Extra-count transition</th><th scope="col">Observed loss-signal changes</th><th scope="col">Assessment</th></tr></thead>
        <tbody>{_observation_rows(entries)}</tbody>
      </table>
    </section>
"""


def _comparison_summary_section(summary: dict[str, JsonValue]) -> str:
    items = _summary_items(summary)
    if not items:
        return ""
    return f"""    <section aria-labelledby="summary-heading">
      <h2 id="summary-heading">Dimensions by observation</h2>
      <dl>{items}</dl>
    </section>
"""


def render_comparison_report(
    comparison: dict[str, JsonValue],
    reference_receipt: dict[str, JsonValue],
    candidate_receipt: dict[str, JsonValue],
) -> str:
    """Recompute a comparison document from both receipts, then render it.

    Verification is not optional and not the caller's job, exactly as
    `render_receipt_report` verifies the receipt it renders. A page is never
    produced from a document that does not match its source receipts.
    """
    verify_comparison_document(comparison, reference_receipt, candidate_receipt)
    return _comparison_html(comparison)


def _comparison_html(comparison: dict[str, JsonValue]) -> str:
    """Render one already-verified comparison document."""
    comparability = cast(str, comparison["comparability"])
    reference = cast(dict[str, JsonValue], comparison["reference"])
    candidate = cast(dict[str, JsonValue], comparison["candidate"])
    reasons = cast(list[JsonValue], comparison["incomparable_reasons"])
    reason_block = (
        f"<ul>{_reason_items(reasons)}</ul>"
        if reasons
        else "<p>Every comparability check held, so the counts below describe the same "
        "measurement taken twice.</p>"
    )
    dimension_sections = _comparison_dimension_sections(
        cast(list[JsonValue], comparison["dimensions"])
    )
    summary_section = _comparison_summary_section(cast(dict[str, JsonValue], comparison["summary"]))
    main = f"""    <div class="result">
      <span>Comparability</span>
      <strong>{_escape(label(_COMPARABILITY_LABELS, comparability))}</strong>
      <span>A comparison reports differences between two aggregate measurements. It does not rank the two exports, infer chronology, or attribute a cause.</span>
    </div>
    <div class="grid" aria-label="Comparison operands">
      {_operand_card("Reference receipt", reference)}
      {_operand_card("Candidate receipt", candidate)}
      <div class="card"><span>Ordering basis</span><strong>{_escape(label(_ORDERING_LABELS, cast(str, comparison["ordering_basis"])))}</strong></div>
      <div class="card"><span>Measurement relationship</span><strong>{_escape(label(_RELATIONSHIP_LABELS, cast(str, comparison["measurement_relationship"])))}</strong></div>
    </div>
    <section aria-labelledby="comparability-heading">
      <h2 id="comparability-heading">Comparability checks</h2>
      {reason_block}
      <table>
        <caption>Each check must hold for two receipts to be differenced at all. A failed check is named by its reason code, not rounded away.</caption>
        <thead><tr><th scope="col">Check</th><th scope="col">Result</th></tr></thead>
        <tbody>{_scope_check_rows(cast(dict[str, JsonValue], comparison["scope_checks"]))}</tbody>
      </table>
    </section>
{dimension_sections}{summary_section}    <section aria-labelledby="integrity-heading">
      <h2 id="integrity-heading">Integrity and provenance</h2>
      <p>This page was rendered only after the comparison document was recomputed field by field from both source receipts and re-checked against the public comparison schema. The digests below are the operands that recomputation used. They are checksums, not signatures, and authenticate neither the operator nor the inputs.</p>
      <dl>
        <dt>Reference baseline SHA-256</dt><dd><code>{_escape(reference["baseline_sha256"])}</code></dd>
        <dt>Reference export SHA-256</dt><dd><code>{_escape(reference["export_sha256"])}</code></dd>
        <dt>Candidate baseline SHA-256</dt><dd><code>{_escape(candidate["baseline_sha256"])}</code></dd>
        <dt>Candidate export SHA-256</dt><dd><code>{_escape(candidate["export_sha256"])}</code></dd>
      </dl>
    </section>
    <section aria-labelledby="limitations-heading">
      <h2 id="limitations-heading">Required limitations</h2>
      <ul>{_limitation_items(cast(list[JsonValue], comparison["limitations"]))}</ul>
    </section>
"""
    return _page(
        title="ExitDrill receipt comparison",
        headline="Two receipts, differenced without a verdict.",
        scope=(
            "This report summarizes a verified, aggregate-only comparison of two offline "
            "structural receipts. It states what differs between two measurements. It does not "
            "rank them, establish which export is better, or explain why anything changed."
        ),
        main=main,
        provenance="a verified comparison document and both source receipts",
    )


def render_receipt_file(path: Path) -> str:
    """Strict-load a bounded receipt and render its offline report."""
    return render_receipt_report(load_receipt(path))


def render_comparison_file(
    comparison_path: Path,
    reference_path: Path,
    candidate_path: Path,
) -> str:
    """Recompute a comparison document from both receipts, then render it.

    `verify_comparison_files` is the same entry point `exitdrill
    verify-comparison` uses, so a forged delta fails here exactly as it fails
    there -- before this function returns anything to write.
    """
    return _comparison_html(
        verify_comparison_files(comparison_path, reference_path, candidate_path)
    )


def document_kind(path: Path) -> str:
    """Return which renderer a bounded JSON document declares itself for.

    Only the declared `schema_version` is read here; the renderer this routes
    to loads the document again under its own document label and does its own
    verification, so a file that changed between the two reads fails that
    verification rather than being rendered as something it is not.
    """
    try:
        raw, _source_sha256 = load_strict_json(
            path,
            max_bytes=_MAX_DOCUMENT_BYTES,
            size_label="2 MiB",
            document_label="report input",
        )
    except StrictJsonError as exc:
        raise ReportError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise ReportError("report input must be a JSON object")
    version = raw.get("schema_version")
    if not isinstance(version, str) or version not in _DOCUMENT_KINDS:
        raise ReportError(
            "report input must declare a supported schema version: "
            f"{RECEIPT_SCHEMA_VERSION} or {COMPARISON_SCHEMA_VERSION}"
        )
    return _DOCUMENT_KINDS[version]


def write_report(path: Path, document: str) -> None:
    """Atomically write a bounded UTF-8 evidence report."""
    write_bounded_file(
        path,
        document.encode("utf-8"),
        max_bytes=_MAX_REPORT_BYTES,
        size_message="report exceeds the 2 MiB limit",
        error=ReportError,
    )
