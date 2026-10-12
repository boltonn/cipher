import bz2
import gzip
import io
import re
import shutil
import subprocess
import tarfile
from functools import partial
from pathlib import Path

import pytest
from filetyper.models.main import FileTyper

from cipher.schemas.ingestion.file import Compression

CSV = b"name,email,phone\n" + b"".join(f"person {i},p{i}@example.com,555-01{i:02d}\n".encode() for i in range(200))


@pytest.fixture(scope="module")
def typer() -> FileTyper:
    return FileTyper()


def _tar(path: Path, mode: str) -> Path:
    with tarfile.open(path, mode) as tar:
        info = tarfile.TarInfo("docs/a.csv")
        info.size = len(CSV)
        tar.addfile(info, io.BytesIO(CSV))
    return path


def test_gzipped_csv_is_a_csv(tmp_path: Path, typer: FileTyper) -> None:
    path = tmp_path / "report.csv.gz"
    with (
        open(path, "wb") as raw,
        gzip.GzipFile(filename="report.csv", mode="wb", fileobj=raw, mtime=1_700_000_000) as gz,
    ):
        gz.write(CSV)
    info = typer.get_file_info(path)
    assert info["filetype"] == "csv"
    assert info["compression"].encoding == Compression.GZIP
    assert info["compression"].filename == "report.csv"
    assert info["compression"].date_modified.year == 2023
    assert info["compression"].sha256 == info["sha256"]


@pytest.mark.parametrize(
    ("name", "mode", "encoding"), [("logs.tar.gz", "w:gz", Compression.GZIP), ("logs.tar.xz", "w:xz", Compression.XZ)]
)
def test_compressed_tar_is_a_tar(tmp_path: Path, typer: FileTyper, name: str, mode: str, encoding: Compression) -> None:
    info = typer.get_file_info(_tar(tmp_path / name, mode))
    assert (info["filetype"], info["filetype_group"]) == ("tar", "archive")
    assert info["compression"].encoding == encoding


def test_bzip2_text(tmp_path: Path, typer: FileTyper) -> None:
    path = tmp_path / "notes.txt.bz2"
    path.write_bytes(bz2.compress(b"Meeting notes for Tuesday. " * 200))
    info = typer.get_file_info(path)
    assert info["filetype_group"] != "archive"
    assert info["compression"].encoding == Compression.BZIP2


def test_corrupt_gzip_stays_as_found(tmp_path: Path, typer: FileTyper) -> None:
    path = tmp_path / "broken.gz"
    path.write_bytes(gzip.compress(CSV)[:20])
    info = typer.get_file_info(path)
    assert info["filetype"] == "gzip"
    assert info["compression"] is None


def test_zip_is_not_compression(tmp_path: Path, typer: FileTyper) -> None:
    import zipfile

    path = tmp_path / "x.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("a.csv", CSV)
    info = typer.get_file_info(path)
    assert info["filetype"] == "zip"
    assert info["compression"] is None


def test_office_bytes_are_not_zips(typer: FileTyper) -> None:
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
    assert typer.infer_bytes(buffer.getvalue())["filetype"] == "docx"


def test_model_labels_take_registry_groups(tmp_path: Path, typer: FileTyper) -> None:
    blob = tmp_path / "e3b0c442"  # a blob: no extension, so the model types it
    blob.write_bytes(
        b"From: Alice <a@example.com>\nTo: b@example.com\nSubject: Hi\nDate: Mon, 1 Jan 2024 10:00:00 +0000\n\nHello Bob\n"
    )
    info = typer.infer_path(blob)
    assert (info["filetype"], info["filetype_group"]) == ("eml", "email")
    blob.write_bytes(CSV)
    assert typer.infer_path(blob)["filetype_group"] == "table"


def test_heuristics_use_the_real_name(tmp_path: Path, typer: FileTyper) -> None:
    blob = tmp_path / "9f86d081"
    blob.write_bytes(b"x,y\n1,2\n")
    assert typer.infer_path(blob, name="plan.csv")["filetype"] == "csv"
    blob.write_bytes(
        b"import os\n\n\ndef main() -> None:\n    print(os.getcwd())\n\n\nif __name__ == '__main__':\n    main()\n"
    )
    assert typer.infer_path(blob, name="notes.txt")["filetype"] == "python"  # generic txt refined by magika


def test_encryption_flags(tmp_path: Path, typer: FileTyper) -> None:
    import zipfile

    from filetyper.encryption import CFB_MAGIC, OOXML_ENCRYPTED_STREAM, is_encrypted

    path = tmp_path / "x.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("a.txt", b"a")
    data = bytearray(path.read_bytes())
    data[data.index(b"PK\x01\x02") + 8] |= 0x1
    path.write_bytes(data)
    assert typer.get_file_info(path)["is_encrypted"]
    assert not is_encrypted(io.BytesIO(b"%PDF-1.7\n1 0 obj\ntrailer << /Root 1 0 R >>"), "pdf")
    assert is_encrypted(io.BytesIO(CFB_MAGIC + bytes(600) + OOXML_ENCRYPTED_STREAM), "doc")


