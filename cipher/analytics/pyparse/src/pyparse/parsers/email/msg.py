"""Outlook .msg files (OLE compound-file format): ``parse_msg``.

Delegates all header-string parsing (address decoding, from/to/cc/bcc,
`EmailClient`/`MessageState` detection, date parsing) to the .eml reader, since a
.msg file's `TransportMessageHeaders` property is the same RFC 822 header
blob `extract_metadata` already reads -- .msg only differs in where
the body and attachments live (OLE properties, not MIME parts), and in
exposing a few native properties (`Subject`, sender addresses,
`InternetMessageId`, `DeliverTime`) that fill in whenever the transport
headers are absent or incomplete, which some .msg exports don't preserve.
"""

import email
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from msg_parser.msg_parser import Message
from olefile import OleFileIO

from cipher.schemas.content.email import EmailAddress, EmailBase
from cipher.schemas.ingestion.file import FileBase
from pyparse.children import ChildSink, describe_only
from pyparse.parsers.email.eml import EmailOptions, extract_metadata, with_meaningful_hash
from pyparse.parsers.email.inline import ContentIdParts, content_id_key, resolve_inline_images
from pyparse.parsers.email.msg_embedded import embedded_message_eml, embedded_message_subject
from pyparse.parsers.email.rtf import rtf_body

_SENDER_PROPERTY_KEYS = ("SenderSmtpAddress", "SenderEmailAddress", "SentRepresentingSmtpAddress")
# PidTagMessageClass as a top-level stream (Unicode, then ANSI); `IPM.Note.SMIME` is an encrypted
# message (its body is an attached smime.p7m), `IPM.Note.SMIME.MultipartSigned` only signed.
_MESSAGE_CLASS_STREAMS = (("__substg1.0_001A001F", "utf-16-le"), ("__substg1.0_001A001E", "latin-1"))
_ENCRYPTED_MESSAGE_CLASS = "ipm.note.smime"


def message_class(ole: OleFileIO) -> str | None:
    """The message's own class (`IPM.Note`, `IPM.Note.SMIME`, ...), or None when absent."""
    for stream, encoding in _MESSAGE_CLASS_STREAMS:
        if ole.exists(stream):
            return ole.openstream(stream).read().decode(encoding, errors="replace").rstrip("\x00")
    return None


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


def _native_sender(properties: dict) -> EmailAddress | None:
    for key in _SENDER_PROPERTY_KEYS:
        if address := properties.get(key):
            return EmailAddress(name=_fix_mojibake(properties.get("SenderName")), value=_fix_mojibake(address))
    return None


def _extract_meta(msg: Message, *, return_raw_header: bool) -> dict[str, Any]:
    """Parse `TransportMessageHeaders` as an .eml's headers, then patch in native OLE properties.

    `TransportMessageHeaders` is the same RFC 822 header blob an .eml file has, so address /
    state / client detection is identical. When headers are missing or don't carry a field
    (from / title / message_id / date_sent), the equivalent native property fills the gap.
    """
    properties = msg.properties
    header_msg = email.message_from_string(_fix_mojibake(properties.get("TransportMessageHeaders")) or "")
    out = extract_metadata(header_msg, return_raw_header=return_raw_header)

    if out["from"] is None:
        out["from"] = _native_sender(properties)
    if out.get("title") is None:
        out["title"] = _fix_mojibake(properties.get("Subject"))
    if out.get("message_id") is None:
        out["message_id"] = properties.get("InternetMessageId")
    if out.get("date_sent") is None:
        native_date = properties.get("DeliverTime") or properties.get("CreationTime")
        if isinstance(native_date, datetime):
            out["date_sent"] = native_date
    return out


def _extract_body(properties: dict) -> tuple[str | None, str | None]:
    """The plain and HTML bodies; an RTF-only body (common in Outlook) is read as text."""
    html = properties.get("Html")
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="ignore")
    plain = properties.get("Body")
    if isinstance(plain, bytes):
        plain = plain.decode("utf-8", errors="ignore")
    plain, html = _fix_mojibake(plain) or None, _fix_mojibake(html) or None
    return (plain, html) if plain or html else rtf_body(properties.get("RtfCompressed"))


def _content_id_parts(msg: Message) -> ContentIdParts:
    """Attached files with a Content-ID (the HTML may show them inline)."""
    parts: ContentIdParts = {}
    for attachment in msg.attachments.values():
        payload = attachment.get("AttachDataObject")
        if payload is not None and (content_id := content_id_key(attachment.get("AttachContentId"))):
            parts[content_id] = (attachment.get("AttachMimeTag") or "application/octet-stream", payload)
    return parts


def _extract_attachments(
    msg: Message, ole: OleFileIO, *, inline_content_ids: set[str], save_inline_images: bool, sink: ChildSink
) -> list[FileBase]:
    """True attachments (attached Outlook items as `.eml`), each handed to ``sink``.

    Images the body shows (``inline_content_ids``) go to ``sink`` only when ``save_inline_images``, and are
    never returned.
    """
    children: list[FileBase] = []
    for storage, attachment in msg.attachments.items():
        file_name = _fix_mojibake(attachment.get("AttachLongFilename") or attachment.get("AttachFilename"))
        is_inline = content_id_key(attachment.get("AttachContentId")) in inline_content_ids
        if (payload := attachment.get("AttachDataObject")) is not None:
            if is_inline and not save_inline_images:
                continue
            child = sink(data=payload, filename=file_name)
            if not is_inline:
                children.append(child)
        elif "EmbeddedMessage" in attachment and (eml := embedded_message_eml(ole, storage)):
            children.append(sink(data=eml, filename=f"{embedded_message_subject(ole, storage) or 'attached'}.eml"))
        else:
            logger.debug(f"Outlook attachment {file_name!r} ({storage}) has no data; skipped")
    return children


def parse_msg(
    source: bytes | str | Path,
    *,
    sink: ChildSink = describe_only,
    options: EmailOptions | None = None,
) -> EmailBase:
    """Parse an Outlook .msg into an ``EmailBase`` (same shape as ``parse_eml``).

    OLE is read as binary, so ``options.encoding`` doesn't apply, and a .msg has no MIME tree
    for HTML sanitization; ``options.return_raw_header`` does apply.

    Args:
        source: Raw bytes, or a path to a ``.msg`` file.
        sink: Receives each attachment (an attached Outlook item as ``.eml``) and returns its record.
        options: How to read it (``EmailOptions``).

    Returns:
        The parsed email; ``is_encrypted`` when its message class is ``IPM.Note.SMIME``.
    """
    options = options or EmailOptions()
    with OleFileIO(source if isinstance(source, bytes) else Path(source)) as ole:
        msg = Message(ole.root.kids_dict)
        metadata = _extract_meta(msg, return_raw_header=options.return_raw_header)
        plain, html = _extract_body(msg.properties)
        html, inline_content_ids = resolve_inline_images(
            html, _content_id_parts(msg), embed=options.embed_inline_images
        )
        attachments = _extract_attachments(
            msg,
            ole,
            inline_content_ids=inline_content_ids,
            save_inline_images=options.save_inline_images,
            sink=sink,
        )
        encrypted = (message_class(ole) or "").lower() == _ENCRYPTED_MESSAGE_CLASS

    return EmailBase(
        html=html,
        plain=plain,
        is_encrypted=encrypted,
        attachments=attachments,
        metadata=with_meaningful_hash(metadata, plain=plain, html=html),
    )
