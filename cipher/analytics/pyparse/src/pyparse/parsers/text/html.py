"""lxml-backed HTML sanitization, text extraction, and link harvesting.

Functions, no state: ``html_to_text`` for plain text, ``sanitize_html`` for display, ``parse_html``
when inline base64 images should come out as child files (through a ``ChildSink``).
"""

from __future__ import annotations

import hashlib
import re
from base64 import b64decode
from dataclasses import dataclass, field
from typing import Any, Final, Literal
from urllib.parse import urlparse

from loguru import logger
from lxml import etree, html as lxml_html

from cipher.schemas._base.base import BaseModel
from cipher.schemas.ingestion.file import FileBase
from pyparse.children import ChildSink


class HtmlParseResult(BaseModel):
    text: str
    children: list[FileBase]


IMG_B64_RE: Final[re.Pattern[str]] = re.compile(
    r"data:(?P<mime>image/(?P<ext>png|jpeg|jpg|gif|webp));base64,(?P<data>[A-Za-z0-9+/=]+)"
)

SAFE_PROTOCOLS: Final[frozenset[str]] = frozenset({"http", "https", "mailto", "ftp", "ftps", ""})

# ``head`` is included so that all <style> blocks, <meta> tags, and <link>
# elements are removed in a single pass when processing full email HTML documents.
DROP_SUBTREE_TAGS: Final[frozenset[str]] = frozenset(
    {
        "head",
        "script",
        "style",
        "noscript",
        "iframe",
        "object",
        "embed",
        "applet",
        "form",
        "input",
        "button",
        "select",
        "textarea",
        "frame",
        "frameset",
        "meta",
        "link",
        "base",
    }
)

MODERATE_TAGS: Final[frozenset[str]] = frozenset(
    {
        "article",
        "aside",
        "div",
        "footer",
        "header",
        "main",
        "nav",
        "section",
        "blockquote",
        "br",
        "caption",
        "cite",
        "dd",
        "details",
        "dfn",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "ol",
        "p",
        "pre",
        "summary",
        "ul",
        "abbr",
        "acronym",
        "b",
        "bdi",
        "bdo",
        "code",
        "del",
        "em",
        "i",
        "ins",
        "kbd",
        "mark",
        "q",
        "s",
        "samp",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "time",
        "u",
        "var",
        "a",
        "img",
        "col",
        "colgroup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
    }
)

MODERATE_ATTRS: Final[dict[str, frozenset[str]]] = {
    "*": frozenset({"class", "id", "lang", "dir", "title", "data-*"}),
    "a": frozenset({"href", "rel", "target"}),
    "img": frozenset({"src", "alt", "width", "height", "loading"}),
    "td": frozenset({"colspan", "rowspan", "headers"}),
    "th": frozenset({"colspan", "rowspan", "scope"}),
    "col": frozenset({"span"}),
    "colgroup": frozenset({"span"}),
    "time": frozenset({"datetime"}),
}

EVENT_ATTR_RE: Final[re.Pattern[str]] = re.compile(r"^on[a-z]+$", re.IGNORECASE)

# Elements whose boundaries should become line breaks in plain-text output --
# lxml's text_content() otherwise joins adjacent blocks with no separator
# ("<h1>Invoice</h1><p>Hello</p>" -> "InvoiceHello").
BLOCK_BREAK_TAGS: Final[frozenset[str]] = frozenset(
    {
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "p",
        "pre",
        "tr",
    }
)


MIN_ALT_WORDS: Final[int] = 3

# Preheader padding marketing mail hides after its preview line. Zero-width
# (non-)joiners are only padding outside a word -- inside one they are spelling
# (Persian, Indic scripts, emoji sequences) and stay.
INVISIBLE_RE: Final[re.Pattern[str]] = re.compile(
    r"[\u00ad\u034f\u200b\u2060\ufeff]|(?<![^\W\d_])[\u200c\u200d]|[\u200c\u200d](?![^\W\d_])"
)
SPACE_LIKE: Final[dict[int, str]] = str.maketrans({"\u00a0": " ", "\u2007": " ", "\u202f": " "})

