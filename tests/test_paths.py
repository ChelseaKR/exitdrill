import hashlib
import os
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


@pytest.mark.parametrize(
    "requested",
    [r"C:\outside\attachment.txt", r"\\server\share\attachment.txt", r"C:relative.txt"],
)
def test_bounded_file_rejects_windows_drive_or_unc_path(
    tmp_path: Path,
    requested: str,
) -> None:
    with pytest.raises(BoundedPathError, match="relative"):
        resolve_bounded_file(tmp_path, requested)


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

    def replace_path_after_open(handle: BinaryIO, *, expected_size: int) -> str:
        replacement.replace(attachment)
        return original_stream(handle, expected_size=expected_size)

    monkeypatch.setattr(paths, "_sha256_stream", replace_path_after_open)
    digest = sha256_bounded_file(tmp_path, "attachment.txt", max_bytes=1024)
    assert digest == hashlib.sha256(b"descriptor-original").hexdigest()
    assert attachment.read_bytes() == b"path-replacement"


def test_hash_rejects_attachment_growth_after_size_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attachment = tmp_path / "attachment.txt"
    attachment.write_bytes(b"initial")
    original_fstat = os.fstat
    appended = False

    def append_after_stat(descriptor: int) -> os.stat_result:
        nonlocal appended
        metadata = original_fstat(descriptor)
        if not appended:
            with attachment.open("ab") as handle:
                handle.write(b"-growth")
            appended = True
        return metadata

    monkeypatch.setattr(os, "fstat", append_after_stat)
    with pytest.raises(BoundedPathError, match="changed size"):
        sha256_bounded_file(tmp_path, "attachment.txt", max_bytes=1024)


def test_hash_rejects_swapped_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if (
        not paths._OPEN_SUPPORTS_DIR_FD
        or not getattr(os, "O_NOFOLLOW", 0)
        or not getattr(os, "O_DIRECTORY", 0)
    ):
        pytest.skip("descriptor-relative no-follow traversal is unavailable")
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (nested / "attachment.txt").write_bytes(b"inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "attachment.txt").write_bytes(b"outside")
    original_open = os.open
    swapped = False

    def swap_before_child_open(
        path: str | bytes | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if dir_fd is not None and path == "nested" and not swapped:
            nested.rename(root / "original-nested")
            nested.symlink_to(outside, target_is_directory=True)
            swapped = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", swap_before_child_open)
    with pytest.raises(BoundedPathError, match="opened safely"):
        sha256_bounded_file(root, "nested/attachment.txt", max_bytes=1024)


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
