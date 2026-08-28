"""Shared table groupings for migration revisions."""

import cipher.datastores.postgres.tables  # noqa: F401  (registers every table on Base.metadata)
from cipher.datastores.postgres.tables.base import Base

ENTITY_LAYER_TABLE_NAMES: frozenset[str] = frozenset(
    {
        "entity",
        "organization",
        "location",
        "selector",
        "mention",
        "entity_relationship",
        "entity_relationship_candidate",
        "entity_match",
    }
)


def entity_layer_tables():
    """The entity-layer tables, in FK-dependency (creation) order."""
    return [t for t in Base.metadata.sorted_tables if t.name in ENTITY_LAYER_TABLE_NAMES]
