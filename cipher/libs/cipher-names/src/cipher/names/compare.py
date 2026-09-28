"""Culture-aware comparison of two personal names.

`compare_names` returns an ordinal `Level`, a per-component breakdown, and a
one-line reason. It is the structural half of the entity-resolution
`name_structure` feature; whole-string translit / trigram / phonetic similarity
are separate features scored elsewhere.
"""

from dataclasses import dataclass
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


def compare_names(
    a: str,
    b: str,
    *,
    culture: Culture | None = None,
    region_hint: str | None = None,
    language: str | None = None,
) -> NameComparison:
    """Compare two raw name strings. Pass a shared `culture` when the context knows it."""
    if fold(a) == fold(b) and fold(a):
        return NameComparison(Level.EXACT, {"whole": "folded-exact"}, "identical after folding")

    pa = parse_name(a, culture=culture, region_hint=region_hint, language=language)
    pb = parse_name(b, culture=culture, region_hint=region_hint, language=language)

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
