"""String folding shared by every other module.

`fold` is the broad successor to `cipher.datastores.postgres.utils.normalize_name`
(NFKD + strip marks + casefold + collapse whitespace). It additionally strips
format/control characters and normalizes punctuation runs, and it does **not**
transliterate — non-Latin scripts pass through unchanged so `translit` can decide.
"""

import re
import unicodedata

__all__ = ["fold", "tokens", "split_tokens", "strip_particles_ok"]

_WS_RE = re.compile(r"\s+")
# Anything that separates name parts in the wild: commas, dots, hyphens, slashes,
# underscores, middle dots, various dashes and quotes.
_SEP_RE = re.compile(r"[\s.,;:!?/\\_·•‧∙\-‐-―'’ʼʻ`\"“”()\[\]{}<>]+")
_FORMAT_CATEGORIES = frozenset({"Cf", "Cc"})


def fold(value: str) -> str:
    """Casefold for matching: NFKC, drop combining marks + format chars, collapse whitespace.

    Latin diacritics are removed (``José`` -> ``jose``); Cyrillic, Arabic, Han
    etc. are left intact.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    kept = [
        ch for ch in decomposed if not unicodedata.combining(ch) and unicodedata.category(ch) not in _FORMAT_CATEGORIES
    ]
    recomposed = unicodedata.normalize("NFKC", "".join(kept))
    return _WS_RE.sub(" ", recomposed.casefold()).strip()


def split_tokens(folded: str) -> list[str]:
    """Split an already-folded string into word tokens on any separator run."""
    return [t for t in _SEP_RE.split(folded) if t]


def tokens(value: str) -> list[str]:
    """Fold `value` and split into word tokens on any separator run."""
    return split_tokens(fold(value))


def strip_particles_ok(token: str, particles: frozenset[str]) -> bool:
    """True when `token` is a nobiliary/relational particle that carries no matching signal."""
    return token in particles
