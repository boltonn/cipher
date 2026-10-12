"""The message inside an opaque-signed S/MIME part (`smime.p7m`, CMS SignedData).

A signed-only p7m carries the real MIME entity as plain content wrapped in the signature, so
it can be read without any key. Enveloped (encrypted) p7m cannot, and is left as an attachment.
Outlook writes BER with indefinite lengths and chunked octet strings, so this reads BER, not just DER.
"""

from typing import NamedTuple

_SIGNED_DATA_OID = bytes.fromhex("2a864886f70d010702")
_SEQUENCE, _EXPLICIT_0 = 0x30, 0xA0
_CONSTRUCTED = 0x20
_PKCS7_MIME_TYPES = frozenset({"application/pkcs7-mime", "application/x-pkcs7-mime"})


class _Node(NamedTuple):
    tag: int
    content: bytes
    children: list["_Node"]


def is_pkcs7_mime(content_type: str, filename: str | None) -> bool:
    """An S/MIME p7m part (signed or encrypted; only signed can be opened)."""
    return content_type in _PKCS7_MIME_TYPES or (filename or "").lower().endswith(".p7m")


def signed_content(data: bytes) -> bytes | None:
    """The signed MIME entity of an opaque-signed p7m, or None (encrypted, detached, or not CMS)."""
    try:
        info, _ = _read(data, 0)
        oid, explicit = info.children[:2]
        if oid.content != _SIGNED_DATA_OID or explicit.tag != _EXPLICIT_0:
            return None
        encapsulated = next(node for node in explicit.children[0].children if node.tag == _SEQUENCE)
        wrapper = next((node for node in encapsulated.children if node.tag == _EXPLICIT_0), None)
        return _octets(wrapper.children[0]) if wrapper else None
    except (IndexError, ValueError, StopIteration):
        return None


def _octets(node: _Node) -> bytes:
    """An OCTET STRING's bytes, joining BER's chunked (constructed) form."""
    return b"".join(_octets(child) for child in node.children) if node.children else node.content


def _read(data: bytes, pos: int) -> tuple[_Node, int]:
    """One BER element at `pos` and the position after it."""
    tag = data[pos]
    if tag & 0x1F == 0x1F:
        raise ValueError("high tag numbers are not used by CMS")
    first, pos = data[pos + 1], pos + 2
    if first == 0x80:
        if not tag & _CONSTRUCTED:
            raise ValueError("indefinite length on a primitive element")
        children = []
        while data[pos : pos + 2] != b"\x00\x00":
            child, pos = _read(data, pos)
            children.append(child)
        return _Node(tag, b"", children), pos + 2
    if first & 0x80:
        width = first & 0x7F
        length, pos = int.from_bytes(data[pos : pos + width]), pos + width
    else:
        length = first
    end = pos + length
    if end > len(data):
        raise ValueError("element runs past the end")
    if not tag & _CONSTRUCTED:
        return _Node(tag, data[pos:end], []), end
    children = []
    while pos < end:
        child, pos = _read(data, pos)
        children.append(child)
    return _Node(tag, b"", children), end
