"""Phonetic keys over the transliterated form of a name.

Metaphone-style skeleton, computed per token and joined, so word order still
matters but spelling variants (`Smith`/`Smyth`, `Kovalchuk`/`Kowalczuk`) and OCR
noise collapse together. Uses `jellyfish` when available, else a compact built-in
consonant-skeleton fallback.
"""

import re

from cipher.names.translit import to_latin

__all__ = ["phonetic_token", "phonetic_key", "backend"]

_JELLYFISH = None
try:
    import jellyfish as _JELLYFISH
except Exception:  # pragma: no cover
    _JELLYFISH = None

_NON_ALPHA = re.compile(r"[^a-z]")
_VOWELS = frozenset("aeiouy")

# Romanization-variance reducers applied before either phonetic algorithm, so
# transliteration spelling choices (Kowalchuk/Kovalchuk, Schmidt/Shmidt) collapse.
_PRECLEAN = (("sch", "sh"), ("tsch", "ch"), ("cz", "ch"), ("ph", "f"), ("ck", "k"), ("kh", "h"), ("w", "v"))


def _preclean(token: str) -> str:
    for a, b in _PRECLEAN:
        token = token.replace(a, b)
    return token


def backend() -> str:
    """``jellyfish`` when the library is importable, else ``builtin``."""
    return "jellyfish" if _JELLYFISH is not None else "builtin"


def _builtin_skeleton(token: str) -> str:
    """Drop vowels (incl. y) except a leading one; collapse doubles."""
    out: list[str] = []
    for i, ch in enumerate(token):
        if ch in _VOWELS and i != 0:
            continue
        if out and out[-1] == ch:
            continue
        out.append(ch)
    return "".join(out)


def phonetic_token(token: str) -> str:
    """Phonetic code for one already-latinized token. ``""`` if it has no letters."""
    token = _preclean(_NON_ALPHA.sub("", token.lower()))
    if not token:
        return ""
    if _JELLYFISH is not None:
        code = _JELLYFISH.metaphone(token)
        return code or _builtin_skeleton(token)
    return _builtin_skeleton(token)


def phonetic_key(name: str) -> str:
    """Space-joined phonetic codes of `name`'s tokens, after transliteration to Latin."""
    latin = to_latin(name)
    codes = [phonetic_token(t) for t in latin.split()]
    return " ".join(c for c in codes if c)
