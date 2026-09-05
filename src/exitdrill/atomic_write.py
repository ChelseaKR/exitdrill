"""The one bounded, atomic, durable writer behind every evidence artifact."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _fsync_parent(directory: Path) -> None:
    """Make the rename itself durable, tolerating platforms that refuse to.

    `os.replace` is atomic against a concurrent reader, but the directory entry
    it creates is not on disk until the containing directory is synced. Without
    this a crash between the replace and the directory's own writeback can come
    back with the file's data intact and no entry pointing at it, which is the
    same thing as no artifact at all.

    Directory `fsync` is not portable -- Windows refuses to open a directory as
    a file descriptor at all -- so failure here is tolerated rather than raised.
    The artifact is already written and already renamed; only its durability
    across a crash is lost, which is exactly what platforms without this syscall
    cannot offer anyway.
    """
    try:
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        return


def write_bounded_file(
    path: Path,
    payload: bytes,
    *,
    max_bytes: int,
    size_message: str,
    error: type[Exception],
) -> None:
    """Atomically and durably write an already-encoded payload under a size bound.

    The bound is checked before anything on disk is touched, so a caller that
    hands over an oversized payload gets its rejection without a parent
    directory or a temporary file being created; `docs/THREAT-MODEL.md` states
    that ordering, and callers' tests assert the parent still does not exist.
    Encoding, and any semantic verification, belong to the caller and have
    already happened by the time this runs.

    Writing beside the target with `mkstemp` and replacing it means an output
    path that is a symlink is replaced rather than written through, so a
    hostile or stale link cannot redirect the write to whatever it points at.
    `error` and `size_message` are the caller's own, so each artifact keeps the
    rejection wording its tests match.
    """
    if len(payload) > max_bytes:
        raise error(size_message)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_parent(path.parent)
    finally:
        temporary.unlink(missing_ok=True)
