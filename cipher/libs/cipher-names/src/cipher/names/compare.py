"""Culture-aware comparison of two personal names.

`compare_names` returns an ordinal `Level`, a per-component breakdown, and a
one-line reason. It is the structural half of the entity-resolution
`name_structure` feature; whole-string translit / trigram / phonetic similarity
are separate features scored elsewhere.
"""

from dataclasses import dataclass, replace
from enum import IntEnum

from cipher.names.culture import Culture
from cipher.names.nicknames import share_nickname_root
from cipher.names.normalize import fold
from cipher.names.parse import ParsedName, parse_name
from cipher.names.phonetic import phonetic_token
from cipher.names.translit import to_latin

__all__ = ["Level", "NameComparison", "compare_names"]


class Level(IntEnum):
    """How strongly two names agree. `CONFLICT` is a veto, not just a low score."""

    CONFLICT = -1
    NONE = 0
    WEAK = 1
    MODERATE = 2
    STRONG = 3
    EXACT = 4


@dataclass(frozen=True, slots=True)
class NameComparison:
    """Result of `compare_names`."""

    level: Level
    components: dict[str, str]
    explanation: str


def _lat(token: str | None) -> str:
    return fold(to_latin(token)) if token else ""


def _given_agreement(a: ParsedName, b: ParsedName) -> str:
    ga, gb = a.given_primary, b.given_primary
    if not ga or not gb:
        return "unknown"
    la, lb = _lat(ga), _lat(gb)
    if la == lb:
        return "exact"
    if (len(la) == 1 and lb.startswith(la)) or (len(lb) == 1 and la.startswith(lb)):
        return "initial"
    if share_nickname_root(ga, b=gb):
        return "nickname"
    if phonetic_token(la) and phonetic_token(la) == phonetic_token(lb):
        return "phonetic"
    return "differ"


def _surname_agreement(a: ParsedName, b: ParsedName) -> str:
    sa, sb = a.primary_surname, b.primary_surname
    if not sa or not sb:
        return "unknown"
    la, lb = _lat(sa), _lat(sb)
    if la == lb:
        return "exact"
    # One side is a single initial that heads the other ("Bolton" vs "B").
    if (len(la) == 1 and lb.startswith(la)) or (len(lb) == 1 and la.startswith(lb)):
        return "initial"
    # East-Slavic gendered surname pair: kuznetsov / kuznetsova, ...
    if (
        {la, lb}
        and (la.rstrip("a") == lb.rstrip("a"))
        and abs(len(la) - len(lb)) <= 2
        and a.culture == Culture.EAST_SLAVIC
    ):
        return "gendered"
    if phonetic_token(la) and phonetic_token(la) == phonetic_token(lb):
        return "phonetic"
    return "differ"


def _patronymic_agreement(a: ParsedName, b: ParsedName) -> str:
    if not a.patronymic or not b.patronymic:
        return "unknown"
    return "exact" if _lat(a.patronymic) == _lat(b.patronymic) else "differ"


_GIVEN_RANK = {"exact": 4, "nickname": 3, "initial": 3, "phonetic": 2, "differ": 0, "unknown": 1}
_GENERATIONAL = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})
_MALE_TITLES = frozenset({"mr", "herr", "sir"})
_FEMALE_TITLES = frozenset({"mrs", "ms", "miss", "mme", "mlle", "madam", "madame", "frau", "sra", "srta"})
_PERSON_TITLES = _MALE_TITLES | _FEMALE_TITLES | frozenset({"dr", "prof", "professor"})


def _middle_agreement(a: ParsedName, b: ParsedName) -> str:
    """First middle name/initial on both sides: `exact`, `initial` (`C` / `Charles`), `differ` or `unknown`."""
    if not a.middle or not b.middle:
        return "unknown"
    la, lb = _lat(a.middle[0]), _lat(b.middle[0])
    if la == lb:
        return "exact"
    if (len(la) == 1 and lb.startswith(la)) or (len(lb) == 1 and la.startswith(lb)):
        return "initial"
    return "differ"


def _generation_agreement(a: ParsedName, b: ParsedName) -> str:
    """Jr / Sr / III: `same`, `differ` (Jr vs Sr), `one_side` (only one says) or `unknown`."""
    ga, gb = set(a.suffixes) & _GENERATIONAL, set(b.suffixes) & _GENERATIONAL
    if ga and gb:
        return "same" if ga == gb else "differ"
    return "one_side" if ga or gb else "unknown"


def _title_gender(name: ParsedName) -> str | None:
    titles = set(name.prefixes)
    if titles & _MALE_TITLES:
        return "male"
    if titles & _FEMALE_TITLES:
        return "female"
    return None


def _surname_overlap(a: ParsedName, b: ParsedName) -> bool:
    """A double-barrelled or maiden surname: `Smith-Jones` / `Smith`, `Mary Smith Jones` / `Mary Jones`."""
    if not a.primary_surname or not b.primary_surname:
        return False
    # the other surname sits right before the surname (`Mary Smith Jones`), or is one of a compound
    ta = {_lat(t) for t in (*a.middle[-1:], *a.surnames)}
    tb = {_lat(t) for t in (*b.middle[-1:], *b.surnames)}
    return _lat(a.primary_surname) in tb or _lat(b.primary_surname) in ta


def _lone_word_as_surname(name: ParsedName, surname_words: frozenset[str]) -> ParsedName:
    """`Bolton` / `Mr. Bolton` alone: a surname, not a given name, when titled or when the data says so."""
    if len(name.given) != 1 or name.surnames or name.middle or name.patronymic:
        return name
    word = name.given[0]
    if not (set(name.prefixes) & _PERSON_TITLES or _lat(word) in surname_words):
        return name
    return replace(name, given=(), surnames=(word,), primary_surname=word)


