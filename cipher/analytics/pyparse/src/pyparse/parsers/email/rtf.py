r"""Outlook's RTF bodies as text, for emails whose only body is RTF (.msg files and winmail.dat).

Outlook stores the body compressed ([MS-OXRTFCP]). Most of those bodies are HTML wrapped
in RTF (`\fromhtml1`, [MS-OXRTFEX]), which is unwrapped back to the HTML; any other RTF
is read as plain text: control words dropped, `\par` as a line break, `\'hh` bytes decoded
with the document's code page and `\uN` characters kept.
"""

import re
from codecs import lookup

from loguru import logger

try:
    import compressed_rtf
except ImportError:
    compressed_rtf = None

_TOKEN = re.compile(rb"\\([a-z]{1,32})(-?\d{1,10})? ?|\\'([0-9a-f]{2})|\\([^a-z])|([{}])|[\r\n]+|(.)", re.I | re.S)
_CODEPAGE = re.compile(rb"\\ansicpg(\d+)")
_SKIPPED_GROUPS = frozenset(
    {
        b"fonttbl", b"colortbl", b"stylesheet", b"info", b"pict", b"object", b"header", b"footer",
        b"headerl", b"headerr", b"footerl", b"footerr", b"themedata", b"colorschememapping",
        b"datastore", b"latentstyles", b"listtable", b"listoverridetable", b"rsidtbl", b"generator",
        b"xmlnstbl", b"mmathPr", b"filetbl", b"revtbl", b"pgdsctbl", b"fldinst", b"bkmkstart", b"bkmkend",
    }
)  # fmt: skip
_CHARACTERS = {
    b"par": "\n", b"line": "\n", b"sect": "\n\n", b"page": "\n\n", b"row": "\n", b"cell": " ", b"tab": "\t",
    b"emdash": "\u2014", b"endash": "\u2013", b"bullet": "\u2022", b"lquote": "\u2018", b"rquote": "\u2019",
    b"ldblquote": "\u201c", b"rdblquote": "\u201d", b"emspace": " ", b"enspace": " ",
}  # fmt: skip
_ESCAPED = {b"~": "\u00a0", b"_": "\u2011", b"-": "", b"{": "{", b"}": "}", b"\\": "\\", b"\n": "\n", b"\r": "\n"}


def decompress_rtf(data: bytes) -> bytes | None:
    """Outlook's compressed RTF body as plain RTF (None when unreadable or `compressed-rtf` isn't installed)."""
    if compressed_rtf is None:
        return None
    try:
        return compressed_rtf.decompress(data)
    except Exception as e:  # noqa: BLE001 -- the library raises bare Exceptions on bad input
        logger.warning(f"Unreadable compressed RTF body: {e}")
        return None


def rtf_body(compressed: bytes | None) -> tuple[str | None, str | None]:
    """An Outlook compressed RTF body as `(plain, html)`: the wrapped HTML when there is one, else plain text."""
    rtf = decompress_rtf(compressed) if compressed else None
    if not rtf:
        return None, None
    text = rtf_to_text(rtf).strip()
    if not text:
        return None, None
    return (None, text) if b"\\fromhtml" in rtf[:2048] else (text, None)


def rtf_to_text(rtf: bytes) -> str:
    """The text of an RTF document (for HTML wrapped in RTF, the HTML source)."""
    is_html = b"\\fromhtml" in rtf[:2048]
    encoding = _encoding(rtf)
    out: list[str] = []
    pending = bytearray()
    stack: list[tuple[int, bool, bool]] = []
    skip_chars, ignorable, suppressed, unicode_skip = 1, False, False, 0

    def emit(value: str | bytes) -> None:
        if ignorable or suppressed:
            return
        if isinstance(value, bytes):
            pending.extend(value)
            return
        if pending:
            out.append(pending.decode(encoding, errors="replace"))
            pending.clear()
        out.append(value)

    for match in _TOKEN.finditer(rtf):
        word, argument, hex_byte, escaped, brace, literal = match.groups()
        if brace:
            unicode_skip = 0
            if brace == b"{":
                stack.append((skip_chars, ignorable, suppressed))
            elif stack:
                skip_chars, ignorable, suppressed = stack.pop()
        elif escaped:
            unicode_skip = 0
            if escaped == b"*":
                ignorable = True
            elif escaped in _ESCAPED:
                emit(_ESCAPED[escaped])
        elif word:
            unicode_skip = 0
            if is_html and word == b"htmltag":
                ignorable = suppressed = False
            elif is_html and word == b"htmlrtf":
                suppressed = argument != b"0"
            elif word in _SKIPPED_GROUPS:
                ignorable = True
            elif word in _CHARACTERS:
                emit(_CHARACTERS[word])
            elif word == b"uc" and argument:
                skip_chars = int(argument)
            elif word == b"u" and argument:
                emit(chr(int(argument) % 0x10000))
                unicode_skip = skip_chars
        elif hex_byte or literal:
            if unicode_skip:
                unicode_skip -= 1
            else:
                emit(bytes.fromhex(hex_byte.decode()) if hex_byte else literal)
    emit("")
    return "".join(out)


def _encoding(rtf: bytes) -> str:
    r"""The `\ansicpgN` code page as a Python codec (cp1252 when absent or unknown)."""
    match = _CODEPAGE.search(rtf[:4096])
    candidate = f"cp{int(match.group(1))}" if match else "cp1252"
    try:
        return lookup(candidate).name
    except LookupError:
        return "cp1252"
