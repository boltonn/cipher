"""RFC 822 / RFC 2822 / MIME email files: ``parse_eml``.

Functions, no state. Child files (attachments, winmail.dat contents, inline images) go to the
caller's ``ChildSink``; HTML handling is ``pyparse.parsers.text.html``.

Design notes
------------
- The parser is a dumb extractor: it surfaces ``html``, ``plain``, and
  ``attachments`` exactly as found in the MIME tree, with no text-derivation
  or sanitization logic baked in.
- HTML sanitization is opt-in via ``EmailOptions(sanitize_html=True)``. When omitted the
  raw decoded HTML is stored as-is so callers that only need text extraction
  don't pay for a second parse pass.
- ``EmailBase`` owns all post-parse logic (text derivation, on-demand
  sanitization) through its ``get_text`` and ``get_sanitized_html`` methods.
- Multiple ``text/html`` parts are merged by concatenating their body
  contents rather than joining full documents, avoiding the invalid-HTML
  problem caused by stacking ``<html>/<head>/<body>`` wrappers.
"""

from __future__ import annotations

import base64
import binascii
import email
import re
from collections.abc import Iterator
from datetime import datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, mktime_tz, parsedate_tz
from pathlib import Path
from typing import Any

import chardet
from loguru import logger
from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas.content.email import EmailBase, EmailCategory, EmailClient, MessageState, NamedParticipantDict
from cipher.schemas.ingestion.file import FileBase
from pyparse.children import ChildSink, describe_only
from pyparse.parsers.email.inline import ContentIdParts, content_id_key, resolve_inline_images
from pyparse.parsers.email.meaningful_hash import meaningful_hash
from pyparse.parsers.email.rtf import rtf_body
from pyparse.parsers.email.smime import is_pkcs7_mime, signed_content
from pyparse.parsers.email.winmail import WinmailContent, is_winmail, parse_winmail
from pyparse.parsers.text.html import html_to_text, parse_html
from pyparse.utils.io import get_encoding_families, map_unsupported_encoding

_BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)
_MESSAGE_ID_RE = re.compile(r"<([^<>\s]+)>")
_ATTACHED_MESSAGE_TYPES = frozenset({"message/rfc822", "message/global"})
_THREAD_INDEX_ROOT_BYTES = 22


def _thread_index_root(thread_index: str | None) -> str | None:
    """Outlook's Thread-Index grows 5 bytes per reply; its first 22 bytes are the same for the whole thread."""
    if not thread_index:
        return None
    try:
        raw = base64.b64decode("".join(thread_index.split()), validate=True)
    except (binascii.Error, ValueError):
        return thread_index.strip()
    return base64.b64encode(raw[:_THREAD_INDEX_ROOT_BYTES]).decode() if len(raw) >= _THREAD_INDEX_ROOT_BYTES else None


def _walk_own_parts(message: Message) -> Iterator[Message]:
    """`Message.walk()` that stops at attached emails and opens opaque-signed S/MIME.

    An attached email's parts belong to it, not to this email. A signed `smime.p7m` is this
    email's own content wrapped in a signature, so it is walked in its place.
    """
    if is_pkcs7_mime(message.get_content_type(), message.get_filename()) and (
        inner := signed_content(message.get_payload(decode=True) or b"")
    ):
        yield from _walk_own_parts(email.message_from_bytes(inner))
        return
    yield message
    if message.get_content_type() in _ATTACHED_MESSAGE_TYPES or not message.is_multipart():
        return
    for part in message.get_payload():
        yield from _walk_own_parts(part)


def _extract_body_content(html: str) -> str:
    """Extract or create body of html.

    Return the inner content of the first <body> tag, or the whole
    string when no ``<body>`` wrapper is present (fragment emails).
    """
    m = _BODY_RE.search(html)
    return m.group(1) if m else html


def _merge_html_parts(parts: list[str]) -> str:
    """Merge multiple decoded text/html MIME parts into a single valid HTML document.

    Joining raw documents stacks ``<html>/<head>/<body>`` wrappers and
    produces invalid markup. Instead we extract each document's body content
    and wrap the concatenation in a single ``<body>``. When only one part
    exists it is returned unchanged to preserve the original document
    structure.
    """
    if len(parts) == 1:
        return parts[0]
    bodies = [_extract_body_content(p) for p in parts]
    return "<body>\n" + "\n".join(bodies) + "\n</body>"