# Inline CSS that draws a visible gap after an element (its right edge) or before it (its left edge).
GAP_AFTER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:margin|padding)-right\s*:\s*[1-9]|display\s*:\s*(?:inline-)?block", re.IGNORECASE
)
GAP_BEFORE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:margin|padding)-left\s*:\s*[1-9]|display\s*:\s*(?:inline-)?block", re.IGNORECASE
)
# A paragraph styled with no bottom margin (Outlook signatures: one <p> per line) is a line, not a paragraph.
NO_BOTTOM_MARGIN_RE: Final[re.Pattern[str]] = re.compile(
    r"margin-bottom\s*:\s*0(?![.\d])|margin\s*:\s*0(?:px|pt|em|cm|in)?\s*(?:;|!|$)", re.IGNORECASE
)
# HTML source whitespace (a line break inside "<span>m\n</span>") renders as one space.
SOURCE_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"[ \t\r\n\f]+")
CONTROL_RE: Final[re.Pattern[str]] = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")
PARAGRAPH_TAGS: Final[frozenset[str]] = frozenset({"p", "h1", "h2", "h3", "h4", "h5", "h6"})


@dataclass(frozen=True)
class SanitizeConfig:
    """Configuration for HTML sanitization.

    Attributes:
        allowed_tags: Tags to preserve. Others are unwrapped (text kept).
        allowed_attrs: Per-tag attribute allowlist. ``"*"`` applies globally.
            Use ``"data-*"`` in a set to enable all ``data-`` attributes.
        drop_subtree_tags: Tags where the tag and all inner content are deleted.
            Defaults to ``DROP_SUBTREE_TAGS``, which includes ``<head>``.
        safe_protocols: URL schemes allowed in link/media attributes.
        strip_comments: Whether to remove HTML comments.
        inline_css: Whether to convert style blocks to inline attributes.
            Requires ``cssutils``.
    """

    allowed_tags: frozenset[str] = field(default_factory=lambda: MODERATE_TAGS)
    allowed_attrs: dict[str, frozenset[str]] = field(default_factory=lambda: MODERATE_ATTRS)
    drop_subtree_tags: frozenset[str] = field(default_factory=lambda: DROP_SUBTREE_TAGS)
    safe_protocols: frozenset[str] = field(default_factory=lambda: SAFE_PROTOCOLS)
    strip_comments: bool = True
    inline_css: bool = False

    @classmethod
    def strict(cls) -> SanitizeConfig:
        """Returns a restrictive configuration safe for raw browser rendering."""
        return cls(
            allowed_tags=frozenset({"a", "b", "i", "em", "strong", "p", "br", "ul", "li"}),
            allowed_attrs={"*": frozenset(), "a": frozenset({"href"})},
        )


def parse_html(
    html: str | bytes,
    *,
    method: Literal["text", "html"] = "text",
    sink: ChildSink | None = None,
) -> HtmlParseResult:
    """Parses an HTML document into clean text or sanitized HTML.

    Args:
        html: Raw HTML input as a string or bytes.
        method: ``"text"`` returns clean plaintext via ``text_content()``.
            ``"html"`` returns a sanitized HTML fragment.
        sink: When given, base64 ``<img>`` images are mined and handed to it;
            their records come back as ``children``.

    Returns:
        An ``HtmlParseResult`` with ``text`` and ``children`` fields.
    """
    raw = html if isinstance(html, bytes) else html.encode("utf-8")
    try:
        doc = lxml_html.fragment_fromstring(
            raw,
            create_parent="div",
            parser=lxml_html.HTMLParser(encoding="utf-8"),
        )
    except Exception:
        return HtmlParseResult(text="", children=[])

    children: list[FileBase] = _mine_images(doc, sink=sink) if sink is not None else []

    if method == "html":
        text = _sanitize_doc(doc)
    else:
        _drop_subtrees(doc)
        _collapse_source_whitespace(doc)
        _surface_inline_text(doc)
        _insert_block_breaks(doc)  # before tables: cells flatten their own blocks
        _format_tables_inplace(doc)
        text = _normalize_text(doc.text_content() or "")

    return HtmlParseResult(text=text, children=children)


