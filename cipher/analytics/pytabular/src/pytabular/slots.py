"""Group typed columns into per-row entity slots and propose the edges between them.

Columns are grouped by role (`sender`, `receiver`, ... or none). Within a role, person
and organization fields make actor slots, location fields a location slot, and
selectors attach to the role's actor. Edges: person→organization `employed_by`,
actor→location `located_in`, and between roles either the LLM's verb or a guess from
the row's fields (a duration suggests `called`, an amount `paid`).
"""

from collections import defaultdict

from cipher.schemas.graph.ontology import EntityType, RelationshipType
from cipher.schemas.ingestion.table_mapping import (
    ColumnDecision,
    EdgeBinding,
    EntitySlot,
    MappingDecisionSource,
    TableMapping,
)
from pytabular.detectors import EdgeHint
from pytabular.fields import FieldUse, field_type

_FAMILY_ROLES = {"spouse", "father", "mother"}
_PAIRED_ROLES = (("sender", "receiver"),)
_TIME_PREFERENCE = ("time.datetime", "time.epoch", "time.date")
_ROLE_FIELDS = frozenset({"person.occupation"})
_EMPLOYMENT_VERBS = frozenset({RelationshipType.EMPLOYED_BY.value, RelationshipType.MEMBER_OF.value})


def _unique(name: str, taken: set[str]) -> str:
    unique, i = name, 2
    while unique in taken:
        unique, i = f"{name}_{i}", i + 1
    taken.add(unique)
    return unique


def _split_by_anchor(columns: list[ColumnDecision], anchor_field: str) -> list[list[ColumnDecision]]:
    """Several `anchor_field` columns in one role -> one group per anchor; others join the nearest anchor to their left."""
    anchors = [c for c in columns if c.field_type == anchor_field]
    if len(anchors) <= 1:
        return [columns]
    groups: list[list[ColumnDecision]] = [[a] for a in anchors]
    for column in columns:
        if column.field_type == anchor_field:
            continue
        left = [i for i, a in enumerate(anchors) if a.index < column.index]
        groups[left[-1] if left else 0].append(column)
    return groups


