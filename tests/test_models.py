"""Direct tests for the small pure helpers in `models.py`.

`matches_field_type` is a public function with a stated contract: it answers
whether a value satisfies *one supported* required-field type, which implies
unsupported types exist and are answered `False` rather than raised on. Both
call sites (`loader.py` and, through it, `evaluator.py`) reject a `value_type`
outside `loader._SCALAR_TYPES` before ever reaching here, so the unsupported
branch is not reachable through the CLI today. That makes it worth testing
directly against its documented behaviour rather than only through callers,
which is what issue #54 asked for.
"""

from __future__ import annotations

import pytest

from exitdrill.models import matches_field_type


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        ("array", [1, 2]),
        ("object", {"a": 1}),
        ("null", None),
        ("integer", 1),
        ("String", "Synthetic Person"),
        ("", "Synthetic Person"),
    ],
)
def test_unsupported_value_type_is_false_rather_than_an_error(
    value_type: str, value: object
) -> None:
    """An unsupported type answers False, including when the value would fit.

    `("integer", 1)` and `("String", "Synthetic Person")` are the interesting
    rows: the value satisfies a supported type under a different name, so a
    fallback that guessed from the value instead of the declared type would
    return True and be caught here.
    """
    assert matches_field_type(value_type, value) is False


@pytest.mark.parametrize(
    ("value_type", "value", "expected"),
    [
        ("string", "Synthetic Person", True),
        ("string", "   ", False),
        ("string", "", False),
        ("string", 1, False),
        ("boolean", True, True),
        ("boolean", False, True),
        ("boolean", "true", False),
        ("boolean", 1, False),
        ("number", 2, True),
        ("number", 2.5, True),
        ("number", True, False),
        ("number", "2", False),
    ],
)
def test_supported_value_types_answer_their_contract(
    value_type: str, value: object, expected: bool
) -> None:
    """Pins the three supported types so the fallback cannot swallow one.

    Without these the unsupported-type test above could pass against a function
    that returned `False` for everything.
    """
    assert matches_field_type(value_type, value) is expected
