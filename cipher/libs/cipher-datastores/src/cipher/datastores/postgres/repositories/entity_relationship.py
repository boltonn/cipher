from sqlalchemy import asc, delete, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.base.graph import GraphRepository
from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.schemas.entity import EntitySummary
from cipher.schemas.entity_relationship import (
    EntityRelationship,
    EntityRelationshipCreate,
    GraphResponse,
    PaginatedRelationshipsResponse,
    RelationshipSearchParameters,
    TraversalDirection,
)
from cipher.schemas.ontology import LOW_SIGNAL_RELATIONSHIPS, RelationshipType

_MAX_DEPTH = 3


class PostgresGraphRepository(GraphRepository):
    """Recursive-CTE-free bounded traversal over `entity_relationship` rows.

    Traversal is breadth-first with an explicit visited set, so it is
    cycle-safe and bounded by `max_depth` (<= 3) and `limit`.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the entity_relationship table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(EntityRelationshipTable.metadata.create_all)

    async def upsert_relationship(self, relationship: EntityRelationshipCreate) -> EntityRelationship:
        """Create or update a confirmed edge, keyed by (src, dst, relationship_type)."""
        values = relationship.model_dump(by_alias=False)
        insert_stmt = pg_insert(EntityRelationshipTable).values(**values)
        stmt = insert_stmt.on_conflict_do_update(
            constraint="uq_entity_relationship_triple",
            set_={
                "weight": insert_stmt.excluded.weight,
                "source": insert_stmt.excluded.source,
                "attributes": insert_stmt.excluded.attributes,
                "date_observed_start": insert_stmt.excluded.date_observed_start,
                "date_observed_end": insert_stmt.excluded.date_observed_end,
            },
        ).returning(EntityRelationshipTable)
        result = await self.session.execute(stmt)
        row = result.scalar_one()
        out = EntityRelationship.model_validate(row)
        await self.session.commit()
        return out

    async def list_relationships(
        self, request: RelationshipSearchParameters
    ) -> PaginatedRelationshipsResponse:
        """List confirmed edges, optionally filtered to those touching one entity."""
        where = []
        if request.dataset_id:
            where.append(EntityRelationshipTable.dataset_id == request.dataset_id)
        if request.relationship_type:
            where.append(EntityRelationshipTable.relationship_type == request.relationship_type)
        if request.entity_id:
            if request.direction == TraversalDirection.OUT:
                where.append(EntityRelationshipTable.src_entity_id == request.entity_id)
            elif request.direction == TraversalDirection.IN:
                where.append(EntityRelationshipTable.dst_entity_id == request.entity_id)
            else:
                where.append(
                    or_(
                        EntityRelationshipTable.src_entity_id == request.entity_id,
                        EntityRelationshipTable.dst_entity_id == request.entity_id,
                    )
                )

        count_result = await self.session.execute(
            select(func.count(EntityRelationshipTable.id)).where(*where)
        )
        total = count_result.scalar_one()

        stmt = (
            select(EntityRelationshipTable)
            .where(*where)
            .order_by(desc(EntityRelationshipTable.date_created))
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )
        result = await self.session.execute(stmt)
        data = [EntityRelationship.model_validate(r) for r in result.scalars().all()]
        return PaginatedRelationshipsResponse(
            total=total, page=request.page, limit=request.limit, data=data
        )

    async def neighbors(
        self,
        *,
        entity_id: str,
        relationship_types: list[RelationshipType] | None = None,
        direction: TraversalDirection = TraversalDirection.BOTH,
        limit: int = 50,
    ) -> GraphResponse:
        """Return depth-1 neighbours of an entity and the connecting edges."""
        edges = await self._edges_from(
            frontier={entity_id}, relationship_types=relationship_types, direction=direction, limit=limit
        )
        node_ids = {entity_id}
        for e in edges:
            node_ids.add(e.src_entity_id)
            node_ids.add(e.dst_entity_id)
        return GraphResponse(nodes=await self._nodes(node_ids), edges=edges)

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
        depth = max(1, min(max_depth, _MAX_DEPTH))
        # With no explicit type filter, co-mention style edges are excluded so
        # traversal stays useful; an explicit filter is taken at face value.
        excluded = LOW_SIGNAL_RELATIONSHIPS if relationship_types is None else frozenset()

        visited: set[str] = {start_entity_id}
        frontier: set[str] = {start_entity_id}
        all_edges: list[EntityRelationship] = []
        seen_edge_ids: set[str] = set()

        for _ in range(depth):
            if not frontier or len(all_edges) >= limit:
                break
            edges = await self._edges_from(
                frontier=frontier,
                relationship_types=relationship_types,
                direction=direction,
                limit=limit - len(all_edges),
                excluded=excluded,
            )
            next_frontier: set[str] = set()
            for e in edges:
                if e.id in seen_edge_ids:
                    continue
                seen_edge_ids.add(e.id)
                all_edges.append(e)
                for nid in (e.src_entity_id, e.dst_entity_id):
                    if nid not in visited:
                        visited.add(nid)
                        next_frontier.add(nid)
            frontier = next_frontier

        return GraphResponse(nodes=await self._nodes(visited), edges=all_edges)

    async def _edges_from(
        self,
        *,
        frontier: set[str],
        relationship_types: list[RelationshipType] | None,
        direction: TraversalDirection,
        limit: int,
        excluded: frozenset[RelationshipType] = frozenset(),
    ) -> list[EntityRelationship]:
        ids = list(frontier)
        where = []
        if direction == TraversalDirection.OUT:
            where.append(EntityRelationshipTable.src_entity_id.in_(ids))
        elif direction == TraversalDirection.IN:
            where.append(EntityRelationshipTable.dst_entity_id.in_(ids))
        else:
            where.append(
                or_(
                    EntityRelationshipTable.src_entity_id.in_(ids),
                    EntityRelationshipTable.dst_entity_id.in_(ids),
                )
            )
        if relationship_types:
            where.append(EntityRelationshipTable.relationship_type.in_([t.value for t in relationship_types]))
        if excluded:
            where.append(EntityRelationshipTable.relationship_type.notin_([t.value for t in excluded]))

        stmt = (
            select(EntityRelationshipTable)
            .where(*where)
            .order_by(asc(EntityRelationshipTable.date_created))
            .limit(max(limit, 0))
        )
        result = await self.session.execute(stmt)
        return [EntityRelationship.model_validate(r) for r in result.scalars().all()]

    async def _nodes(self, entity_ids: set[str]) -> list[EntitySummary]:
        if not entity_ids:
            return []
        result = await self.session.execute(
            select(EntityTable).where(EntityTable.id.in_(list(entity_ids)))
        )
        return [EntitySummary.model_validate(r) for r in result.scalars().all()]

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete all confirmed edges for a dataset (used by reset-entities)."""
        result = await self.session.execute(
            delete(EntityRelationshipTable).where(EntityRelationshipTable.dataset_id == dataset_id)
        )
        await self.session.commit()
        return result.rowcount or 0