def build_slots(
    columns: list[ColumnDecision], *, hints: list[EdgeHint] | None = None, locked: TableMapping | None = None
) -> tuple[list[EntitySlot], list[EdgeBinding]]:
    """Slots and edges for `columns`; user-set slots and edges in `locked` are kept as they are."""
    user_slots = [s for s in (locked.slots if locked else []) if s.decision_source is MappingDecisionSource.USER]
    user_edges = [e for e in (locked.edges if locked else []) if e.decision_source is MappingDecisionSource.USER]
    taken = {s.name for s in user_slots}
    claimed = {i for s in user_slots for i in s.columns}

    by_role: dict[str, dict[str, list[ColumnDecision]]] = defaultdict(lambda: defaultdict(list))
    for column in columns:
        spec = field_type(column.field_type)
        if column.index in claimed or spec.use is not FieldUse.ENTITY:
            continue
        by_role[column.role or ""][spec.group].append(column)

    slots: list[EntitySlot] = list(user_slots)
    actors: dict[str, list[EntitySlot]] = defaultdict(list)
    for slot in user_slots:
        if slot.entity_type in (EntityType.PERSON, EntityType.ORGANIZATION, EntityType.SELECTOR):
            actors[slot.name].append(slot)
    edges: list[EdgeBinding] = []

    for role, groups in by_role.items():
        people = [
            EntitySlot(
                name=_unique(role or "person", taken), entity_type=EntityType.PERSON, columns=[c.index for c in group]
            )
            for group in _split_by_anchor(groups.get("person", []), "person.full_name")
            if group
        ]
        orgs = [
            EntitySlot(
                name=_unique(role if role and not people else "_".join(filter(None, [role, "organization"])), taken),
                entity_type=EntityType.ORGANIZATION,
                columns=[c.index for c in group],
            )
            for group in _split_by_anchor(groups.get("organization", []), "organization.name")
            if group
        ]
        role_actors = people + orgs
        selectors = groups.get("selector", [])
        if role_actors:
            role_actors[0].columns.extend(c.index for c in selectors)
        else:
            role_actors = [
                EntitySlot(
                    name=_unique("_".join(filter(None, [role, c.field_type.split(".", 1)[1]])), taken),
                    entity_type=EntityType.SELECTOR,
                    columns=[c.index],
                )
                for c in selectors
            ]
        slots.extend(role_actors)
        actors[role].extend(role_actors)
        if people and orgs:
            edges.append(
                EdgeBinding(
                    src_slot=people[0].name, dst_slot=orgs[0].name, relationship_type=RelationshipType.EMPLOYED_BY.value
                )
            )
        if location := groups.get("location"):
            place = EntitySlot(
                name=_unique("_".join(filter(None, [role, "location"])), taken),
                entity_type=EntityType.LOCATION,
                columns=[c.index for c in location],
            )
            slots.append(place)
            if role_actors and role_actors[0].entity_type is not EntityType.SELECTOR:
                edges.append(
                    EdgeBinding(
                        src_slot=role_actors[0].name,
                        dst_slot=place.name,
                        relationship_type=RelationshipType.LOCATED_IN.value,
                    )
                )

    edges.extend(_between_roles(actors, columns=columns, hints=hints or []))
    columns_by_index = {c.index: c for c in columns}
    date_column = next((c.index for f in _TIME_PREFERENCE for c in columns if c.field_type == f), None)
    attributes = [c.index for c in columns if field_type(c.field_type).use is FieldUse.EDGE_ATTRIBUTE]
    # A role / occupation describes employment; amounts, durations, directions describe the interaction.
    roles = [i for i in attributes if columns_by_index[i].field_type in _ROLE_FIELDS]
    others = [i for i in attributes if i not in roles]
    for edge in edges:
        edge.date_column = date_column
        edge.attribute_columns = roles if edge.relationship_type in _EMPLOYMENT_VERBS else others
        edge.is_proposed_verb = edge.relationship_type not in {t.value for t in RelationshipType}

    locked_pairs = {(e.src_slot, e.dst_slot) for e in user_edges}
    edges = user_edges + [e for e in edges if (e.src_slot, e.dst_slot) not in locked_pairs]
    for slot in slots:
        for column in columns:
            if column.index in slot.columns:
                column.slot = slot.name
    return slots, edges


def _between_roles(
    actors: dict[str, list[EntitySlot]], *, columns: list[ColumnDecision], hints: list[EdgeHint]
) -> list[EdgeBinding]:
    def first(role: str) -> EntitySlot | None:
        return actors[role][0] if actors.get(role) else None

    edges: list[EdgeBinding] = []
    for hint in hints:
        src, dst = first(hint.src_role), first(hint.dst_role)
        if src and dst and src is not dst:
            edges.append(EdgeBinding(src_slot=src.name, dst_slot=dst.name, relationship_type=hint.verb))
    if edges:
        return edges

    fields = {c.field_type for c in columns}
    verb = (
        "called"
        if "time.duration" in fields
        else "paid"
        if "edge.amount" in fields
        else "messaged"
        if "other.free_text" in fields
        else "interacted_with"
    )
    for src_role, dst_role in _PAIRED_ROLES:
        if (src := first(src_role)) and (dst := first(dst_role)):
            edges.append(EdgeBinding(src_slot=src.name, dst_slot=dst.name, relationship_type=verb))
    primary = first("") or first("owner")
    for role in _FAMILY_ROLES:
        if primary and (relative := first(role)):
            edges.append(
                EdgeBinding(
                    src_slot=primary.name, dst_slot=relative.name, relationship_type=RelationshipType.FAMILY_OF.value
                )
            )
    return edges
