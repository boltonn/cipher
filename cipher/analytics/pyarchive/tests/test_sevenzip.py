import shutil
import subprocess
from pathlib import Path

import pytest
from pyarchive import (
    ArchiveEncryptedError,
    ArchiveLimit,
    ArchiveLimitError,
    ArchiveLimits,
    MemberSkipReason,
    extract,
    find_sevenzip,
)

from cipher.schemas.ingestion.file import ArchiveSandbox
from cipher.utils.output import OutputStore
from cipher.utils.uri import read_bytes

SEVENZIP = find_sevenzip()
pytestmark = pytest.mark.skipif(SEVENZIP is None, reason="no 7zz installed")
NO_DISK_RESERVE = ArchiveLimits(min_free_bytes=0, sandbox=ArchiveSandbox.REQUIRED)


@pytest.fixture
def store(tmp_path: Path) -> OutputStore:
    return OutputStore(tmp_path / "out")


@pytest.fixture
def source(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "dir").mkdir(parents=True)
    (src / "dir" / "a.txt").write_text("alpha")
    (src / "b.txt").write_text("bravo")
    (src / "link").symlink_to("/etc/passwd")
    return src


def _7z(archive: Path, src: Path, *options: str) -> Path:
    subprocess.run([str(SEVENZIP), "a", "-snl", "-bso0", *options, str(archive), "."], cwd=src, check=True)
    return archive


def test_7z_members_dirs_and_links(tmp_path: Path, store: OutputStore, source: Path) -> None:
    path = _7z(tmp_path / "x.7z", source)
    members = {m.member_path: m for m in extract(path, "sevenzip", store, limits=NO_DISK_RESERVE)}
    assert set(members) == {"b.txt", "dir/a.txt", "link"}
    assert members["link"].skip_reason == MemberSkipReason.LINK
    assert read_bytes(members["dir/a.txt"].stored.uri) == b"alpha"
    assert members["b.txt"].date_last_updated is not None
    assert list(store.scratch_dir.iterdir()) == []


def test_7z_encrypted_data_and_listing(tmp_path: Path, store: OutputStore, source: Path) -> None:
    data_encrypted = _7z(tmp_path / "d.7z", source, "-pSECRET")
    members = list(extract(data_encrypted, "sevenzip", store, limits=NO_DISK_RESERVE))
    assert all(m.is_encrypted for m in members if m.skip_reason != MemberSkipReason.LINK)
    assert {m.skip_reason for m in members} == {MemberSkipReason.ENCRYPTED, MemberSkipReason.LINK}

    listing_encrypted = _7z(tmp_path / "h.7z", source, "-pSECRET", "-mhe=on")
    with pytest.raises(ArchiveEncryptedError):
        list(extract(listing_encrypted, "sevenzip", store, limits=NO_DISK_RESERVE))


def test_7z_passwords_tried_in_turn(tmp_path: Path, store: OutputStore, source: Path) -> None:
    path = _7z(tmp_path / "d.7z", source, "-pFIRST", "-ms=off")
    (source / "c.txt").write_text("charlie")
    subprocess.run([str(SEVENZIP), "a", "-bso0", "-pSECOND", str(path), "c.txt"], cwd=source, check=True)
    members = {
        m.member_path: m
        for m in extract(path, "sevenzip", store, limits=NO_DISK_RESERVE, passwords=["x", "SECOND", "FIRST"])
    }
    assert read_bytes(members["c.txt"].stored.uri) == b"charlie"
    assert read_bytes(members["dir/a.txt"].stored.uri) == b"alpha"
    assert members["b.txt"].is_encrypted and members["b.txt"].skip_reason is None

    listing_encrypted = _7z(tmp_path / "h.7z", source, "-pSECRET", "-mhe=on")
    members = {
        m.member_path: m
        for m in extract(listing_encrypted, "sevenzip", store, limits=NO_DISK_RESERVE, passwords=["x", "SECRET"])
    }
    assert read_bytes(members["b.txt"].stored.uri) == b"bravo"


def test_zip_passwords_and_methods_only_7zz_reads(tmp_path: Path, store: OutputStore, source: Path) -> None:
    def zip_with(name: str, *options: str) -> Path:
        return _7z(tmp_path / name, source, "-tzip", *options)

    zipcrypto = zip_with("zc.zip", "-pPW", "-mem=ZipCrypto")  # the stdlib decrypts this one itself
    members = {
        m.member_path: m for m in extract(zipcrypto, "zip", store, limits=NO_DISK_RESERVE, passwords=["no", "PW"])
    }
    assert read_bytes(members["b.txt"].stored.uri) == b"bravo"

    aes = zip_with("aes.zip", "-pPW", "-mem=AES256")
    locked = {m.member_path: m for m in extract(aes, "zip", store, limits=NO_DISK_RESERVE)}
    assert locked["b.txt"].skip_reason == MemberSkipReason.ENCRYPTED
    members = {m.member_path: m for m in extract(aes, "zip", store, limits=NO_DISK_RESERVE, passwords=["PW"])}
    assert read_bytes(members["dir/a.txt"].stored.uri) == b"alpha"
    assert members["dir/a.txt"].is_encrypted

    deflate64 = zip_with("d64.zip", "-mm=Deflate64")
    members = {m.member_path: m for m in extract(deflate64, "zip", store, limits=NO_DISK_RESERVE)}
    assert read_bytes(members["b.txt"].stored.uri) == b"bravo"
    assert list(store.scratch_dir.iterdir()) == []


