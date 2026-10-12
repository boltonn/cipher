"""Is a file encrypted -- does reading it need a password? Cheap checks per format; no password is guessed.

7z / rar header encryption needs the archive's own reader, so archive extraction sets it there.
An encrypted email (S/MIME enveloped, PGP) still has readable headers; only its body needs the key.
An Outlook .msg is flagged by pyparse when parsed (its message class), not here: that needs the OLE reader.
A PDF encrypted only against editing or printing opens without a password, so it is not encrypted
here; telling the two apart needs `pypdfium2` (the `pdf` extra), without it any `/Encrypt` counts.
"""

import base64
import re
import zipfile
from email.parser import BytesHeaderParser
from functools import cache
from typing import BinaryIO

from loguru import logger

SCAN_BYTES = 1 << 20
CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# An encrypted docx/xlsx/pptx is an OLE compound file holding an `EncryptedPackage` stream.
OOXML_ENCRYPTED_STREAM = "EncryptedPackage".encode("utf-16-le")
ZIP_FILETYPES = frozenset({"zip", "jar", "xpi", "apk"})
# CMS content types that need a key: EnvelopedData (1.2.840.113549.1.7.3), AuthEnvelopedData (...9.16.1.23).
CMS_ENCRYPTED_OIDS = (bytes.fromhex("2a864886f70d010703"), bytes.fromhex("2a864886f70d0109100117"))
PKCS7_MIME_TYPES = frozenset({"application/pkcs7-mime", "application/x-pkcs7-mime"})
PGP_MESSAGE = b"-----BEGIN PGP MESSAGE-----"
PGP_FILETYPES = frozenset({"pgp", "asc", "pem"})
# Only their archive reader can tell (archive extraction sets the flag), so a re-type leaves it be.
READER_DECIDES_FILETYPES = frozenset({"sevenzip", "rar", "iso", "cab", "arj", "lha", "xar", "dmg", "squashfs"})


def is_encrypted(raw: BinaryIO, filetype: str) -> bool:
    """True when the file (or, for a zip, any member) is encrypted.

    Args:
        raw: The file's bytes, seekable, positioned at its start (left there on return).
        filetype: Its filetype.
    """
    try:
        if filetype in ZIP_FILETYPES:
            with zipfile.ZipFile(raw) as archive:
                return any(info.flag_bits & 0x1 for info in archive.infolist())
        head = raw.read(SCAN_BYTES)
        if filetype == "eml":
            return _eml_is_encrypted(head)
        if filetype == "pkcs7":
            return _cms_is_encrypted(head)
        if filetype in PGP_FILETYPES or head.lstrip().startswith(PGP_MESSAGE):
            return head.lstrip().startswith(PGP_MESSAGE) or _is_binary_pgp_message(head)
        if head.startswith(CFB_MAGIC):
            return OOXML_ENCRYPTED_STREAM in head
        if filetype == "pdf":
            raw.seek(max(raw.seek(0, 2) - SCAN_BYTES, 0))
            return (b"/Encrypt" in head or b"/Encrypt" in raw.read()) and _pdf_needs_password(raw)
        return False
    except (zipfile.BadZipFile, OSError, ValueError):
        return False
    finally:
        raw.seek(0)


def _eml_is_encrypted(head: bytes) -> bool:
    """S/MIME enveloped (`application/pkcs7-mime`, not `signed-data`), PGP/MIME (`multipart/encrypted`), or inline PGP."""
    headers = BytesHeaderParser().parsebytes(head)
    content_type = headers.get_content_type()
    if content_type == "multipart/encrypted":
        return True
    if content_type in PKCS7_MIME_TYPES:
        smime_type = (headers.get_param("smime-type") or "").lower()
        if smime_type:
            return smime_type != "signed-data"
        body = head.split(b"\r\n\r\n", 1)[-1] if b"\r\n\r\n" in head else head.split(b"\n\n", 1)[-1]
        return _cms_is_encrypted(body)
    return content_type == "text/plain" and PGP_MESSAGE in head


def _cms_is_encrypted(data: bytes) -> bool:
    """A CMS / PKCS#7 blob (DER, or base64 / PEM of it) whose content type needs a key."""
    der = data
    if not data.startswith(b"\x30"):
        text = re.sub(rb"-----[^-]+-----|\s", b"", data[:4096])
        try:
            der = base64.b64decode(text[: len(text) // 4 * 4])
        except ValueError:
            return False
    return any(oid in der[:64] for oid in CMS_ENCRYPTED_OIDS)


def _is_binary_pgp_message(head: bytes) -> bool:
    """An OpenPGP message that opens with a session-key packet (public-key 1 or symmetric 3), old or new format."""
    if not head:
        return False
    first = head[0]
    if first & 0xC0 == 0xC0:
        return first & 0x3F in (1, 3)
    return first & 0x80 == 0x80 and (first >> 2) & 0x0F in (1, 3)


def _pdf_needs_password(raw: BinaryIO) -> bool:
    try:
        import pypdfium2
    except ImportError:
        _warn_no_pdfium()
        return True
    raw.seek(0)
    try:
        pypdfium2.PdfDocument(raw).close()
    except pypdfium2.PdfiumError as e:
        return getattr(e, "err_code", None) == pypdfium2.raw.FPDF_ERR_PASSWORD
    return False


@cache
def _warn_no_pdfium() -> None:
    logger.warning(
        "Missing pypdfium2 (install filetyper's `pdf` extra): without it filetyper can't tell a PDF that needs "
        "a password from one only locked against editing or printing, so every PDF with /Encrypt is flagged "
        "is_encrypted, including ones that open freely"
    )