def with_meaningful_hash(metadata: dict[str, Any], *, plain: str | None, html: str | None) -> dict[str, Any]:
    """`metadata` plus its meaningful hash (the body is only read when there is no Message-ID)."""
    body = plain or (html_to_text(html) if html and not metadata.get("message_id") else None)
    if hashed := meaningful_hash(metadata, body):
        metadata["meaningful_hash"], metadata["meaningful_hash_source"] = hashed
    return metadata


class EmailOptions(BaseModel):
    """How to read an email (separate from the email itself)."""

    encoding: str = Field(default="ISO-8859-1", description="Encoding when reading an .eml from a path")
    return_raw_header: bool = Field(default=False, description="Attach the decoded header dict as `raw_header`")
    sanitize_html: bool = Field(default=False, description="Sanitize the HTML (and mine its inline images)")
    embed_inline_images: bool = Field(
        default=False, description="Swap the HTML's cid: links for data: URIs so the body renders on its own"
    )
    save_inline_images: bool = Field(
        default=True,
        description="Hand images the body shows (cid: links) to the sink as child files; never listed as attachments",
    )


def _decode_header_value(raw: str) -> str:
    parts = decode_header(raw)
    try:
        return str(make_header(parts))
    except (UnicodeDecodeError, LookupError):
        return _decode_header_fallback(parts)


def _decode_header_fallback(parts: list[tuple[bytes, str | None]]) -> str:
    decoded: list[str] = []
    for raw_bytes, enc in parts:
        if enc is None:
            decoded.append(raw_bytes.decode(errors="replace"))
            continue
        try:
            decoded.append(raw_bytes.decode(enc))
            continue
        except LookupError:
            enc = map_unsupported_encoding(enc) or enc
        except UnicodeDecodeError:
            pass
        detected = chardet.detect(raw_bytes).get("encoding")
        if detected:
            try:
                decoded.append(raw_bytes.decode(detected))
                continue
            except UnicodeDecodeError:
                pass
        for candidate in get_encoding_families(enc) or []:
            try:
                decoded.append(raw_bytes.decode(candidate))
                break
            except UnicodeDecodeError:
                continue
        else:
            decoded.append(raw_bytes.decode(enc or "utf-8", errors="ignore"))
    return "".join(decoded)


def _decode_all_headers(msg: Message) -> dict[str, str]:
    return {key.lower(): _decode_header_value(value) for key, value in dict(msg.items()).items()}


def _get_addresses(msg: Message, header_field: str) -> list[NamedParticipantDict]:
    raw = msg.get_all(header_field, [])
    results: list[NamedParticipantDict] = []
    for name, addr in getaddresses(raw):
        try:
            decoded_name = _decode_header_value(name) or None
        except Exception:
            decoded_name = None
        results.append(NamedParticipantDict(name=decoded_name, value=re.sub(r"\s+", "", addr)))
    return results


def _decode_part(part: Message, fallback: str = "utf-8") -> str:
    raw = part.get_payload(decode=True)
    if raw is None:
        return ""
    charset = part.get_content_charset(fallback)
    try:
        return raw.decode(charset, errors="ignore")
    except LookupError:
        detected = chardet.detect(raw).get("encoding")
        return raw.decode(detected or fallback, errors="ignore")


