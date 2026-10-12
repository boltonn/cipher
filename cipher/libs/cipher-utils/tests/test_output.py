import asyncio
import hashlib
from io import BytesIO
from pathlib import Path

import pytest

from cipher.utils.output import OutputStore
from cipher.utils.uri import list_files, local_copy, local_path, matches, read_bytes


def test_local_path_decodes_file_uris(tmp_path: Path) -> None:
    file = tmp_path / "a b%.txt"
    file.write_bytes(b"hi")
    assert local_path(file.as_uri()) == file
    assert local_path(str(file)) == file
    assert read_bytes(file.as_uri()) == b"hi"
    with local_copy(file.as_uri()) as same:
        assert same == file
    with pytest.raises(ValueError):
        local_path("s3://bucket/key")


def test_stream_write_hashes_and_dedups(tmp_path: Path) -> None:
    store = OutputStore(tmp_path / "out")
    content = b"x" * 3_000_000
    first = store.put_stream(BytesIO(content))
    second = store.put_stream(BytesIO(content))

    assert first.sha256 == hashlib.sha256(content).hexdigest()
    assert first.md5 == hashlib.md5(content).hexdigest()
    assert first.size == len(content)
    assert (first.is_new, second.is_new) == (True, False)
    assert read_bytes(first.uri) == content
    assert list(store.scratch_dir.iterdir()) == []


def test_writer_discards_on_error(tmp_path: Path) -> None:
    store = OutputStore(tmp_path / "out")
    with pytest.raises(RuntimeError), store.writer() as writer:
        writer.write(b"partial")
        raise RuntimeError("limit tripped")
    assert list(store.scratch_dir.iterdir()) == []
    assert not store.exists(hashlib.sha256(b"partial").hexdigest())


def test_put_file_move_and_copy(tmp_path: Path) -> None:
    store = OutputStore(tmp_path / "out")
    scratch = tmp_path / "member.bin"
    scratch.write_bytes(b"member")
    copied = store.put_file(scratch)
    assert scratch.exists() and copied.is_new
    moved = store.put_file(scratch, move=True)
    assert not scratch.exists() and not moved.is_new
    assert read_bytes(moved.uri) == b"member"
    assert list(store.scratch_dir.iterdir()) == []


def test_list_files_filters(tmp_path: Path) -> None:
    (tmp_path / "mail").mkdir()
    (tmp_path / "mail" / "a.eml").write_bytes(b"a")
    (tmp_path / "b.pdf").write_bytes(b"bb")
    (tmp_path / "skip.tmp").write_bytes(b"")

    async def found(**globs):
        return sorted([f.relative_path async for f in list_files(tmp_path, **globs)])

    assert asyncio.run(found()) == ["b.pdf", "mail/a.eml", "skip.tmp"]
    assert asyncio.run(found(exclude=["*.tmp"])) == ["b.pdf", "mail/a.eml"]
    assert asyncio.run(found(include=["mail/*"])) == ["mail/a.eml"]
    assert matches("x/y/z.pdf", include=["*.pdf"]) and not matches("a.pdf", exclude=["*.pdf"])
