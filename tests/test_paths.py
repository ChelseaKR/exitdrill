import hashlib
from pathlib import Path
from typing import BinaryIO

import pytest

from exitdrill import paths
from exitdrill.paths import (
    BoundedPathError,
    ByteBudget,
    resolve_bounded_file,
    sha256_bounded_file,
)


def test_bounded_file_accepts_regular_local_file(tmp_path: Path) -> None:
    path = tmp_path / "file.txt"
    path.write_text("content", encoding="utf-8")
    assert resolve_bounded_file(tmp_path, "file.txt") == path


def test_bounded_file_rejects_escape(tmp_path: Path) -> None:
    requested = "../escape"
    (tmp_path.parent / "escape").write_text("outside", encoding="utf-8")
    with pytest.raises(BoundedPathError):
        resolve_bounded_file(tmp_path, requested)


def test_bounded_file_rejects_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(BoundedPathError, match="relative"):
        resolve_bounded_file(tmp_path, str(tmp_path / "absolute"))


def test_bounded_file_rejects_directory(tmp_path: Path) -> None:
    (tmp_path / "directory").mkdir()
    with pytest.raises(BoundedPathError, match="regular file"):
        resolve_bounded_file(tmp_path, "directory")


def test_hash_size_check_and_read_share_one_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attachment = tmp_path / "attachment.txt"
    attachment.write_bytes(b"descriptor-original")
    replacement = tmp_path / "replacement.txt"
    replacement.write_bytes(b"path-replacement")
    original_stream = paths._sha256_stream

    def replace_path_after_open(handle: BinaryIO) -> str:
        replacement.replace(attachment)
        return original_stream(handle)

    monkeypatch.setattr(paths, "_sha256_stream", replace_path_after_open)
    digest = sha256_bounded_file(tmp_path, "attachment.txt", max_bytes=1024)
    assert digest == hashlib.sha256(b"descriptor-original").hexdigest()
    assert attachment.read_bytes() == b"path-replacement"


def test_hash_rejects_attachment_over_size_limit(tmp_path: Path) -> None:
    attachment = tmp_path / "attachment.txt"
    attachment.write_bytes(b"oversized")
    with pytest.raises(BoundedPathError, match="size limit"):
        sha256_bounded_file(tmp_path, "attachment.txt", max_bytes=2)


def test_hash_rejects_cumulative_attachment_budget_before_second_read(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_bytes(b"1234")
    second.write_bytes(b"5678")
    budget = ByteBudget(limit=6)
    sha256_bounded_file(tmp_path, "first.txt", max_bytes=10, total_budget=budget)
    with pytest.raises(BoundedPathError, match="total byte limit"):
        sha256_bounded_file(tmp_path, "second.txt", max_bytes=10, total_budget=budget)
    assert budget.consumed == 4
