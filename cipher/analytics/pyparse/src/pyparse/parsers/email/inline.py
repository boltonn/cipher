"""Inline images: parts the HTML body shows through ``cid:`` links (signature logos, pasted screenshots).

A mail client shows these in the body and does not list them as attachments.
"""

import base64
import re
from urllib.parse import unquote

_CID_RE = re.compile(r"""cid:([^"'\s>)]+)""", re.IGNORECASE)
MAX_EMBEDDED_BYTES = 2_000_000

type ContentIdParts = dict[str, tuple[str, bytes]]
"""Parts with a Content-ID, keyed by ``content_id_key``: (MIME type, bytes)."""


def content_id_key(raw: str | None) -> str | None:
    """A Content-ID header (``<image001.png@01D5...>``) as the key its ``cid:`` links use."""
    return (raw or "").strip().strip("<>").lower() or None


def resolve_inline_images(
    html: str | None, parts: ContentIdParts, *, embed: bool = False
) -> tuple[str | None, set[str]]:
    """The Content-IDs the HTML shows inline, and (when ``embed``) the HTML with those links as ``data:`` URIs.

    Args:
        html: The email's HTML body.
        parts: The email's parts that carry a Content-ID.
        embed: Swap each ``cid:`` link for its image so the body renders on its own
            (images over ``MAX_EMBEDDED_BYTES`` keep their link).

    Returns:
        The HTML, and the Content-ID keys it shows.
    """
    if not html or not parts:
        return html, set()
    shown: set[str] = set()

    def swap(match: re.Match[str]) -> str:
        key = unquote(match.group(1)).lower()
        if (found := parts.get(key)) is None:
            return match.group(0)
        shown.add(key)
        mime_type, data = found
        if not embed or len(data) > MAX_EMBEDDED_BYTES:
            return match.group(0)
        return f"data:{mime_type};base64,{base64.b64encode(data).decode()}"

    resolved = _CID_RE.sub(swap, html)
    return (resolved if embed else html), shown
