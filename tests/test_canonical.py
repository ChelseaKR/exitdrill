from pathlib import Path

import pytest

from exitdrill.canonical import canonical_json_bytes, is_sha256_hex, sha256_bytes, sha256_file


def test_canonical_json_and_hashes_are_stable(tmp_path: Path) -> None:
    assert canonical_json_bytes({"b": 1, "a": "é"}) == b'{"a":"\xc3\xa9","b":1}'
    path = tmp_path / "content"
    path.write_bytes(b"hello")
    expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert sha256_bytes(b"hello") == expected
    assert sha256_file(path) == expected


def test_is_sha256_hex_accepts_what_the_hashers_above_produce() -> None:
    assert is_sha256_hex(sha256_bytes(b"hello"))
    assert is_sha256_hex("0" * 64)
    assert is_sha256_hex("0123456789abcdef" * 4)


@pytest.mark.parametrize(
    ("value", "why"),
    [
        ("", "empty"),
        ("a" * 63, "one character short"),
        ("a" * 65, "one character long"),
        ("A" * 64, "uppercase hex is not what sha256_bytes emits"),
        ("g" * 64, "outside the hex alphabet"),
        (f"{'a' * 63} ", "trailing space"),
        (f"{'a' * 64}\n", "trailing newline"),
        (f"\n{'a' * 64}", "leading newline"),
        (f"{'a' * 32}\n{'a' * 31}", "embedded newline"),
    ],
)
def test_is_sha256_hex_rejects_everything_that_is_not_one(value: str, why: str) -> None:
    """The newline cases are why the shared pattern is unanchored (issue #92).

    This replaced two `^[0-9a-f]{64}$` patterns and one character-membership
    check. `$` matches before a trailing newline, so an anchored pattern is
    only safe here because it was always applied with `fullmatch` rather than
    `match`. Dropping the anchors removes that dependence; these cases fail if
    anyone reintroduces it as `match`.
    """
    assert not is_sha256_hex(value), why
