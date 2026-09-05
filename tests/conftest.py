import json
import os
from pathlib import Path
from shutil import copytree

import coverage
import pytest

PROJECT = Path(__file__).parents[1]

# The nesting depth issue #57 used to defeat CPython's JSON decoder, and the
# ceiling `parser_defeating_json_depth` refuses to search past. The cap keeps
# the largest document the search can build at 2.56 MB, below `loader.py`'s
# 4 MiB document limit, so the same depth is usable at every boundary.
_PARSER_SEARCH_START = 20_000
_PARSER_SEARCH_CAP = 1_280_000


def pytest_sessionstart() -> None:
    """Let coverage follow the suite into the scripts it runs as subprocesses.

    Several gate tests assert on the exit code and the exact stdout of a real
    `python scripts/<gate>.py` invocation, so those call sites have to stay
    subprocesses; importing the module instead would stop proving the thing they
    exist to prove. Coverage does not follow into a child process on its own.
    The `coverage` distribution installs a `.pth` hook that calls
    `coverage.process_startup()` at interpreter start, but only when
    `COVERAGE_PROCESS_START` names a configuration file, so this sets it and
    every subprocess the suite launches inherits it through `os.environ`. The
    child then arms itself from the same `[tool.coverage.run]` block, whose
    `parallel = true` is what keeps its data file from colliding with the
    parent's before pytest-cov combines them.

    `COVERAGE_FILE` is pinned to the parent's own data file because a child's
    default is `.coverage` relative to *its* working directory: without this a
    subprocess launched with `cwd=tmp_path` would write somewhere nothing
    combines, and its coverage would vanish silently rather than visibly.

    Skipped when coverage is not running (`--no-cov`, or a plain `pytest`
    invocation), so a child never writes data files nothing will combine.
    """
    current = coverage.Coverage.current()
    if current is None:
        return
    os.environ["COVERAGE_PROCESS_START"] = str(PROJECT / "pyproject.toml")
    os.environ["COVERAGE_FILE"] = str(Path(current.config.data_file).resolve())


@pytest.fixture(scope="session")
def parser_defeating_json_depth() -> int:
    """A nesting depth this interpreter's JSON decoder refuses to walk.

    `json.loads` recurses, and the depth at which it gives up is an interpreter
    detail rather than a project constant. CPython 3.12 and 3.13 raise
    `RecursionError` at the 20,000 levels issue #57 used; 3.14 parses that
    document and only gives up past it. Every `except RecursionError` arm on
    this project's three JSON trust boundaries needs the decoder to fail
    *before* the boundary's own depth bound is consulted, so the tests that
    exercise those arms have to find the depth instead of hard-coding one.

    The search doubles from #57's depth and fails the run at the cap. That
    failure is the point: if no document in the range defeats the decoder, the
    three arms have stopped being observable on this interpreter, which is
    exactly the unfalsifiable-guard state ADR 0023 forbids, and it should
    surface as a red suite rather than as three quietly uncovered lines.
    """
    depth = _PARSER_SEARCH_START
    while depth <= _PARSER_SEARCH_CAP:
        try:
            json.loads("[" * depth + "]" * depth)
        except RecursionError:
            return depth
        depth *= 2
    pytest.fail(
        f"no nesting depth up to {_PARSER_SEARCH_CAP} defeats this interpreter's JSON "
        "decoder, so the RecursionError arms in strict_json.py, directus_canary.py "
        "and civicrm_target_canary.py can no longer be observed to fire"
    )


@pytest.fixture
def example_root() -> Path:
    return Path(__file__).parents[1] / "examples" / "synthetic-crm"


@pytest.fixture
def copied_example(tmp_path: Path, example_root: Path) -> Path:
    destination = tmp_path / "synthetic-crm"
    copytree(example_root, destination)
    return destination
