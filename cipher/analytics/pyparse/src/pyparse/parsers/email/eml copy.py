"""Stateless parser for RFC 822 / RFC 2822 / MIME email files.

HTML handling is delegated to ``pyparse.parsers.text.html.HtmlParser``.
"""

from __future__ import annotations

import email
import hashlib
import re
from datetime import datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, mktime_tz, parsedate_tz
from enum import StrEnum
from pathlib import Path
from typing import Any

import chardet
from filetyper import FileTyper

from pyparse.parsers.text.html import HtmlParser, HtmlParseResult
from pyparse.utils.io import get_encoding_families, map_unsupported_encoding, safe_open
from cipher.schemas.email import EmailAddressDict, EmailBase, EmailState
from cipher.schemas.file import FileBase


class TextMode(StrEnum):
    """Controls what ``EmailBase.text`` contains.

    Attributes:
        HTML_EXTRACTED: Plaintext extracted from the ``text/html`` part via
            ``HtmlParser``. Falls back to the ``text/plain`` part when no HTML
            part exists. Default, because HTML parts are typically richer.
        PLAIN: The raw ``text/plain`` MIME part as-is. Falls back to HTML
            extraction when no plain part exists.
        PLAIN_ONLY: The ``text/plain`` part with no fallback. ``None`` when absent.
        COMBINED: Both plain and HTML-extracted text concatenated, with exact
            duplicates removed. Useful for archival or search pipelines.
    """

    HTML_EXTRACTED = "html_extracted"
    PLAIN = "plain"
    PLAIN_ONLY = "plain_only"
    COMBINED = "combined"


