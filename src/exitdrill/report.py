"""Accessible offline evidence reports for verified structural receipts."""

from __future__ import annotations

import html
import os
import tempfile
from pathlib import Path
from typing import cast

from exitdrill.models import JsonValue
from exitdrill.receipt import load_receipt, verify_receipt

_MAX_REPORT_BYTES = 2 * 1024 * 1024
_STATUS_LABELS = {
    "fail": "Fail",
    "finding": "Finding",
    "indeterminate": "Indeterminate",
    "not_structurally_restorable": "Not structurally restorable",
    "pass": "Pass",
    "structurally_restorable": "Structurally restorable",
    "structurally_restorable_with_findings": "Structurally restorable with findings",
}
_DIMENSION_LABELS = {
    "attachments": "Attachments",
    "audit_events": "Audit events",
    "entities": "Entities",
    "permissions": "Permissions",
    "relationships": "Relationships",
}
_LIMITATION_LABELS = {
    "does_not_authenticate_export_or_baseline": "Does not authenticate the export or baseline.",
    "does_not_prove_operational_equivalence": "Does not prove operational equivalence.",
    "does_not_prove_vendor_deletion": "Does not prove vendor deletion.",
    "field_value_equivalence_limited_to_declared_required_fields": (
        "Field-value equivalence is limited to baseline-declared required fields."
    ),
    "does_not_verify_permission_principal_identity": (
        "Does not verify permission-principal identity."
    ),
}


class ReportError(ValueError):
    """Raised when an evidence report cannot be safely rendered or written."""


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _status_label(value: object) -> str:
    text = str(value)
    return _STATUS_LABELS.get(text, text.replace("_", " ").capitalize())


def _dimension_rows(dimensions: list[JsonValue]) -> str:
    rows: list[str] = []
    for raw in dimensions:
        if not isinstance(raw, dict):
            raise ReportError("verified receipt contains a malformed dimension")
        name = cast(str, raw["name"])
        status = cast(str, raw["status"])
        cells = (
            _DIMENSION_LABELS.get(name, name.replace("_", " ").title()),
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
            f'<tr><th scope="row">{row_heading}</th>{row_cells}'
            f'<td><span class="status status-{_escape(status)}">'
            f"{_escape(_status_label(status))}</span></td></tr>"
        )
    return "".join(rows)


def _limitation_items(limitations: list[JsonValue]) -> str:
    return "".join(
        f"<li>{_escape(_LIMITATION_LABELS.get(cast(str, item), cast(str, item)))}</li>"
        for item in limitations
    )


def render_receipt_report(receipt: dict[str, JsonValue]) -> str:
    """Render a deterministic, aggregate-only HTML report from a verified receipt."""
    payload_sha256 = verify_receipt(receipt)
    payload = cast(dict[str, JsonValue], receipt["payload"])
    dimensions = cast(list[JsonValue], payload["dimensions"])
    limitations = cast(list[JsonValue], payload["trust_limitations"])
    overall_status = cast(str, payload["overall_status"])
    status_label = _status_label(overall_status)
    source_system = cast(str, payload["source_system"])
    drill_id = cast(str, payload["drill_id"])
    remediation_signals = cast(int, payload["observed_remediation_signals"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
  <title>ExitDrill structural receipt — {_escape(source_system)}</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; --ink: #17211b; --muted: #526159; --paper: #f5f7f3; --card: #ffffff; --line: #cbd5cd; --accent: #145c3b; --pass: #17643d; --fail: #a52a2a; --finding: #8a5800; --unknown: #5b4b8a; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--paper); color: var(--ink); line-height: 1.5; }}
    a {{ color: var(--accent); }}
    .skip {{ position: absolute; left: -9999px; }}
    .skip:focus {{ left: 1rem; top: 1rem; background: white; padding: .75rem; z-index: 2; }}
    header, main, footer {{ width: min(70rem, calc(100% - 2rem)); margin-inline: auto; }}
    header {{ padding: 3rem 0 1.5rem; }}
    .eyebrow {{ color: var(--accent); font-size: .82rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }}
    h1 {{ max-width: 18ch; margin: .35rem 0 .5rem; font-size: clamp(2rem, 6vw, 4.5rem); line-height: .98; letter-spacing: -.04em; }}
    .scope {{ max-width: 58rem; color: var(--muted); font-size: 1.05rem; }}
    .result {{ margin: 1.5rem 0; border-left: .55rem solid var(--accent); background: var(--card); padding: 1.25rem 1.5rem; box-shadow: 0 .2rem 1.2rem rgb(28 44 34 / 8%); }}
    .result strong {{ display: block; font-size: clamp(1.35rem, 3vw, 2rem); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: 1rem; margin: 1rem 0 2rem; }}
    .card, section {{ background: var(--card); border: 1px solid var(--line); border-radius: .5rem; padding: 1rem 1.2rem; }}
    .card span {{ color: var(--muted); display: block; font-size: .8rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }}
    .card strong {{ display: block; font-size: 1.35rem; overflow-wrap: anywhere; }}
    section {{ margin: 1rem 0; overflow-x: auto; }}
    h2 {{ margin-top: 0; font-size: 1.25rem; }}
    table {{ border-collapse: collapse; min-width: 58rem; width: 100%; }}
    caption {{ color: var(--muted); padding: 0 0 .75rem; text-align: left; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: .7rem .55rem; text-align: right; vertical-align: top; }}
    th:first-child, td:first-child {{ text-align: left; }}
    thead th {{ color: var(--muted); font-size: .76rem; letter-spacing: .03em; text-transform: uppercase; }}
    .status {{ border: 1px solid currentColor; border-radius: 999px; display: inline-block; font-size: .78rem; font-weight: 800; padding: .15rem .5rem; white-space: nowrap; }}
    .status-pass, .status-structurally_restorable {{ color: var(--pass); }}
    .status-fail, .status-not_structurally_restorable {{ color: var(--fail); }}
    .status-finding, .status-structurally_restorable_with_findings {{ color: var(--finding); }}
    .status-indeterminate {{ color: var(--unknown); }}
    code {{ font-size: .82rem; overflow-wrap: anywhere; }}
    footer {{ color: var(--muted); padding: 1rem 0 3rem; }}
  </style>
</head>
<body>
  <a class="skip" href="#report">Skip to report</a>
  <header>
    <div class="eyebrow">ExitDrill evidence report</div>
    <h1>Structural recovery, without the victory lap.</h1>
    <p class="scope">This report summarizes a verified, aggregate-only offline structural exit drill. It does not establish operational equivalence, a successful cutover, or vendor deletion.</p>
  </header>
  <main id="report">
    <div class="result">
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
  </main>
  <footer>Generated locally by ExitDrill from a verified receipt. No external assets, scripts, or network requests are used.</footer>
</body>
</html>
"""


def render_receipt_file(path: Path) -> str:
    """Strict-load a bounded receipt and render its offline report."""
    return render_receipt_report(load_receipt(path))


def write_report(path: Path, document: str) -> None:
    """Atomically write a bounded UTF-8 evidence report."""
    encoded = document.encode("utf-8")
    if len(encoded) > _MAX_REPORT_BYTES:
        raise ReportError("report exceeds the 2 MiB limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
