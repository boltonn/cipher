"""Which selector types run by default, and their resolver priorities.

Priorities come from each pack's ``priority`` field; this module just exposes a
fast cached lookup and the phase gate.
"""

import functools

from cipher.schemas.graph.ontology import SelectorType
from pyselectors.packs.loader import load_pack

ENABLED_TYPES: tuple[SelectorType, ...] = (
    SelectorType.EMAIL,
    SelectorType.IP,
    SelectorType.IBAN,
    SelectorType.IMEI,
    SelectorType.IMSI,
    SelectorType.BANK_CARD,
    SelectorType.PASSPORT,
    SelectorType.CRYPTO_ADDRESS,
    SelectorType.PHONE,
    SelectorType.NATIONAL_ID,
    SelectorType.SOCIAL_HANDLE,
    SelectorType.DOMAIN,
    SelectorType.MAC_ADDRESS,
    SelectorType.LICENSE_PLATE,
)


@functools.cache
def priority(selector_type: SelectorType) -> int:
    """Resolver priority for a type (higher wins an overlap). Falls back to 50."""
    try:
        return load_pack(selector_type.value).priority
    except FileNotFoundError:
        return 50


@functools.cache
def cue_words(selector_type: SelectorType, *, min_weight: float = 0.0) -> dict[str, tuple[str, ...]]:
    """Per language, the context terms that announce `selector_type` (weight above `min_weight`).

    The same words that lift a match in running text name a column of that type
    (`телефон`, `госномер`, `bssid`), so column-header matching reuses the strong ones.
    """
    pack = load_pack(selector_type.value)
    return {
        language: tuple(t.term for t in terms if t.term and t.weight > min_weight)
        for language, terms in pack.context.terms.items()
    }
