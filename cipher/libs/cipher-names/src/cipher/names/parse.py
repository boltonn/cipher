"""Culture-aware split of a personal name into components.

`parse_name` folds and tokenizes, strips honorifics/generational suffixes, then
dispatches to a per-culture parser that fills a `ParsedName`. Every parser is a
small pure function; when a name doesn't fit its culture's shape the generic
"first token given, last token surname" fallback applies rather than an error.
"""

from dataclasses import dataclass

from cipher.names.culture import PARTICLES, PATRONYMIC_SUFFIXES, Culture, infer_culture
from cipher.names.normalize import fold, split_tokens
from cipher.names.script import Script, dominant_script
from cipher.names.translit import to_latin

__all__ = ["ParsedName", "parse_name"]

_HONORIFICS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "miss",
        "mx",
        "dr",
        "prof",
        "professor",
        "sir",
        "madam",
        "madame",
        "mme",
        "mlle",
        "herr",
        "frau",
        "sr",
        "sra",
        "srta",
        "hon",
        "rev",
        "fr",
        "capt",
        "col",
        "gen",
        "lt",
        "sgt",
        "maj",
        "cmdr",
        "eng",
    }
)
_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v", "phd", "md", "esq", "jd", "dds", "cpa", "mba", "rn"})
_ARABIC_NASAB = frozenset({"bin", "ibn", "bint", "abu", "umm"})
_ICELANDIC_PAT = ("son", "dottir", "dóttir", "bur")


@dataclass(frozen=True, slots=True)
class ParsedName:
    """A name broken into matchable parts. All string fields are `fold()`-ed."""

    raw: str
    culture: Culture
    script: Script
    given: tuple[str, ...] = ()
    middle: tuple[str, ...] = ()
    surnames: tuple[str, ...] = ()
    patronymic: str | None = None
    particles: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    suffixes: tuple[str, ...] = ()
    primary_surname: str | None = None

    @property
    def given_primary(self) -> str | None:
        """First given-name token, the one that carries the most matching signal."""
        return self.given[0] if self.given else None

    @property
    def all_tokens(self) -> tuple[str, ...]:
        """Given + middle + surnames + patronymic, particles dropped."""
        parts = [*self.given, *self.middle, *self.surnames]
        if self.patronymic:
            parts.append(self.patronymic)
        return tuple(parts)


def _spread_initials(raw: str) -> str:
    """`EF Bolton` -> `E F Bolton`: a 2-3 capital-letter word before the last is run-together initials.

    Not when the whole name is capitals (`NICK BOLTON`), where case says nothing.
    """
    words = raw.split()
    if len(words) < 2 or all(w.isupper() for w in words if any(c.isalpha() for c in w)):
        return raw
    return " ".join(
        " ".join(w) if i < len(words) - 1 and 2 <= len(w) <= 3 and w.isalpha() and w.isupper() else w
        for i, w in enumerate(words)
    )


def _is_initial(token: str) -> bool:
    return len(token) == 1 and token.isalpha()


def _looks_patronymic(token: str) -> bool:
    latin = to_latin(token)
    return any(latin.endswith(sfx) for sfx in PATRONYMIC_SUFFIXES)


def _split_leading_trailing(tokens: list[str]) -> tuple[list[str], list[str], list[str]]:
    prefixes: list[str] = []
    suffixes: list[str] = []
    body = list(tokens)
    while body and body[0] in _HONORIFICS:
        prefixes.append(body.pop(0))
    while body and body[-1] in _SUFFIXES:
        suffixes.insert(0, body.pop())
    return prefixes, body, suffixes


def _pull_particles(tokens: list[str], particles: frozenset[str]) -> tuple[list[str], list[str]]:
    """Return (non-particle tokens, particle tokens), order preserved."""
    keep = [t for t in tokens if t not in particles]
    part = [t for t in tokens if t in particles]
    return keep, part


