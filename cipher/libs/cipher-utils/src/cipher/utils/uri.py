"""Files by uri: a local path / `file://` or `s3://bucket/key`, read and listed with the same calls.

`Uri` is `universal_pathlib`'s `UPath` (pathlib's API over fsspec), so callers never branch on
local vs S3. Credentials come from boto3's standard chain (env, `~/.aws`, instance role); S3
needs the `cipher-utils[aws]` extra (`s3fs`).

Readers get a path when the file is local (nothing copied or loaded) and bytes, a seekable
stream, or -- for readers that only take a path -- a temp copy when it is remote.
"""

import fnmatch
import os
import shutil
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, Field
from upath import UPath

Uri = UPath

MAX_IN_MEMORY_BYTES = int(os.environ.get("MAX_IN_MEMORY_MIB", "1024")) << 20
"""Remote files bigger than this are streamed to a temp file instead of read into memory."""


class FoundFile(BaseModel):
    """One file a crawl found."""

    uri: str = Field(description="Where the file lives: a local path or s3://bucket/key")
    relative_path: str = Field(description="Its path below the crawled uri, `/`-separated")
    size: int
    date_modified: datetime | None = Field(default=None)


def to_uri(value: "str | Path | UPath") -> UPath:
    """A `Uri` for a local path, a percent-encoded `file://` uri (as `Path.as_uri` writes), or `s3://...`."""
    if isinstance(value, UPath):
        return value
    text = str(value)
    if text.startswith("file://"):
        return UPath(unquote(urlparse(text).path))
    if "://" not in text:
        return UPath(Path(text).expanduser())
    return UPath(text)


def is_local(uri: "str | Path | UPath") -> bool:
    """True when the uri names a file on this host's filesystem."""
    return to_uri(uri).protocol in ("", "file", "local")


def local_path(uri: "str | Path | UPath") -> Path:
    """The local path of a local uri; raises for a remote one (use `local_copy` to read it as a file)."""
    found = to_uri(uri)
    if not is_local(found):
        raise ValueError(f"{found} is not a local file; read it with read_bytes / open_binary / local_copy")
    return Path(found.path)


def read_bytes(uri: "str | Path | UPath") -> bytes:
    """A file's whole content."""
    return to_uri(uri).read_bytes()


def open_binary(uri: "str | Path | UPath") -> BinaryIO:
    """A seekable binary stream; on S3 only the byte ranges actually read are fetched."""
    return to_uri(uri).open("rb")


@contextmanager
def local_copy(uri: "str | Path | UPath", *, suffix: str = "") -> Iterator[Path]:
    """A local path to read the file by: the file itself when local, else a temp copy deleted on exit.

    Args:
        uri: The file.
        suffix: Extension for the temp copy, for readers that type a file by its name.
    """
    found = to_uri(uri)
    if is_local(found):
        yield Path(found.path)
        return
    with NamedTemporaryFile(suffix=suffix or "".join(Path(found.name).suffixes), delete=False) as tmp:
        with found.open("rb") as source:
            shutil.copyfileobj(source, tmp, 1 << 20)
    try:
        yield Path(tmp.name)
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def matches(relative_path: str, *, include: Sequence[str] = (), exclude: Sequence[str] = ()) -> bool:
    """Whether a crawled path passes the include / exclude globs (`*` also crosses `/`)."""
    if include and not any(fnmatch.fnmatch(relative_path, pattern) for pattern in include):
        return False
    return not any(fnmatch.fnmatch(relative_path, pattern) for pattern in exclude)


async def list_files(
    uri: "str | Path | UPath", *, include: Sequence[str] = (), exclude: Sequence[str] = ()
) -> AsyncIterator[FoundFile]:
    """Every file under a directory or `s3://bucket/prefix/` (or the one file it names), filtered by globs.

    S3 is listed flat, 1,000 keys per request, and yielded page by page as it arrives.

    Args:
        uri: Where to look.
        include: Keep only paths matching one of these (relative to `uri`).
        exclude: Drop paths matching one of these.
    """
    root = to_uri(uri)
    if is_local(root):
        base = Path(root.path)
        if base.is_file():
            stat = base.stat()
            yield FoundFile(
                uri=str(base), relative_path=base.name, size=stat.st_size, date_modified=_from_timestamp(stat.st_mtime)
            )
            return
        for directory, _, names in os.walk(base):
            for name in sorted(names):
                path = Path(directory) / name
                relative = path.relative_to(base).as_posix()
                if not path.is_file() or not matches(relative, include=include, exclude=exclude):
                    continue
                stat = path.stat()
                yield FoundFile(
                    uri=str(path), relative_path=relative, size=stat.st_size, date_modified=_from_timestamp(stat.st_mtime)
                )
        return

    import s3fs

    fs = s3fs.S3FileSystem(asynchronous=True)
    bucket, _, prefix = root.path.partition("/")
    if prefix and not prefix.endswith("/") and await fs._isfile(root.path):
        info = await fs._info(root.path)
        yield FoundFile(
            uri=str(root), relative_path=root.name, size=info["size"], date_modified=info.get("LastModified")
        )
        return
    prefix = f"{prefix.rstrip('/')}/" if prefix else ""
    async for info in fs._iterdir(bucket, delimiter="", prefix=prefix):
        if info.get("type") != "file" or info["Key"].endswith("/"):
            continue
        relative = info["Key"][len(prefix) :]
        if matches(relative, include=include, exclude=exclude):
            yield FoundFile(
                uri=f"s3://{bucket}/{info['Key']}",
                relative_path=relative,
                size=info["size"],
                date_modified=info.get("LastModified"),
            )


def _from_timestamp(value: float) -> datetime:
    return datetime.fromtimestamp(value, tz=UTC)
