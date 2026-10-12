from datetime import datetime

from sqlalchemy import and_, asc, delete, desc, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.base.graph import GraphRepository
from cipher.datastores.postgres.repositories.selector_links import HeaderEvidence, decide_header_links
from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.event import EventTable
from cipher.datastores.postgres.tables.event_participant import EventParticipantTable
from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.face_match import FaceMatchTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.schemas._base.review import ReviewStatus
from cipher.schemas.graph.entity import EntitySummary
from cipher.schemas.graph.entity_relationship import (
    EntityRelationship,
    EntityRelationshipCreate,
    GraphNode,
    GraphResponse,
    PaginatedRelationshipsResponse,
    RelationshipSearchParameters,
    TopConnection,
    TopConnectionsRequest,
    TopConnectionsResponse,
    TraversalDirection,
)
from cipher.schemas.graph.ontology import (
    LOW_SIGNAL_RELATIONSHIPS,
    WEIGHTED_RELATIONSHIPS,
    EntityType,
    GraphNodeType,
    RelationshipSource,
    RelationshipType,
)

_MAX_DEPTH = 3
_ACTOR_TYPES = (EntityType.PERSON, EntityType.ORGANIZATION)
_EDGE_INSERT_CHUNK = 2000

# A pair of already-identified people sharing a single photo is a weak signal;
# an `appears_in_photo_with` edge between two verified faces is only kept once
# they share at least this many photos. Edges backed by a *pending* face match
# (a lead) are kept regardless of count. Set to 1 to keep every co-occurrence.
_DEFAULT_MIN_VERIFIED_PHOTOS = 2


def _directional_weight(
    edge: EntityRelationshipTable, *, seed_is_src: bool, direction: TraversalDirection
) -> float | None:
    """The edge's weight as seen from the seed end; None for an undirected edge when a direction is asked."""
    if direction == TraversalDirection.BOTH:
        return edge.weight
    if not edge.directed:
        return None
    return edge.weight if seed_is_src == (direction == TraversalDirection.OUT) else 0.0


def _edge_sort_key(edge: EntityRelationship) -> tuple[float, datetime]:
    return (-(edge.weight or 0.0), edge.date_created)