def sanitize_html(html: str | bytes, *, config: SanitizeConfig | None = None) -> str:
    """Sanitizes an HTML fragment, returning a clean HTML string.

    Args:
        html: Raw HTML input.
        config: Sanitization options. Defaults to the moderate preset.

    Returns:
        A sanitized HTML fragment with no ``<html>`` or ``<body>`` wrapper.
    """
    cfg = config or SanitizeConfig()
    doc = _parse(html)

    if cfg.strip_comments:
        etree.strip_tags(doc, etree.Comment)
    if cfg.inline_css:
        _inline_css(doc)

    return _sanitize_doc(doc, cfg)


def _format_tables_inplace(doc: Any) -> None:
    """Replaces data ``<table>`` elements with pipe-table text in-place.

    Only a table with no table inside it and 2+ columns is data. Anything
    else is page layout (HTML email is built from nested layout tables):
    its cells are left in the tree as blocks, so their text appears once,
    on its own line, instead of once per nesting level.

    Args:
        doc: An lxml element whose table descendants will be replaced.
    """
    for table in doc.xpath("//table"):
        rows = table.xpath("./tr | ./thead/tr | ./tbody/tr | ./tfoot/tr")
        cells = [row.xpath("./td | ./th") for row in rows]
        parent = table.getparent()
        is_data = parent is not None and not table.xpath(".//table") and max(map(len, cells), default=0) >= 2
        if not is_data:
            for cell in (cell for row in cells for cell in row):
                cell.tail = "\n" + (cell.tail or "")
            continue
        table_text = _format_table(cells)
        prev = table.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + table_text + (table.tail or "")
        else:
            parent.text = (parent.text or "") + table_text + (table.tail or "")
        parent.remove(table)


def extract_links(html: str | bytes, *, replacement_tag: str | None = None) -> tuple[str, list[str]]:
    """Harvests href values from anchor elements.

    Args:
        html: HTML input to process.
        replacement_tag: When set, each ``<a>`` element is replaced with
            this tag name and its attributes are stripped.

    Returns:
        A tuple of ``(html, urls)``.
    """
    doc = _parse(html)
    links: list[str] = []

    for anchor in doc.iter("a"):
        href = (anchor.get("href") or "").strip()
        if href:
            links.append(href)
        if replacement_tag:
            anchor.tag = replacement_tag
            for attr in list(anchor.attrib):
                del anchor.attrib[attr]

    return _serialize(doc), links


def html_to_text(html: str | bytes) -> str:
    """Extracts normalized plaintext from HTML without image mining.

    Args:
        html: HTML input.

    Returns:
        Normalized plaintext with collapsed whitespace.
    """
    doc = _parse(html)
    _drop_subtrees(doc)
    _collapse_source_whitespace(doc)
    _surface_inline_text(doc)
    _insert_block_breaks(doc)
    _format_tables_inplace(doc)
    return _normalize_text(doc.text_content() or "")


def _normalize_text(content: str) -> str:
    r"""Collapses runs of spaces and excess blank lines in extracted text.

    Trimming whitespace around each newline first is what makes the
    blank-line collapse effective -- nested block elements emit lines
    holding only inherited indentation, which ``\n{3,}`` alone never
    matches.
    """
    content = INVISIBLE_RE.sub("", content).translate(SPACE_LIKE)
    content = re.sub(r"[ \t]{2,}", " ", content)
    content = re.sub(r"[ \t]*\n[ \t]*", "\n", content)
    return re.sub(r"\n{3,}", "\n\n", content).strip()


def _mine_images(doc: Any, *, sink: ChildSink) -> list[FileBase]:
    """Hands each base64 ``<img src="data:...">`` image to ``sink``; returns their records."""
    children: list[FileBase] = []
    for img in doc.xpath("//img[contains(@src, 'data:image')]"):
        match = IMG_B64_RE.search(img.get("src", ""))
        if not match:
            continue
        try:
            data = b64decode(match.group("data"))
        except ValueError as exc:
            logger.warning(f"Skipped an inline image whose base64 doesn't decode: {exc}")
            continue
        children.append(sink(data=data, filename=f"{hashlib.md5(data).hexdigest()}.{match.group('ext')}"))  # noqa: S324
    return children


