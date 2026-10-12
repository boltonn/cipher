"""Comparison of two organization names.

`compare_names` reads given name + surname, which is meaningless for an
organization: `Amazon Web Services, Inc` parses as surname `Amazon Web Services`,
given `Inc`, and "agrees" with `HBO Digital Services, Inc`. Organizations are
compared on their *core* instead -- legal forms and mailbox noise dropped -- and
only distinctive words count as agreement (`Services` and `Digital` are shared by
thousands of unrelated companies).
"""

import re
from difflib import SequenceMatcher

from cipher.names.compare import Level, NameComparison
from cipher.names.normalize import fold, split_tokens
from cipher.names.phonetic import phonetic_token
from cipher.names.translit import to_latin

__all__ = ["compare_org_names", "org_acronym", "org_core", "org_distinctive"]

_LEGAL_FORMS = frozenset(
    [
        "inc",
        "incorporated",
        "llc",
        "l",
        "l",
        "c",
        "ltd",
        "limited",
        "corp",
        "corporation",
        "co",
        "plc",
        "gmbh",
        "ag",
        "sa",
        "nv",
        "bv",
        "pty",
        "lp",
        "llp",
        "sarl",
        "srl",
        "spa",
        "oy",
        "ab",
        "as",
        "kk",
        "ooo",
        "oao",
        "zao",
        "pao",
        "ооо",
        "оао",
        "зао",
        "пао",
        "тов",
    ]
)
# mailbox decoration around a sender name: `Adaire (no reply)`, `Udemy - do not reply`
_MAILBOX_NOISE = frozenset(["no", "reply", "noreply", "donotreply", "do", "not"])
# Words that appear in thousands of unrelated organization names -- agreement on these alone is not evidence.
_GENERIC = frozenset(
    [
        "the",
        "of",
        "and",
        "for",
        "&",
        "a",
        "an",
        "services",
        "service",
        "digital",
        "group",
        "holdings",
        "solutions",
        "systems",
        "technologies",
        "technology",
        "international",
        "global",
        "national",
        "american",
        "united",
        "financial",
        "management",
        "team",
        "partners",
        "consulting",
        "media",
        "marketing",
        "news",
        "network",
        "online",
        "enterprises",
        "industries",
        "associates",
        "center",
        "centre",
        "health",
        "insurance",
        "bank",
        "store",
        "shop",
        "support",
        "company",
        "companies",
        "trust",
        "capital",
        "fund",
        "foundation",
        "institute",
        "university",
        "college",
        "school",
        "department",
        "office",
        "agency",
        "association",
        "society",
        "club",
        "community",
        "church",
        "hospital",
        "medical",
        "care",
        "home",
        "homes",
        "real",
        "estate",
        "property",
        "properties",
        "leasing",
        "rentals",
        "apartments",
        "residential",
        "realty",
        "labs",
        "lab",
        "studio",
        "studios",
        "press",
        "publishing",
        "communications",
        "web",
        "mobile",
        "data",
        "cloud",
        "software",
        "products",
        "product",
        "brands",
        "store",
        "stores",
        "north",
        "south",
        "east",
        "west",
        "new",
        "first",
        "us",
        "usa",
        "america",
    ]
)
_SIMILAR_TOKEN = 0.8
_POSSESSIVE_RE = re.compile(r"['’ʼ]s\b")


def org_core(name: str) -> list[str]:
    """Words of the name without legal forms, a leading `the`, or mailbox noise (`acme`, `web`, `services`)."""
    tokens = split_tokens(_POSSESSIVE_RE.sub("", fold(to_latin(name))))
    core = [t for t in tokens if t not in _LEGAL_FORMS and t not in _MAILBOX_NOISE]
    if core[:1] == ["the"]:
        core = core[1:]
    return core or tokens


def _acronym(tokens: list[str]) -> str:
    return "".join(t[0] for t in tokens if t not in ("of", "and", "&", "the"))


def org_distinctive(name: str) -> list[str]:
    """The core words that identify this organization (`amazon`, `web` -- not `services`)."""
    return [t for t in org_core(name) if t not in _GENERIC]


def org_acronym(name: str) -> str | None:
    """The acronym a multi-word organization is known by (`aws`), or the name itself when it is one word."""
    core = org_core(name)
    return _acronym(core) if len(core) >= 2 else (core[0] if core and len(core[0]) >= 2 else None)


def _similar(a: str, b: str) -> bool:
    return (
        a == b
        or (phonetic_token(a) or a) == (phonetic_token(b) or b)
        or (min(len(a), len(b)) >= 4 and SequenceMatcher(None, a, b).ratio() >= _SIMILAR_TOKEN)
    )


def compare_org_names(a: str, b: str) -> NameComparison:
    """Compare two organization names on their distinctive words.

    * same core (legal form / `the` / `no reply` aside) -> EXACT
    * one is the acronym of the other (`AWS` / `Amazon Web Services`) -> STRONG
    * one core contains the other's distinctive words (`Adaire` / `Adaire Leasing`) -> MODERATE
    * some distinctive word shared -> WEAK
    * distinctive words on both sides, none even similar -> CONFLICT (a different organization)
    """
    ca, cb = org_core(a), org_core(b)
    if ca == cb:
        return NameComparison(Level.EXACT, {"core": "exact"}, "same name apart from legal form / noise")
    if "".join(ca) == "".join(cb):
        return NameComparison(Level.EXACT, {"core": "spacing"}, "same name apart from spacing")
    for short, long in ((ca, cb), (cb, ca)):
        if len(short) == 1 and len(long) >= 2 and len(short[0]) >= 2 and short[0] == _acronym(long):
            return NameComparison(Level.STRONG, {"core": "acronym"}, f"{short[0].upper()} is the acronym")

    da, db = [t for t in ca if t not in _GENERIC], [t for t in cb if t not in _GENERIC]
    shared = [t for t in da if any(_similar(t, u) for u in db)]
    components = {"distinctive_a": " ".join(da), "distinctive_b": " ".join(db), "shared": " ".join(shared)}
    if shared:
        if len(shared) == min(len(da), len(db)):
            return NameComparison(
                Level.MODERATE, components, f"shares {' '.join(shared)!r}; one name extends the other"
            )
        return NameComparison(Level.WEAK, components, f"shares {' '.join(shared)!r}")
    if da and db:
        return NameComparison(Level.CONFLICT, components, "no distinctive word in common -- a different organization")
    return NameComparison(Level.NONE, components, "only generic words to compare")