class PostgresGraphRepository(GraphRepository):
    """Recursive-CTE-free bounded traversal over `entity_relationship` rows.

    Traversal is breadth-first with an explicit visited set, so it is
    cycle-safe and bounded by `max_depth` (<= 3) and `limit`. Resolved
    `event_participant` rows join the walk as `participant_in` edges to event
    nodes (read-time only, never stored), so person -> event -> person is two hops.
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

    async def delete_relationship(
        self, *, src_entity_id: str, dst_entity_id: str, relationship_type: RelationshipType
    ) -> bool:
        """Delete a confirmed edge identified by its (src, dst, type) triple."""
        result = await self.session.execute(
            delete(EntityRelationshipTable).where(
                EntityRelationshipTable.src_entity_id == src_entity_id,
                EntityRelationshipTable.dst_entity_id == dst_entity_id,
                EntityRelationshipTable.relationship_type == relationship_type,
            )
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def list_relationships(self, request: RelationshipSearchParameters) -> PaginatedRelationshipsResponse:
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

        count_result = await self.session.execute(select(func.count(EntityRelationshipTable.id)).where(*where))
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
        return PaginatedRelationshipsResponse(total=total, page=request.page, limit=request.limit, data=data)

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
        return GraphResponse(nodes=await self._graph_nodes(node_ids), edges=edges)

    async def traverse(
        self,
        *,
        start_entity_id: str,
        max_depth: int = 2,
        relationship_types: list[RelationshipType] | None = None,
        direction: TraversalDirection = TraversalDirection.BOTH,
        limit: int = 100,
        min_weight: float = 0,
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
                min_weight=min_weight,
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

        return GraphResponse(nodes=await self._graph_nodes(visited), edges=all_edges, truncated=len(all_edges) >= limit)

    async def top_connections(self, request: TopConnectionsRequest) -> TopConnectionsResponse:
        """Rank the seeds' neighbours by summed edge weight (see `TopConnectionsRequest`)."""
        seeds = set(request.entity_ids) | await self._owned_selectors(set(request.entity_ids))
        where = [
            or_(EntityRelationshipTable.src_entity_id.in_(seeds), EntityRelationshipTable.dst_entity_id.in_(seeds)),
            EntityRelationshipTable.weight.is_not(None),
        ]
        if request.relationship_types:
            where.append(EntityRelationshipTable.relationship_type.in_(request.relationship_types))
        else:
            where.append(EntityRelationshipTable.relationship_type.in_(WEIGHTED_RELATIONSHIPS))
        if request.dataset_id:
            where.append(
                or_(
                    EntityRelationshipTable.dataset_id == request.dataset_id,
                    EntityRelationshipTable.dataset_id.is_(None),
                )
            )
        edges = (await self.session.execute(select(EntityRelationshipTable).where(*where))).scalars().all()

        by_neighbour: dict[str, TopConnection] = {}
        without_direction = 0
        for edge in edges:
            if edge.src_entity_id in seeds and edge.dst_entity_id in seeds:
                continue
            seed_is_src = edge.src_entity_id in seeds
            weight = _directional_weight(edge, seed_is_src=seed_is_src, direction=request.direction)
            if weight is None:
                without_direction += 1
                continue
            if weight <= 0:
                continue
            neighbour = edge.dst_entity_id if seed_is_src else edge.src_entity_id
            conn = by_neighbour.setdefault(
                neighbour,
                TopConnection(
                    entity=EntitySummary(id=neighbour, entity_type=EntityType.SELECTOR, display_name=neighbour),
                    weight=0,
                    relationship_types=[],
                ),
            )
            conn.weight += weight
            if edge.relationship_type not in conn.relationship_types:
                conn.relationship_types.append(edge.relationship_type)
            conn.date_first = min(filter(None, [conn.date_first, edge.date_observed_start]), default=None)
            conn.date_last = max(filter(None, [conn.date_last, edge.date_observed_end]), default=None)

        owners = await self._sole_owners(set(by_neighbour)) if request.roll_up else {}
        merged: dict[str, TopConnection] = {}
        for neighbour, conn in by_neighbour.items():
            key = owners.get(neighbour, neighbour)
            if key in seeds:
                continue  # another address of the seed itself
            target = merged.setdefault(key, conn.model_copy(update={"weight": 0, "relationship_types": [], "via": []}))
            target.weight += conn.weight
            target.relationship_types = list(dict.fromkeys([*target.relationship_types, *conn.relationship_types]))
            target.date_first = min(filter(None, [target.date_first, conn.date_first]), default=None)
            target.date_last = max(filter(None, [target.date_last, conn.date_last]), default=None)
            if key != neighbour:
                target.via.append(conn.entity)

        ranked = sorted(merged.items(), key=lambda kv: kv[1].weight, reverse=True)[: request.limit]
        nodes = {
            n.id: n
            for n in await self._nodes(seeds | {key for key, _ in ranked} | {v.id for _, c in ranked for v in c.via})
        }
        connections = [
            conn.model_copy(
                update={"entity": nodes.get(key, conn.entity), "via": [nodes.get(v.id, v) for v in conn.via]}
            )
            for key, conn in ranked
        ]
        return TopConnectionsResponse(
            seeds=[nodes[i] for i in seeds if i in nodes],
            connections=connections,
            edges_without_direction=without_direction,
        )

    async def _owned_selectors(self, entity_ids: set[str]) -> set[str]:
        """Selectors the given actors `has_selector`-own (empty until resolution links any)."""
        rows = await self.session.execute(
            select(EntityRelationshipTable.dst_entity_id).where(
                EntityRelationshipTable.src_entity_id.in_(entity_ids),
                EntityRelationshipTable.relationship_type == RelationshipType.HAS_SELECTOR,
            )
        )
        return set(rows.scalars())

    async def _sole_owners(self, selector_ids: set[str]) -> dict[str, str]:
        """Selector -> its owner, only where exactly one actor owns it (a shared mailbox stays a selector)."""
        rows = await self.session.execute(
            select(EntityRelationshipTable.dst_entity_id, EntityRelationshipTable.src_entity_id).where(
                EntityRelationshipTable.dst_entity_id.in_(selector_ids),
                EntityRelationshipTable.relationship_type == RelationshipType.HAS_SELECTOR,
            )
        )
        owners: dict[str, set[str]] = {}
        for selector_id, owner_id in rows.all():
            owners.setdefault(selector_id, set()).add(owner_id)
        return {sel: next(iter(o)) for sel, o in owners.items() if len(o) == 1}

    async def _edges_from(
        self,
        *,
        frontier: set[str],
        relationship_types: list[RelationshipType] | None,
        direction: TraversalDirection,
        limit: int,
        excluded: frozenset[RelationshipType] = frozenset(),
        min_weight: float = 0,
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
            where.append(EntityRelationshipTable.relationship_type.in_(list(relationship_types)))
        if excluded:
            where.append(EntityRelationshipTable.relationship_type.notin_(list(excluded)))
        if min_weight > 0:
            where.append(
                or_(
                    EntityRelationshipTable.weight.is_(None),
                    EntityRelationshipTable.weight >= min_weight,
                )
            )

        stmt = (
            select(EntityRelationshipTable)
            .where(*where)
            .order_by(
                desc(func.coalesce(EntityRelationshipTable.weight, 0.0)),
                asc(EntityRelationshipTable.date_created),
            )
            .limit(max(limit, 0))
        )
        result = await self.session.execute(stmt)
        edges = [EntityRelationship.model_validate(r) for r in result.scalars().all()]
        wants_events = (
            not relationship_types or RelationshipType.PARTICIPANT_IN in relationship_types
        ) and RelationshipType.PARTICIPANT_IN not in excluded
        if wants_events:
            edges += await self._participant_edges(frontier=frontier, direction=direction, limit=limit)
            edges = sorted(edges, key=_edge_sort_key)[: max(limit, 0)]
        return edges

    async def _participant_edges(
        self, *, frontier: set[str], direction: TraversalDirection, limit: int
    ) -> list[EntityRelationship]:
        """Resolved `event_participant` rows touching the frontier, as `participant_in` edges (entity -> event)."""
        ids = list(frontier)
        touches = {
            TraversalDirection.OUT: EventParticipantTable.entity_id.in_(ids),
            TraversalDirection.IN: EventParticipantTable.event_id.in_(ids),
            TraversalDirection.BOTH: or_(
                EventParticipantTable.entity_id.in_(ids), EventParticipantTable.event_id.in_(ids)
            ),
        }[direction]
        stmt = (
            select(EventParticipantTable, EventTable)
            .join(EventTable, EventTable.id == EventParticipantTable.event_id)
            .where(touches, EventParticipantTable.entity_id.is_not(None), EventParticipantTable.is_resource.is_(False))
            .order_by(desc(EventTable.date_start))
            .limit(max(limit, 0))
        )
        return [
            EntityRelationship(
                id=participant.id,
                dataset_id=event.dataset_id,
                src_entity_id=participant.entity_id,
                dst_entity_id=event.id,
                relationship_type=RelationshipType.PARTICIPANT_IN,
                source=RelationshipSource.EXTRACTION if event.extractor else RelationshipSource.MANUAL,
                attributes={"role": participant.role, "rsvp_status": participant.rsvp_status},
                date_observed_start=event.date_start,
                date_observed_end=event.date_end or event.date_start,
                date_created=participant.date_created,
                date_updated=participant.date_created,
            )
            for participant, event in (await self.session.execute(stmt)).tuples().all()
        ]

    async def _graph_nodes(self, node_ids: set[str]) -> list[GraphNode]:
        """Entity nodes plus the event nodes `participant_in` edges point at."""
        entities = [GraphNode.model_validate(n.model_dump()) for n in await self._nodes(node_ids)]
        missing = list(node_ids - {n.id for n in entities})
        if not missing:
            return entities
        events = (await self.session.execute(select(EventTable).where(EventTable.id.in_(missing)))).scalars().all()
        return entities + [
            GraphNode(id=e.id, entity_type=GraphNodeType.EVENT, display_name=e.title, is_verified=e.is_verified)
            for e in events
        ]

    async def _nodes(self, entity_ids: set[str]) -> list[EntitySummary]:
        if not entity_ids:
            return []
        result = await self.session.execute(select(EntityTable).where(EntityTable.id.in_(list(entity_ids))))
        return [EntitySummary.model_validate(r) for r in result.scalars().all()]

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete all confirmed edges for a dataset (used by reset-entities)."""
        result = await self.session.execute(
            delete(EntityRelationshipTable).where(EntityRelationshipTable.dataset_id == dataset_id)
        )
        await self.session.commit()
        return result.rowcount or 0

    async def plan_header_selector_links(self, dataset_id: str) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
        """`(to_link, to_unlink)` actor->selector pairs for a dataset -- see `link_header_selectors`."""
        actor = MentionTable.__table__.alias("a")
        selector = MentionTable.__table__.alias("s")
        # Contact cards (and other structured fields): a name next to its numbers in one
        # record is strong evidence on its own -- link every co-occurrence.
        contact_pairs = (
            select(actor.c.entity_id.label("actor_id"), selector.c.entity_id.label("selector_id"))
            .select_from(
                actor.join(
                    selector,
                    and_(
                        selector.c.file_id == actor.c.file_id,
                        selector.c.mentioned_id == actor.c.mentioned_id,
                        selector.c.field_path == actor.c.field_path,
                        selector.c.dataset_id == actor.c.dataset_id,
                    ),
                ).join(EntityTable, EntityTable.id == actor.c.entity_id)
            )
            .where(
                actor.c.dataset_id == dataset_id,
                actor.c.entity_attribute == "name",
                actor.c.entity_id.is_not(None),
                actor.c.field_path.is_not(None),
                actor.c.field_path.not_like("header.%"),
                EntityTable.entity_type.in_(_ACTOR_TYPES),
                selector.c.entity_type == EntityType.SELECTOR,
                selector.c.entity_id.is_not(None),
            )
            .distinct()
        )
        contact = {(r.actor_id, r.selector_id) for r in (await self.session.execute(contact_pairs)).all()}

        # Email headers: one pairing proves little -- decide from all of an address's evidence.
        evidence_rows = (
            await self.session.execute(
                text(
                    "SELECT m.entity_id AS address_id, addr.display_name AS address, n.surface_text AS name, "
                    "n.entity_id AS resolved_id, count(DISTINCT n.file_id) AS emails "
                    "FROM mention n JOIN mention m ON m.file_id = n.file_id AND m.field_path = n.field_path "
                    "AND m.selector_type = 'EMAIL' AND m.entity_id IS NOT NULL "
                    "JOIN entity addr ON addr.id = m.entity_id "
                    "WHERE n.dataset_id = :dataset_id AND n.field_path LIKE 'header.%' AND n.selector_type IS NULL "
                    "GROUP BY 1, 2, 3, 4"
                ),
                {"dataset_id": dataset_id},
            )
        ).all()
        evidence = [HeaderEvidence(**row._mapping) for row in evidence_rows]
        resolved_ids = {row.resolved_id for row in evidence if row.resolved_id}
        actors = (
            await self.session.execute(
                select(EntityTable.id, EntityTable.display_name).where(
                    EntityTable.id.in_(resolved_ids), EntityTable.entity_type.in_(_ACTOR_TYPES)
                )
            )
        ).all()
        header = decide_header_links(evidence, {row.id: row.display_name for row in actors})

        addresses = list({row.address_id for row in evidence})
        # An analyst has decided who owns these: inference neither adds nor prunes their owners,
        # so a "Move here" / "Also link here" on the entity page sticks across re-runs.
        analyst_owned = set(
            (
                await self.session.execute(
                    select(EntityRelationshipTable.dst_entity_id).where(
                        EntityRelationshipTable.relationship_type == RelationshipType.HAS_SELECTOR,
                        EntityRelationshipTable.source == RelationshipSource.MANUAL,
                        EntityRelationshipTable.dst_entity_id.in_(addresses),
                    )
                )
            ).scalars()
        )
        header = {(actor, address) for actor, address in header if address not in analyst_owned}
        existing = (
            await self.session.execute(
                select(EntityRelationshipTable.src_entity_id, EntityRelationshipTable.dst_entity_id).where(
                    EntityRelationshipTable.dataset_id == dataset_id,
                    EntityRelationshipTable.relationship_type == RelationshipType.HAS_SELECTOR,
                    EntityRelationshipTable.source == RelationshipSource.SELECTOR_INFERENCE,
                    EntityRelationshipTable.dst_entity_id.in_(addresses),
                )
            )
        ).all()
        keep = contact | header
        stale = {(r.src_entity_id, r.dst_entity_id) for r in existing} - keep
        return keep, {(actor, address) for actor, address in stale if address not in analyst_owned}

    async def link_header_selectors(self, dataset_id: str) -> int:
        """Reconcile inferred `has_selector` edges between actors and the selectors they appear with.

        Contact-card names are linked to every selector in the same record. Email
        header addresses are linked only on evidence of ownership (the address spells
        the actor's name, or the actor's name dominates its header slots -- see
        `selector_links`). Inferred edges that no longer qualify are removed; manual
        and other-source edges are never touched, and an address an analyst has
        linked by hand is left exactly as they set it. Called by the `resolve-entities`
        sweep and after a Review-queue name resolution. Returns the number of pairs
        linked.
        """
        to_link, to_unlink = await self.plan_header_selector_links(dataset_id)
        values = [
            {
                "dataset_id": dataset_id,
                "src_entity_id": actor_id,
                "dst_entity_id": selector_id,
                "relationship_type": RelationshipType.HAS_SELECTOR,
                "directed": True,
                "source": RelationshipSource.SELECTOR_INFERENCE,
                "attributes": {},
            }
            for actor_id, selector_id in to_link
        ]
        for start in range(0, len(values), _EDGE_INSERT_CHUNK):
            insert_stmt = pg_insert(EntityRelationshipTable).values(values[start : start + _EDGE_INSERT_CHUNK])
            await self.session.execute(insert_stmt.on_conflict_do_nothing(constraint="uq_entity_relationship_triple"))
        for actor_id, selector_id in to_unlink:
            await self.session.execute(
                delete(EntityRelationshipTable).where(
                    EntityRelationshipTable.dataset_id == dataset_id,
                    EntityRelationshipTable.src_entity_id == actor_id,
                    EntityRelationshipTable.dst_entity_id == selector_id,
                    EntityRelationshipTable.relationship_type == RelationshipType.HAS_SELECTOR,
                    EntityRelationshipTable.source == RelationshipSource.SELECTOR_INFERENCE,
                )
            )
        await self.session.commit()
        return len(to_link)

    # --- Face co-occurrence (`appears_in_photo_with`) --------------------------
    #
    # An undirected person<->person edge for every pair of people detected in the
    # same image. "Detected as" is deliberately loose: a face counts towards a
    # person if it is assigned to them (`face.person_id`) OR merely has a pending
    # `face_match` to them, so an edge appears before either identification is
    # confirmed. The edge set is *derived* from current face / face_match state,
    # so it self-heals: confirming a match keeps the person in the image's set
    # (now via `person_id`); rejecting one drops them, which prunes that photo
    # from the pair's evidence and deletes the edge once nothing supports it.
    #
    # `dataset_id` is NULL on these edges -- a pair can share photos across
    # datasets and the person bridge nodes are themselves dataset-agnostic.
    #
    # A pair of already-identified people is only linked once they share
    # `min_verified_photos` photos (default 2); a pair with any pending-match
    # photo -- a lead about a not-yet-confirmed connection -- is linked from the
    # first photo.

    _COOCCURRENCE_VERIFIED = "verified"
    _COOCCURRENCE_POTENTIAL = "potential"

    async def _cooccurrence_persons_by_image(self, image_ids: list[str] | None) -> dict[str, dict[str, bool]]:
        """Map `image_id -> {person_id: an_assigned_face_exists}` for identified faces.

        A person is keyed under an image if a face there is assigned to them or
        has a pending `face_match` to them; the bool is True once some face in
        that image is actually assigned to them (assignment outranks a pending
        match when both point at the same person).
        """
        pending = (
            select(FaceMatchTable.face_id, FaceMatchTable.person_id)
            .where(FaceMatchTable.status == ReviewStatus.PENDING)
            .subquery()
        )
        person_id = func.coalesce(FaceTable.person_id, pending.c.person_id)
        stmt = (
            select(
                FaceTable.image_id,
                person_id.label("person_id"),
                FaceTable.person_id.is_not(None).label("assigned"),
            )
            .outerjoin(pending, pending.c.face_id == FaceTable.id)
            .where(person_id.is_not(None), FaceTable.date_rejected.is_(None))
        )
        if image_ids is not None:
            if not image_ids:
                return {}
            stmt = stmt.where(FaceTable.image_id.in_(image_ids))

        by_image: dict[str, dict[str, bool]] = {}
        for image_id, pid, assigned in (await self.session.execute(stmt)).all():
            bucket = by_image.setdefault(image_id, {})
            bucket[pid] = bucket.get(pid, False) or bool(assigned)
        return by_image

    @classmethod
    def _cooccurrence_pairs(cls, persons_by_image: dict[str, dict[str, bool]]) -> dict[tuple[str, str], dict[str, str]]:
        """Canonical `(src < dst)` person pair -> `{image_id: 'verified' | 'potential'}`."""
        pairs: dict[tuple[str, str], dict[str, str]] = {}
        for image_id, persons in persons_by_image.items():
            ordered = sorted(persons)
            for i, src in enumerate(ordered):
                for dst in ordered[i + 1 :]:
                    basis = cls._COOCCURRENCE_VERIFIED if persons[src] and persons[dst] else cls._COOCCURRENCE_POTENTIAL
                    pairs.setdefault((src, dst), {})[image_id] = basis
        return pairs

    @classmethod
    def _cooccurrence_edge_kept(cls, evidence: dict[str, str], min_verified_photos: int) -> bool:
        """Whether a pair's evidence clears the noise floor.

        Kept if any photo is a *potential* (pending-match) co-occurrence -- a
        lead worth surfacing from the first frame -- or the pair shares at least
        `min_verified_photos` fully-verified photos.
        """
        if any(basis == cls._COOCCURRENCE_POTENTIAL for basis in evidence.values()):
            return True
        return len(evidence) >= min_verified_photos

    @classmethod
    def _cooccurrence_attributes(cls, evidence: dict[str, str]) -> dict:
        items = sorted(
            ({"image_id": image_id, "basis": basis} for image_id, basis in evidence.items()),
            key=lambda item: item["image_id"],
        )
        verified = sum(1 for item in items if item["basis"] == cls._COOCCURRENCE_VERIFIED)
        return {"evidence": items, "photo_count": len(items), "verified_photo_count": verified}

    async def _known_entity_ids(self, ids: set[str]) -> set[str]:
        if not ids:
            return set()
        rows = await self.session.execute(select(EntityTable.id).where(EntityTable.id.in_(list(ids))))
        return set(rows.scalars().all())

    async def _load_cooccurrence_edges(self) -> dict[tuple[str, str], EntityRelationshipTable]:
        rows = await self.session.execute(
            select(EntityRelationshipTable).where(
                EntityRelationshipTable.relationship_type == RelationshipType.APPEARS_IN_PHOTO_WITH
            )
        )
        return {(row.src_entity_id, row.dst_entity_id): row for row in rows.scalars().all()}

    async def _write_cooccurrence_edge(self, src: str, dst: str, evidence: dict[str, str]) -> None:
        attributes = self._cooccurrence_attributes(evidence)
        insert_stmt = pg_insert(EntityRelationshipTable).values(
            dataset_id=None,
            src_entity_id=src,
            dst_entity_id=dst,
            relationship_type=RelationshipType.APPEARS_IN_PHOTO_WITH,
            directed=False,
            weight=float(attributes["photo_count"]),
            source=RelationshipSource.FACE_COOCCURRENCE,
            attributes=attributes,
        )
        await self.session.execute(
            insert_stmt.on_conflict_do_update(
                constraint="uq_entity_relationship_triple",
                set_={
                    "weight": insert_stmt.excluded.weight,
                    "source": insert_stmt.excluded.source,
                    "attributes": insert_stmt.excluded.attributes,
                },
            )
        )

    async def _drop_cooccurrence_edge(self, src: str, dst: str) -> None:
        await self.session.execute(
            delete(EntityRelationshipTable).where(
                EntityRelationshipTable.src_entity_id == src,
                EntityRelationshipTable.dst_entity_id == dst,
                EntityRelationshipTable.relationship_type == RelationshipType.APPEARS_IN_PHOTO_WITH,
            )
        )

    async def rebuild_face_cooccurrence(
        self, min_verified_photos: int = _DEFAULT_MIN_VERIFIED_PHOTOS
    ) -> dict[str, int]:
        """Rebuild every `appears_in_photo_with` edge from current face state.

        Idempotent full reconciliation: derive the desired person<->person pairs
        from all faces + assignments + pending `face_match` rows, keep the ones
        that clear the noise floor (`min_verified_photos` shared photos for a
        fully-verified pair; any count for a pair with a pending-match lead),
        upsert those, and delete every other existing edge. Pairs whose person
        has no `entity` bridge node yet are skipped (and counted).
        """
        persons_by_image = await self._cooccurrence_persons_by_image(None)
        desired = self._cooccurrence_pairs(persons_by_image)

        known = await self._known_entity_ids({person_id for pair in desired for person_id in pair})
        resolved = {pair: evidence for pair, evidence in desired.items() if pair[0] in known and pair[1] in known}
        kept = {
            pair: evidence
            for pair, evidence in resolved.items()
            if self._cooccurrence_edge_kept(evidence, min_verified_photos)
        }

        existing = await self._load_cooccurrence_edges()
        for (src, dst), evidence in kept.items():
            await self._write_cooccurrence_edge(src, dst, evidence)
        removed = 0
        for src, dst in existing.keys() - kept.keys():
            await self._drop_cooccurrence_edge(src, dst)
            removed += 1

        await self.session.commit()
        return {
            "edges_written": len(kept),
            "edges_removed": removed,
            "images_considered": len(persons_by_image),
            "pairs_below_floor": len(resolved) - len(kept),
            "pairs_skipped_no_entity": len(desired) - len(resolved),
        }

    async def recompute_face_cooccurrence_for_faces(
        self, face_ids: list[str], min_verified_photos: int = _DEFAULT_MIN_VERIFIED_PHOTOS
    ) -> dict[str, int]:
        """Recompute `appears_in_photo_with` edges for the images these faces sit in.

        Convenience wrapper over `recompute_face_cooccurrence_for_images` that
        resolves the faces to their images first -- so it must run *before* the
        faces are deleted. For a post-deletion refresh, capture the image ids
        up front and call the image variant.
        """
        face_ids = [face_id for face_id in dict.fromkeys(face_ids) if face_id]
        if not face_ids:
            return {"edges_written": 0, "edges_removed": 0, "images_touched": 0}
        image_rows = await self.session.execute(select(FaceTable.image_id).where(FaceTable.id.in_(face_ids)).distinct())
        return await self.recompute_face_cooccurrence_for_images(
            list(image_rows.scalars().all()), min_verified_photos=min_verified_photos
        )

    async def recompute_face_cooccurrence_for_images(
        self, image_ids: list[str], min_verified_photos: int = _DEFAULT_MIN_VERIFIED_PHOTOS
    ) -> dict[str, int]:
        """Re-derive `appears_in_photo_with` edges for a set of images.

        Same reconciliation as `rebuild_face_cooccurrence`, scoped to the given
        images: each affected edge keeps its evidence from other images and only
        has these images' contribution rewritten, so confirming or rejecting one
        match immediately adds or prunes the right photo -- and deletes the edge
        once nothing supports it or it drops back below the noise floor. Safe to
        call inline after a face assignment, a match review, or a face deletion.
        """
        image_ids = [image_id for image_id in dict.fromkeys(image_ids) if image_id]
        if not image_ids:
            return {"edges_written": 0, "edges_removed": 0, "images_touched": 0}
        touched = set(image_ids)

        desired_local = self._cooccurrence_pairs(await self._cooccurrence_persons_by_image(image_ids))
        existing = await self._load_cooccurrence_edges()

        affected: set[tuple[str, str]] = set(desired_local)
        for pair, row in existing.items():
            if touched & {item["image_id"] for item in row.attributes.get("evidence", [])}:
                affected.add(pair)

        known = await self._known_entity_ids({person_id for pair in affected for person_id in pair})

        written = removed = 0
        for pair in affected:
            row = existing.get(pair)
            merged: dict[str, str] = {}
            if row is not None:
                merged = {
                    item["image_id"]: item["basis"]
                    for item in row.attributes.get("evidence", [])
                    if item["image_id"] not in touched
                }
            merged.update(desired_local.get(pair, {}))

            keep = bool(merged) and self._cooccurrence_edge_kept(merged, min_verified_photos)
            if keep and pair[0] in known and pair[1] in known:
                await self._write_cooccurrence_edge(pair[0], pair[1], merged)
                written += 1
            elif row is not None:
                await self._drop_cooccurrence_edge(pair[0], pair[1])
                removed += 1

        await self.session.commit()
        return {"edges_written": written, "edges_removed": removed, "images_touched": len(touched)}

    async def count_face_cooccurrence(self) -> dict[str, float]:
        """`(edge count, summed weight)` for `appears_in_photo_with` -- for the stats CLI."""
        row = (
            await self.session.execute(
                select(
                    func.count(EntityRelationshipTable.id),
                    func.coalesce(func.sum(EntityRelationshipTable.weight), 0.0),
                ).where(EntityRelationshipTable.relationship_type == RelationshipType.APPEARS_IN_PHOTO_WITH)
            )
        ).one()
        return {"edges": float(row[0]), "photo_links": float(row[1])}
