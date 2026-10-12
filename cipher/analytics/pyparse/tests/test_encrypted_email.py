import shutil
import subprocess
from pathlib import Path

import pytest
from pyparse.children import DirectorySink
from pyparse.parsers.email import parse_eml
from pyparse.parsers.email.msg import message_class


@pytest.fixture(scope="module")
def smime(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    if shutil.which("openssl") is None:
        pytest.skip("no openssl")
    d = tmp_path_factory.mktemp("smime")
    run = lambda *args: subprocess.run(args, check=True, capture_output=True, cwd=d)  # noqa: E731
    run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "k.pem", "-out", "c.pem",
        "-days", "1", "-subj", "/CN=test")  # fmt: skip
    (d / "m.txt").write_text("Content-Type: text/plain\n\nThe plan for Monday.\n")
    common = ("-from", "alice@example.com", "-to", "bob@example.com", "-subject", "Plan")
    run("openssl", "smime", "-encrypt", "-aes256", "-in", "m.txt", *common, "-out", "enc.eml", "c.pem")
    run("openssl", "smime", "-sign", "-nodetach", "-in", "m.txt", *common, "-out", "signed.eml",
        "-signer", "c.pem", "-inkey", "k.pem")  # fmt: skip
    return {path.name: path.read_bytes() for path in d.glob("*.eml")}


def test_encrypted_eml_keeps_headers(smime: dict[str, bytes], tmp_path: Path) -> None:
    encrypted = parse_eml(smime["enc.eml"], sink=DirectorySink(out_dir=tmp_path))
    assert encrypted.is_encrypted
    assert encrypted.metadata.title == "Plan" and encrypted.metadata.sent_from.value == "alice@example.com"
    signed = parse_eml(smime["signed.eml"], sink=DirectorySink(out_dir=tmp_path / "s"))
    assert not signed.is_encrypted and "The plan for Monday." in (signed.plain or "")


def test_pgp_eml_is_encrypted() -> None:
    pgp_mime = b'Content-Type: multipart/encrypted; protocol="application/pgp-encrypted"; boundary=b\n\n--b--\n'
    assert parse_eml(pgp_mime).is_encrypted
    assert not parse_eml(b"Subject: hi\nContent-Type: text/plain\n\nhello\n").is_encrypted


class _Ole:
    def __init__(self, streams: dict[str, bytes]) -> None:
        self.streams = streams

    def exists(self, name: str) -> bool:
        return name in self.streams

    def openstream(self, name: str):  # noqa: ANN201
        import io

        return io.BytesIO(self.streams[name])


def test_msg_message_class() -> None:
    encrypted = _Ole({"__substg1.0_001A001F": "IPM.Note.SMIME".encode("utf-16-le")})
    signed = _Ole({"__substg1.0_001A001E": b"IPM.Note.SMIME.MultipartSigned\x00"})
    assert message_class(encrypted) == "IPM.Note.SMIME"
    assert message_class(signed) == "IPM.Note.SMIME.MultipartSigned"
    assert message_class(_Ole({})) is None
