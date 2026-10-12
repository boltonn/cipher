"""Where a parser's child files go: attachments, files packed in winmail.dat, images inlined in HTML.

A parser never decides where bytes are stored or how they are typed. It hands each child's bytes
to a `ChildSink`, which returns the child's `FileBase`. The default sink only types and hashes (no
bytes are kept); `DirectorySink` also writes them to a folder; a pipeline passes its own (e.g. one
writing into the output store).
"""

import hashlib
from functools import cache
from pathlib import Path
from typing import Protocol

from filetyper import FileTyper

from cipher.schemas.ingestion.file import FileBase


class ChildSink(Protocol):
    """Takes one child's bytes and returns its file record."""

    def __call__(self, *, data: bytes, filename: str | None) -> FileBase:
        """Store (or not) and describe one child."""
        ...


@cache
def shared_file_typer() -> FileTyper:
    """One `FileTyper` per process: building one costs ~30 ms, too slow to repeat per email."""
    return FileTyper()


def describe(*, data: bytes, filename: str | None, file_typer: FileTyper | None = None) -> FileBase:
    """A child's file record from its bytes: hashes plus filetyper's description (nothing is written)."""
    md5, sha256 = hashlib.md5(data).hexdigest(), hashlib.sha256(data).hexdigest()  # noqa: S324 -- identity, not security
    info = (file_typer or shared_file_typer()).describe(
        md5=md5, sha256=sha256, size=len(data), data=data, name=filename
    )
    return FileBase(
        filename=filename,
        filetype=info["filetype"],
        filetype_group=info["filetype_group"],
        filetype_name=info.get("filetype_name"),
        md5=md5,
        sha256=sha256,
        mime_type=info["mime_type"],
        size=len(data),
        compression=info["compression"],
        is_encrypted=info["is_encrypted"],
    )


def describe_only(*, data: bytes, filename: str | None) -> FileBase:
    """The default sink: children are typed and hashed but their bytes are not kept."""
    return describe(data=data, filename=filename)


class DirectorySink:
    """Writes each child to `out_dir` as `<md5><extension>`; its record's `path` and `uri` point there."""

    def __init__(self, *, out_dir: Path, file_typer: FileTyper | None = None) -> None:
        self.out_dir, self.file_typer = out_dir, file_typer

    def __call__(self, *, data: bytes, filename: str | None) -> FileBase:
        """Describe the child, then write it."""
        child = describe(data=data, filename=filename, file_typer=self.file_typer)
        extension = Path(filename).suffix if filename and Path(filename).suffix else ""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.out_dir / f"{child.md5}{extension or '.bin'}"
        out_path.write_bytes(data)
        return child.model_copy(update={"path": str(out_path), "uri": out_path.as_uri()})