# --- per-culture parsers ---------------------------------------------------------
# Each takes the honorific/suffix-stripped body tokens + the resolved culture/script
# and returns a fully populated ParsedName.


def _parse_western(body: list[str], culture: Culture, script: Script, raw: str) -> ParsedName:
    particles_set = PARTICLES.get(culture, PARTICLES[Culture.GENERIC_WESTERN])
    keep, particles = _pull_particles(body, particles_set)
    if not keep:
        return ParsedName(raw=raw, culture=culture, script=script, particles=tuple(particles))
    if len(keep) == 1:
        return ParsedName(raw=raw, culture=culture, script=script, given=(keep[0],), particles=tuple(particles))
    given = (keep[0],)
    middle = tuple(keep[1:-1])
    surnames = (keep[-1],)
    return ParsedName(
        raw=raw,
        culture=culture,
        script=script,
        given=given,
        middle=middle,
        surnames=surnames,
        particles=tuple(particles),
        primary_surname=surnames[-1],
    )


def _parse_east_slavic(body: list[str], culture: Culture, script: Script, raw: str) -> ParsedName:
    if len(body) >= 3:
        # "Given Patronymic Surname" (running text) vs "Surname Given Patronymic" (documents).
        if _looks_patronymic(body[1]):
            given, patronymic, surname = body[0], body[1], body[-1]
        elif _looks_patronymic(body[-1]):
            surname, given, patronymic = body[0], body[1], body[-1]
        else:
            given, patronymic, surname = body[0], None, body[-1]
        used = {given, surname, patronymic}
        return ParsedName(
            raw=raw,
            culture=culture,
            script=script,
            given=(given,),
            middle=tuple(t for t in body if t not in used),
            surnames=(surname,),
            patronymic=patronymic,
            primary_surname=surname,
        )
    if len(body) == 2:
        if _looks_patronymic(body[1]):
            return ParsedName(raw=raw, culture=culture, script=script, given=(body[0],), patronymic=body[1])
        return ParsedName(
            raw=raw,
            culture=culture,
            script=script,
            given=(body[0],),
            surnames=(body[1],),
            primary_surname=body[1],
        )
    return _parse_western(body, culture, script, raw)


def _parse_hispanic(body: list[str], culture: Culture, script: Script, raw: str) -> ParsedName:
    particles_set = PARTICLES[Culture.HISPANIC]
    keep, particles = _pull_particles(body, particles_set)
    if len(keep) <= 1:
        return _parse_western(body, culture, script, raw)
    if len(keep) == 2:
        given, surnames = (keep[0],), (keep[1],)
    else:
        # last two tokens are paternal + maternal surnames.
        given, surnames = tuple(keep[:-2]), tuple(keep[-2:])
    return ParsedName(
        raw=raw,
        culture=culture,
        script=script,
        given=given,
        surnames=surnames,
        particles=tuple(particles),
        primary_surname=surnames[0],  # paternal
    )


def _parse_lusophone(body: list[str], culture: Culture, script: Script, raw: str) -> ParsedName:
    particles_set = PARTICLES[Culture.LUSOPHONE]
    keep, particles = _pull_particles(body, particles_set)
    if len(keep) <= 1:
        return _parse_western(body, culture, script, raw)
    given = (keep[0],)
    surnames = tuple(keep[1:])
    return ParsedName(
        raw=raw,
        culture=culture,
        script=script,
        given=given,
        surnames=surnames,
        particles=tuple(particles),
        primary_surname=surnames[-1],  # paternal is last
    )


