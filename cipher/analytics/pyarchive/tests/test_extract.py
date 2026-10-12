import gzip
import io
import os
import tarfile
import zipfile
from pathlib import Path

import pytest
from pyarchive import (
    ArchiveCorruptError,
    ArchiveLimit,
    ArchiveLimitError,
    ArchiveLimits,
    MemberSkipReason,
    decode_to_store,
    extract,
)
from pyarchive.names import normalize_member_name

from cipher.schemas.ingestion.file import Compression
from cipher.utils.output import OutputStore
from cipher.utils.uri import read_bytes

NO_DISK_RESERVE = ArchiveLimits(min_free_bytes=0)
SMALL_BOMB_LIMITS = ArchiveLimits(min_free_bytes=0, max_ratio=10, ratio_min_bytes=1 << 20)


@pytest.fixture
def store(tmp_path: Path) -> OutputStore:
    return OutputStore(tmp_path / "out")


def _zip(path: Path, members: list[tuple[str | zipfile.ZipInfo, bytes]]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in members:
            z.writestr(name, data)
    return path


def _tar(path: Path, members: list[tuple[str, bytes]], mode: str = "w:gz", links: tuple[str, ...] = ()) -> Path:
    with tarfile.open(path, mode) as tar:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for name in links:
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            tar.addfile(info)
    return path


def test_member_names_are_normalized() -> None:
    assert normalize_member_name("../../etc/passwd") == "etc/passwd"
    assert normalize_member_name("/abs/x.txt") == "abs/x.txt"
    assert normalize_member_name("C:\\Users\\nick\\a.txt") == "Users/nick/a.txt"
    assert normalize_member_name("a/./b\x00/c") == "a/b/c"
    assert normalize_member_name("../..") == ""


def test_zip_round_trip_with_hostile_names(tmp_path: Path, store: OutputStore) -> None:
    path = _zip(
        tmp_path / "x.zip", [("../../evil.txt", b"evil"), ("dir/a.txt", b"a"), ("dir/a.txt", b"second a"), ("..", b"x")]
    )
    members = list(extract(path, "zip", store, limits=NO_DISK_RESERVE))

    assert [m.member_path for m in members] == ["evil.txt", "dir/a.txt", "dir/a~2.txt", "_unnamed_1"]
    assert read_bytes(members[2].stored.uri) == b"second a"
    assert all(Path(m.stored.uri.removeprefix("file://")).is_relative_to(store.root.path) for m in members)
    assert not (tmp_path.parent / "evil.txt").exists()


def test_zip_links_and_encrypted_are_skipped(tmp_path: Path, store: OutputStore) -> None:
    link = zipfile.ZipInfo("link")
    link.external_attr = 0o120777 << 16
    path = _zip(tmp_path / "x.zip", [(link, b"/etc/passwd"), ("locked.txt", b"secret"), ("ok.txt", b"ok")])
    data = bytearray(path.read_bytes())  # zipfile won't write the encrypted flag, so set it in the central directory
    entry = data.index(b"PK\x01\x02", data.index(b"PK\x01\x02") + 1)
    assert data[entry + 46 : entry + 56] == b"locked.txt"
    data[entry + 8] |= 0x1
    path.write_bytes(data)
    members = {m.member_path: m for m in extract(path, "zip", store, limits=NO_DISK_RESERVE)}
    assert members["link"].skip_reason == MemberSkipReason.LINK
    assert members["locked.txt"].is_encrypted and members["locked.txt"].stored is None  # no password: nothing stored
    assert members["locked.txt"].skip_reason == MemberSkipReason.ENCRYPTED
    assert members["ok.txt"].skip_reason is None and not members["ok.txt"].is_encrypted


def test_corrupt_zip_member_does_not_stop_the_rest(tmp_path: Path, store: OutputStore) -> None:
    path = tmp_path / "x.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("bad.txt", b"A" * 1000)
        z.writestr("good.txt", b"fine")
    data = bytearray(path.read_bytes())
    data[data.index(b"A" * 1000) + 500] = ord("B")
    path.write_bytes(data)

    members = {m.member_path: m for m in extract(path, "zip", store, limits=NO_DISK_RESERVE)}
    assert members["bad.txt"].skip_reason == MemberSkipReason.CORRUPT
    assert members["good.txt"].stored is not None
    assert list(store.scratch_dir.iterdir()) == []


def test_ratio_bomb_stops_and_keeps_earlier_members(tmp_path: Path, store: OutputStore) -> None:
    path = _zip(tmp_path / "bomb.zip", [("first.txt", b"real evidence"), ("zeros.bin", bytes(8 << 20))])
    seen = []
    with pytest.raises(ArchiveLimitError) as error:
        for member in extract(path, "zip", store, limits=SMALL_BOMB_LIMITS):
            seen.append(member.member_path)
    assert error.value.limit == ArchiveLimit.RATIO
    assert seen == ["first.txt"]
    assert list(store.scratch_dir.iterdir()) == []


def test_total_bytes_and_entries_limits(tmp_path: Path, store: OutputStore) -> None:
    path = _zip(tmp_path / "x.zip", [(f"{i}.txt", os.urandom(1000)) for i in range(5)])
    with pytest.raises(ArchiveLimitError) as error:
        list(extract(path, "zip", store, limits=ArchiveLimits(min_free_bytes=0, max_total_bytes=2500)))
    assert error.value.limit == ArchiveLimit.TOTAL_BYTES

    with pytest.raises(ArchiveLimitError) as error:
        list(extract(path, "zip", store, limits=ArchiveLimits(min_free_bytes=0, max_entries=3)))
    assert error.value.limit == ArchiveLimit.ENTRIES


def test_disk_reserve(tmp_path: Path, store: OutputStore) -> None:
    path = _zip(tmp_path / "x.zip", [("a.txt", b"a")])
    with pytest.raises(ArchiveLimitError) as error:
        list(extract(path, "zip", store, limits=ArchiveLimits(min_free_bytes=1 << 62)))
    assert error.value.limit == ArchiveLimit.DISK


@pytest.mark.parametrize(
    ("mode", "compression"),
    [("w", None), ("w:gz", Compression.GZIP), ("w:bz2", Compression.BZIP2), ("w:xz", Compression.XZ)],
)
def test_tar_family(tmp_path: Path, store: OutputStore, mode: str, compression: Compression | None) -> None:
    path = _tar(tmp_path / "x.tar", [("../a.txt", b"a"), ("dir/b.txt", b"b")], mode=mode, links=("dir/link",))
    members = list(extract(path, "tar", store, compression=compression, limits=NO_DISK_RESERVE))
    assert [(m.member_path, m.skip_reason) for m in members] == [
        ("a.txt", None),
        ("dir/b.txt", None),
        ("dir/link", MemberSkipReason.LINK),
    ]


def test_tar_zstd(tmp_path: Path, store: OutputStore) -> None:
    from backports import zstd

    plain = _tar(tmp_path / "x.tar", [("a.txt", b"zstd member")], mode="w")
    path = tmp_path / "x.tar.zst"
    path.write_bytes(zstd.compress(plain.read_bytes()))
    [member] = extract(path, "tar", store, compression=Compression.ZSTD, limits=NO_DISK_RESERVE)
    assert read_bytes(member.stored.uri) == b"zstd member"


def test_truncated_tar_gz_keeps_what_was_read(tmp_path: Path, store: OutputStore) -> None:
    path = _tar(tmp_path / "x.tar.gz", [("first.txt", b"kept"), ("big.bin", os.urandom(2 << 20))])
    path.write_bytes(path.read_bytes()[: path.stat().st_size // 2])
    seen = []
    with pytest.raises(ArchiveCorruptError):
        for member in extract(path, "tar", store, compression=Compression.GZIP, limits=NO_DISK_RESERVE):
            seen.append(member.member_path)
    assert seen == ["first.txt"]
    assert list(store.scratch_dir.iterdir()) == []


def test_resume_skips_recorded_members(tmp_path: Path, store: OutputStore) -> None:
    for path, filetype, compression in (
        (_zip(tmp_path / "x.zip", [("a.txt", b"a"), ("b.txt", b"b")]), "zip", None),
        (_tar(tmp_path / "x.tar.gz", [("a.txt", b"a"), ("b.txt", b"b")]), "tar", Compression.GZIP),
    ):
        members = list(
            extract(path, filetype, store, compression=compression, limits=NO_DISK_RESERVE, skip=lambda p: p == "a.txt")
        )
        assert [(m.member_path, m.skip_reason, m.stored is None) for m in members] == [
            ("a.txt", MemberSkipReason.ALREADY_DONE, True),
            ("b.txt", None, False),
        ]


def test_progress_is_reported(tmp_path: Path, store: OutputStore) -> None:
    path = _zip(tmp_path / "x.zip", [(f"{i}.txt", b"x") for i in range(3)])
    reports = []
    list(extract(path, "zip", store, limits=NO_DISK_RESERVE, on_progress=reports.append))
    assert reports[-1].members_done == reports[-1].members_total == 3
    assert reports[-1].bytes_in_total == path.stat().st_size


def test_decode_single_stream(tmp_path: Path, store: OutputStore) -> None:
    path = tmp_path / "report.csv.gz"
    path.write_bytes(gzip.compress(b"a,b\n1,2\n"))
    stored = decode_to_store(path, Compression.GZIP, store, NO_DISK_RESERVE)
    assert read_bytes(stored.uri) == b"a,b\n1,2\n"

    bomb = tmp_path / "bomb.gz"
    bomb.write_bytes(gzip.compress(bytes(8 << 20)))
    with pytest.raises(ArchiveLimitError):
        decode_to_store(bomb, Compression.GZIP, store, SMALL_BOMB_LIMITS)
    assert list(store.scratch_dir.iterdir()) == []


def test_sweep_tmp(store: OutputStore) -> None:
    stale = store.scratch_dir / "left-by-a-crash"
    stale.write_bytes(b"partial")
    os.utime(stale, (0, 0))
    fresh = store.scratch_dir / "in-flight"
    fresh.write_bytes(b"partial")
    assert store.sweep_tmp() == 1
    assert [p.name for p in store.scratch_dir.iterdir()] == ["in-flight"]


MBOX = (
    b"From alice@x.com Mon Jul 21 07:28:00 2025\n"
    b"From: alice@x.com\nSubject: Lease\n\nCan we meet?\n>From the landlord: yes\n\n"
    b"From MAILER-DAEMON Tue Jul 22 09:00:00 2025\n"
    b"From: bob@y.com\nSubject: Lease\n\nTuesday.\n"
    b"From - Wed Jul 23 10:00:00 2025\n"
    b"From: carol@z.com\nSubject: a/b\n\nFrom here on, no.\n"
)


def test_mbox_messages_become_eml_members(tmp_path: Path, store: OutputStore) -> None:
    path = tmp_path / "Inbox"
    path.write_bytes(gzip.compress(MBOX))
    members = list(extract(path, "mbox", store, compression=Compression.GZIP, limits=NO_DISK_RESERVE))
    assert [member.member_path for member in members] == ["Lease.eml", "Lease~2.eml", "a_b.eml"]
    first, _, last = (read_bytes(member.stored.uri) for member in members)
    assert first.startswith(b"From: alice@x.com\n") and b"\nFrom the landlord: yes\n" in first
    assert last.endswith(b"From here on, no.\n")


def test_mbox_resume_skips_recorded_messages(tmp_path: Path, store: OutputStore) -> None:
    path = tmp_path / "Inbox.mbox"
    path.write_bytes(MBOX)
    members = list(extract(path, "mbox", store, limits=NO_DISK_RESERVE, skip={"Lease.eml"}.__contains__))
    assert [member.skip_reason for member in members] == [MemberSkipReason.ALREADY_DONE, None, None]


def test_archive_size_limit(tmp_path: Path, store: OutputStore, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _zip(tmp_path / "big.zip", [("a.txt", b"a" * 1000)])
    with pytest.raises(ArchiveLimitError, match="archive_bytes"):
        list(extract(path, "zip", store, limits=ArchiveLimits(max_archive_bytes=100)))
    monkeypatch.setenv("PYARCHIVE_MAX_ARCHIVE_GIB", "0.0000001")  # ~107 bytes
    with pytest.raises(ArchiveLimitError):
        list(extract(path, "zip", store))
    monkeypatch.delenv("PYARCHIVE_MAX_ARCHIVE_GIB")
    assert [m.member_path for m in extract(path, "zip", store)] == ["a.txt"]  # local: no default limit
