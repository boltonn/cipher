"""An email attached inside an Outlook .msg, rebuilt as `.eml` bytes so it is extracted as an email of its own.

An attached Outlook item is not a file inside the .msg but a nested message storage
([MS-OXMSG] 2.2.2.1), which `msg_parser` cannot read (it looks its properties up at the root).
Its properties are read here straight from the OLE storage, and its own attachments come along,
with a nested attached message becoming a `message/rfc822` part.
"""

import email
import struct
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.policy import default
from email.utils import format_datetime, formataddr

from loguru import logger
from olefile import OleFileIO

from pyparse.parsers.email.rtf import rtf_body

EMBEDDED_MESSAGE_STORAGE = "__substg1.0_3701000D"
_ATTACH_PREFIX = "__attach_version1.0_"
_RECIP_PREFIX = "__recip_version1.0_"
_PROPERTIES_STREAM = "__properties_version1.0"
_EMBEDDED_HEADER_BYTES, _CHILD_HEADER_BYTES = 24, 8
_PT_SYSTIME, _PT_LONG = 0x0040, 0x0003
_FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)

_SUBJECT, _TRANSPORT_HEADERS = 0x0037, 0x007D
_BODY, _RTF_COMPRESSED, _HTML = 0x1000, 0x1009, 0x1013
_SENDER_NAME, _SENDER_ADDRESS, _SENDER_SMTP = 0x0C1A, 0x0C1F, 0x5D01
_MESSAGE_ID, _IN_REPLY_TO, _REFERENCES = 0x1035, 0x1042, 0x1039
_SUBMIT_TIME, _DELIVERY_TIME = 0x0039, 0x0E06
_DISPLAY_NAME, _EMAIL_ADDRESS, _SMTP_ADDRESS, _RECIPIENT_TYPE = 0x3001, 0x3003, 0x39FE, 0x0C15
_ATTACH_DATA, _ATTACH_FILENAME, _ATTACH_LONG_FILENAME = 0x3701, 0x3704, 0x3707
_RECIPIENT_HEADERS = {1: "To", 2: "Cc", 3: "Bcc"}
_BODY_HEADERS = frozenset({"content-type", "content-transfer-encoding", "mime-version", "content-disposition"})