def _parse_header_params(header: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for segment in header.split(";")[1:]:
        segment = segment.strip()
        if "=" not in segment:
            continue
        key, _, value = segment.partition("=")
        out[key.strip().strip('"')] = value.strip().strip('"')
    return out


def _resolve_filename(part: Message, content_type: str | None) -> str | None:
    name = part.get_filename()
    if name:
        return _decode_header_value(name)
    if content_type:
        params = _parse_header_params(content_type)
        return params.get("name")
    return None


def _parse_date(date_str: str) -> datetime | None:
    try:
        tup = parsedate_tz(date_str)
        return datetime.fromtimestamp(mktime_tz(tup)) if tup else None
    except Exception:
        return None


def _build_attachment(
    part: Message, content_type: str, disposition_params: dict[str, str], *, sink: ChildSink
) -> FileBase | None:
    """A MIME attachment part handed to ``sink`` (an attached email as its own ``.eml``); None without a payload."""
    file_name = disposition_params.get("filename") or _resolve_filename(part, content_type) or None
    if part.get_content_type() in _ATTACHED_MESSAGE_TYPES:
        attached = part.get_payload(0)
        payload: bytes | None = attached.as_bytes()
        file_name = file_name or f"{_decode_header_value(attached.get('subject', '')).strip() or 'attached'}.eml"
    else:
        payload = part.get_payload(decode=True)
    if payload is None:
        logger.debug(f"Attachment {file_name!r} has no payload; skipped")
        return None
    attachment = sink(data=payload, filename=file_name)
    if raw_mod := disposition_params.get("modification-date"):
        attachment.date_last_updated = _parse_date(raw_mod)
    if raw_cre := disposition_params.get("creation-date"):
        attachment.date_created = _parse_date(raw_cre)
    return attachment


def _extract_parts(msg: Message, *, options: EmailOptions, sink: ChildSink) -> dict[str, Any]:
    """Walk the MIME tree and collect plain text, HTML, and attachments.

    ``html`` is set to the merged body of all ``text/html`` parts (see
    ``_merge_html_parts``). When ``sanitize_html=True`` it is additionally
    sanitized (unsafe tags stripped, inline images mined).

    Inline base64 images are mined (and handed to ``sink``) only when ``sanitize_html=True``.

    Args:
        msg: Parsed ``email.message.Message`` object.
        options: How to read it (sanitizing, inline images).
        sink: Receives every child file.

    Returns:
        Dict with keys ``html``, ``plain``, ``attachments`` (true attachments, not inline images).
    """
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[FileBase] = []
    winmail_bodies: list[WinmailContent] = []
    attachment_parts: list[tuple[Message, str, dict[str, str]]] = []
    content_id_parts: ContentIdParts = {}

    for part in _walk_own_parts(msg):
        content_type = part.get_content_type()
        raw_disposition = part.get("Content-Disposition")
        kind = raw_disposition.split(";")[0].strip().lower() if raw_disposition else None

        if content_type.startswith("multipart"):
            continue

        # "attachment" is the unambiguous case. But inline images
        # referenced via cid: in the HTML body (kind == "inline") and
        # parts some senders send with no Content-Disposition header at
        # all (kind is None, identified only by Content-Type's `name=`
        # param) are just as much real files -- every one of them needs
        # its own File row, even though none of them get text-extracted
        # by default. text/plain and text/html are excluded since those
        # are the body itself, never a distinct file, even on the rare
        # occasion one of them carries a filename param.
        is_attachment = (
            kind == "attachment"
            or content_type in _ATTACHED_MESSAGE_TYPES
            or (
                kind in (None, "inline")
                and content_type not in ("text/plain", "text/html")
                and _resolve_filename(part, content_type) is not None
            )
        )

        if is_winmail(content_type, part.get_filename()) and (
            winmail := parse_winmail(part.get_payload(decode=True) or b"")
        ):
            winmail_bodies.append(winmail)
            attachments.extend(_winmail_attachments(winmail, sink=sink))
            continue

        if is_attachment:
            params = _parse_header_params(raw_disposition) if raw_disposition else {}
            attachment_parts.append((part, content_type, params))
            if content_id := content_id_key(part.get("Content-ID")):
                content_id_parts[content_id] = (content_type, part.get_payload(decode=True) or b"")
            continue

        if content_type == "text/plain":
            plain_parts.append(_decode_part(part))
        elif content_type == "text/html":
            html_parts.append(_decode_part(part))

    if not plain_parts and not html_parts:
        for winmail in winmail_bodies:
            plain_body, html_body = (
                (winmail.plain, winmail.html) if winmail.plain or winmail.html else rtf_body(winmail.rtf_compressed)
            )
            plain_parts += [plain_body] if plain_body else []
            html_parts += [html_body] if html_body else []
    plain: str | None = "\n\n".join(plain_parts) or None
    html: str | None = _merge_html_parts(html_parts) if html_parts else None

    if html and options.sanitize_html:
        html = parse_html(html, method="html", sink=sink).text or None
    html, shown = resolve_inline_images(html, content_id_parts, embed=options.embed_inline_images)
    for part, content_type, params in attachment_parts:
        is_inline = content_id_key(part.get("Content-ID")) in shown
        if is_inline and not options.save_inline_images:
            continue
        item = _build_attachment(part, content_type, params, sink=sink)
        if item is not None and not is_inline:
            attachments.append(item)

    return {"html": html, "plain": plain, "attachments": attachments}


def _winmail_attachments(winmail: WinmailContent, *, sink: ChildSink) -> list[FileBase]:
    """winmail.dat's packed files (a winmail.dat inside one is opened too)."""
    files: list[FileBase] = []
    for found in winmail.attachments:
        if nested := parse_winmail(found.data):
            files.extend(_winmail_attachments(nested, sink=sink))
        else:
            files.append(sink(data=found.data, filename=found.filename))
    return files


def extract_metadata(msg: Message, *, return_raw_header: bool) -> dict[str, Any]:
    """Header fields (subject, addresses, dates, ids, thread keys, client, state) as `EmailMetadata` input."""
    headers = _decode_all_headers(msg)
    out: dict[str, Any] = {}

    if subject := headers.pop("subject", None):
        out["title"] = subject.strip()

    from_addrs = _get_addresses(msg, "from")
    out["from"] = from_addrs[0] if from_addrs else None
    out["to"] = _get_addresses(msg, "to")
    out["cc"] = _get_addresses(msg, "cc")
    out["bcc"] = _get_addresses(msg, "bcc")

    if date_str := headers.pop("date", None):
        out["date_sent"] = _parse_date(date_str)

    out["message_id"] = headers.get("message-id", "").strip().strip("<>") or None
    out["references"] = _MESSAGE_ID_RE.findall(headers.get("references", ""))
    out["in_reply_to"] = next(iter(_MESSAGE_ID_RE.findall(headers.get("in-reply-to", ""))), None)
    out["conversation_id"] = next(
        (
            key
            for key in (
                headers.get("x-gm-thrid"),
                _thread_index_root(headers.get("thread-index")),
                *out["references"],
                out["in_reply_to"],
                out["message_id"],
            )
            if key
        ),
        None,
    )
    out["labels"] = [v.strip() for v in headers.get("x-gmail-labels", "").split(",") if v.strip()]

    client = EmailClient.detect(headers)
    out["email_client"] = client
    out["categories"] = EmailCategory.for_email(client, out["labels"])
    if client == EmailClient.GMAIL:
        out["state"] = MessageState.from_gmail_labels(out["labels"])
    elif client == EmailClient.OUTLOOK:
        out["state"] = MessageState.from_folder(headers.get("x-folder"))
    else:
        out["state"] = None

    if return_raw_header:
        out["raw_header"] = headers

    return out


def parse_eml(
    source: bytes | str | Path,
    *,
    sink: ChildSink = describe_only,
    options: EmailOptions | None = None,
) -> EmailBase:
    """Parse an RFC 822 / MIME email into an ``EmailBase``.

    ``html`` is the merged ``text/html`` content (sanitized when ``options.sanitize_html``),
    ``plain`` the ``text/plain`` content; every attachment, winmail.dat packed file and (when
    sanitizing) inline image goes through ``sink``.

    Args:
        source: Raw bytes, or a path to an ``.eml`` file.
        sink: Receives each child file and returns its record (default: typed, bytes not kept).
        options: How to read it (``EmailOptions``).

    Returns:
        The parsed email.

    Raises:
        TypeError: When ``source`` is not bytes, str, or Path.
    """
    options = options or EmailOptions()
    if isinstance(source, bytes):
        msg = email.message_from_bytes(source)
    elif isinstance(source, (str, Path)):
        with open(Path(source), encoding=options.encoding) as fh:
            msg = email.message_from_file(fh)
    else:
        raise TypeError(f"Unsupported source type: {type(source).__name__!r}")

    metadata = extract_metadata(msg, return_raw_header=options.return_raw_header)
    parts = _extract_parts(msg, options=options, sink=sink)
    return EmailBase(
        html=parts["html"],
        plain=parts["plain"],
        is_encrypted=_body_is_encrypted(msg, parts["plain"]),
        attachments=parts["attachments"],
        metadata=with_meaningful_hash(metadata, plain=parts["plain"], html=parts["html"]),
    )


def _body_is_encrypted(msg: email.message.Message, plain: str | None) -> bool:
    """The body needs a key: PGP/MIME, inline PGP, or an S/MIME p7m that isn't merely signed."""
    content_type = msg.get_content_type()
    if content_type == "multipart/encrypted":
        return True
    if is_pkcs7_mime(content_type, msg.get_filename()):
        return signed_content(msg.get_payload(decode=True) or b"") is None
    return content_type == "text/plain" and "-----BEGIN PGP MESSAGE-----" in (plain or "")
