"""Does an email address's own text agree with a person's name?

People build addresses from their names -- `nbolton04` (Nick Bolton), `efbolton`
(E. F. Bolton), `nick.bolton`, or a custom domain like `efbolton.net`. That is
direct evidence for (or against) which of several same-surname people owns the
address, independent of what display names happen to sit next to it in headers.
"""

import re
from enum import StrEnum

from cipher.names.nicknames import share_nickname_root
from cipher.names.normalize import fold
from cipher.names.parse import ParsedName, parse_name

# Shared mailbox providers: their domain says nothing about the owner.
_FREEMAIL = frozenset(
    {
        "gmail", "googlemail", "yahoo", "ymail", "hotmail", "outlook", "live", "msn", "aol", "icloud",
        "me", "mac", "protonmail", "proton", "gmx", "mail", "comcast", "verizon", "att", "sbcglobal",
    }
)  # fmt: skip
_MAX_INITIALS = 3


class AddressAgreement(StrEnum):
    MATCH = "match"  # the address spells this person's name or initials + surname
    CONFLICT = "conflict"  # it spells the surname with someone else's name/initials
    NEUTRAL = "neutral"  # no name signal (`bolton213`, `info@`, a company domain, ...)


def _name_parts(address: str) -> list[str]:
    """The owner-chosen strings in an address: the local part, plus a non-freemail domain label."""
    local, _, domain = fold(address).partition("@")
    parts = [local]
    label = domain.split(".")[0] if domain else ""
    if label and label not in _FREEMAIL:
        parts.append(label)
    return parts


def _initials(name: ParsedName) -> str:
    return "".join(token[0] for token in (*name.given, *name.middle) if token)


def _given_agrees(token: str, name: ParsedName) -> bool:
    given = name.given_primary or ""
    if not given or not token:
        return False
    if len(given) == 1:  # the name only has an initial
        return token[0] == given
    return token == given or share_nickname_root(token, b=given)


def _part_agreement(part: str, name: ParsedName) -> AddressAgreement:
    surname = name.primary_surname or ""
    words = [re.sub(r"[^a-z]", "", word) for word in re.split(r"[._\-+]", part)]
    words = [word for word in words if word]
    letters = "".join(words)
    if not letters:
        return AddressAgreement.NEUTRAL

    # A surname known only by its initial ("Nick B"): initials + surname-initial prefix.
    if len(surname) == 1:
        initials = _initials(name)
        if initials and letters.startswith(initials) and letters[len(initials) : len(initials) + 1] == surname:
            return AddressAgreement.MATCH
        return AddressAgreement.MATCH if any(_given_agrees(word, name) for word in words) else AddressAgreement.NEUTRAL

    if not surname or surname not in letters:
        # No surname to anchor on; a spelled-out given name still counts ("nick.b@").
        return AddressAgreement.MATCH if any(_given_agrees(word, name) for word in words) else AddressAgreement.NEUTRAL

    if any(_given_agrees(word, name) for word in words if word != surname):
        return AddressAgreement.MATCH
    prefix, _, suffix = letters.partition(surname)
    initials = _initials(name)
    if prefix:
        if _given_agrees(prefix, name) or (initials and prefix in (initials, initials[0])):
            return AddressAgreement.MATCH
        # "efbolton" for "Edmond Bolton": extra letters may be middle initials the name omits.
        if initials and not name.middle and len(prefix) <= _MAX_INITIALS and prefix[0] == initials[0]:
            return AddressAgreement.MATCH
        # A short prefix is someone's initials; a long one is some other word -- no signal.
        return AddressAgreement.CONFLICT if len(prefix) <= _MAX_INITIALS else AddressAgreement.NEUTRAL
    if suffix and initials and suffix in (initials, initials[0]):  # "boltonn", "boltonef"
        return AddressAgreement.MATCH
    return AddressAgreement.NEUTRAL  # surname alone: shared by the whole family


def address_name_agreement(address: str, names: list[str]) -> AddressAgreement:
    """How an address agrees with a person known by any of `names` (best over names and address parts)."""
    results = {
        _part_agreement(part, parse_name(name)) for name in names if name.strip() for part in _name_parts(address)
    }
    if AddressAgreement.MATCH in results:
        return AddressAgreement.MATCH
    if AddressAgreement.CONFLICT in results:
        return AddressAgreement.CONFLICT
    return AddressAgreement.NEUTRAL
