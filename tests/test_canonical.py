from pathlib import Path

from exitdrill.canonical import canonical_json_bytes, sha256_bytes, sha256_file


def test_canonical_json_and_hashes_are_stable(tmp_path: Path) -> None:
    assert canonical_json_bytes({"b": 1, "a": "é"}) == b'{"a":"\xc3\xa9","b":1}'
    path = tmp_path / "content"
    path.write_bytes(b"hello")
    expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert sha256_bytes(b"hello") == expected
    assert sha256_file(path) == expected