class EmlParser:
    """Parser for RFC 822 / RFC 2822 / MIME email files.

    ``EmailBase.html`` is always the sanitized ``text/html`` MIME part —
    unsafe tags, ``<head>``, and all ``<style>`` blocks are stripped, but the
    HTML structure is otherwise preserved. It is ``None`` when the email has no
    HTML part.

    ``EmailBase.text`` is controlled by ``TextMode`` and is derived
    independently from ``html``.

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

    def _get_addresses(self, msg: Message, header_field: str) -> list[EmailAddressDict]:
        raw = msg.get_all(header_field, [])
        results: list[EmailAddressDict] = []
        for name, addr in getaddresses(raw):
            try:
                decoded_name = self._decode_header_value(name) or None
            except Exception:
                decoded_name = None
            results.append(
                EmailAddressDict(name=decoded_name, address=re.sub(r"\s+", "", addr))
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

        out_path: Path | None = None
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
        )
        if raw_mod := disposition_params.get("modification-date"):
            attachment.date_last_updated = self._parse_date(raw_mod)
        if raw_cre := disposition_params.get("creation-date"):
            attachment.date_created = self._parse_date(raw_cre)
        return attachment

    def _process_html_part(
        self,
        raw_html: str,
        *,
        extract_images: bool,
        out_dir: Path | None,
    ) -> HtmlParseResult:
        """Runs the raw HTML MIME part through ``HtmlParser``.

        Always uses ``method="html"`` so the result contains sanitized markup
        (safe for frontend display) rather than extracted plaintext. Image
        mining is a side effect controlled by ``extract_images``.

        Args:
            raw_html: Decoded ``text/html`` MIME content.
            extract_images: When ``True``, base64 ``<img>`` src data is mined
                into ``FileBase`` children.
            out_dir: Written-to directory for mined images.

        Returns:
            An ``HtmlParseResult`` whose ``.text`` is sanitized HTML and
            ``.children`` contains any mined image ``FileBase`` records.
        """
        return self.html_parser.parse(
            raw_html,
            method="html",
            extract_images=extract_images,
            out_dir=out_dir,
        )

    def _derive_text(
        self,
        plain: str | None,
        raw_html: str | None,
        mode: TextMode,
    ) -> str | None:
        """Derives ``EmailBase.text`` from available MIME parts.

        This is a pure text-derivation step. It does not mine images — that
        is handled exclusively by ``_process_html_part`` to avoid double work.

        Args:
            plain: Decoded ``text/plain`` content, or ``None``.
            raw_html: Decoded ``text/html`` content, or ``None``.
            mode: Controls the text derivation strategy.

        Returns:
            The resolved text string, or ``None`` when the chosen source is
            unavailable.
        """
        html_text: str | None = None
        if raw_html and mode is not TextMode.PLAIN_ONLY:
            result = self.html_parser.parse(
                raw_html, method="text", extract_images=False
            )
            html_text = result.text or None

        if mode is TextMode.HTML_EXTRACTED:
            return html_text or plain

        if mode is TextMode.PLAIN:
            return plain or html_text

        if mode is TextMode.PLAIN_ONLY:
            return plain

        if mode is TextMode.COMBINED:
            candidates = [p.strip() for p in (plain, html_text) if p and p.strip()]
            unique = list(dict.fromkeys(candidates))
            return "\n\n".join(unique) or None

        return None

    def _extract_parts(
        self,
        msg: Message,
        *,
        text_mode: TextMode,
        extract_children: bool,
        out_dir: Path | None,
    ) -> dict[str, Any]:
        plain_parts: list[str] = []
        html_parts: list[str] = []
        attachments: list[FileBase] = []

        for part in msg.walk():
            content_type = part.get_content_type()
            raw_disposition = part.get("Content-Disposition")

            if content_type.startswith("multipart"):
                continue

            if raw_disposition:
                kind = raw_disposition.split(";")[0].strip().lower()
                if kind == "attachment":
                    params = self._parse_header_params(raw_disposition)
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

        raw_html: str | None = "\n\n".join(html_parts) or None
        plain: str | None = "\n\n".join(plain_parts) or None

        # HTML pipeline: sanitize the HTML part and optionally mine images.
        # This is the sole place image mining happens to avoid double passes.
        sanitized_html: str | None = None
        if raw_html:
            html_result = self._process_html_part(
                raw_html,
                extract_images=extract_children,
                out_dir=out_dir,
            )
            sanitized_html = html_result.text or None
            attachments.extend(html_result.children)

        # Text pipeline: derived independently, no image mining.
        text = self._derive_text(plain, raw_html, text_mode)

        return {"text": text, "html": sanitized_html, "attachments": attachments}

    def _extract_meta(self, msg: Message, *, return_raw_header: bool) -> dict[str, Any]:
        headers = self._decode_all_headers(msg)
        # NOTE: useful for seeing new email client headers
        # pprint(f"Decoded headers: {headers}")
        out: dict[str, Any] = {}

        if subject := headers.pop("subject", None):
            out["subject"] = subject.strip()

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
        extract_children: bool = False,
        out_dir: Path | None = None,
        text_mode: TextMode = TextMode.HTML_EXTRACTED,
    ) -> EmailBase:
        """Parses an EML file from bytes or a file path into an ``EmailBase``.

        ``result.html`` is always the sanitized ``text/html`` MIME part.
        ``result.text`` is controlled by ``text_mode``.

        Args:
            source: Raw bytes, a path string, or a ``Path`` to an ``.eml`` file.
            encoding: Filesystem encoding hint used when ``source`` is a path.
            return_raw_header: Attaches the decoded header dict to
                ``EmailBase.raw_header`` when ``True``.
            extract_children: Writes attachment payloads to ``out_dir`` and
                mines base64 images from the HTML body. Requires ``out_dir``.
            out_dir: Target directory for extracted files.
            text_mode: Controls what ``EmailBase.text`` contains. Defaults to
                ``TextMode.HTML_EXTRACTED`` (plaintext from the HTML part).

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
            text_mode=text_mode,
            extract_children=extract_children,
            out_dir=out_dir,
        )

        return EmailBase(
            html=parts["html"],
            text=parts["text"],
            attachments=parts["attachments"],
            metadata=metadata,
        )
