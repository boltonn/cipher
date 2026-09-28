"""Transliteration of a name to lowercase ASCII Latin.

Three tiers, best first:

1. **ICU** (`PyICU`) — ``Any-Latin; Latin-ASCII; Lower``. Script-complete.
2. **anyascii** — permissive pure-Python, good coverage, no system deps.
3. **built-in** — NFKD ASCII strip plus a compact Cyrillic/Greek romanization
   table, so the module is useful with zero third-party packages installed.

Which tier ran is reported by `backend()` for diagnostics.
"""

import unicodedata

__all__ = ["to_latin", "backend"]

_ICU = None
_ANYASCII = None
try:  # tier 1
    import icu  # type: ignore  # optional `[icu]` extra; not in hard deps

    _ICU = icu.Transliterator.createInstance("Any-Latin; Latin-ASCII; Lower")
except Exception:  # pragma: no cover - depends on optional native lib
    _ICU = None

if _ICU is None:  # tier 2
    try:
        from anyascii import anyascii as _ANYASCII
    except Exception:  # pragma: no cover
        _ANYASCII = None


# Compact romanization for the built-in tier. Enough for the common cases; ICU or
# anyascii do this far better.
_CYRILLIC = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "і": "i",
    "ї": "yi",
    "є": "ye",
    "ґ": "g",
}
_GREEK = {
    "α": "a",
    "β": "v",
    "γ": "g",
    "δ": "d",
    "ε": "e",
    "ζ": "z",
    "η": "i",
    "θ": "th",
    "ι": "i",
    "κ": "k",
    "λ": "l",
    "μ": "m",
    "ν": "n",
    "ξ": "x",
    "ο": "o",
    "π": "p",
    "ρ": "r",
    "σ": "s",
    "ς": "s",
    "τ": "t",
    "υ": "y",
    "φ": "f",
    "χ": "ch",
    "ψ": "ps",
    "ω": "o",
}
_BUILTIN = {**_CYRILLIC, **_GREEK}


def backend() -> str:
    """Which transliteration tier is active: ``icu`` | ``anyascii`` | ``builtin``."""
    if _ICU is not None:
        return "icu"
    if _ANYASCII is not None:
        return "anyascii"
    return "builtin"


def _builtin_latin(text: str) -> str:
    out: list[str] = []
    for ch in unicodedata.normalize("NFKD", text.lower()):
        if unicodedata.combining(ch):
            continue
        if ch in _BUILTIN:
            out.append(_BUILTIN[ch])
        elif ch.isascii():
            out.append(ch)
    return "".join(out)


def to_latin(text: str) -> str:
    """Return `text` as lowercase ASCII Latin, or ``""`` if nothing romanizable remains."""
    if not text:
        return ""
    if _ICU is not None:
        romanized = _ICU.transliterate(text)
    elif _ANYASCII is not None:
        romanized = _ANYASCII(text).lower()
    else:
        romanized = _builtin_latin(text)
    return "".join(ch for ch in romanized if ch.isascii()).strip()
