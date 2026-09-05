"""The shared writer behind write_receipt, write_report, and write_comparison.

Each caller's own tests cover its bound, its error type, and its symlink and
replace-failure behaviour; those stay where they are. What lives here is the
part no caller can see from outside: that the rename is made durable, and that
a platform which refuses to do so still gets its artifact.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

import pytest

from exitdrill.atomic_write import write_bounded_file


class _Rejected(ValueError):
    """A caller's own error type, to prove the writer raises what it is handed."""


def _write(path: Path, payload: bytes = b"payload\n") -> None:
    write_bounded_file(
        path,
        payload,
        max_bytes=1024,
        size_message="artifact exceeds the 1 KiB limit",
        error=_Rejected,
    )


def _is_directory(descriptor: int) -> bool:
    return stat.S_ISDIR(os.fstat(descriptor).st_mode)


def test_the_parent_directory_is_fsynced_after_the_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The line that makes "atomically write" true rather than nearly true.

    `os.replace` is atomic against a concurrent reader, but the directory entry
    it creates is not durable until the directory is synced. Without the final
    step a crash can leave the file's data on disk with nothing naming it. The
    ordering matters as much as the presence: syncing the directory before the
    rename would sync an entry that does not exist yet.
    """
    order: list[str] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def recording_fsync(descriptor: int) -> None:
        order.append("directory" if _is_directory(descriptor) else "file")
        real_fsync(descriptor)

    def recording_replace(source: object, target: object) -> None:
        order.append("replace")
        real_replace(source, target)  # type: ignore[arg-type]

    monkeypatch.setattr("exitdrill.atomic_write.os.fsync", recording_fsync)
    monkeypatch.setattr("exitdrill.atomic_write.os.replace", recording_replace)

    _write(tmp_path / "artifact.bin")

    assert order == ["file", "replace", "directory"]
    assert (tmp_path / "artifact.bin").read_bytes() == b"payload\n"


def test_a_platform_that_refuses_to_fsync_a_directory_still_gets_its_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Durability is best-effort; the artifact is not.

    Some filesystems reject `fsync` on a directory descriptor. The file is
    already written and already renamed by the time that can happen, so the
    only thing lost is crash durability -- which such a platform cannot offer
    in the first place. Raising here would turn a successful write into a
    failed command.
    """
    real_fsync = os.fsync

    def refusing_fsync(descriptor: int) -> None:
        if _is_directory(descriptor):
            raise OSError(errno.EINVAL, "synthetic directory fsync refusal")
        real_fsync(descriptor)

    monkeypatch.setattr("exitdrill.atomic_write.os.fsync", refusing_fsync)

    _write(tmp_path / "artifact.bin")

    assert (tmp_path / "artifact.bin").read_bytes() == b"payload\n"
    assert not list(tmp_path.glob(".artifact.bin.*.tmp"))


def test_a_platform_that_refuses_to_open_a_directory_still_gets_its_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other way into the same tolerance: Windows has no directory fd.

    `mkstemp` opens a path that is not a directory, so it is unaffected by the
    refusal below; only the durability step is.
    """
    real_open = os.open

    def refusing_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if Path(os.fsdecode(path)).is_dir():  # type: ignore[arg-type]
            raise OSError(errno.EACCES, "synthetic directory open refusal")
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("exitdrill.atomic_write.os.open", refusing_open)

    _write(tmp_path / "artifact.bin")

    assert (tmp_path / "artifact.bin").read_bytes() == b"payload\n"
    assert not list(tmp_path.glob(".artifact.bin.*.tmp"))


def test_the_bound_is_checked_before_any_filesystem_mutation(tmp_path: Path) -> None:
    """Stated against the writer's own contract, as ADR 0023 asks.

    `docs/THREAT-MODEL.md` records that the encoded bound runs before directory
    or temporary-file creation. Each caller asserts this for its own artifact;
    this asserts it of the one implementation they now share, including that
    the message and the type both come from the caller.
    """
    parent = tmp_path / "not-created"

    with pytest.raises(_Rejected, match="artifact exceeds the 1 KiB limit"):
        _write(parent / "artifact.bin", b"x" * 1025)

    assert not parent.exists()