def compare_names(
    a: str,
    b: str,
    *,
    culture: Culture | None = None,
    region_hint: str | None = None,
    language: str | None = None,
    surname_words: frozenset[str] = frozenset(),
) -> NameComparison:
    """Compare two raw name strings. Pass a shared `culture` when the context knows it.

    `surname_words` are words the data uses as surnames far more than as given names, so a
    lone `Bolton` is compared as a surname. On top of given/surname agreement, a middle name,
    a patronymic, Jr/Sr or a Mr/Ms title that disagree mean a different person; a Jr on one
    side only caps the match at moderate (father and son share the rest).
    """
    if fold(a) == fold(b) and fold(a):
        return NameComparison(Level.EXACT, {"whole": "folded-exact"}, "identical after folding")

    pa = _lone_word_as_surname(
        parse_name(a, culture=culture, region_hint=region_hint, language=language), surname_words
    )
    pb = _lone_word_as_surname(
        parse_name(b, culture=culture, region_hint=region_hint, language=language), surname_words
    )
    base = _compare_parsed(a, b, pa, pb)
    return _apply_details(base, pa, pb)


def _apply_details(base: NameComparison, pa: ParsedName, pb: ParsedName) -> NameComparison:
    """Middle name, patronymic, generation and title: vetoes and caps on top of given/surname agreement."""
    if base.level <= Level.NONE:
        return base
    components = dict(base.components)
    middle = components["middle"] = _middle_agreement(pa, pb)
    generation = components["generation"] = _generation_agreement(pa, pb)
    patronymic = components.get("patronymic", "unknown")
    ga, gb = _title_gender(pa), _title_gender(pb)
    if middle == "differ":
        return NameComparison(Level.CONFLICT, components, "middle names differ -- a different person")
    if patronymic == "differ":
        return NameComparison(Level.CONFLICT, components, "patronymics differ -- a different person")
    if generation == "differ":
        return NameComparison(Level.CONFLICT, components, "Jr / Sr differ -- a different generation")
    if ga and gb and ga != gb:
        return NameComparison(Level.CONFLICT, components, "Mr vs Ms -- a different person")
    if generation == "one_side" and base.level > Level.MODERATE:
        return NameComparison(Level.MODERATE, components, f"{base.explanation}; only one is Jr/Sr (parent or child?)")
    if middle in ("exact", "initial") and base.level == Level.STRONG:
        return NameComparison(Level.EXACT, components, f"{base.explanation}, middle {middle}")
    return NameComparison(base.level, components, base.explanation)


def _compare_parsed(a: str, b: str, pa: ParsedName, pb: ParsedName) -> NameComparison:
    if _lat(a) == _lat(b) and _lat(a):
        return NameComparison(Level.STRONG, {"whole": "translit-exact"}, "identical after transliteration")

    given = _given_agreement(pa, pb)
    surname = _surname_agreement(pa, pb)
    patronymic = _patronymic_agreement(pa, pb)
    components = {"given": given, "surname": surname, "patronymic": patronymic}

    # Icelandic and other no-surname forms: lean on given + patronymic.
    if surname == "unknown" and (pa.patronymic or pb.patronymic):
        if given in ("exact", "nickname") and patronymic == "exact":
            return NameComparison(Level.EXACT, components, "given and patronymic agree, no surname")
        if given in ("exact", "nickname"):
            return NameComparison(Level.WEAK, components, "given agrees; patronymic differs or missing")
        return NameComparison(Level.NONE, components, "given names differ")

    if surname == "initial":
        if given == "exact":
            return NameComparison(Level.MODERATE, components, "given exact, surname initial only")
        if given in ("nickname", "initial"):
            return NameComparison(Level.WEAK, components, f"given {given}, surname initial only")
        # A lone initial ("B") heads half the surnames alive -- with no given-name
        # agreement it is not evidence, so treat it as a different surname.
        surname = components["surname"] = "differ"

    if surname == "differ" and _surname_overlap(pa, pb) and given in ("exact", "nickname", "initial"):
        return NameComparison(
            Level.STRONG, components, "one surname is part of the other's (double-barrelled / maiden)"
        )

    if surname == "differ":
        if given in ("exact", "nickname", "initial"):
            return NameComparison(Level.WEAK, components, "same given name, different surname")
        return NameComparison(Level.CONFLICT, components, "different surname and different given name")

    if surname in ("exact", "gendered", "phonetic"):
        strong_surname = surname != "phonetic"
        if given == "exact":
            lvl = Level.EXACT if strong_surname else Level.STRONG
            return NameComparison(lvl, components, f"surname {surname}, given exact")
        if given in ("nickname", "initial"):
            return NameComparison(Level.STRONG, components, f"surname {surname}, given {given}")
        if given == "phonetic":
            return NameComparison(Level.MODERATE, components, f"surname {surname}, given phonetic")
        if given == "unknown":
            return NameComparison(Level.MODERATE, components, f"surname {surname}, given not comparable")
        return NameComparison(Level.MODERATE, components, f"surname {surname}, given differs (same family?)")

    # surname unknown on at least one side.
    if given == "exact":
        return NameComparison(Level.MODERATE, components, "given exact, surname missing on one side")
    if _GIVEN_RANK.get(given, 0) >= 3:
        return NameComparison(Level.WEAK, components, f"given {given}, surname missing on one side")
    return NameComparison(Level.NONE, components, "insufficient agreement")