def test_magic_and_empty_beat_the_name(tmp_path: Path, typer: FileTyper) -> None:
    blob = tmp_path / "9f86d081"
    blob.write_bytes(bytes([0, 5, 22, 7, 0, 2, 0, 0]) + bytes(200))
    assert typer.infer_path(blob, name="._report.py")["filetype"] == "appledouble"  # macOS metadata, not python
    blob.write_bytes(b"")
    assert typer.infer_path(blob, name="__init__.py")["filetype"] == "empty"


def test_shapefile_family_by_header(tmp_path: Path, typer: FileTyper) -> None:
    blob = tmp_path / "blob"
    blob.write_bytes(bytes([0, 0, 39, 10, 255, 255, 254, 112]) + bytes(200))
    assert typer.infer_path(blob, name="Routes.sbx")["filetype"] == "shapefileindex"  # magika guesses iso
    blob.write_bytes(bytes([0, 0, 39, 10]) + bytes(200))
    assert typer.infer_path(blob, name="Routes.shp")["filetype"] == "shapefile"


@pytest.mark.parametrize(("user_password", "expected"), [("secret", True), ("", False)])
def test_pdf_encrypted_only_when_it_needs_a_password(user_password: str, expected: bool) -> None:
    fitz = pytest.importorskip("fitz")
    pytest.importorskip("pypdfium2")
    from filetyper.encryption import is_encrypted

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "lease")
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=user_password, owner_pw="owner", permissions=0)
    assert is_encrypted(io.BytesIO(data), "pdf") is expected  # owner-only: locked against editing, opens freely


@pytest.fixture(scope="module")
def smime(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    if shutil.which("openssl") is None:
        pytest.skip("no openssl")
    d = tmp_path_factory.mktemp("smime")
    run = partial(subprocess.run, check=True, capture_output=True, cwd=d)
    run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "k.pem", "-out", "c.pem",
         "-days", "1", "-subj", "/CN=test"])  # fmt: skip
    (d / "m.txt").write_text("Content-Type: text/plain\n\nThe plan for Monday.\n")
    run(["openssl", "smime", "-encrypt", "-aes256", "-in", "m.txt", "-out", "enc.eml", "c.pem"])
    run(["openssl", "smime", "-sign", "-nodetach", "-in", "m.txt", "-out", "signed.eml", "-signer", "c.pem",
         "-inkey", "k.pem"])  # fmt: skip
    run(["openssl", "cms", "-encrypt", "-aes256", "-in", "m.txt", "-outform", "DER", "-out", "enc.p7m", "c.pem"])
    run(["openssl", "cms", "-sign", "-nodetach", "-in", "m.txt", "-outform", "DER", "-out", "signed.p7m",
         "-signer", "c.pem", "-inkey", "k.pem"])  # fmt: skip
    return {path.name: path.read_bytes() for path in d.iterdir()}


def test_smime_encrypted_but_not_signed(smime: dict[str, bytes]) -> None:
    from filetyper.encryption import is_encrypted

    assert is_encrypted(io.BytesIO(smime["enc.eml"]), "eml")
    assert not is_encrypted(io.BytesIO(smime["signed.eml"]), "eml")
    no_hint = re.sub(rb";\s*smime-type=enveloped-data", b"", smime["enc.eml"])  # decided from the CMS body instead
    assert b"smime-type" not in no_hint and is_encrypted(io.BytesIO(no_hint), "eml")
    assert is_encrypted(io.BytesIO(smime["enc.p7m"]), "pkcs7")
    assert not is_encrypted(io.BytesIO(smime["signed.p7m"]), "pkcs7")


def test_pgp_encrypted() -> None:
    from filetyper.encryption import is_encrypted

    pgp_mime = b'Content-Type: multipart/encrypted; protocol="application/pgp-encrypted"; boundary=b\n\n--b--\n'
    assert is_encrypted(io.BytesIO(pgp_mime), "eml")
    inline = b"Content-Type: text/plain\n\n-----BEGIN PGP MESSAGE-----\nhQEMA...\n-----END PGP MESSAGE-----\n"
    assert is_encrypted(io.BytesIO(inline), "eml")
    assert not is_encrypted(io.BytesIO(b"Content-Type: text/plain\n\nhello\n"), "eml")
    if shutil.which("gpg"):
        for armor in ([], ["--armor"]):
            data = subprocess.run(
                ["gpg", "--batch", "--yes", "--passphrase", "x", "--pinentry-mode", "loopback", "--symmetric",
                 "--output", "-", *armor],
                input=b"secret", capture_output=True, check=True,
            ).stdout  # fmt: skip
            assert is_encrypted(io.BytesIO(data), "pgp")
