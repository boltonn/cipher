"""Where Cipher writes files it creates itself (archive members, decoded files, email attachments).

Content-addressed: `<output uri>/<sha256[:2]>/<sha256[2:4]>/<sha256>`, written once however many
times it is found. The output uri is a local directory or `s3://bucket/prefix`; on S3 each
file is written to a local scratch file while it is hashed, then uploaded.

A file row's `uri` points at the stored file; its `path` says where the file was found.
"""

import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO, Self

from pydantic import BaseModel, Field
from upath import UPath

from cipher.utils.uri import is_local, to_uri

CHUNK_SIZE = 1 << 20


class StoredFile(BaseModel):
    """What a write produced: the content's hashes, size, and where it was stored."""

    md5: str = Field(description="MD5 of the content")
    sha256: str = Field(description="SHA256 of the content; also its key in the store")
    size: int = Field(description="Size of the content in bytes")
    uri: str = Field(description="URI of the stored file")
    is_new: bool = Field(default=True, description="False when the store already held this content")


class OutputWriter:
    """Hashes while it writes to a scratch file, then stores it under its sha256."""

    def __init__(self, store: "OutputStore") -> None:
        self._store = store
        self._tmp = NamedTemporaryFile(dir=store.scratch_dir, delete=False)  # noqa: SIM115 -- closed by commit/discard
        self._md5 = hashlib.md5()
        self._sha256 = hashlib.sha256()
        self.size = 0

    def write(self, chunk: bytes) -> None:
        """Append a chunk of content."""
        self._tmp.write(chunk)
        self._md5.update(chunk)
        self._sha256.update(chunk)
        self.size += len(chunk)

    def commit(self) -> StoredFile:
        """Store the content under its sha256 (atomically); drop it if the store already holds it."""
        self._tmp.close()
        sha256 = self._sha256.hexdigest()
        is_new = self._store.place(Path(self._tmp.name), sha256=sha256)
        return StoredFile(
            md5=self._md5.hexdigest(), sha256=sha256, size=self.size, uri=self._store.uri_for(sha256), is_new=is_new
        )

    def discard(self) -> None:
        """Abandon the write (e.g. a limit tripped mid-member)."""
        self._tmp.close()
        Path(self._tmp.name).unlink(missing_ok=True)

    def __enter__(self) -> Self:
        """Open for writing; leaving with an exception discards the write."""
        return self

    def __exit__(self, exc_type: type[BaseException] | None, *_: object) -> None:
        """Discard on error; a committed write is left alone."""
        if exc_type is not None:
            self.discard()


class OutputStore:
    """Content-addressed files under an output uri (local directory or `s3://bucket/prefix`)."""

    def __init__(self, uri: "str | Path | UPath", *, scratch_dir: Path | None = None) -> None:
        """Open a store.

        Args:
            uri: The output uri.
            scratch_dir: Local directory for files being written; defaults to `<uri>/.tmp` when the
                uri is local (same filesystem, so storing is a rename), else the system temp dir.
        """
        self.root = to_uri(uri)
        self.is_local = is_local(self.root)
        if self.is_local:
            self.root = UPath(Path(self.root.path).expanduser().resolve())
        default_scratch = (
            Path(self.root.path) / ".tmp" if self.is_local else Path(tempfile.gettempdir()) / "cipher-output"
        )
        self.scratch_dir = scratch_dir or default_scratch
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

    def location(self, sha256: str) -> UPath:
        """Where the file with this sha256 is stored."""
        return self.root / sha256[:2] / sha256[2:4] / sha256

    def uri_for(self, sha256: str) -> str:
        """The `uri` a file row stores for this content."""
        location = self.location(sha256)
        return Path(location.path).as_uri() if self.is_local else str(location)

    def exists(self, sha256: str) -> bool:
        """True when the store already holds this content."""
        return self.location(sha256).exists()

    def place(self, scratch_file: Path, *, sha256: str) -> bool:
        """Move a finished scratch file onto its key (dropping it when already stored); True when new."""
        target = self.location(sha256)
        if target.exists():
            scratch_file.unlink(missing_ok=True)
            return False
        if self.is_local:
            Path(target.path).parent.mkdir(parents=True, exist_ok=True)
            os.replace(scratch_file, target.path)
        else:
            target.fs.put_file(str(scratch_file), target.path)
            scratch_file.unlink(missing_ok=True)
        return True

    def sweep_tmp(self, older_than_seconds: float = 3600) -> int:
        """Delete scratch files (and dirs) a crashed or killed run left mid-write; returns how many.

        Only files older than `older_than_seconds` are touched, so a concurrent writer's file is left alone.
        """
        cutoff = time.time() - older_than_seconds
        stale = [tmp for tmp in self.scratch_dir.iterdir() if tmp.stat().st_mtime < cutoff]
        for tmp in stale:
            if tmp.is_dir():
                shutil.rmtree(tmp, ignore_errors=True)
            else:
                tmp.unlink(missing_ok=True)
        return len(stale)

    def writer(self) -> OutputWriter:
        """A writer for streaming content in chunks; use as a context manager to discard on error."""
        return OutputWriter(self)

    def put_stream(self, stream: BinaryIO) -> StoredFile:
        """Store everything read from `stream`."""
        with self.writer() as writer:
            while chunk := stream.read(CHUNK_SIZE):
                writer.write(chunk)
            return writer.commit()

    def put_file(self, path: Path, *, move: bool = False) -> StoredFile:
        """Store a file already on disk; `move` takes it (a rename when the store is on the same filesystem)."""
        md5, sha256 = hashlib.md5(), hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                md5.update(chunk)
                sha256.update(chunk)
        digest = sha256.hexdigest()
        size = path.stat().st_size
        if move:
            is_new = self.place(path, sha256=digest)
        else:
            with NamedTemporaryFile(dir=self.scratch_dir, delete=False) as copy:
                pass
            shutil.copyfile(path, copy.name)
            is_new = self.place(Path(copy.name), sha256=digest)
        return StoredFile(md5=md5.hexdigest(), sha256=digest, size=size, uri=self.uri_for(digest), is_new=is_new)
