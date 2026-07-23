from pathlib import Path
from shutil import copytree

import pytest


@pytest.fixture
def example_root() -> Path:
    return Path(__file__).parents[1] / "examples" / "synthetic-crm"


@pytest.fixture
def copied_example(tmp_path: Path, example_root: Path) -> Path:
    destination = tmp_path / "synthetic-crm"
    copytree(example_root, destination)
    return destination
