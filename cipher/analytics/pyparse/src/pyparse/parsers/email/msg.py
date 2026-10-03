"""Parser for Outlook .msg files (OLE compound-file format).

Delegates all header-string parsing (address decoding, from/to/cc/bcc,
`EmailClient`/`MessageState` detection, date parsing) to `EmlParser`, since a
.msg file's `TransportMessageHeaders` property is the same RFC 822 header
blob `EmlParser` already knows how to read -- .msg only differs in where
the body and attachments live (OLE properties, not MIME parts), and in
exposing a few native properties (`Subject`, sender addresses,
`InternetMessageId`, `DeliverTime`) that fill in whenever the transport
headers are absent or incomplete, which some .msg exports don't preserve.
"""

import email
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from filetyper import FileTyper
from loguru import logger
from msg_parser.msg_parser import Message
from olefile import OleFileIO

from cipher.schemas.content.email import EmailAddress, EmailBase
from cipher.schemas.ingestion.file import FileBase
from pyparse.parsers.email.eml import EmlParser
from pyparse.utils.io import safe_open

try:
    import compressed_rtf
except ImportError:
    compressed_rtf = None

_SENDER_PROPERTY_KEYS = ("SenderSmtpAddress", "SenderEmailAddress", "SentRepresentingSmtpAddress")


def _fix_mojibake(text: str | None) -> str | None:
    """Undo a double-decode `msg_parser` applies to non-Unicode string properties.

    `msg_parser`'s property-ID map hardcodes every named string property as
    PT_UNICODE and decodes it as UTF-16LE regardless of the property's
    actual per-file type code -- for a .msg that stored a property as
    PT_STRING8 (single-byte/ANSI, common for older or US-authored messages),
    every pair of ANSI bytes gets merged into one CJK-range codepoint (e.g.
    "He" -> "效"). Re-encoding the mangled string as UTF-16LE recovers the
    original bytes; only applied when doing so yields printable text, since
    a property that genuinely was PT_UNICODE must be left alone.
    """
    if not text:
        return text
    try:
        # PT_STRING8 properties are often NUL-terminated; that terminator
        # survives the byte-pair regrouping as a trailing \x00 that would
        # otherwise fail the printability check below.
        candidate = text.encode("utf-16-le").decode("latin-1").rstrip("\x00")
    except UnicodeError:
        return text
    if not candidate:
        return text
    printable = sum(1 for c in candidate if c.isprintable() or c in "\r\n\t")
    return candidate if printable / len(candidate) > 0.98 else text


