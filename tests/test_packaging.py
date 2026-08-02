import tomllib
from pathlib import Path

import exitdrill


def test_package_metadata_and_typing_marker_are_aligned() -> None:
    project = Path(__file__).parents[1]
    metadata = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["name"] == "exitdrill"
    assert metadata["project"]["version"] == exitdrill.__version__
    assert metadata["project"]["scripts"]["exitdrill"] == "exitdrill.cli:main"
    assert metadata["project"]["dependencies"] == ["jsonschema>=4.23"]
    assert (project / "src" / "exitdrill" / "py.typed").is_file()


def test_public_api_surface_stays_small() -> None:
    assert exitdrill.__all__ == [
        "compare_receipt_files",
        "load_baseline",
        "load_export",
        "run_drill",
        "verify_comparison_document",
        "verify_receipt",
    ]
    assert not hasattr(exitdrill, "comparison_has_observed_loss_signal_increase")