def _format_table(cells: list[list[Any]]) -> str:
    rows: list[str] = []
    for row in cells:
        texts = []
        for cell in row:
            collapsed = re.sub(r"\s+", " ", cell.text_content()).strip()
            # drop NULL bytes and non-printable control characters
            texts.append("".join(ch for ch in collapsed if ch.isprintable()))
        if any(texts):
            rows.append(f"| {' | '.join(texts)} |")

    if not rows:
        return ""

    col_count = rows[0].count("|") - 1
    rows.insert(1, f"|{'|'.join(['---'] * col_count)}|")
    return "\n" + "\n".join(rows) + "\n"


def _parse(html: str | bytes) -> Any:

    if not html:
        return lxml_html.fromstring("<div></div>")

    raw = html if isinstance(html, bytes) else html.encode("utf-8")

    # 1. Pre-clean self-closing html/body tags which cause the "too many bodies" error
    # This fixes: <html /> or <body />. Then drop control bytes lxml refuses
    # when text is reassigned (corrupt trailing binary in some emails).
    raw = re.sub(rb"<(html|body)([^>]*)\s/>", rb"<\1\2>", raw, flags=re.IGNORECASE)
    raw = re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b"", raw)

    # 2. Use fromstring for better resilience with full documents
    try:
        return lxml_html.fromstring(raw, parser=lxml_html.HTMLParser(encoding="utf-8"))
    except Exception:
        # logger.warning(f"Initial parse failed, trying fragment: {exc}")
        return lxml_html.fragment_fromstring(raw, create_parent="div", parser=lxml_html.HTMLParser(encoding="utf-8"))


def _serialize(doc: Any) -> str:

    # If we parsed a full doc, we only want the content inside <body>
    body = doc.find(".//body")
    target = body if body is not None else doc

    # Serialize only the children of the target to return a fragment
    parts = [lxml_html.tostring(child, encoding="unicode", method="html") for child in target.iterchildren()]
    return "".join(parts)


def _surface_inline_text(doc: Any) -> None:
    """Keeps text a browser would show that text_content() loses.

    A descriptive image ``alt`` (3+ words -- image-only emails carry their
    whole message there; "logo" / "Facebook" icons are skipped) becomes
    text, and a link sitting flush against a neighbouring element gets the
    space its CSS padding draws ("<a>Ada Lovelace</a><span>in</span>"), as
    does any element flush against a sibling whose inline style draws a gap
    between them (Medium's "<span>Ada</span><span style="margin-left:8px">in</span>").
    """
    for image in doc.iter("img"):
        alt = (image.get("alt") or "").strip()
        if len(alt.split()) >= MIN_ALT_WORDS:
            image.tail = f" {alt} " + (image.tail or "")
    for link in doc.iter("a"):
        previous = link.getprevious()
        if previous is not None and not previous.tail:
            previous.tail = " "
        if link.getnext() is not None and not link.tail:
            link.tail = " "
    for element in doc.iter("*"):
        following = element.getnext()
        if following is None or element.tail:
            continue
        if GAP_AFTER_RE.search(element.get("style") or "") or GAP_BEFORE_RE.search(following.get("style") or ""):
            element.tail = " "


def _collapse_source_whitespace(doc: Any) -> None:
    """Collapses whitespace runs in the HTML source to one space, as a browser does (``<pre>`` aside).

    Line breaks then come only from the markup (blocks, ``<br>``), never from how the
    source happened to be wrapped.
    """
    for element in doc.iter():
        if not isinstance(element.tag, str):
            continue
        in_pre = element.tag == "pre" or next(element.iterancestors("pre"), None) is not None
        if element.text and not in_pre:
            element.text = SOURCE_WHITESPACE_RE.sub(" ", CONTROL_RE.sub("", element.text))
        if element.tail and next(element.iterancestors("pre"), None) is None:
            element.tail = SOURCE_WHITESPACE_RE.sub(" ", CONTROL_RE.sub("", element.tail))