def test_7z_resume_and_ratio(tmp_path: Path, store: OutputStore, source: Path) -> None:
    path = _7z(tmp_path / "x.7z", source)
    members = list(extract(path, "sevenzip", store, limits=NO_DISK_RESERVE, skip=lambda p: p == "b.txt"))
    assert {m.member_path: m.skip_reason for m in members}["b.txt"] == MemberSkipReason.ALREADY_DONE

    (source / "zeros.bin").write_bytes(bytes(64 << 20))
    bomb = _7z(tmp_path / "bomb.7z", source)
    limits = ArchiveLimits(min_free_bytes=0, max_ratio=10, ratio_min_bytes=1 << 20)
    with pytest.raises(ArchiveLimitError) as error:
        list(extract(bomb, "sevenzip", store, limits=limits))
    assert error.value.limit == ArchiveLimit.RATIO
    assert list(store.scratch_dir.iterdir()) == []


@pytest.mark.skipif(shutil.which("genisoimage") is None, reason="no genisoimage to build an ISO")
def test_iso(tmp_path: Path, store: OutputStore, source: Path) -> None:
    (source / "link").unlink()
    iso = tmp_path / "disk.iso"
    subprocess.run(["genisoimage", "-quiet", "-R", "-J", "-o", str(iso), str(source)], check=True)
    members = {m.member_path: m for m in extract(iso, "iso", store, limits=NO_DISK_RESERVE)}
    assert read_bytes(members["dir/a.txt"].stored.uri) == b"alpha"


def test_non_ascii_names(tmp_path: Path, store: OutputStore) -> None:
    src = tmp_path / "ru"
    src.mkdir()
    (src / "Сотрудники.txt").write_text("список")
    members = list(extract(_7z(tmp_path / "ru.7z", src), "sevenzip", store, limits=NO_DISK_RESERVE))
    assert [m.member_path for m in members] == ["Сотрудники.txt"]
    assert read_bytes(members[0].stored.uri) == "список".encode()


def test_sandbox_off_still_limits_members(tmp_path: Path, store: OutputStore, source: Path) -> None:
    (source / "big.bin").write_bytes(bytes(3 << 20))
    path = _7z(tmp_path / "x.7z", source, "-pPW")
    off = ArchiveLimits(min_free_bytes=0, sandbox=ArchiveSandbox.OFF)
    members = {m.member_path: m for m in extract(path, "sevenzip", store, limits=off, passwords=["PW"])}
    assert read_bytes(members["dir/a.txt"].stored.uri) == b"alpha"

    small = off.model_copy(update={"max_member_bytes": 1 << 20})  # no RLIMIT_FSIZE without the jail
    with pytest.raises(ArchiveLimitError) as tripped:
        list(extract(path, "sevenzip", OutputStore(tmp_path / "other"), limits=small, passwords=["PW"]))
    assert tripped.value.limit == ArchiveLimit.MEMBER_BYTES


def test_missing_tools_fail_saying_what_to_install(
    tmp_path: Path, store: OutputStore, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    from pyarchive import MissingDependencyError, missing_dependency

    module = sys.modules["pyarchive.extract"]  # `pyarchive.extract` is also the exported function

    seven = _7z(tmp_path / "x.7z", source)
    aes = _7z(tmp_path / "aes.zip", source, "-tzip", "-pPW", "-mem=AES256")
    (source / "plain.txt").write_text("plain")
    subprocess.run([str(SEVENZIP), "a", "-bso0", "-tzip", "-mm=Deflate", str(aes), "plain.txt"], cwd=source, check=True)
    monkeypatch.setattr(module, "find_sevenzip", lambda: None)

    with pytest.raises(MissingDependencyError, match="~/.local/share/cipher/bin/7zz"):
        list(extract(seven, "sevenzip", store, limits=NO_DISK_RESERVE))
    read = []
    with pytest.raises(MissingDependencyError, match="only 7zz reads"):
        read.extend(m.member_path for m in extract(aes, "zip", store, limits=NO_DISK_RESERVE, passwords=["PW"]))
    assert "plain.txt" in read  # what the stdlib could read is kept

    monkeypatch.setattr(module, "MISSING_DECODERS", {"zst": "the zstd decoder: install the `zstd` extra"})
    assert "zstd` extra" in missing_dependency("zst")
    assert missing_dependency("zip") is None


def test_wrong_password_block_error_is_not_corruption(
    tmp_path: Path, store: OutputStore, source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong password sometimes also prints `ERROR: Data Error : #1` (the block, no member): not corrupt."""
    import sys

    module = sys.modules["pyarchive.backends.sevenzip"]
    real = module._jailed

    def with_block_error(binary: Path, args: list[str], *rest: object) -> subprocess.Popen:
        if args[0] != "x" or "-p-" in args:
            return real(binary, args, *rest)
        script = (
            "import sys, subprocess; r = subprocess.run(sys.argv[1:]); print('ERROR: Data Error : #1'); sys.exit(2)"
        )
        return real(Path(sys.executable), ["-c", script, str(binary), *args], *rest)

    monkeypatch.setattr(module, "_jailed", with_block_error)
    path = _7z(tmp_path / "d.7z", source, "-pFIRST", "-ms=off")
    off = ArchiveLimits(min_free_bytes=0, sandbox=ArchiveSandbox.OFF)  # the wrapper itself must be able to run 7zz
    members = list(extract(path, "sevenzip", store, limits=off, passwords=["x"]))
    assert {m.skip_reason for m in members if m.member_path != "link"} == {MemberSkipReason.ENCRYPTED}
