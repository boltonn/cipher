"""Dominant-script detection for a name string.

Cheap: one pass over the letters, bucketed by Unicode code-point range. Used to
pick a transliteration path and to seed culture inference.
"""

from enum import StrEnum

__all__ = ["Script", "script_histogram", "dominant_script"]


class Script(StrEnum):
    """A writing system, coarse enough for name routing."""

    LATIN = "latin"
    CYRILLIC = "cyrillic"
    GREEK = "greek"
    ARABIC = "arabic"
    HEBREW = "hebrew"
    HAN = "han"
    HANGUL = "hangul"
    KANA = "kana"
    DEVANAGARI = "devanagari"
    THAI = "thai"
    OTHER = "other"


# Ordered (start, end, script) ranges; first hit wins. Not exhaustive, but covers
# every script CIPHER expects to see in personal names.
_RANGES: tuple[tuple[int, int, Script], ...] = (
    (0x0041, 0x005A, Script.LATIN),
    (0x0061, 0x007A, Script.LATIN),
    (0x00C0, 0x024F, Script.LATIN),  # Latin-1 Supplement + Extended-A/B
    (0x1E00, 0x1EFF, Script.LATIN),  # Latin Extended Additional (Vietnamese)
    (0x0370, 0x03FF, Script.GREEK),
    (0x1F00, 0x1FFF, Script.GREEK),
    (0x0400, 0x052F, Script.CYRILLIC),
    (0x2DE0, 0x2DFF, Script.CYRILLIC),
    (0xA640, 0xA69F, Script.CYRILLIC),
    (0x0590, 0x05FF, Script.HEBREW),
    (0x0600, 0x06FF, Script.ARABIC),
    (0x0750, 0x077F, Script.ARABIC),
    (0x08A0, 0x08FF, Script.ARABIC),
    (0xFB50, 0xFDFF, Script.ARABIC),
    (0xFE70, 0xFEFF, Script.ARABIC),
    (0x0900, 0x097F, Script.DEVANAGARI),
    (0x0E00, 0x0E7F, Script.THAI),
    (0x3040, 0x309F, Script.KANA),
    (0x30A0, 0x30FF, Script.KANA),
    (0x31F0, 0x31FF, Script.KANA),
    (0xAC00, 0xD7AF, Script.HANGUL),
    (0x1100, 0x11FF, Script.HANGUL),
    (0x3130, 0x318F, Script.HANGUL),
    (0x3400, 0x4DBF, Script.HAN),
    (0x4E00, 0x9FFF, Script.HAN),
    (0xF900, 0xFAFF, Script.HAN),
    (0x20000, 0x2A6DF, Script.HAN),
)


def _script_of(cp: int) -> Script | None:
    for start, end, script in _RANGES:
        if start <= cp <= end:
            return script
    return None


def script_histogram(text: str) -> dict[Script, int]:
    """Count letters per script. Non-letters and unmapped letters are ignored/OTHER."""
    counts: dict[Script, int] = {}
    for ch in text:
        if not ch.isalpha():
            continue
        script = _script_of(ord(ch)) or Script.OTHER
        counts[script] = counts.get(script, 0) + 1
    return counts


def dominant_script(text: str) -> Script:
    """The script most of the string's letters belong to. `OTHER` when there are none."""
    counts = script_histogram(text)
    if not counts:
        return Script.OTHER
    return max(counts, key=counts.__getitem__)
