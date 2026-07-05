"""Stateless parser for RFC 822 / RFC 2822 / MIME email files.

HTML handling is delegated to ``pyparse.parsers.text.html.HtmlParser``.

Design notes
------------
- The parser is a dumb extractor: it surfaces ``html``, ``plain``, and
  ``attachments`` exactly as found in the MIME tree, with no text-derivation
  or sanitization logic baked in.
- HTML sanitization is opt-in via ``sanitize_html=True``. When omitted the
  raw decoded HTML is stored as-is so callers that only need text extraction
  don't pay for a second parse pass.
- ``EmailBase`` owns all post-parse logic (text derivation, on-demand
  sanitization) through its ``get_text`` and ``get_sanitized_html`` methods.
- Multiple ``text/html`` parts are merged by concatenating their body
  contents rather than joining full documents, avoiding the invalid-HTML
  problem caused by stacking ``<html>/<head>/<body>`` wrappers.
"""

from __future__ import annotations

import email
import hashlib
import re
from datetime import datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, mktime_tz, parsedate_tz
from pathlib import Path
from typing import Any

import chardet
from filetyper import FileTyper

from cipher.schemas.email import EmailBase, EmailState, ParticipantDict, ParticipantType
from cipher.schemas.file import FileBase
from pyparse.parsers.text.html import HtmlParser
from pyparse.utils.io import get_encoding_families, map_unsupported_encoding, safe_open

_BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)


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


