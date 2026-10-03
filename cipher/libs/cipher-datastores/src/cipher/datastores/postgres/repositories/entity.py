from sqlalchemy import and_, asc, case, delete, desc, distinct, func, literal, or_, select, union_all, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.geo import geojson_to_geom, geom_to_geojson, point_to_geom
from cipher.datastores.postgres.repositories._merge import fold_entity
from cipher.datastores.postgres.repositories.entity_name_key import (
    PostgresEntityNameKeyRepository,
    refresh_entity_name_keys,
)
from cipher.datastores.postgres.repositories.mention import provenance_case
from cipher.datastores.postgres.repositories.tag import PostgresTagRepository
from cipher.datastores.postgres.tables.entity import EntityTable, is_canonical_entity
from cipher.datastores.postgres.tables.entity_match import EntityMatchTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.location import LocationTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.organization import OrganizationTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.datastores.postgres.tables.selector import SelectorTable
from cipher.datastores.postgres.utils import normalize_name, strip_null_bytes
from cipher.names import entity_keys
from cipher.schemas._base.common import SortOrder
from cipher.schemas.graph.entity import (
    BreakdownItem,
    Entity,
    EntityBreakdown,
    EntityCreate,
    EntityListItem,
    EntityProfile,
    EntitySearchParameters,
    EntitySearchResult,
    EntitySortField,
    EntitySummary,
    EntityUpdate,
    PaginatedEntitiesResponse,
    PaginatedRelatedEntitiesResponse,
    RelatedEntity,
    RelatedEntitySearchParameters,
    RelatedEntitySort,
    SelectorMention,
)
from cipher.schemas.graph.entity_match import DecisionSource, EntityMatchStatus
from cipher.schemas.graph.entity_resolution import ResolutionCandidate
from cipher.schemas.graph.location import LocationCreate, LocationUpdate
from cipher.schemas.graph.mention import MentionProvenance
from cipher.schemas.graph.ontology import (
    LOW_SIGNAL_RELATIONSHIPS,
    EntitySource,
    EntityType,
    RelationshipSource,
    RelationshipType,
    SelectorSubtype,
    SelectorType,
    validate_relationship,
)
from cipher.schemas.graph.organization import (
    OrganizationCreate,
    OrganizationMember,
    OrganizationStructure,
    OrganizationUpdate,
)
from cipher.schemas.graph.selector import Selector, SelectorCreate, SelectorUpdate
from cipher.schemas.identity.person import Person, PersonSource
from cipher.schemas.interaction.tag import TagSource, TagTargetType

_DETAIL_TABLE = {
    EntityType.ORGANIZATION: OrganizationTable,
    EntityType.LOCATION: LocationTable,
    EntityType.SELECTOR: SelectorTable,
}


def _detail_key(entity_type: EntityType):
    """Column on the detail table that equals the entity node's id.

    Location detail is bridged by shared id (`location.id == entity.id`); the
    others hang off an `entity_id` FK.
    """
    if entity_type == EntityType.LOCATION:
        return LocationTable.id
    return _DETAIL_TABLE[entity_type].entity_id


_NAME_TRGM_FLOOR = 0.3


def _entity_with_selector(row) -> Entity:
    """Build an ``Entity`` from an ``(EntityTable, selector_type, selector_subtype)`` result row."""
    entity = Entity.model_validate(row[0])
    if row[1] is not None:
        entity = entity.model_copy(update={"selector_type": row[1], "selector_subtype": row[2]})
    return entity


def _in_dataset(dataset_id: str):
    """An entity belongs to a dataset: scoped to it, or dataset-agnostic and mentioned in it.

    Dataset-agnostic nodes are person bridges and every location (shared PostGIS rows) --
    without the second branch they vanish from a dataset's lists and counts.
    """
    return or_(
        EntityTable.dataset_id == dataset_id,
        and_(
            EntityTable.dataset_id.is_(None),
            select(MentionTable.id)
            .where(MentionTable.dataset_id == dataset_id, MentionTable.entity_id == EntityTable.id)
            .exists(),
        ),
    )


