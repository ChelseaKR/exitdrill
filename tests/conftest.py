import json
import os
from pathlib import Path
from shutil import copytree

import coverage
import pytest

PROJECT = Path(__file__).parents[1]

_FIRST_PROBED_DEPTH = 20_000
_LAST_PROBED_DEPTH = 640_000


def pytest_sessionstart() -> None:
    """Let coverage follow the suite into the scripts it runs as subprocesses.

    Several gate tests assert on the exit code and the exact stdout of a real
    `python scripts/<gate>.py` invocation, so those call sites have to stay
    subprocesses; importing the module instead would stop proving the thing
    they exist to prove. Coverage does not follow into a child process on its
    own. The `coverage` distribution installs a `.pth` hook that calls
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


@pytest.fixture
def example_root() -> Path:
    return Path(__file__).parents[1] / "examples" / "synthetic-crm"


@pytest.fixture
def copied_example(tmp_path: Path, example_root: Path) -> Path:
    destination = tmp_path / "synthetic-crm"
    copytree(example_root, destination)
    return destination


@pytest.fixture
def json_the_parser_cannot_walk() -> str:
    """JSON nested deeper than this interpreter's `json` decoder will recurse.

    Three tests exercise the `RecursionError` arm that each strict decoder puts
    between a raw interpreter error and its trust boundary. They used to spell
    that input as a literal 20,000 levels, which was a bet on a constant rather
    than a measurement: CPython 3.14 bounds decoder recursion by remaining C
    stack instead of a fixed count, so 20,000 parses there. The arm silently
    stopped being exercised on 3.14 while the same literal still defeated 3.12
    and 3.13 (issue #90).

    Probing for a depth the running decoder actually refuses keeps the arm
    exercised on every interpreter, and raising when no such depth exists keeps
    a silent pass from taking its place. The search doubles rather than
    bisecting because only the refusal matters, not the exact boundary, and the
    boundary is a property of the interpreter and platform rather than a number
    worth recording.
    """
    depth = _FIRST_PROBED_DEPTH
    while depth <= _LAST_PROBED_DEPTH:
        document = "[" * depth + "]" * depth
        try:
            json.loads(document)
        except RecursionError:
            return document
        depth *= 2
    raise AssertionError(
        f"no nesting up to {_LAST_PROBED_DEPTH} levels defeated this interpreter's JSON "
        "decoder, so the RecursionError arm cannot be exercised here"
    )