def _insert_block_breaks(doc: Any) -> None:
    """Puts a newline around each block-level element so text_content() keeps block boundaries.

    A paragraph or heading ends in a blank line unless its style removes the bottom margin.

    The leading break only goes in where inline content runs straight into
    the block ("Algebra<div>Imperial</div>"); a preceding block already
    ends with its own.
    """
    blocks = list(doc.iter(*BLOCK_BREAK_TAGS))
    for element in blocks:
        previous, parent = element.getprevious(), element.getparent()
        if element.tag in ("br", "hr") or parent is None:
            continue
        if previous is None:
            if (parent.text or "").strip():
                parent.text += "\n"
        elif previous.tag not in BLOCK_BREAK_TAGS or (previous.tail or "").strip():
            previous.tail = (previous.tail or "") + "\n"
    for element in blocks:
        is_paragraph = element.tag in PARAGRAPH_TAGS and not NO_BOTTOM_MARGIN_RE.search(element.get("style") or "")
        element.tail = ("\n\n" if is_paragraph else "\n") + (element.tail or "")


def _drop_subtrees(doc: Any, tags: frozenset[str] | None = None) -> None:
    """Removes subtrees safely using built-in lxml tools."""
    targets = tags if tags is not None else DROP_SUBTREE_TAGS
    # strip_elements automatically handles removing the node,
    # its children, and merging tail text correctly.
    etree.strip_elements(doc, *targets, with_tail=False)


def _sanitize_doc(doc: Any, config: SanitizeConfig | None = None) -> str:
    cfg = config or SanitizeConfig()
    _drop_subtrees(doc, cfg.drop_subtree_tags)

    # Use a set for allowed tags for O(1) lookup
    allowed = set(cfg.allowed_tags)

    # Iterate and remove non-allowed tags while keeping content
    for element in doc.iter():
        if element.tag not in allowed:
            # strip_tags removes the element, but promotes
            # its children and tail to the parent level.
            etree.strip_tags(doc, element.tag)
        else:
            _scrub_attrs(element, element.tag, cfg)

    return _serialize(doc)


def _scrub_attrs(element: Any, tag_name: str, cfg: SanitizeConfig) -> None:
    global_ok = cfg.allowed_attrs.get("*", frozenset())
    tag_ok = cfg.allowed_attrs.get(tag_name, frozenset())
    allow_data = "data-*" in global_ok

    for attr in list(element.attrib):
        if EVENT_ATTR_RE.match(attr):
            del element.attrib[attr]
            continue
        is_valid = attr in global_ok or attr in tag_ok or (allow_data and attr.startswith("data-"))
        if not is_valid:
            del element.attrib[attr]
            continue
        if attr in ("href", "src", "action"):
            element.attrib[attr] = _safe_url(element.attrib[attr], cfg.safe_protocols)


def _unwrap(element: Any) -> None:
    parent = element.getparent()
    if parent is None:
        return
    index = parent.index(element)
    if element.text:
        if index == 0:
            parent.text = (parent.text or "") + element.text
        else:
            parent[index - 1].tail = (parent[index - 1].tail or "") + element.text
    for i, child in enumerate(list(element)):
        parent.insert(index + i, child)
    if element.tail:
        moved = list(element)
        if moved:
            parent[index + len(moved) - 1].tail = (parent[index + len(moved) - 1].tail or "") + element.tail
        else:
            parent.text = (parent.text or "") + element.tail
    parent.remove(element)


def _safe_url(url: str, safe_protocols: frozenset[str]) -> str:
    if not url:
        return ""

    # REMOVE NULL BYTES AND CONTROL CHARACTERS
    # This addresses the ValueError directly
    url = "".join(ch for ch in url if ch.isprintable() or ch in "\n\r\t")
    url = url.replace("\x00", "").strip()

    try:
        scheme = urlparse(url).scheme.lower()
    except Exception:
        return "#"

    if scheme not in safe_protocols:
        return "#"
    return url


def _inline_css(doc: Any) -> None:
    try:
        import cssutils
    except ImportError:
        raise RuntimeError("cssutils is required for inline_css=True") from None

    style_blocks = [el.text for el in doc.iter("style") if el.text]
    for el in list(doc.iter("style")):
        el.getparent().remove(el)

    if not style_blocks:
        return

    sheet = cssutils.parseString("\n".join(style_blocks))
    for rule in sheet:
        if rule.type != rule.STYLE_RULE:
            continue
        try:
            style_val = rule.style.cssText
            if isinstance(style_val, bytes):
                style_val = style_val.decode("utf-8")
            for el in doc.cssselect(rule.selectorText):
                current = el.get("style", "")
                el.set("style", f"{current};{style_val}".lstrip(";"))
        except Exception:
            continue