class PostgresEntityRepository:
    """Postgres datastore for entity nodes and their 1:1 detail rows."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the entity-layer tables using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(EntityTable.metadata.create_all)

    async def get_count(self) -> int:
        """Get total count of entities."""
        result = await self.session.execute(select(func.count(EntityTable.id)))
        return result.scalar_one()

    async def create_entity(
        self,
        entity: EntityCreate,
        detail: OrganizationCreate | LocationCreate | SelectorCreate | None = None,
        *,
        source: TagSource | None = None,
    ) -> Entity:
        """Create an entity node plus its type-specific detail row in one transaction.

        Its `tags` (and a location detail's) are recorded as `source`'s decision -- required when there are any.
        """
        values = strip_null_bytes(entity.model_dump(by_alias=False, exclude={"tags"}))
        values["display_name_normalized"] = normalize_name(entity.display_name)
        tags = list(entity.tags or [])

        row = EntityTable(**values)
        self.session.add(row)
        await self.session.flush()

        await refresh_entity_name_keys(
            self.session,
            entity_id=row.id,
            entity_type=entity.entity_type,
            display_name=entity.display_name,
            aliases=entity.aliases or [],
        )

        detail_table = _DETAIL_TABLE.get(entity.entity_type)
        if detail is not None and detail_table is not None:
            detail_values = strip_null_bytes(detail.model_dump(by_alias=False))
            tags += detail_values.pop("tags", None) or []
            if entity.entity_type == EntityType.LOCATION:
                # Location detail is bridged by shared id (like person), not an
                # entity_id FK: the detail row *is* the entity node's geo half.
                detail_values.pop("entity_id", None)
                geo_json = detail_values.pop("geo_json", None)
                if geo_json is not None:
                    detail_values["geom"] = geojson_to_geom(geo_json)
                elif detail_values.get("latitude") is not None and detail_values.get("longitude") is not None:
                    detail_values["geom"] = point_to_geom(
                        latitude=detail_values["latitude"], longitude=detail_values["longitude"]
                    )
                detail_values["id"] = row.id
            else:
                detail_values["entity_id"] = row.id
            self.session.add(detail_table(**detail_values))
            if entity.entity_type == EntityType.LOCATION:
                await self.session.flush()  # the location row must exist before the FK points at it
                row.location_id = row.id

        result = Entity.model_validate(row)
        await self.session.commit()
        if tags:
            if source is None:
                raise ValueError("Entity tags need a source (who or what tagged them)")
            await PostgresTagRepository(self.session).set_tags(
                target_type=TagTargetType.ENTITY, target_id=result.id, tags=tags, source=source
            )
            return await self.get_entity(result.id)
        return result

    async def upsert_person_entity(self, person: Person, *, source: EntitySource = EntitySource.MANUAL) -> Entity:
        """Create or refresh the knowledge-graph node that mirrors a person.

        The bridge node shares the person's id (``entity.id == person.id``) and
        is dataset-agnostic, so a person resolves to the same entity across every
        dataset they appear in. Idempotent -- safe to call on every person write.
        `source` marks how the node arose (`face_clustering` for an unnamed
        cluster, `manual` for an analyst-created identity).
        """
        display_name = person.name or "Unnamed Person"
        values = strip_null_bytes(
            {
                "id": person.id,
                "person_id": person.id,
                "entity_type": EntityType.PERSON,
                "dataset_id": None,
                "source": source,
                "display_name": display_name,
                "display_name_normalized": normalize_name(display_name),
                "aliases": person.aliases,
                "is_verified": person.is_verified,
            }
        )
        stmt = (
            pg_insert(EntityTable)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[EntityTable.id],
                set_={
                    "display_name": values["display_name"],
                    "display_name_normalized": values["display_name_normalized"],
                    "aliases": values["aliases"],
                    "is_verified": values["is_verified"],
                    "person_id": person.id,
                },
            )
            .returning(EntityTable)
        )
        row = (await self.session.execute(stmt)).scalar_one()
        await refresh_entity_name_keys(
            self.session,
            entity_id=row.id,
            entity_type=EntityType.PERSON,
            display_name=row.display_name,
            aliases=row.aliases or [],
        )
        # The bridge carries the person's tag assignments (recorded against the shared id).
        await PostgresTagRepository(self.session).refresh(target_type=TagTargetType.ENTITY, target_ids=[row.id])
        await self.session.commit()
        return await self.get_entity(row.id)

    async def delete_person_entity(self, person_id: str) -> bool:
        """Drop the bridge node for a person (mentions/edges null out per their FKs) and its tags."""
        return await self.delete_entity(person_id)

    async def get_entity(self, entity_id: str) -> Entity | None:
        """Retrieve an entity node by ID (with its selector type/subtype, when it is a selector)."""
        result = await self.session.execute(
            select(EntityTable, SelectorTable.selector_type, SelectorTable.selector_subtype)
            .outerjoin(SelectorTable, SelectorTable.entity_id == EntityTable.id)
            .where(EntityTable.id == entity_id)
        )
        row = result.first()
        return _entity_with_selector(row) if row else None

    async def update_entity(self, entity_id: str, data: EntityUpdate, *, user_id: str) -> Entity | None:
        """Patch an entity node; a `tags` list is recorded as `user_id`'s edit."""
        if data.tags is not None and await self.get_entity(entity_id) is not None:
            await PostgresTagRepository(self.session).set_tags(
                target_type=TagTargetType.ENTITY, target_id=entity_id, tags=data.tags, source=TagSource.user(user_id)
            )
        patch = data.model_dump(exclude_unset=True, exclude={"tags"}, by_alias=False)
        if "display_name" in patch and patch["display_name"] is not None:
            patch["display_name_normalized"] = normalize_name(patch["display_name"])
        if not patch:
            return await self.get_entity(entity_id)
        stmt = update(EntityTable).where(EntityTable.id == entity_id).values(**patch).returning(EntityTable)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None and {"display_name", "aliases"} & patch.keys():
            await refresh_entity_name_keys(
                self.session,
                entity_id=row.id,
                entity_type=row.entity_type,
                display_name=row.display_name,
                aliases=row.aliases or [],
            )
        entity = Entity.model_validate(row) if row else None
        await self.session.commit()
        return entity

    async def set_name_embedding(self, entity_id: str, embedding: list[float]) -> None:
        """Store the display-name embedding used for fuzzy resolution."""
        await self.session.execute(
            update(EntityTable).where(EntityTable.id == entity_id).values(name_embedding=embedding)
        )
        await self.session.commit()

    async def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity node (detail rows, mentions, and edges cascade or null out) and its tags."""
        result = await self.session.execute(delete(EntityTable).where(EntityTable.id == entity_id))
        await PostgresTagRepository(self.session).delete_for_targets(
            target_type=TagTargetType.ENTITY, target_ids=[entity_id]
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def delete_nonmanual_by_dataset_id(self, dataset_id: str) -> dict[str, int]:
        """Drop a dataset's extraction-built entities (+ their detail) for reset-entities.

        Keeps anything an analyst authored (`source = manual`). `organization` /
        `selector` detail cascade on the `entity` delete; `location` detail is a
        shared-id bridge (`entity.location_id -> location.id`, SET NULL) so its
        rows are removed explicitly first -- but only the bridged ones, leaving
        standalone `location` rows (e.g. a photo's EXIF point with no entity)
        untouched. Returns `{"entities": n, "locations": m}`.
        """
        doomed = select(EntityTable.id).where(
            EntityTable.dataset_id == dataset_id,
            EntityTable.source != EntitySource.MANUAL,
        )
        loc_result = await self.session.execute(
            delete(LocationTable).where(
                LocationTable.id.in_(
                    select(EntityTable.location_id).where(
                        EntityTable.id.in_(doomed), EntityTable.location_id.is_not(None)
                    )
                )
            )
        )
        ent_result = await self.session.execute(delete(EntityTable).where(EntityTable.id.in_(doomed)))
        await self.session.commit()
        return {"entities": ent_result.rowcount or 0, "locations": loc_result.rowcount or 0}

    async def _list_stats(self, entity_ids: list[str], *, mention_where: list) -> dict[str, dict[str, int]]:
        """Mention / file / edge / pending-match counts for one page of entity rows."""
        if not entity_ids:
            return {}
        stats: dict[str, dict[str, int]] = {entity_id: {} for entity_id in entity_ids}
        mention_rows = await self.session.execute(
            select(
                MentionTable.entity_id,
                func.count(MentionTable.id),
                func.count(distinct(MentionTable.file_id)),
            )
            .where(*mention_where, MentionTable.entity_id.in_(entity_ids))
            .group_by(MentionTable.entity_id)
        )
        for entity_id, mention_count, file_count in mention_rows.all():
            stats[entity_id].update(mention_count=mention_count, file_count=file_count)

        endpoints = union_all(
            select(EntityRelationshipTable.src_entity_id.label("entity_id")).where(
                EntityRelationshipTable.src_entity_id.in_(entity_ids)
            ),
            select(EntityRelationshipTable.dst_entity_id.label("entity_id")).where(
                EntityRelationshipTable.dst_entity_id.in_(entity_ids)
            ),
        ).subquery()
        edge_rows = await self.session.execute(
            select(endpoints.c.entity_id, func.count()).group_by(endpoints.c.entity_id)
        )
        for entity_id, relationship_count in edge_rows.all():
            stats[entity_id]["relationship_count"] = relationship_count

        match_entity = func.coalesce(EntityMatchTable.provisional_entity_id, EntityMatchTable.entity_id)
        match_rows = await self.session.execute(
            select(match_entity, func.count(EntityMatchTable.id))
            .where(
                EntityMatchTable.status == EntityMatchStatus.PENDING,
                or_(
                    EntityMatchTable.entity_id.in_(entity_ids),
                    EntityMatchTable.provisional_entity_id.in_(entity_ids),
                ),
            )
            .group_by(match_entity)
        )
        for entity_id, pending_match_count in match_rows.all():
            if entity_id in stats:
                stats[entity_id]["pending_match_count"] = pending_match_count
        return stats

    async def list_entities(self, request: EntitySearchParameters) -> PaginatedEntitiesResponse:
        """List/filter entity nodes with pagination and sorting."""
        where = []
        if request.dataset_id:
            # Dataset-scoped rows, plus dataset-agnostic bridge nodes (person
            # entities have dataset_id NULL) that are actually mentioned in this
            # dataset -- otherwise a person who appears all over `rag` is
            # invisible on `rag`'s entity list.
            where.append(_in_dataset(request.dataset_id))
        if request.entity_type:
            where.append(EntityTable.entity_type == request.entity_type)
        if request.is_verified is not None:
            where.append(EntityTable.is_verified == request.is_verified)
        if request.provisional is not None:
            # provisional = auto-created by the resolver, awaiting verification or a merge
            where.append(~is_canonical_entity() if request.provisional else is_canonical_entity())
            if request.provisional:
                where.append(EntityTable.entity_type != EntityType.SELECTOR)
        if request.tags:
            where.append(EntityTable.tags.overlap(request.tags))
        if request.query:
            floor = normalize_name(request.query)
            where.append(
                or_(
                    EntityTable.display_name_normalized.ilike(f"%{floor}%"),
                    func.similarity(EntityTable.display_name_normalized, floor) >= _NAME_TRGM_FLOOR,
                )
            )
        if request.selector_type:
            where.append(
                EntityTable.id.in_(
                    select(SelectorTable.entity_id).where(SelectorTable.selector_type == request.selector_type)
                )
            )
        if request.selector_subtype:
            where.append(
                EntityTable.id.in_(
                    select(SelectorTable.entity_id).where(SelectorTable.selector_subtype == request.selector_subtype)
                )
            )
        if request.country:
            where.append(
                or_(
                    EntityTable.id.in_(
                        select(OrganizationTable.entity_id).where(OrganizationTable.country.ilike(request.country))
                    ),
                    EntityTable.location_id.in_(
                        select(LocationTable.id).where(LocationTable.country.ilike(request.country))
                    ),
                )
            )
        if request.category:
            where.append(
                EntityTable.id.in_(
                    select(OrganizationTable.entity_id).where(OrganizationTable.category.ilike(request.category))
                )
            )
        if request.date_of_birth_from or request.date_of_birth_to:
            dob_where = []
            if request.date_of_birth_from:
                dob_where.append(PersonTable.date_of_birth >= request.date_of_birth_from)
            if request.date_of_birth_to:
                dob_where.append(PersonTable.date_of_birth <= request.date_of_birth_to)
            where.append(EntityTable.person_id.in_(select(PersonTable.id).where(*dob_where)))

        count_result = await self.session.execute(select(func.count(EntityTable.id)).where(*where))
        total = count_result.scalar_one()

        mention_where = [MentionTable.entity_id.is_not(None)]
        if request.dataset_id:
            mention_where.append(MentionTable.dataset_id == request.dataset_id)

        stmt = (
            select(EntityTable, SelectorTable.selector_type, SelectorTable.selector_subtype)
            .outerjoin(SelectorTable, SelectorTable.entity_id == EntityTable.id)
            .where(*where)
        )
        if request.sort_by == EntitySortField.MENTION_COUNT and request.query:
            # typeahead: a name query leaves few rows, so count per match instead of totalling the dataset
            sort_column = (
                select(func.count())
                .where(MentionTable.entity_id == EntityTable.id, *mention_where)
                .scalar_subquery()
            )
        elif request.sort_by == EntitySortField.MENTION_COUNT:
            mention_totals = (
                # count(*) not count(id): answerable from ix_mention_dataset_entity alone (index-only scan)
                select(MentionTable.entity_id, func.count().label("mention_count"))
                .where(*mention_where)
                .group_by(MentionTable.entity_id)
                .subquery()
            )
            sort_column = func.coalesce(mention_totals.c.mention_count, 0)
            stmt = stmt.outerjoin(mention_totals, mention_totals.c.entity_id == EntityTable.id)
        elif request.sort_by == EntitySortField.RELEVANCE and request.query:
            # typeahead: exact name, then prefix, then substring, then closest trigram (typo) match
            floor = normalize_name(request.query)
            name = EntityTable.display_name_normalized
            result = await self.session.execute(
                stmt.order_by(
                    desc(name == floor),
                    desc(name.startswith(floor, autoescape=True)),
                    desc(name.contains(floor, autoescape=True)),
                    desc(func.similarity(name, floor)),
                    func.length(name),
                )
                .offset((request.page - 1) * request.limit)
                .limit(request.limit)
            )
            return await self._list_page(request=request, total=total, rows=result.all(), mention_where=mention_where)
        else:
            sort_column = {
                EntitySortField.DISPLAY_NAME: EntityTable.display_name_normalized,
                EntitySortField.DATE_CREATED: EntityTable.date_created,
                EntitySortField.DATE_UPDATED: EntityTable.date_updated,
            }[request.sort_by]
        order = desc(sort_column) if request.sort_order == SortOrder.DESC else asc(sort_column)

        result = await self.session.execute(
            stmt.order_by(order, EntityTable.display_name_normalized)
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )
        return await self._list_page(request=request, total=total, rows=result.all(), mention_where=mention_where)

    async def _list_page(
        self, *, request: EntitySearchParameters, total: int, rows: list, mention_where: list
    ) -> PaginatedEntitiesResponse:
        entities = [_entity_with_selector(row) for row in rows]
        stats = await self._list_stats([e.id for e in entities], mention_where=mention_where)
        data = [EntityListItem(**e.model_dump(), **stats.get(e.id, {})) for e in entities]
        return PaginatedEntitiesResponse(total=total, page=request.page, limit=request.limit, data=data)

    async def entity_breakdown(self, *, dataset_id: str | None = None) -> EntityBreakdown:
        """Counts of a dataset's entities by type / selector type / selector subtype."""
        ent_where = [_in_dataset(dataset_id)] if dataset_id else []
        sel_where = [SelectorTable.dataset_id == dataset_id] if dataset_id else []

        by_type = (
            await self.session.execute(
                select(EntityTable.entity_type, func.count(EntityTable.id))
                .where(*ent_where)
                .group_by(EntityTable.entity_type)
                .order_by(func.count(EntityTable.id).desc())
            )
        ).all()
        by_sel_type = (
            await self.session.execute(
                select(SelectorTable.selector_type, func.count(SelectorTable.id))
                .where(*sel_where)
                .group_by(SelectorTable.selector_type)
                .order_by(func.count(SelectorTable.id).desc())
            )
        ).all()
        by_sel_subtype = (
            await self.session.execute(
                select(SelectorTable.selector_subtype, func.count(SelectorTable.id))
                .where(*sel_where, SelectorTable.selector_subtype.is_not(None))
                .group_by(SelectorTable.selector_subtype)
                .order_by(func.count(SelectorTable.id).desc())
            )
        ).all()

        return EntityBreakdown(
            total=sum(n for _, n in by_type),
            by_entity_type=[BreakdownItem(key=str(k), count=n) for k, n in by_type],
            by_selector_type=[BreakdownItem(key=str(k), count=n) for k, n in by_sel_type],
            by_selector_subtype=[BreakdownItem(key=str(k), count=n) for k, n in by_sel_subtype],
        )

    async def find_by_normalized_name(
        self, *, dataset_id: str, entity_type: EntityType, normalized_value: str
    ) -> Entity | None:
        """Exact match on `display_name_normalized` -- the resolution blocking key for names.

        Person lookups also match dataset-agnostic bridge nodes (`dataset_id IS
        NULL`) and prefer them, so a name resolves to the real cross-dataset
        person when one exists.
        """
        scope = EntityTable.dataset_id == dataset_id
        prefer_global = EntityTable.id  # stable fallback ordering
        if entity_type == EntityType.PERSON:
            scope = or_(scope, EntityTable.dataset_id.is_(None))
            prefer_global = EntityTable.dataset_id.is_(None).desc()
        stmt = (
            select(EntityTable)
            .where(
                EntityTable.entity_type == entity_type,
                EntityTable.display_name_normalized == normalized_value,
                scope,
            )
            .order_by(prefer_global)
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return Entity.model_validate(row) if row else None

    async def search_by_name(
        self,
        *,
        dataset_id: str | None,
        query: str,
        limit: int = 10,
        entity_type: EntityType | None = None,
    ) -> list[EntitySearchResult]:
        """Substring + trigram fuzzy search on the normalized display name.

        A plain ``ilike`` substring branch (for queries of 2+ chars) keeps short
        prefixes matching long values like email selectors, where trigram
        similarity stays under the floor until most of the string is typed.
        """
        normalized = normalize_name(query)
        score = func.similarity(EntityTable.display_name_normalized, normalized)
        substring = EntityTable.display_name_normalized.ilike(f"%{normalized}%")
        name_match = or_(substring, score >= _NAME_TRGM_FLOOR) if len(normalized) >= 2 else score >= _NAME_TRGM_FLOOR
        where = [name_match]
        if dataset_id is not None:
            where.append(
                or_(
                    EntityTable.dataset_id == dataset_id,
                    and_(
                        EntityTable.dataset_id.is_(None),
                        # Correlated EXISTS, not `id IN (SELECT ... FROM mention)`: the IN form
                        # makes the planner cost a ~1.5M-row materialize, which trips JIT
                        # compilation (~120 ms) on every call -- 190 ms -> 0.5 ms.
                        select(MentionTable.id)
                        .where(MentionTable.entity_id == EntityTable.id, MentionTable.dataset_id == dataset_id)
                        .exists(),
                    ),
                )
            )
        if entity_type:
            where.append(EntityTable.entity_type == entity_type)

        # Canonical entities ahead of auto-created ones (a name's many provisional
        # spellings would otherwise fill the page), then prefix hits, other
        # substring hits, pure fuzzy -- each tier by descending trigram score.
        rank = case(
            (EntityTable.display_name_normalized.ilike(f"{normalized}%"), 2),
            (substring, 1),
            else_=0,
        )
        stmt = (
            select(EntityTable, score.label("score"))
            .where(*where)
            .order_by(desc(is_canonical_entity()), desc(rank), desc("score"))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            EntitySearchResult(
                **EntitySummary.model_validate(row).model_dump(),
                is_provisional=Entity.model_validate(row).is_provisional,
                match_reason="name trigram",
                score=max(0.0, min(1.0, float(value))),
            )
            for row, value in result.all()
        ]

    async def get_resolution_candidates(
        self,
        *,
        name: str,
        dataset_id: str | None,
        entity_type: EntityType | None = None,
        normalized_value: str | None = None,
        selector_values: list[str] | None = None,
        cross_dataset: bool = False,
        limit: int = 50,
    ) -> list[ResolutionCandidate]:
        """Blocking-only candidate generation for entity resolution (R1).

        Unions four strategies, best-first: the person/org that already
        `has_selector` a value the mention sits next to (`selector_values`) ->
        exact folded name -> `entity_name_key` blocking (transliterated /
        phonetic / surname / ...) -> name trigram. Returns deduped
        `ResolutionCandidate`s with `blocked_by` set; scoring is R2.
        """
        normalized = normalized_value or normalize_name(name)
        acc: dict[str, dict] = {}  # entity_id -> {"blocked_by": set, "trigram": float | None}

        def _mark(entity_id: str, tag: str, trigram: float | None = None) -> None:
            slot = acc.setdefault(entity_id, {"blocked_by": set(), "trigram": None})
            slot["blocked_by"].add(tag)
            if trigram is not None and (slot["trigram"] is None or trigram > slot["trigram"]):
                slot["trigram"] = trigram

        if selector_values:
            actor_q = (
                select(EntityRelationshipTable.src_entity_id)
                .join(SelectorTable, SelectorTable.entity_id == EntityRelationshipTable.dst_entity_id)
                .where(
                    SelectorTable.normalized_value.in_(selector_values),
                    EntityRelationshipTable.relationship_type == RelationshipType.HAS_SELECTOR,
                )
                .distinct()
            )
            if not cross_dataset:
                actor_q = actor_q.join(EntityTable, EntityTable.id == EntityRelationshipTable.src_entity_id).where(
                    or_(EntityTable.dataset_id == dataset_id, EntityTable.dataset_id.is_(None))
                )
            for (eid,) in (await self.session.execute(actor_q)).all():
                _mark(eid, "selector")

        if normalized:
            # Selectors resolve by value, never by name -- keep them out of the
            # name/trigram branches (they otherwise trigram-match their own
            # address string and get vetoed downstream).
            exact_q = select(EntityTable.id).where(
                EntityTable.display_name_normalized == normalized,
                EntityTable.entity_type != EntityType.SELECTOR,
            )
            if entity_type is not None:
                exact_q = exact_q.where(EntityTable.entity_type == entity_type)
            if not cross_dataset:
                exact_q = exact_q.where(or_(EntityTable.dataset_id == dataset_id, EntityTable.dataset_id.is_(None)))
            for (eid,) in (await self.session.execute(exact_q.limit(limit))).all():
                _mark(eid, "name_exact")

        key_repo = PostgresEntityNameKeyRepository(self.session)
        for eid, key_types in await key_repo.candidates(
            keys=entity_keys(name),
            dataset_id=dataset_id,
            entity_type=entity_type,
            cross_dataset=cross_dataset,
            limit=limit,
        ):
            for key_type in key_types:
                _mark(eid, f"key:{key_type}")

        if dataset_id is not None and not cross_dataset:
            for result in await self.search_by_name(
                dataset_id=dataset_id, query=name, limit=limit, entity_type=entity_type
            ):
                _mark(result.id, "trigram", result.score)

        if not acc:
            return []

        # Drop selector nodes that a trigram/ilike branch pulled in on their own
        # value; they are not name-resolution targets.
        summaries = {
            row.id: EntitySummary.model_validate(row)
            for row in (
                await self.session.execute(
                    select(EntityTable).where(
                        EntityTable.id.in_(acc.keys()), EntityTable.entity_type != EntityType.SELECTOR
                    )
                )
            ).scalars()
        }

        def _rank(item: tuple[str, dict]) -> tuple:
            tags = item[1]["blocked_by"]
            key_hits = sum(1 for t in tags if t.startswith("key:"))
            return (
                "selector" in tags,
                "name_exact" in tags,
                key_hits,
                item[1]["trigram"] or 0.0,
            )

        candidates = [
            ResolutionCandidate(
                entity=summaries[eid],
                blocked_by=sorted(slot["blocked_by"]),
                trigram_score=slot["trigram"],
            )
            for eid, slot in sorted(acc.items(), key=_rank, reverse=True)
            if eid in summaries
        ]
        return candidates[:limit]

    async def search_by_selector(
        self, *, dataset_id: str | None, normalized_value: str, selector_type: SelectorType | None = None
    ) -> Entity | None:
        """Exact lookup of the entity owning a normalized selector value.

        A ``dataset_id`` matches that dataset *or* a dataset-agnostic
        (analyst-attached) selector; ``None`` matches any selector with the value.
        """
        where = [SelectorTable.normalized_value == normalized_value]
        if dataset_id is not None:
            where.append(or_(SelectorTable.dataset_id == dataset_id, SelectorTable.dataset_id.is_(None)))
        if selector_type:
            where.append(SelectorTable.selector_type == selector_type)
        stmt = (
            select(EntityTable)
            .join(SelectorTable, SelectorTable.entity_id == EntityTable.id)
            .where(*where)
            .order_by(SelectorTable.dataset_id.is_(None))  # prefer a dataset-scoped hit
            .limit(1)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return Entity.model_validate(row) if row else None

    async def get_or_create_selector(
        self,
        *,
        dataset_id: str | None,
        selector_type: SelectorType,
        raw_value: str,
        normalized_value: str,
        selector_subtype: SelectorSubtype | None = None,
        region_hint: str | None = None,
        display_name: str | None = None,
        attributes: dict[str, str] | None = None,
    ) -> tuple[Entity, bool]:
        """Return the entity for a normalized selector value, creating it if absent.

        ``dataset_id`` may be ``None`` -- an analyst-attached selector known from
        external knowledge, not observed in a dataset. On a dedupe hit, new
        ``attributes`` keys are merged onto the existing selector detail.

        Returns (entity, created).
        """
        existing = await self.search_by_selector(
            dataset_id=dataset_id, normalized_value=normalized_value, selector_type=selector_type
        )
        if existing:
            if attributes:
                await self.session.execute(
                    update(SelectorTable)
                    .where(SelectorTable.entity_id == existing.id)
                    .values(attributes=SelectorTable.attributes.op("||")(attributes))
                )
            return existing, False

        entity = await self.create_entity(
            EntityCreate(
                dataset_id=dataset_id,
                entity_type=EntityType.SELECTOR,
                display_name=display_name or raw_value,
            ),
            detail=SelectorCreate(
                entity_id="",  # set to the new entity id inside create_entity
                dataset_id=dataset_id,
                selector_type=selector_type,
                selector_subtype=selector_subtype,
                raw_value=raw_value,
                normalized_value=normalized_value,
                region_hint=region_hint,
                attributes=attributes or {},
            ),
        )
        return entity, True

    async def promote_entity(self, entity_id: str, *, reviewed_by: str | None = None) -> Entity | None:
        """Make a provisional entity canonical, keeping its id (its mentions stay put).

        A person gains a person record sharing its id (`entity.id == person.id`) so it
        gets a person page and becomes a merge target; any other type is marked
        analyst-made (`source=manual`). No-op on an already-canonical entity.
        """
        row = await self.session.get(EntityTable, entity_id)
        if row is None:
            return None
        if row.entity_type == EntityType.PERSON and row.person_id is None:
            self.session.add(
                PersonTable(
                    id=row.id, name=row.display_name, aliases=list(row.aliases or []), source=PersonSource.MANUAL
                )
            )
            await self.session.flush()
            row.person_id = row.id
            row.dataset_id = None
        elif row.entity_type != EntityType.PERSON:
            row.source = EntitySource.MANUAL
        # "a new entity" answers its merge proposals: none of those
        await self.session.execute(
            update(EntityMatchTable)
            .where(
                EntityMatchTable.provisional_entity_id == entity_id,
                EntityMatchTable.status == EntityMatchStatus.PENDING,
            )
            .values(
                status=EntityMatchStatus.REJECTED,
                reviewed_by=reviewed_by,
                reviewed_at=func.now(),
                decision_source=DecisionSource.ANALYST.value,
            )
        )
        entity = Entity.model_validate(row)
        await self.session.commit()
        return entity

    async def retype_entity(self, entity_id: str, entity_type: EntityType) -> dict[str, int] | None:
        """Change an auto-created entity's type (person <-> organization). None if it's missing.

        Its name mentions take the new type, its name keys are rebuilt, an organization detail
        row is dropped when it stops being one, and edges the new type can't have (a person's
        `member_of` on an organization) are deleted.

        Raises:
            ValueError: if the entity isn't auto-created or the type isn't person/organization.
        """
        row = await self.session.get(EntityTable, entity_id)
        if row is None:
            return None
        if not Entity.model_validate(row).is_provisional:
            raise ValueError(f"{row.display_name} is verified; only auto-created entities can change type")
        if entity_type not in (EntityType.PERSON, EntityType.ORGANIZATION):
            raise ValueError("an auto-created entity can only become a person or an organization")
        if row.entity_type == entity_type:
            return {"mentions": 0, "edges_removed": 0}

        if row.entity_type == EntityType.ORGANIZATION:
            await self.session.execute(delete(OrganizationTable).where(OrganizationTable.entity_id == entity_id))
        row.entity_type = entity_type
        await refresh_entity_name_keys(
            self.session,
            entity_id=entity_id,
            entity_type=entity_type,
            display_name=row.display_name,
            aliases=row.aliases or [],
        )
        mentions = await self.session.execute(
            update(MentionTable)
            .where(MentionTable.entity_id == entity_id, MentionTable.entity_attribute == "name")
            .values(entity_type=entity_type)
        )

        other = EntityTable.__table__.alias("other")
        edges = await self.session.execute(
            select(
                EntityRelationshipTable.id,
                EntityRelationshipTable.relationship_type,
                EntityRelationshipTable.src_entity_id,
                other.c.entity_type,
            )
            .join(
                other,
                other.c.id
                == case(
                    (EntityRelationshipTable.src_entity_id == entity_id, EntityRelationshipTable.dst_entity_id),
                    else_=EntityRelationshipTable.src_entity_id,
                ),
            )
            .where(
                or_(
                    EntityRelationshipTable.src_entity_id == entity_id,
                    EntityRelationshipTable.dst_entity_id == entity_id,
                )
            )
        )
        invalid = []
        for edge_id, relationship_type, src_id, other_type in edges:
            src_type, dst_type = (entity_type, other_type) if src_id == entity_id else (other_type, entity_type)
            try:
                validate_relationship(relationship_type=relationship_type, src_type=src_type, dst_type=dst_type)
            except ValueError:
                invalid.append(edge_id)
        if invalid:
            await self.session.execute(delete(EntityRelationshipTable).where(EntityRelationshipTable.id.in_(invalid)))
        await self.session.commit()
        return {"mentions": mentions.rowcount or 0, "edges_removed": len(invalid)}

    async def merge_entities(self, *, canonical_id: str, provisional_id: str) -> dict[str, int]:
        """Fold the provisional entity into the canonical one, then delete it.

        Repoints everything keyed on ``provisional_id`` -- mentions, relationship
        edges + candidates, entity-match review rows, event participations and
        comment threads -- onto ``canonical_id``, and keeps the provisional's
        name as a canonical alias. Returns per-table moved counts.

        Raises:
            ValueError: if the ids are equal or either entity is missing.
        """
        moved = await fold_entity(self.session, source_id=provisional_id, target_id=canonical_id)
        await self.session.commit()
        return moved

    async def update_detail(
        self,
        entity_id: str,
        data: OrganizationUpdate | LocationUpdate | SelectorUpdate,
    ) -> dict | None:
        """Patch the type-specific detail row for an entity, returning the fresh detail dict.

        Only organization / location / selector details are editable here; person
        details are edited through the persons API.
        """
        entity = await self.get_entity(entity_id)
        if entity is None:
            return None
        detail_table = _DETAIL_TABLE.get(entity.entity_type)
        if detail_table is None:
            return None
        patch = strip_null_bytes(data.model_dump(exclude_unset=True, by_alias=False))
        if entity.entity_type == EntityType.LOCATION:
            patch.pop("geo_json", None)
            if patch.get("latitude") is not None and patch.get("longitude") is not None:
                patch["geom"] = point_to_geom(latitude=patch["latitude"], longitude=patch["longitude"])
        if entity.entity_type == EntityType.ORGANIZATION:
            if "parent_id" in patch:
                await self._check_parent(entity_id, patch["parent_id"])
            # Most organizations are auto-created without a detail row -- create it on first edit.
            insert_stmt = pg_insert(OrganizationTable).values(entity_id=entity_id, **patch)
            await self.session.execute(
                insert_stmt.on_conflict_do_update(index_elements=["entity_id"], set_=patch)
                if patch
                else insert_stmt.on_conflict_do_nothing(index_elements=["entity_id"])
            )
            if "parent_id" in patch:
                await self._sync_part_of(entity_id, patch["parent_id"])
            await self.session.commit()
        elif patch:
            await self.session.execute(
                update(detail_table).where(_detail_key(entity.entity_type) == entity_id).values(**patch)
            )
            await self.session.commit()
        return await self._detail_dict(entity)

    async def set_organization_parent(self, entity_id: str, parent_id: str | None) -> None:
        """Make `parent_id` the organization `entity_id` is a unit of (None detaches it)."""
        await self.update_detail(entity_id, OrganizationUpdate(parent_id=parent_id))

    async def _check_parent(self, entity_id: str, parent_id: str | None) -> None:
        """Reject a parent that isn't an organization, is the org itself, or sits below it."""
        if parent_id is None:
            return
        if parent_id == entity_id:
            raise ValueError("An organization can't be its own parent")
        parent = await self.get_entity(parent_id)
        if parent is None or parent.entity_type != EntityType.ORGANIZATION:
            raise ValueError("The parent must be an organization")
        seen, current = {entity_id}, parent_id
        while current is not None:
            if current in seen:
                raise ValueError("That parent is already below this organization")
            seen.add(current)
            current = await self.session.scalar(
                select(OrganizationTable.parent_id).where(OrganizationTable.entity_id == current)
            )

    async def _sync_part_of(self, entity_id: str, parent_id: str | None) -> None:
        """Mirror `organization.parent_id` as the org's single `part_of` edge."""
        await self.session.execute(
            delete(EntityRelationshipTable).where(
                EntityRelationshipTable.src_entity_id == entity_id,
                EntityRelationshipTable.relationship_type == RelationshipType.PART_OF,
            )
        )
        if parent_id is not None:
            self.session.add(
                EntityRelationshipTable(
                    src_entity_id=entity_id,
                    dst_entity_id=parent_id,
                    relationship_type=RelationshipType.PART_OF,
                    directed=True,
                    source=RelationshipSource.MANUAL,
                    attributes={},
                )
            )

    async def organization_structure(self, entity_id: str, *, limit: int = 200) -> OrganizationStructure:
        """Parent chain, sub-units, locations and people of an organization, read from its edges."""
        ancestors: list[EntitySummary] = []
        seen, current = {entity_id}, entity_id
        while True:
            parent = await self.session.scalar(
                select(EntityTable)
                .join(EntityRelationshipTable, EntityRelationshipTable.dst_entity_id == EntityTable.id)
                .where(
                    EntityRelationshipTable.src_entity_id == current,
                    EntityRelationshipTable.relationship_type == RelationshipType.PART_OF,
                )
                .limit(1)
            )
            if parent is None or parent.id in seen:
                break
            ancestors.append(EntitySummary.model_validate(parent))
            seen.add(parent.id)
            current = parent.id

        async def linked(*, outgoing: bool, types: list[RelationshipType]):
            near, far = (
                (EntityRelationshipTable.src_entity_id, EntityRelationshipTable.dst_entity_id)
                if outgoing
                else (EntityRelationshipTable.dst_entity_id, EntityRelationshipTable.src_entity_id)
            )
            rows = await self.session.execute(
                select(EntityTable, EntityRelationshipTable.relationship_type, EntityRelationshipTable.attributes)
                .join(EntityRelationshipTable, far == EntityTable.id)
                .where(near == entity_id, EntityRelationshipTable.relationship_type.in_(types))
                .order_by(EntityTable.display_name)
                .limit(limit)
            )
            return rows.all()

        children = await linked(outgoing=False, types=[RelationshipType.PART_OF])
        locations = await linked(outgoing=True, types=[RelationshipType.LOCATED_IN])
        members = await linked(outgoing=False, types=[RelationshipType.EMPLOYED_BY, RelationshipType.MEMBER_OF])
        return OrganizationStructure(
            ancestors=ancestors,
            children=[EntitySummary.model_validate(e) for e, _, _ in children],
            locations=[EntitySummary.model_validate(e) for e, _, _ in locations],
            members=[
                OrganizationMember(
                    entity=EntitySummary.model_validate(e), relationship_type=rt, role=(attrs or {}).get("role")
                )
                for e, rt, attrs in members
            ],
        )

    async def get_selector_detail(self, entity_id: str) -> Selector | None:
        """Fetch the selector detail row for a selector entity."""
        result = await self.session.execute(select(SelectorTable).where(SelectorTable.entity_id == entity_id))
        row = result.scalar_one_or_none()
        return Selector.model_validate(row) if row else None

    async def list_selectors(self, *, dataset_id: str | None = None) -> list[Selector]:
        """Every selector detail row, optionally scoped to one dataset (for backfill jobs)."""
        stmt = select(SelectorTable)
        if dataset_id:
            stmt = stmt.where(SelectorTable.dataset_id == dataset_id)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [Selector.model_validate(r) for r in rows]

    async def refresh_selector(
        self,
        entity_id: str,
        *,
        attributes: dict[str, str] | None = None,
        region_hint: str | None = None,
        normalized_value: str | None = None,
    ) -> None:
        """Overwrite the recomputable fields of one selector row (backfill).

        ``normalized_value`` is only changed when explicitly passed -- it is the
        blocking key, so a caller that changes it must own the collision risk.
        """
        values: dict = {}
        if attributes is not None:
            values["attributes"] = attributes
        if region_hint is not None:
            values["region_hint"] = region_hint
        if normalized_value is not None:
            values["normalized_value"] = normalized_value
        if not values:
            return
        await self.session.execute(update(SelectorTable).where(SelectorTable.entity_id == entity_id).values(**values))

    async def get_profile(self, entity_id: str) -> EntityProfile | None:
        """Assemble the aggregate dossier for one entity."""
        entity = await self.get_entity(entity_id)
        if entity is None:
            return None

        detail = await self._detail_dict(entity)

        prov_case = provenance_case().label("provenance")
        counts_result = await self.session.execute(
            select(prov_case, func.count(MentionTable.id))
            .where(MentionTable.entity_id == entity_id)
            .group_by(prov_case)
        )
        mention_counts = {str(k): v for k, v in counts_result.all()}

        # The headline "Mentions" number: distinct files where the entity is
        # named in document text (NER). Header From/To/Cc are relationships, not
        # mentions; selector hits show under Selectors.
        file_count = (
            await self.session.execute(
                select(func.count(func.distinct(MentionTable.file_id))).where(
                    MentionTable.entity_id == entity_id,
                    MentionTable.file_id.is_not(None),
                    provenance_case() == MentionProvenance.TEXT.value,
                )
            )
        ).scalar_one()

        top_mentions_result = await self.session.execute(
            select(MentionTable)
            .where(MentionTable.entity_id == entity_id)
            .order_by(desc(MentionTable.date_created))
            .limit(5)
        )
        from cipher.schemas.graph.mention import Mention

        top_mentions = [Mention.model_validate(m) for m in top_mentions_result.scalars().all()]

        related_preview = await self.list_related(
            entity_id,
            RelatedEntitySearchParameters(sort=RelatedEntitySort.WEIGHT, limit=8, page=1),
        )
        selectors_preview = await self.list_related(
            entity_id,
            RelatedEntitySearchParameters(
                entity_type=EntityType.SELECTOR, sort=RelatedEntitySort.NAME, limit=12, page=1
            ),
        )
        selectors = [n.entity for n in selectors_preview.data]
        selector_mentions = await self._selector_mention_counts(selectors)

        face_ids: list[str] = []
        if entity.person_id:
            faces_result = await self.session.execute(
                select(FaceTable.id).where(FaceTable.person_id == entity.person_id)
            )
            face_ids = list(faces_result.scalars().all())

        return EntityProfile(
            entity=entity,
            detail=detail,
            selectors=selectors,
            selector_mentions=selector_mentions,
            mention_counts=mention_counts,
            file_count=file_count,
            related_entities=related_preview.data,
            related_total=related_preview.total,
            selector_total=selectors_preview.total,
            top_mentions=top_mentions,
            face_ids=face_ids,
        )

    async def _selector_mention_counts(self, selectors: list[EntitySummary]) -> list[SelectorMention]:
        """For each linked selector, count mentions sharing its normalized value (any dataset, resolved or not)."""
        if not selectors:
            return []
        rows = (
            await self.session.execute(
                select(
                    SelectorTable.entity_id,
                    SelectorTable.selector_type,
                    SelectorTable.selector_subtype,
                    SelectorTable.normalized_value,
                ).where(SelectorTable.entity_id.in_([s.id for s in selectors]))
            )
        ).all()
        values = [r.normalized_value for r in rows if r.normalized_value]
        by_value: dict[str, dict] = {}
        if values:
            is_from = or_(
                MentionTable.field_path.like("header.from%"),
                MentionTable.field_path.like("header.sender%"),
            )
            is_to = or_(
                MentionTable.field_path.like("header.to%"),
                MentionTable.field_path.like("header.cc%"),
                MentionTable.field_path.like("header.bcc%"),
            )
            prov = provenance_case()
            count_rows = (
                await self.session.execute(
                    select(
                        MentionTable.normalized_value.label("value"),
                        func.count(MentionTable.id).label("mention_count"),
                        func.count(distinct(case((is_from, MentionTable.file_id)))).label("sent_files"),
                        func.count(distinct(case((is_to, MentionTable.file_id)))).label("received_files"),
                        func.count(case((prov == MentionProvenance.TEXT.value, MentionTable.id))).label("text_count"),
                        func.count(case((prov == MentionProvenance.PATTERN.value, MentionTable.id))).label(
                            "pattern_count"
                        ),
                    )
                    .where(MentionTable.normalized_value.in_(values))
                    .group_by(MentionTable.normalized_value)
                )
            ).all()
            by_value = {
                r.value: {
                    "mention_count": r.mention_count,
                    "sent_count": r.sent_files,
                    "received_count": r.received_files,
                    "text_count": r.text_count,
                    "pattern_count": r.pattern_count,
                }
                for r in count_rows
            }
        return [
            SelectorMention(
                entity_id=r.entity_id,
                selector_type=r.selector_type,
                selector_subtype=r.selector_subtype,
                normalized_value=r.normalized_value,
                **by_value.get(r.normalized_value, {}),
            )
            for r in rows
        ]

    async def _detail_dict(self, entity: Entity) -> dict | None:
        if entity.entity_type == EntityType.PERSON and entity.person_id:
            result = await self.session.execute(select(PersonTable).where(PersonTable.id == entity.person_id))
            row = result.scalar_one_or_none()
        else:
            detail_table = _DETAIL_TABLE.get(entity.entity_type)
            if detail_table is None:
                return None
            result = await self.session.execute(
                select(detail_table).where(_detail_key(entity.entity_type) == entity.id)
            )
            row = result.scalar_one_or_none()
        if row is None:
            return None
        detail = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        if entity.entity_type == EntityType.LOCATION:
            geom = detail.pop("geom", None)
            detail["geo_json"] = geom_to_geojson(geom).model_dump(mode="json") if geom is not None else None
        return detail

    async def _related_entities(self, entity_id: str) -> list[RelatedEntity]:
        out_stmt = (
            select(
                EntityRelationshipTable.relationship_type,
                EntityRelationshipTable.attributes,
                EntityTable,
            )
            .join(EntityTable, EntityTable.id == EntityRelationshipTable.dst_entity_id)
            .where(
                EntityRelationshipTable.src_entity_id == entity_id,
                EntityRelationshipTable.relationship_type.notin_([t.value for t in LOW_SIGNAL_RELATIONSHIPS]),
            )
            .limit(50)
        )
        in_stmt = (
            select(
                EntityRelationshipTable.relationship_type,
                EntityRelationshipTable.attributes,
                EntityTable,
            )
            .join(EntityTable, EntityTable.id == EntityRelationshipTable.src_entity_id)
            .where(
                EntityRelationshipTable.dst_entity_id == entity_id,
                EntityRelationshipTable.relationship_type.notin_([t.value for t in LOW_SIGNAL_RELATIONSHIPS]),
            )
            .limit(50)
        )
        out_rows = (await self.session.execute(out_stmt)).all()
        in_rows = (await self.session.execute(in_stmt)).all()
        related = [
            RelatedEntity(
                relationship_type=rt,
                direction="out",
                attributes=attrs or {},
                entity=EntitySummary.model_validate(e),
            )
            for rt, attrs, e in out_rows
        ]
        related += [
            RelatedEntity(
                relationship_type=rt,
                direction="in",
                attributes=attrs or {},
                entity=EntitySummary.model_validate(e),
            )
            for rt, attrs, e in in_rows
        ]
        return related

    async def list_related(
        self, entity_id: str, params: RelatedEntitySearchParameters
    ) -> PaginatedRelatedEntitiesResponse:
        """Paginated neighbours of an entity, each with its connecting edge.

        Unions the outbound and inbound legs so an edge surfaces regardless of which
        side this entity sits on -- undirected ones (e.g. `family_of`, stored
        with a canonical endpoint order) and both directions of `emailed`.
        """
        rel = EntityRelationshipTable
        low_signal = list(LOW_SIGNAL_RELATIONSHIPS)

        def _leg(neighbour_col, anchor_col, direction: str):
            stmt = select(
                neighbour_col.label("neighbour_id"),
                rel.relationship_type.label("relationship_type"),
                rel.attributes.label("attributes"),
                rel.weight.label("weight"),
                rel.date_created.label("date_created"),
                literal(direction).label("direction"),
            ).where(anchor_col == entity_id, rel.relationship_type.notin_(low_signal))
            if params.relationship_type is not None:
                stmt = stmt.where(rel.relationship_type == params.relationship_type)
            return stmt

        legs = []
        if params.direction in ("both", "out"):
            legs.append(_leg(rel.dst_entity_id, rel.src_entity_id, "out"))
        if params.direction in ("both", "in"):
            legs.append(_leg(rel.src_entity_id, rel.dst_entity_id, "in"))
        union_stmt = legs[0] if len(legs) == 1 else legs[0].union_all(*legs[1:])
        edges = union_stmt.subquery("edges")

        joined = select(
            edges.c.neighbour_id,
            edges.c.relationship_type,
            edges.c.attributes,
            edges.c.weight,
            edges.c.date_created,
            edges.c.direction,
            EntityTable,
        ).join(EntityTable, EntityTable.id == edges.c.neighbour_id)
        if params.entity_type is not None:
            joined = joined.where(EntityTable.entity_type == params.entity_type)

        total = (await self.session.execute(select(func.count()).select_from(joined.subquery()))).scalar_one()

        if params.sort == RelatedEntitySort.WEIGHT:
            joined = joined.order_by(desc(func.coalesce(edges.c.weight, 0.0)), asc(EntityTable.display_name_normalized))
        elif params.sort == RelatedEntitySort.RECENT:
            joined = joined.order_by(desc(edges.c.date_created))
        else:
            joined = joined.order_by(asc(EntityTable.display_name_normalized))
        joined = joined.offset((params.page - 1) * params.limit).limit(params.limit)

        rows = (await self.session.execute(joined)).all()
        neighbours = [
            RelatedEntity(
                relationship_type=self._coerce_relationship_type(row.relationship_type),
                direction=row.direction,
                attributes=row.attributes or {},
                entity=EntitySummary.model_validate(row[-1]),
                weight=int(row.weight) if row.weight is not None else None,
            )
            for row in rows
        ]

        selector_neighbours = [n.entity for n in neighbours if n.entity.entity_type == EntityType.SELECTOR]
        if selector_neighbours:
            detail = {c.entity_id: c for c in await self._selector_mention_counts(selector_neighbours)}
            for n in neighbours:
                match = detail.get(n.entity.id)
                if match is not None:
                    n.mention_count = match.mention_count
                    n.selector_type = match.selector_type
                    n.selector_subtype = match.selector_subtype
                    n.normalized_value = match.normalized_value

        return PaginatedRelatedEntitiesResponse(total=total, page=params.page, limit=params.limit, data=neighbours)

    @staticmethod
    def _coerce_relationship_type(value) -> RelationshipType:
        """A unioned subquery drops the Enum type, so the raw stored name comes back."""
        if isinstance(value, RelationshipType):
            return value
        try:
            return RelationshipType(value)
        except ValueError:
            return RelationshipType[value]
