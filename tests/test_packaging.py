import tomllib
from pathlib import Path

import exitdrill


def test_package_metadata_and_typing_marker_are_aligned() -> None:
    project = Path(__file__).parents[1]
    metadata = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["name"] == "exitdrill"
    assert metadata["project"]["version"] == exitdrill.__version__
    assert metadata["project"]["scripts"]["exitdrill"] == "exitdrill.cli:main"
    assert (project / "src" / "exitdrill" / "py.typed").is_file()