class _Storage:
    """Typed property reads from one storage of a .msg (a message, an attachment, or a recipient)."""

    def __init__(self, ole: OleFileIO, path: list[str], header_bytes: int) -> None:
        self.ole, self.path, self.header_bytes = ole, path, header_bytes

    def string(self, property_id: int) -> str | None:
        for kind, encoding in (("001F", "utf-16-le"), ("001E", "cp1252")):
            if (raw := self._stream(f"__substg1.0_{property_id:04X}{kind}")) is not None:
                return raw.decode(encoding, errors="replace").rstrip("\x00") or None
        return None

    def binary(self, property_id: int) -> bytes | None:
        return self._stream(f"__substg1.0_{property_id:04X}0102")

    def fixed(self, property_id: int, kind: int) -> bytes | None:
        """The 8-byte value of a fixed-length property ([MS-OXMSG] 2.4.2)."""
        raw = self._stream(_PROPERTIES_STREAM) or b""
        for offset in range(self.header_bytes, len(raw) - 15, 16):
            tag = struct.unpack_from("<I", raw, offset)[0]
            if tag == (property_id << 16 | kind):
                return raw[offset + 8 : offset + 16]
        return None

    def time(self, property_id: int) -> datetime | None:
        raw = self.fixed(property_id, _PT_SYSTIME)
        ticks = struct.unpack("<Q", raw)[0] if raw else 0
        return _FILETIME_EPOCH + timedelta(microseconds=ticks // 10) if ticks else None

    def children(self, prefix: str, header_bytes: int) -> list["_Storage"]:
        depth = len(self.path) + 1
        return [
            _Storage(self.ole, entry, header_bytes)
            for entry in self.ole.listdir(streams=False, storages=True)
            if len(entry) == depth and entry[: depth - 1] == self.path and entry[-1].startswith(prefix)
        ]

    def has(self, name: str) -> bool:
        return self.ole.exists([*self.path, name])

    def _stream(self, name: str) -> bytes | None:
        stream = [*self.path, name]
        return self.ole.openstream(stream).read() if self.ole.exists(stream) else None


def embedded_message_eml(ole: OleFileIO, attachment_storage: str) -> bytes | None:
    """The message attached at `attachment_storage` (an `__attach_version1.0_#...` name) as `.eml` bytes."""
    try:
        storage = _Storage(ole, [attachment_storage, EMBEDDED_MESSAGE_STORAGE], _EMBEDDED_HEADER_BYTES)
        return _to_email(storage).as_bytes(policy=default.clone(linesep="\r\n"))
    except (OSError, ValueError, struct.error) as e:
        logger.warning(f"Unreadable embedded message in {attachment_storage}: {e}")
        return None


def embedded_message_subject(ole: OleFileIO, attachment_storage: str) -> str | None:
    """The attached message's subject, for its file name."""
    return _Storage(ole, [attachment_storage, EMBEDDED_MESSAGE_STORAGE], _EMBEDDED_HEADER_BYTES).string(_SUBJECT)


def _to_email(storage: _Storage) -> EmailMessage:
    message = EmailMessage()
    for name, value in _headers(storage):
        try:
            message[name] = value
        except (ValueError, TypeError):
            logger.debug(f"Dropped unrepresentable {name} header on an embedded message")

    plain, html = storage.string(_BODY), storage.string(_HTML)
    if html is None and (raw_html := storage.binary(_HTML)):
        html = raw_html.decode("utf-8", errors="replace")
    if not (plain or html):
        plain, html = rtf_body(storage.binary(_RTF_COMPRESSED))
    message.set_content(plain or "")
    if html:
        message.add_alternative(html, subtype="html")

    for attachment in storage.children(_ATTACH_PREFIX, _CHILD_HEADER_BYTES):
        filename = attachment.string(_ATTACH_LONG_FILENAME) or attachment.string(_ATTACH_FILENAME)
        if attachment.has(EMBEDDED_MESSAGE_STORAGE):
            nested = _Storage(storage.ole, [*attachment.path, EMBEDDED_MESSAGE_STORAGE], _EMBEDDED_HEADER_BYTES)
            message.add_attachment(_to_email(nested))
        elif (data := attachment.binary(_ATTACH_DATA)) is not None:
            message.add_attachment(data, maintype="application", subtype="octet-stream", filename=filename)
    return message


def _headers(storage: _Storage) -> list[tuple[str, str]]:
    """The original transport headers when Outlook kept them; otherwise rebuilt from properties."""
    if transport := storage.string(_TRANSPORT_HEADERS):
        parsed = email.message_from_string(transport)
        return [(name, str(value)) for name, value in parsed.items() if name.lower() not in _BODY_HEADERS]

    headers: list[tuple[str, str]] = []
    if sender := storage.string(_SENDER_SMTP) or storage.string(_SENDER_ADDRESS):
        headers.append(("From", formataddr((storage.string(_SENDER_NAME) or "", sender))))
    recipients: dict[str, list[str]] = {}
    for recipient in storage.children(_RECIP_PREFIX, _CHILD_HEADER_BYTES):
        kind = recipient.fixed(_RECIPIENT_TYPE, _PT_LONG)
        header = _RECIPIENT_HEADERS.get(struct.unpack_from("<I", kind)[0] if kind else 1, "To")
        address = recipient.string(_SMTP_ADDRESS) or recipient.string(_EMAIL_ADDRESS) or ""
        recipients.setdefault(header, []).append(formataddr((recipient.string(_DISPLAY_NAME) or "", address)))
    headers.extend((header, ", ".join(addresses)) for header, addresses in recipients.items())
    if subject := storage.string(_SUBJECT):
        headers.append(("Subject", subject))
    if sent := storage.time(_SUBMIT_TIME) or storage.time(_DELIVERY_TIME):
        headers.append(("Date", format_datetime(sent)))
    for header, property_id in (
        ("Message-ID", _MESSAGE_ID),
        ("In-Reply-To", _IN_REPLY_TO),
        ("References", _REFERENCES),
    ):
        if value := storage.string(property_id):
            headers.append((header, value))
    return headers
