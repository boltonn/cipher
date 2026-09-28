"""Hypocorism -> formal given name expansion (`bob` -> {`robert`}).

A static per-language table (`data/nicknames.json`), loaded once and folded.
Deterministic and explainable — the intended substitute for reaching at an
embedding model to catch nickname equivalence. Coverage is partial by design.
"""

import json
from functools import cache
from importlib.resources import files

from cipher.names.normalize import fold

__all__ = ["canonical_forms", "share_nickname_root"]


@cache
def _table() -> dict[str, frozenset[str]]:
    raw = json.loads(files("cipher.names.data").joinpath("nicknames.json").read_text("utf-8"))
    merged: dict[str, set[str]] = {}
    for lang, entries in raw.items():
        if lang.startswith("_"):
            continue
        for nick, formals in entries.items():
            key = fold(nick)
            merged.setdefault(key, set()).update(fold(f) for f in formals)
    return {k: frozenset(v) for k, v in merged.items()}


def canonical_forms(given: str, *, language: str | None = None) -> frozenset[str]:
    """Formal given names `given` may stand for, plus `given` itself (all folded).

    `language` is accepted for future per-language scoping; the table is currently
    merged across languages.
    """
    key = fold(given)
    if not key:
        return frozenset()
    return frozenset({key, *_table().get(key, frozenset())})


def share_nickname_root(a: str, *, b: str, language: str | None = None) -> bool:
    """True when two given names resolve to an overlapping set of formal names."""
    return bool(canonical_forms(a, language=language) & canonical_forms(b, language=language))
