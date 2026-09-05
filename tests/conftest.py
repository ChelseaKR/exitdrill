import json
from pathlib import Path
from shutil import copytree

import pytest

_FIRST_PROBED_DEPTH = 20_000
_LAST_PROBED_DEPTH = 640_000


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
