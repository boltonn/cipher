"""Outlook's `winmail.dat` (TNEF, `application/ms-tnef`): the attachments and body hidden inside it.

Outlook sends rich-text mail as TNEF, so the recipient sees one opaque `winmail.dat` while the
real files (and sometimes the only copy of the body) are packed in it. Format: [MS-OXTNEF].
"""

import struct
from typing import NamedTuple

from loguru import logger

_SIGNATURE = 0x223E9F78
_LEVEL_ATTACHMENT = 2

_ATT_BODY = 0x800C
_ATT_ATTACH_DATA = 0x800F
_ATT_ATTACH_TITLE = 0x8010
_ATT_ATTACH_REND_DATA = 0x9002
_ATT_MAPI_PROPS = 0x9003
_ATT_ATTACHMENT = 0x9005

_PR_DISPLAY_NAME = 0x3001
_PR_ATTACH_DATA = 0x3701
_PR_ATTACH_LONG_FILENAME = 0x3707
_PR_BODY = 0x1000
_PR_RTF_COMPRESSED = 0x1009
_PR_BODY_HTML = 0x1013

_PT_STRING8, _PT_UNICODE, _PT_BINARY, _PT_OBJECT = 0x001E, 0x001F, 0x0102, 0x000D
_MULTI_VALUED = 0x1000
_VARIABLE_TYPES = frozenset({_PT_STRING8, _PT_UNICODE, _PT_BINARY, _PT_OBJECT})
_FIXED_SIZES = {0x0001: 4, 0x0002: 4, 0x0003: 4, 0x0004: 4, 0x0005: 8, 0x0006: 8, 0x0007: 8, 0x000A: 4}
_FIXED_SIZES |= {0x000B: 4, 0x0014: 8, 0x0040: 8, 0x0048: 16}
_NAMED_PROPERTY_ID = 0x8000
_IID_BYTES = 16


class WinmailAttachment(NamedTuple):
    filename: str | None
    data: bytes


class WinmailContent(NamedTuple):
    plain: str | None
    html: str | None
    rtf_compressed: bytes | None
    attachments: list[WinmailAttachment]


def is_winmail(content_type: str, filename: str | None) -> bool:
    """A winmail.dat part, by type or Outlook's fixed name."""
    return (
        content_type in ("application/ms-tnef", "application/vnd.ms-tnef") or (filename or "").lower() == "winmail.dat"
    )


def parse_winmail(data: bytes) -> WinmailContent | None:
    """The body and attachments packed in a winmail.dat, or None when it isn't one or is unreadable."""
    if len(data) < 6 or struct.unpack_from("<I", data)[0] != _SIGNATURE:
        return None
    message: dict[int, object] = {}
    attachments: list[dict[int, object]] = []
    pos = 6
    try:
        while pos + 9 <= len(data):
            level, attribute, length = struct.unpack_from("<BII", data, pos)
            value = data[pos + 9 : pos + 9 + length]
            pos += 9 + length + 2
            attribute &= 0xFFFF
            if attribute == _ATT_ATTACH_REND_DATA:
                attachments.append({})
            target = attachments[-1] if level == _LEVEL_ATTACHMENT and attachments else message
            if attribute in (_ATT_MAPI_PROPS, _ATT_ATTACHMENT):
                target.update(_mapi_properties(value))
            elif attribute == _ATT_BODY:
                message.setdefault(_PR_BODY, value.rstrip(b"\x00").decode("cp1252", errors="replace"))
            elif attribute == _ATT_ATTACH_DATA:
                target.setdefault(_PR_ATTACH_DATA, value)
            elif attribute == _ATT_ATTACH_TITLE:
                target.setdefault(_PR_DISPLAY_NAME, value.rstrip(b"\x00").decode("cp1252", errors="replace"))
    except (struct.error, ValueError) as e:
        logger.warning(f"winmail.dat unreadable past byte {pos}: {e}")
    html = message.get(_PR_BODY_HTML)
    return WinmailContent(
        plain=_text(message.get(_PR_BODY)),
        html=html.decode("utf-8", errors="replace") if isinstance(html, bytes) else _text(html),
        rtf_compressed=rtf if isinstance(rtf := message.get(_PR_RTF_COMPRESSED), bytes) else None,
        attachments=[
            WinmailAttachment(
                filename=_text(found.get(_PR_ATTACH_LONG_FILENAME)) or _text(found.get(_PR_DISPLAY_NAME)),
                data=found[_PR_ATTACH_DATA],
            )
            for found in attachments
            if isinstance(found.get(_PR_ATTACH_DATA), bytes)
        ],
    )


def _text(value: object) -> str | None:
    return value.rstrip("\x00") or None if isinstance(value, str) else None


def _mapi_properties(data: bytes) -> dict[int, object]:
    """A TNEF MAPI property list: property id -> its (first) value."""
    (count,), pos = struct.unpack_from("<I", data), 4
    properties: dict[int, object] = {}
    for _ in range(count):
        kind, property_id = struct.unpack_from("<HH", data, pos)
        pos += 4
        if property_id >= _NAMED_PROPERTY_ID:
            pos += _IID_BYTES
            (name_kind,) = struct.unpack_from("<I", data, pos)
            pos += 8 if name_kind == 0 else 8 + _padded(struct.unpack_from("<I", data, pos + 4)[0])
        base = kind & ~_MULTI_VALUED
        values = 1
        if kind & _MULTI_VALUED or base in _VARIABLE_TYPES:
            (values,) = struct.unpack_from("<I", data, pos)
            pos += 4
        first = None
        for index in range(values):
            if base in _VARIABLE_TYPES:
                (length,) = struct.unpack_from("<I", data, pos)
                raw = data[pos + 4 : pos + 4 + length]
                pos += 4 + _padded(length)
            elif base in _FIXED_SIZES:
                raw = data[pos : pos + _FIXED_SIZES[base]]
                pos += _FIXED_SIZES[base]
            else:
                raise ValueError(f"unknown MAPI property type {kind:#06x}")
            if index == 0:
                first = _decode(base, raw)
        properties.setdefault(property_id, first)
    return properties


def _decode(base: int, raw: bytes) -> object:
    match base:
        case 0x001F:
            return raw.decode("utf-16-le", errors="replace")
        case 0x001E:
            return raw.decode("cp1252", errors="replace")
        case 0x000D:
            return raw[_IID_BYTES:]
        case _:
            return raw


def _padded(length: int) -> int:
    return (length + 3) & ~3
