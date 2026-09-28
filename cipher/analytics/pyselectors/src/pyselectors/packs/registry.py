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
)


@functools.cache
def priority(selector_type: SelectorType) -> int:
    """Resolver priority for a type (higher wins an overlap). Falls back to 50."""
    try:
        return load_pack(selector_type.value).priority
    except FileNotFoundError:
        return 50
