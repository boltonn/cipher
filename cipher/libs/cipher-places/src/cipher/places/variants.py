"""Dictionary-form fallbacks for a place name written as running text.

The gazetteer indexes dictionary forms; text inflects them. Each function here
proposes other spellings of one surface -- a Russian/Ukrainian case form's
lemma (`Москве` -> `москва`), an Arabic/Persian name without its attached
prefix (`ببغداد` -> `بغداد`), a Chinese name with or without its `省`/`市`
suffix. They are proposals only: the gazetteer tries them when the surface as
written matches nothing, and keeps the first that names a known place.
"""

import re
from functools import lru_cache
from itertools import product

_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_UKRAINIAN = re.compile(r"[іїєґІЇЄҐ]")
_ARABIC = re.compile(r"[؀-ۿ]")
_CJK = re.compile(r"[一-鿿]")

_ARABIC_PARTICLES = re.compile(r"^(?:في|من|الى|إلى|على|در|از|به)\s+")
_ARABIC_PROCLITICS = re.compile(r"^(?:[وف]?(?:لل|[بكل](?=ال)|[بل])|[وف])(?=..)")
_ARABIC_UNIT_WORDS = ("محافظة", "استان", "منطقة", "مدينة", "شهر")
_CJK_UNIT_SUFFIXES = ("自治区", "省", "市", "县", "区")
_MAX_FORMS = 3


@lru_cache(maxsize=2)
def _morph(lang: str):
    import pymorphy3

    return pymorphy3.MorphAnalyzer(lang=lang)


def _slavic(surface: str, lang: str) -> list[str]:
    """Nominative forms of a (multi-word) Russian/Ukrainian name: nouns lemmatised, adjectives agreed with the head noun."""
    try:
        morph = _morph(lang)
    except (ImportError, ValueError):
        return []
    tokens = re.split(r"([\s\-]+)", surface)
    parses = [morph.parse(t)[:_MAX_FORMS] if _CYRILLIC.search(t) else [] for t in tokens]
    head = next((p for ps in reversed(parses) for p in ps if "NOUN" in p.tag), None)
    options: list[list[str]] = []
    for token, token_parses in zip(tokens, parses, strict=True):
        forms: list[str] = []
        for parse in token_parses:
            agreed = None
            if "ADJF" in parse.tag and head is not None and head.tag.gender:
                agreed = parse.inflect({"nomn", "sing", head.tag.gender})
            form = agreed.word if agreed else parse.normal_form
            if form not in forms:
                forms.append(form)
        options.append(forms or [token])
    return ["".join(combo) for combo in product(*options)][: _MAX_FORMS**2]


def _arabic(surface: str) -> list[str]:
    """An Arabic/Persian name without a leading preposition or attached prefix, then with a province word."""
    bare = _ARABIC_PARTICLES.sub("", surface)
    stripped = _ARABIC_PROCLITICS.sub(lambda m: "ال" if m.group(0).endswith("لل") else "", bare)
    forms = [f for f in (bare, stripped) if f != surface]
    return forms + [f"{unit} {name}" for name in (bare, stripped) for unit in _ARABIC_UNIT_WORDS]


def _cjk(surface: str) -> list[str]:
    """A Chinese name without its administrative suffix, then with one."""
    for suffix in _CJK_UNIT_SUFFIXES:
        if surface.endswith(suffix) and len(surface) > len(suffix) + 1:
            return [surface.removesuffix(suffix)]
    return [surface + suffix for suffix in ("省", "市")]


@lru_cache(maxsize=50_000)
def name_variants(surface: str) -> tuple[str, ...]:
    """Other spellings `surface` may be a form of, most likely first; never includes `surface` itself."""
    if _CYRILLIC.search(surface):
        langs = ("uk", "ru") if _UKRAINIAN.search(surface) else ("ru", "uk")
        forms = [form for lang in langs for form in _slavic(surface, lang)]
    elif _ARABIC.search(surface):
        forms = _arabic(surface)
    elif _CJK.search(surface):
        forms = _cjk(surface)
    else:
        forms = []
    return tuple(dict.fromkeys(f for f in forms if f and f.casefold() != surface.casefold()))
