from exitdrill.models import matches_field_type


def test_matches_field_type_unsupported_type_returns_false() -> None:
    assert matches_field_type("array", [1, 2]) is False
    assert matches_field_type("object", {"key": "val"}) is False
    assert matches_field_type("null", None) is False
    assert matches_field_type("unknown", "some_value") is False


def test_matches_field_type_supported_types() -> None:
    assert matches_field_type("string", "hello") is True
    assert matches_field_type("string", "") is False
    assert matches_field_type("string", "   ") is False
    assert matches_field_type("string", 123) is False

    assert matches_field_type("boolean", True) is True
    assert matches_field_type("boolean", False) is True
    assert matches_field_type("boolean", 1) is False

    assert matches_field_type("number", 42) is True
    assert matches_field_type("number", 3.14) is True
    assert matches_field_type("number", True) is False
    assert matches_field_type("number", "42") is False
