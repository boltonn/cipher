"""Abstract interface for the relationship graph.

`PostgresGraphRepository` implements this over `entity_relationship` rows with
recursive CTEs. A future `Neo4jGraphRepository` can implement the same contract
so callers (the API and the chat agent) do not change.
"""

from abc import ABC, abstractmethod

from cipher.schemas.entity_relationship import (
    EntityRelationship,
    EntityRelationshipCreate,
    GraphResponse,
    PaginatedRelationshipsResponse,
    RelationshipSearchParameters,
    TraversalDirection,
)
from cipher.schemas.ontology import RelationshipType


class GraphRepository(ABC):
    """Storage-agnostic operations on the entity relationship graph."""

    @abstractmethod
    async def upsert_relationship(self, relationship: EntityRelationshipCreate) -> EntityRelationship:
        """Create or update a confirmed edge, keyed by (src, dst, relationship_type)."""

    @abstractmethod
    async def list_relationships(
        self, request: RelationshipSearchParameters
    ) -> PaginatedRelationshipsResponse:
        """List confirmed edges, optionally filtered to those touching one entity."""

    @abstractmethod
    async def neighbors(
        self,
        *,
        entity_id: str,
        relationship_types: list[RelationshipType] | None = None,
        direction: TraversalDirection = TraversalDirection.BOTH,
        limit: int = 50,
    ) -> GraphResponse:
        """Return depth-1 neighbours of an entity and the connecting edges."""

    @abstractmethod
    async def traverse(
        self,
        *,
        start_entity_id: str,
        max_depth: int = 2,
        relationship_types: list[RelationshipType] | None = None,
        direction: TraversalDirection = TraversalDirection.BOTH,
        limit: int = 100,
    ) -> GraphResponse:
        """Return the bounded subgraph reachable from a starting node."""