def _parse_arabic(body: list[str], culture: Culture, script: Script, raw: str) -> ParsedName:
    """`Ahmed bin Khalid Al-Saud`: given `ahmed`, patronymic `khalid` (the father), surname `saud`."""
    articles = frozenset({"al", "el"})
    nasab = next((i for i, t in enumerate(body) if t in ("bin", "ibn", "bint")), None)
    father = body[nasab + 1] if nasab is not None and nasab + 1 < len(body) else None
    cleaned = [t for t in body if t not in articles]
    keep = [t for t in cleaned if t not in _ARABIC_NASAB]
    particles = [t for t in body if t in _ARABIC_NASAB or t in articles]
    if not keep:
        return ParsedName(raw=raw, culture=culture, script=script, particles=tuple(particles))
    given = (keep[0],)
    surnames = tuple(t for t in keep[1:] if t != father)
    return ParsedName(
        raw=raw,
        culture=culture,
        script=script,
        given=given,
        surnames=surnames,
        patronymic=father,
        particles=tuple(particles),
        primary_surname=surnames[-1] if surnames else None,
    )


def _parse_family_first(body: list[str], culture: Culture, script: Script, raw: str) -> ParsedName:
    """CJK / Korean / Vietnamese / Hungarian: family name leads."""
    if len(body) == 1:
        token = body[0]
        if dominant_script(token) == Script.HAN and 2 <= len(token) <= 4:
            return ParsedName(
                raw=raw,
                culture=culture,
                script=script,
                surnames=(token[0],),
                given=(token[1:],),
                primary_surname=token[0],
            )
        return ParsedName(raw=raw, culture=culture, script=script, given=(token,))
    surname = body[0]
    return ParsedName(
        raw=raw,
        culture=culture,
        script=script,
        surnames=(surname,),
        given=tuple(body[1:]),
        primary_surname=surname,
    )


def _parse_icelandic(body: list[str], culture: Culture, script: Script, raw: str) -> ParsedName:
    if len(body) >= 2 and any(to_latin(body[-1]).endswith(sfx) for sfx in _ICELANDIC_PAT):
        return ParsedName(
            raw=raw,
            culture=culture,
            script=script,
            given=(body[0],),
            middle=tuple(body[1:-1]),
            patronymic=body[-1],
        )
    return _parse_western(body, culture, script, raw)


_PARSERS = {
    Culture.GENERIC_WESTERN: _parse_western,
    Culture.GERMANIC: _parse_western,
    Culture.EAST_SLAVIC: _parse_east_slavic,
    Culture.HISPANIC: _parse_hispanic,
    Culture.LUSOPHONE: _parse_lusophone,
    Culture.ARABIC: _parse_arabic,
    Culture.CJK: _parse_family_first,
    Culture.KOREAN: _parse_family_first,
    Culture.VIETNAMESE: _parse_family_first,
    Culture.HUNGARIAN: _parse_family_first,
    Culture.ICELANDIC: _parse_icelandic,
}


def parse_name(
    raw: str,
    *,
    culture: Culture | None = None,
    region_hint: str | None = None,
    language: str | None = None,
) -> ParsedName:
    """Split `raw` into name components using the given or inferred `culture`."""
    script = dominant_script(raw)
    resolved = culture or infer_culture(region_hint=region_hint, language=language, text=raw)

    folded = fold(_spread_initials(raw))
    # "Surname, Given ..." -> tokens in "Given ... Surname" order
    if "," in folded:
        left, _, right = folded.partition(",")
        body_tokens = split_tokens(right) + split_tokens(left)
    else:
        body_tokens = split_tokens(folded)
    prefixes, body, suffixes = _split_leading_trailing(body_tokens)
    if not body:
        return ParsedName(raw=raw, culture=resolved, script=script, prefixes=tuple(prefixes), suffixes=tuple(suffixes))

    parsed = _PARSERS[resolved](body, resolved, script, raw)
    return ParsedName(
        raw=parsed.raw,
        culture=parsed.culture,
        script=parsed.script,
        given=parsed.given,
        middle=parsed.middle,
        surnames=parsed.surnames,
        patronymic=parsed.patronymic,
        particles=parsed.particles,
        prefixes=tuple(prefixes),
        suffixes=tuple(suffixes),
        primary_surname=parsed.primary_surname,
    )
