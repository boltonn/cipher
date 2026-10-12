"""Name-culture inference.

A `Culture` picks which parsing rules apply (name order, patronymics, how many
surnames, which particles). Inference is best-effort and cheap; a wrong guess
weakens `name_structure` matching, it never hard-fails. Signals, strongest first:
explicit region hint -> language -> dominant script.
"""

from enum import StrEnum

from cipher.names.script import Script, dominant_script

__all__ = ["Culture", "infer_culture", "PARTICLES", "PATRONYMIC_SUFFIXES"]


class Culture(StrEnum):
    """A cluster of naming conventions, not a nationality."""

    GENERIC_WESTERN = "generic_western"
    EAST_SLAVIC = "east_slavic"
    HISPANIC = "hispanic"
    LUSOPHONE = "lusophone"
    ARABIC = "arabic"
    CJK = "cjk"
    KOREAN = "korean"
    VIETNAMESE = "vietnamese"
    HUNGARIAN = "hungarian"
    ICELANDIC = "icelandic"
    GERMANIC = "germanic"


# ISO-3166-ish region hint -> culture.
_REGION_CULTURE: dict[str, Culture] = {
    "RU": Culture.EAST_SLAVIC,
    "UA": Culture.EAST_SLAVIC,
    "BY": Culture.EAST_SLAVIC,
    "KZ": Culture.EAST_SLAVIC,
    "KG": Culture.EAST_SLAVIC,
    "ES": Culture.HISPANIC,
    "MX": Culture.HISPANIC,
    "AR": Culture.HISPANIC,
    "CO": Culture.HISPANIC,
    "CL": Culture.HISPANIC,
    "PE": Culture.HISPANIC,
    "VE": Culture.HISPANIC,
    "CU": Culture.HISPANIC,
    "PT": Culture.LUSOPHONE,
    "BR": Culture.LUSOPHONE,
    "AO": Culture.LUSOPHONE,
    "MZ": Culture.LUSOPHONE,
    "SA": Culture.ARABIC,
    "EG": Culture.ARABIC,
    "AE": Culture.ARABIC,
    "IQ": Culture.ARABIC,
    "SY": Culture.ARABIC,
    "JO": Culture.ARABIC,
    "MA": Culture.ARABIC,
    "DZ": Culture.ARABIC,
    "LB": Culture.ARABIC,
    "LY": Culture.ARABIC,
    "YE": Culture.ARABIC,
    "KW": Culture.ARABIC,
    "CN": Culture.CJK,
    "TW": Culture.CJK,
    "HK": Culture.CJK,
    "SG": Culture.CJK,
    "JP": Culture.CJK,
    "KR": Culture.KOREAN,
    "KP": Culture.KOREAN,
    "VN": Culture.VIETNAMESE,
    "HU": Culture.HUNGARIAN,
    "IS": Culture.ICELANDIC,
    "DE": Culture.GERMANIC,
    "AT": Culture.GERMANIC,
    "NL": Culture.GERMANIC,
    "CH": Culture.GERMANIC,
    "BE": Culture.GERMANIC,
}

_LANGUAGE_CULTURE: dict[str, Culture] = {
    "ru": Culture.EAST_SLAVIC,
    "uk": Culture.EAST_SLAVIC,
    "be": Culture.EAST_SLAVIC,
    "es": Culture.HISPANIC,
    "pt": Culture.LUSOPHONE,
    "ar": Culture.ARABIC,
    "fa": Culture.ARABIC,
    "zh": Culture.CJK,
    "ja": Culture.CJK,
    "ko": Culture.KOREAN,
    "vi": Culture.VIETNAMESE,
    "hu": Culture.HUNGARIAN,
    "is": Culture.ICELANDIC,
    "de": Culture.GERMANIC,
    "nl": Culture.GERMANIC,
}

_SCRIPT_CULTURE: dict[Script, Culture] = {
    Script.CYRILLIC: Culture.EAST_SLAVIC,
    Script.ARABIC: Culture.ARABIC,
    Script.HAN: Culture.CJK,
    Script.HANGUL: Culture.KOREAN,
    Script.KANA: Culture.CJK,
}

# Nobiliary / relational particles per culture (folded). Kept with the surname for
# matching, dropped for sorting and for the surname blocking key.
PARTICLES: dict[Culture, frozenset[str]] = {
    Culture.GENERIC_WESTERN: frozenset(
        {"van", "von", "de", "del", "della", "di", "da", "der", "den", "ter", "la", "le"}
    ),
    Culture.HISPANIC: frozenset({"de", "del", "de la", "de los", "de las", "la", "las", "los", "y"}),
    Culture.LUSOPHONE: frozenset({"de", "da", "do", "das", "dos", "e"}),
    Culture.GERMANIC: frozenset({"von", "van", "der", "den", "ter", "zu", "zum", "zur", "vom", "de"}),
    Culture.ARABIC: frozenset({"al", "el", "bin", "ibn", "bint", "abu", "umm", "abd", "abdel", "abdul"}),
    Culture.EAST_SLAVIC: frozenset(),
}

# East-Slavic patronymic suffixes (transliterated, folded).
PATRONYMIC_SUFFIXES: frozenset[str] = frozenset(
    {"ovich", "evich", "ich", "ovna", "evna", "inichna", "ovych", "yovych", "ivna"}
)


_ARABIC_NASAB_WORDS = frozenset({"bin", "ibn", "bint"})
# `-ich` alone also ends Germanic surnames (Dietrich), so only the unambiguous forms count
_SLAVIC_PATRONYMIC_ENDINGS = ("ovich", "evich", "ovna", "evna", "ovych", "ivna")


def _shape_culture(text: str) -> Culture | None:
    """Latin-script names that still show their convention: `Ahmed bin Khalid`, `Ivan Petrovich Sidorov`."""
    words = [w.strip(".,").lower() for w in text.split()]
    if _ARABIC_NASAB_WORDS & set(words[1:-1]):
        return Culture.ARABIC
    if len(words) >= 3 and any(w.endswith(_SLAVIC_PATRONYMIC_ENDINGS) for w in words[1:]):
        return Culture.EAST_SLAVIC
    return None


def infer_culture(
    *,
    region_hint: str | None = None,
    language: str | None = None,
    text: str | None = None,
) -> Culture:
    """Best guess at the naming convention for a name. Defaults to `GENERIC_WESTERN`."""
    if region_hint:
        hit = _REGION_CULTURE.get(region_hint.strip().upper())
        if hit:
            return hit
    if language:
        hit = _LANGUAGE_CULTURE.get(language.strip().lower()[:2])
        if hit:
            return hit
    if text:
        hit = _SCRIPT_CULTURE.get(dominant_script(text)) or _shape_culture(text)
        if hit:
            return hit
    return Culture.GENERIC_WESTERN
