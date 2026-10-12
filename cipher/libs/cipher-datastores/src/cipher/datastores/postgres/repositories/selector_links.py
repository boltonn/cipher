"""Which person/org owns an email address, from header evidence (`has_selector`).

A header slot pairs a display name with an address. One pairing proves little -- a
parent writing from a child's account, "Cathi" on a Wayfair on-behalf-of address, a
name the resolver mis-matched on surname alone. So an actor is linked to an address
only when the evidence says it's theirs:

* the address spells their name or initials (`nbolton04` -> Nick, `efbolton.net` ->
  E. F.), seen with them at least once; or
* their name dominates the address's header slots: >= `_MIN_SHARE` of its named
  emails and >= `_MIN_EMAILS`. A slot counts toward an actor when its name agrees
  with theirs -- resolved to them (and not a different given name: "Mary Bolton"
  mis-resolved to Edmond doesn't count) or still unresolved ("Nick Bolton" counts
  toward Nick B).

When the address spells one candidate's name, candidates it doesn't spell are not
linked from dominance alone.
"""

from dataclasses import dataclass
from functools import lru_cache

from cipher.names import AddressAgreement, Level, address_name_agreement, compare_names, is_role_address

_MIN_EMAILS = 3
_MIN_SHARE = 0.5
_AGREEING_GIVEN = frozenset({"exact", "nickname", "initial"})


@dataclass(frozen=True)
class HeaderEvidence:
    """Emails whose header slot paired `name` (resolved to `resolved_id`, or not) with an address."""

    address_id: str
    address: str
    name: str
    resolved_id: str | None
    emails: int


@lru_cache(maxsize=100_000)
def _names_agree(name: str, actor_name: str) -> bool:
    comparison = compare_names(name, actor_name)
    if comparison.level >= Level.STRONG:  # identical / transliteration-identical carry no components
        return True
    components = comparison.components
    return components.get("given") in _AGREEING_GIVEN and components.get("surname") != "differ"


def decide_header_links(evidence: list[HeaderEvidence], actor_names: dict[str, str]) -> set[tuple[str, str]]:
    """`(actor_id, address_id)` pairs to link. `actor_names` maps candidate actor ids to display names."""
    by_address: dict[str, list[HeaderEvidence]] = {}
    for row in evidence:
        by_address.setdefault(row.address_id, []).append(row)

    links: set[tuple[str, str]] = set()
    for address_id, rows in by_address.items():
        total = sum(row.emails for row in rows)
        candidates = {row.resolved_id for row in rows if row.resolved_id in actor_names}
        address = rows[0].address
        if not candidates or is_role_address(address):
            continue
        agreement = {actor: address_name_agreement(address, [actor_names[actor]]) for actor in candidates}
        spelled = {actor for actor, value in agreement.items() if value == AddressAgreement.MATCH}
        for actor in candidates:
            support = sum(
                row.emails
                for row in rows
                if row.resolved_id in (actor, None) and _names_agree(row.name, actor_names[actor])
            )
            if spelled and actor not in spelled:
                continue
            if (actor in spelled and support >= 1) or (support >= _MIN_EMAILS and support / total >= _MIN_SHARE):
                links.add((actor, address_id))
    return links
