from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SystemExit(f"{relative_path} is not a JSON object")
    return document


def main() -> None:
    clean = _read("examples/synthetic-crm/out/receipt.json")["payload"]
    lossy = _read("examples/synthetic-crm-lossy/out/receipt.json")["payload"]
    comparison = _read("examples/synthetic-crm/out/comparison.json")
    changed = ", ".join(comparison["summary"]["observed_loss_signal_increases"])

    print(
        f"clean: {clean['overall_status']} ({clean['observed_remediation_signals']} loss signals)"
    )
    print(
        f"lossy: {lossy['overall_status']} ({lossy['observed_remediation_signals']} loss signals)"
    )
    print(f"changed dimensions: {changed}")
    print(
        "reports: examples/synthetic-crm/out/report.html and "
        "examples/synthetic-crm-lossy/out/report.html"
    )


if __name__ == "__main__":
    main()