class EmlParser:
    """Parser for RFC 822 / RFC 2822 / MIME email files.

    The parser stores the raw decoded HTML and plain-text parts on
    ``EmailBase`` without imposing any text-derivation or sanitization
    strategy. Callers control post-parse behaviour through ``EmailBase``
    methods:

    - ``email.get_text(mode)`` — derive a text string from whichever parts
      are available.
    - ``email.get_sanitized_html()`` — run the HTML through ``HtmlParser``
      on demand.

    Sanitization during parsing is available via ``sanitize_html=True`` when
    you need the cleaned markup up-front (e.g. for immediate frontend display).

    Args:
        file_typer: Shared ``FileTyper`` instance used for attachment metadata
            enrichment and base64 image mining. A default instance is created
            when omitted.
    """

    def __init__(self, file_typer: FileTyper | None = None) -> None:
        self.file_typer = file_typer or FileTyper()
        self.html_parser = HtmlParser(filetyper=self.file_typer)

    def _decode_header_value(self, raw: str) -> str:
        parts = decode_header(raw)
        try:
            return str(make_header(parts))
        except (UnicodeDecodeError, LookupError):
            return self._decode_header_fallback(parts)

    @staticmethod
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

    def _decode_all_headers(self, msg: Message) -> dict[str, str]:
        return {
            key.lower(): self._decode_header_value(value)
            for key, value in dict(msg.items()).items()
        }

    def _get_addresses(self, msg: Message, header_field: str) -> list[ParticipantDict]:
        raw = msg.get_all(header_field, [])
        results: list[ParticipantDict] = []
        for name, addr in getaddresses(raw):
            try:
                decoded_name = self._decode_header_value(name) or None
            except Exception:
                decoded_name = None
            results.append(
                ParticipantDict(
                    name=decoded_name, type=ParticipantType.EMAIL, value=re.sub(r"\s+", "", addr)
                )
            )
        return results

    @staticmethod
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

    @staticmethod
    def _parse_header_params(header: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for segment in header.split(";")[1:]:
            segment = segment.strip()
            if "=" not in segment:
                continue
            key, _, value = segment.partition("=")
            out[key.strip().strip('"')] = value.strip().strip('"')
        return out

    def _resolve_filename(self, part: Message, content_type: str | None) -> str | None:
        name = part.get_filename()
        if name:
            return self._decode_header_value(name)
        if content_type:
            params = self._parse_header_params(content_type)
            return params.get("name")
        return None

    @staticmethod
    def _parse_date(date_str: str) -> datetime | None:
        try:
            tup = parsedate_tz(date_str)
            return datetime.fromtimestamp(mktime_tz(tup)) if tup else None
        except Exception:
            return None

    def _build_attachment(
        self,
        part: Message,
        content_type: str,
        disposition_params: dict[str, str],
        *,
        extract_children: bool,
        out_dir: Path | None,
    ) -> FileBase | None:
        """Builds a ``FileBase`` from a MIME attachment part.

        Always returns attachment metadata. When ``extract_children=True`` the
        payload is also written to ``out_dir``.

        Args:
            part: The MIME part to process.
            content_type: Raw Content-Type header value.
            disposition_params: Parsed Content-Disposition parameters.
            extract_children: When ``True``, writes the payload to ``out_dir``.
            out_dir: Target directory. Required when ``extract_children=True``.

        Returns:
            A populated ``FileBase``, or ``None`` when the part has no payload.
        """
        payload: bytes | None = part.get_payload(decode=True)
        if payload is None:
            return None

        file_name = (
            disposition_params.get("filename")
            or self._resolve_filename(part, content_type)
            or None
        )
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

        attachment = FileBase(
            filename=file_name,
            filetype=filetype_info["filetype"],
            filetype_group=filetype_info["filetype_group"],
            md5=md5,
            sha256=sha256,
            mime_type=filetype_info["mime_type"],
            size=len(payload),
            **({"path": str(out_path), "uri": out_path.as_uri()} if extract_children else {}),
        )
        if raw_mod := disposition_params.get("modification-date"):
            attachment.date_last_updated = self._parse_date(raw_mod)
        if raw_cre := disposition_params.get("creation-date"):
            attachment.date_created = self._parse_date(raw_cre)
        return attachment

    def _extract_parts(
        self,
        msg: Message,
        *,
        sanitize_html: bool,
        extract_children: bool,
        out_dir: Path | None,
    ) -> dict[str, Any]:
        """Walk the MIME tree and collect plain text, HTML, and attachments.

        ``html`` is set to the merged body of all ``text/html`` parts (see
        ``_merge_html_parts``). When ``sanitize_html=True`` it is additionally
        run through ``HtmlParser`` to strip unsafe tags and mine images.

        Image mining only occurs when both ``sanitize_html=True`` and
        ``extract_children=True``, since ``HtmlParser`` is the component that
        performs the mining.

        Args:
            msg: Parsed ``email.message.Message`` object.
            sanitize_html: When ``True``, run the merged HTML through
                ``HtmlParser`` to strip unsafe tags and mine images.
            extract_children: Write attachment payloads to ``out_dir``.
            out_dir: Target directory for extracted files.

        Returns:
            Dict with keys ``html``, ``plain``, ``attachments``.
        """
        plain_parts: list[str] = []
        html_parts: list[str] = []
        attachments: list[FileBase] = []

        for part in msg.walk():
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
            is_attachment = kind == "attachment" or (
                kind in (None, "inline")
                and content_type not in ("text/plain", "text/html")
                and self._resolve_filename(part, content_type) is not None
            )

            if is_attachment:
                params = self._parse_header_params(raw_disposition) if raw_disposition else {}
                item = self._build_attachment(
                    part,
                    content_type,
                    params,
                    extract_children=extract_children,
                    out_dir=out_dir,
                )
                if item is not None:
                    attachments.append(item)
                continue

            if content_type == "text/plain":
                plain_parts.append(self._decode_part(part))
            elif content_type == "text/html":
                html_parts.append(self._decode_part(part))

        plain: str | None = "\n\n".join(plain_parts) or None
        html: str | None = _merge_html_parts(html_parts) if html_parts else None

        if html and sanitize_html:
            result = self.html_parser.parse(
                html,
                method="html",
                extract_images=extract_children,
                out_dir=out_dir,
            )
            html = result.text or None
            attachments.extend(result.children)

        return {"html": html, "plain": plain, "attachments": attachments}

    def _extract_meta(self, msg: Message, *, return_raw_header: bool) -> dict[str, Any]:
        headers = self._decode_all_headers(msg)
        out: dict[str, Any] = {}

        if subject := headers.pop("subject", None):
            out["title"] = subject.strip()

        from_addrs = self._get_addresses(msg, "from")
        out["from"] = from_addrs[0] if from_addrs else None
        out["to"] = self._get_addresses(msg, "to")
        out["cc"] = self._get_addresses(msg, "cc")
        out["bcc"] = self._get_addresses(msg, "bcc")

        if date_str := headers.pop("date", None):
            out["date_sent"] = self._parse_date(date_str)

        thread_keys = ["thread-index", "x-gm-thrid"]
        out["conversation_id"] = next(
            (headers[k] for k in thread_keys if headers.get(k) is not None), None
        )
        out["state"] = EmailState.from_folder(headers.get("x-folder"))
        out["message_id"] = headers.get("message-id", "").strip().strip("<>") or None
        out["labels"] = [
            v.strip() for v in headers.get("x-gmail-labels", "").split(",") if v.strip()
        ]

        if return_raw_header:
            out["raw_header"] = headers

        return out

    def parse(
        self,
        source: bytes | str | Path,
        *,
        encoding: str = "ISO-8859-1",
        return_raw_header: bool = False,
        sanitize_html: bool = False,
        extract_children: bool = False,
        out_dir: Path | None = None,
    ) -> EmailBase:
        """Parse an EML file from bytes or a file path into an ``EmailBase``.

        The returned object exposes:

        - ``result.html`` — the merged ``text/html`` content, sanitized when
          ``sanitize_html=True``, otherwise raw decoded content.
        - ``result.plain`` — the ``text/plain`` content as decoded
          (``None`` when absent).
        - ``result.get_text(mode)`` — derive a text string on demand.
        - ``result.get_sanitized_html()`` — sanitize on demand when
          ``sanitize_html=False`` was used at parse time.

        Args:
            source: Raw bytes, a path string, or a ``Path`` to an ``.eml`` file.
            encoding: Filesystem encoding hint used when ``source`` is a path.
            return_raw_header: Attaches the decoded header dict to
                ``EmailBase.raw_header`` when ``True``.
            sanitize_html: When ``True``, run the HTML part through
                ``HtmlParser`` during parsing (strips unsafe tags, mines
                images). Leave ``False`` when you only need text extraction
                or want to sanitize later via ``EmailBase.get_sanitized_html``.
            extract_children: Write attachment payloads to ``out_dir`` and
                mine base64 images from the HTML body (requires
                ``sanitize_html=True`` for image mining). Requires ``out_dir``.
            out_dir: Target directory for extracted files.

        Returns:
            A fully assembled ``EmailBase`` instance.

        Raises:
            TypeError: When ``source`` is not bytes, str, or Path.
            ValueError: When ``extract_children=True`` and ``out_dir`` is None.
        """
        if isinstance(source, bytes):
            msg = email.message_from_bytes(source)
        elif isinstance(source, (str, Path)):
            with open(Path(source), encoding=encoding) as fh:
                msg = email.message_from_file(fh)
        else:
            raise TypeError(f"Unsupported source type: {type(source).__name__!r}")

        metadata = self._extract_meta(msg, return_raw_header=return_raw_header)
        parts = self._extract_parts(
            msg,
            sanitize_html=sanitize_html,
            extract_children=extract_children,
            out_dir=out_dir,
        )

        return EmailBase(
            html=parts["html"],
            plain=parts["plain"],
            attachments=parts["attachments"],
            metadata=metadata,
        )