class MsgParser:
    """Parser for Outlook .msg files.

    Args:
        file_typer: Shared ``FileTyper`` instance used for attachment metadata
            enrichment, same as ``EmlParser``. A default instance is created
            when omitted.
    """

    def __init__(self, file_typer: FileTyper | None = None) -> None:
        self.file_typer = file_typer or FileTyper()
        self._eml_parser = EmlParser(file_typer=self.file_typer)

    @staticmethod
    def _load(source: bytes | str | Path) -> Message:
        if isinstance(source, bytes):
            return Message(OleFileIO(source).root.kids_dict)
        with OleFileIO(Path(source)) as ole:
            return Message(ole.root.kids_dict)

    @staticmethod
    def _native_sender(properties: dict) -> EmailAddress | None:
        for key in _SENDER_PROPERTY_KEYS:
            if address := properties.get(key):
                return EmailAddress(name=_fix_mojibake(properties.get("SenderName")), value=_fix_mojibake(address))
        return None

    def _extract_meta(self, msg: Message, *, return_raw_header: bool) -> dict[str, Any]:
        """Parse `TransportMessageHeaders` via `EmlParser`, then patch in native OLE properties.

        `TransportMessageHeaders` is the same RFC 822 header blob an .eml
        file has, so address/state/client detection is identical -- reused
        as-is rather than reimplemented. When headers are missing or don't
        carry a given field (from/title/message_id/date_sent), the
        equivalent native property fills the gap.
        """
        properties = msg.properties
        header_msg = email.message_from_string(_fix_mojibake(properties.get("TransportMessageHeaders")) or "")
        out = self._eml_parser._extract_meta(header_msg, return_raw_header=return_raw_header)

        if out["from"] is None:
            out["from"] = self._native_sender(properties)
        if out.get("title") is None:
            out["title"] = _fix_mojibake(properties.get("Subject"))
        if out.get("message_id") is None:
            out["message_id"] = properties.get("InternetMessageId")
        if out.get("date_sent") is None:
            native_date = properties.get("DeliverTime") or properties.get("CreationTime")
            if isinstance(native_date, datetime):
                out["date_sent"] = native_date

        return out

    @staticmethod
    def _extract_body(properties: dict) -> tuple[str | None, str | None]:
        html = properties.get("Html")
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="ignore")
        html = _fix_mojibake(html)

        plain = properties.get("Body")
        if isinstance(plain, bytes):
            plain = plain.decode("utf-8", errors="ignore")
        plain = _fix_mojibake(plain)

        if not plain and not html and compressed_rtf and "RtfCompressed" in properties:
            try:
                plain = compressed_rtf.decompress(properties["RtfCompressed"])
            except Exception as e:
                logger.error(f"Error decompressing RTF body: {e}")

        return plain or None, html or None

    def _extract_attachments(self, msg: Message, *, extract_children: bool, out_dir: Path | None) -> list[FileBase]:
        attachments = []
        for attachment in msg.attachments.values():
            payload: bytes | None = attachment.get("AttachDataObject")
            if payload is None:
                continue

            file_name = _fix_mojibake(attachment.get("AttachLongFilename") or attachment.get("AttachFilename"))
            ext = Path(file_name).suffix if file_name else None
            md5 = hashlib.md5(payload).hexdigest()
            sha256 = hashlib.sha256(payload).hexdigest()
            filetype_info = self.file_typer.infer(payload)

            if extract_children:
                if out_dir is None:
                    raise ValueError("out_dir must be provided when extract_children=True")
                if ext is None and filetype_info.extensions:
                    ext = filetype_info.extensions[0]
                out_path = out_dir / f"{md5}{ext or '.bin'}"
                with safe_open(out_path, "wb") as fh:
                    fh.write(payload)

            attachments.append(
                FileBase(
                    filename=file_name,
                    filetype=filetype_info["filetype"],
                    filetype_group=filetype_info["filetype_group"],
                    md5=md5,
                    sha256=sha256,
                    mime_type=filetype_info["mime_type"],
                    size=len(payload),
                    **({"path": str(out_path), "uri": out_path.as_uri()} if extract_children else {}),
                )
            )
        return attachments

    def parse(
        self,
        source: bytes | str | Path,
        *,
        return_raw_header: bool = False,
        extract_children: bool = False,
        out_dir: Path | None = None,
    ) -> EmailBase:
        """Parse an Outlook .msg file from bytes or a file path into an ``EmailBase``.

        Mirrors ``EmlParser.parse``'s return shape for interchangeability via
        ``parse_email()``. Has no ``encoding``/``sanitize_html`` parameters --
        OLE is read as binary (no filesystem-encoding concern) and .msg has
        no MIME tree to run through ``HtmlParser``.

        Args:
            source: Raw bytes, a path string, or a ``Path`` to a ``.msg`` file.
            return_raw_header: Attaches the decoded transport-header dict to
                ``EmailBase.raw_header`` when ``True``.
            extract_children: Write attachment payloads to ``out_dir``.
            out_dir: Target directory for extracted files. Required when
                ``extract_children=True``.

        Returns:
            A fully assembled ``EmailBase`` instance.

        Raises:
            ValueError: When ``extract_children=True`` and ``out_dir`` is None.
        """
        msg = self._load(source)
        metadata = self._extract_meta(msg, return_raw_header=return_raw_header)
        plain, html = self._extract_body(msg.properties)
        attachments = self._extract_attachments(msg, extract_children=extract_children, out_dir=out_dir)

        return EmailBase(html=html, plain=plain, attachments=attachments, metadata=metadata)
