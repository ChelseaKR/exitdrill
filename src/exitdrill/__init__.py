"""ExitDrill structural vendor-exit drills."""

from exitdrill.comparison import compare_receipt_files, verify_comparison_document
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.receipt import verify_receipt

__all__ = [
    "compare_receipt_files",
    "load_baseline",
    "load_export",
    "run_drill",
    "verify_comparison_document",
    "verify_receipt",
]
__version__ = "0.1.0"
