from sqlalchemy import and_, asc, delete, desc, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.geo import geojson_to_geom, geom_to_geojson, point_to_geom
from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.location import LocationTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.organization import OrganizationTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.datastores.postgres.tables.selector import SelectorTable
from cipher.datastores.postgres.utils import normalize_name, strip_null_bytes
from cipher.schemas._base.common import SortOrder
from cipher.schemas.graph.entity import (
    Entity,
    EntityCreate,
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
from cipher.schemas.graph.location import LocationCreate, LocationUpdate
from cipher.schemas.graph.ontology import (
    LOW_SIGNAL_RELATIONSHIPS,
    EntitySource,
    EntityType,
    RelationshipType,
    SelectorKind,
)
from cipher.schemas.graph.organization import OrganizationCreate, OrganizationUpdate
from cipher.schemas.graph.selector import Selector, SelectorCreate, SelectorUpdate
from cipher.schemas.identity.person import Person

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
    ) -> Entity:
        """Create an entity node plus its type-specific detail row in one transaction."""
        values = strip_null_bytes(entity.model_dump(by_alias=False))
        values["display_name_normalized"] = normalize_name(entity.display_name)

        row = EntityTable(**values)
        self.session.add(row)
        await self.session.flush()

        detail_table = _DETAIL_TABLE.get(entity.entity_type)
        if detail is not None and detail_table is not None:
            detail_values = strip_null_bytes(detail.model_dump(by_alias=False))
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
                row.location_id = row.id
            else:
                detail_values["entity_id"] = row.id
            self.session.add(detail_table(**detail_values))

        result = Entity.model_validate(row)
        await self.session.commit()
        return result

    async def upsert_person_entity(self, person: Person) -> Entity:
        """Create or refresh the knowledge-graph node that mirrors a person.

        The bridge node shares the person's id (``entity.id == person.id``) and
        is dataset-agnostic, so a person resolves to the same entity across every
        dataset they appear in. Idempotent -- safe to call on every person write.
        """
        display_name = person.name or "Unnamed Person"
        values = strip_null_bytes(
            {
                "id": person.id,
                "person_id": person.id,
                "entity_type": EntityType.PERSON,
                "dataset_id": None,
                "source": EntitySource.MANUAL,
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
        entity = Entity.model_validate(row)
        await self.session.commit()
        return entity

    async def delete_person_entity(self, person_id: str) -> bool:
        """Drop the bridge node for a person (mentions/edges null out per their FKs)."""
        result = await self.session.execute(delete(EntityTable).where(EntityTable.id == person_id))
        await self.session.commit()
        return bool(result.rowcount)

    async def get_entity(self, entity_id: str) -> Entity | None:
        """Retrieve an entity node by ID."""
        result = await self.session.execute(select(EntityTable).where(EntityTable.id == entity_id))
        row = result.scalar_one_or_none()
        return Entity.model_validate(row) if row else None

    async def update_entity(self, entity_id: str, data: EntityUpdate) -> Entity | None:
        """Patch an entity node."""
        patch = data.model_dump(exclude_unset=True, by_alias=False)
        if "display_name" in patch and patch["display_name"] is not None:
            patch["display_name_normalized"] = normalize_name(patch["display_name"])
        if not patch:
            return await self.get_entity(entity_id)
        stmt = update(EntityTable).where(EntityTable.id == entity_id).values(**patch).returning(EntityTable)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
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
        """Delete an entity node (detail rows, mentions, and edges cascade or null out)."""
        result = await self.session.execute(delete(EntityTable).where(EntityTable.id == entity_id))
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

    async def list_entities(self, request: EntitySearchParameters) -> PaginatedEntitiesResponse:
        """List/filter entity nodes with pagination and sorting."""
        where = []
        if request.dataset_id:
            # Dataset-scoped rows, plus dataset-agnostic bridge nodes (person
            # entities have dataset_id NULL) that are actually mentioned in this
            # dataset -- otherwise a person who appears all over `rag` is
            # invisible on `rag`'s entity list.
            where.append(
                or_(
                    EntityTable.dataset_id == request.dataset_id,
                    and_(
                        EntityTable.dataset_id.is_(None),
                        EntityTable.id.in_(
                            select(MentionTable.entity_id).where(MentionTable.dataset_id == request.dataset_id)
                        ),
                    ),
                )
            )
        if request.entity_type:
            where.append(EntityTable.entity_type == request.entity_type)
        if request.is_verified is not None:
            where.append(EntityTable.is_verified == request.is_verified)
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
        if request.selector_kind:
            where.append(
                EntityTable.id.in_(
                    select(SelectorTable.entity_id).where(SelectorTable.selector_kind == request.selector_kind)
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
        if request.org_type:
            where.append(
                EntityTable.id.in_(
                    select(OrganizationTable.entity_id).where(OrganizationTable.org_type.ilike(request.org_type))
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

        sort_column = {
            EntitySortField.DISPLAY_NAME: EntityTable.display_name_normalized,
            EntitySortField.DATE_CREATED: EntityTable.date_created,
            EntitySortField.DATE_UPDATED: EntityTable.date_updated,
        }[request.sort_by]
        order = desc(sort_column) if request.sort_order == SortOrder.DESC else asc(sort_column)

        stmt = (
            select(EntityTable)
            .where(*where)
            .order_by(order)
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )
        result = await self.session.execute(stmt)
        data = [Entity.model_validate(r) for r in result.scalars().all()]
        return PaginatedEntitiesResponse(total=total, page=request.page, limit=request.limit, data=data)

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
        dataset_id: str,
        query: str,
        limit: int = 10,
        entity_type: EntityType | None = None,
    ) -> list[EntitySearchResult]:
        """Trigram fuzzy search on the normalized display name."""
        normalized = normalize_name(query)
        score = func.similarity(EntityTable.display_name_normalized, normalized)
        where = [
            or_(
                EntityTable.dataset_id == dataset_id,
                and_(
                    EntityTable.dataset_id.is_(None),
                    EntityTable.id.in_(
                        select(MentionTable.entity_id).where(MentionTable.dataset_id == dataset_id)
                    ),
                ),
            ),
            score >= _NAME_TRGM_FLOOR,
        ]
        if entity_type:
            where.append(EntityTable.entity_type == entity_type)

        stmt = select(EntityTable, score.label("score")).where(*where).order_by(desc("score")).limit(limit)
        result = await self.session.execute(stmt)
        return [
            EntitySearchResult(
                **EntitySummary.model_validate(row).model_dump(),
                match_reason="name trigram",
                score=max(0.0, min(1.0, float(value))),
            )
            for row, value in result.all()
        ]

    async def search_by_selector(
        self, *, dataset_id: str, normalized_value: str, selector_kind: SelectorKind | None = None
    ) -> Entity | None:
        """Exact lookup of the entity owning a normalized selector value."""
        where = [
            SelectorTable.dataset_id == dataset_id,
            SelectorTable.normalized_value == normalized_value,
        ]
        if selector_kind:
            where.append(SelectorTable.selector_kind == selector_kind)
        stmt = select(EntityTable).join(SelectorTable, SelectorTable.entity_id == EntityTable.id).where(*where)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return Entity.model_validate(row) if row else None

    async def get_or_create_selector(
        self,
        *,
        dataset_id: str,
        selector_kind: SelectorKind,
        raw_value: str,
        normalized_value: str,
        region_hint: str | None = None,
        display_name: str | None = None,
    ) -> tuple[Entity, bool]:
        """Return the entity for a normalized selector value, creating it if absent.

        Returns (entity, created).
        """
        existing = await self.search_by_selector(
            dataset_id=dataset_id, normalized_value=normalized_value, selector_kind=selector_kind
        )
        if existing:
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
                selector_kind=selector_kind,
                raw_value=raw_value,
                normalized_value=normalized_value,
                region_hint=region_hint,
            ),
        )
        return entity, True

    async def merge_entities(self, *, canonical_id: str, provisional_id: str) -> None:
        """Move all mentions and edges from a provisional entity onto the canonical one, then delete it."""
        await self.session.execute(
            update(MentionTable).where(MentionTable.entity_id == provisional_id).values(entity_id=canonical_id)
        )
        await self.session.execute(
            update(EntityRelationshipTable)
            .where(EntityRelationshipTable.src_entity_id == provisional_id)
            .values(src_entity_id=canonical_id)
        )
        await self.session.execute(
            update(EntityRelationshipTable)
            .where(EntityRelationshipTable.dst_entity_id == provisional_id)
            .values(dst_entity_id=canonical_id)
        )
        await self.session.execute(delete(EntityTable).where(EntityTable.id == provisional_id))
        await self.session.commit()

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
        if patch:
            await self.session.execute(
                update(detail_table).where(_detail_key(entity.entity_type) == entity_id).values(**patch)
            )
            await self.session.commit()
        return await self._detail_dict(entity)

    async def get_selector_detail(self, entity_id: str) -> Selector | None:
        """Fetch the selector detail row for a selector entity."""
        result = await self.session.execute(select(SelectorTable).where(SelectorTable.entity_id == entity_id))
        row = result.scalar_one_or_none()
        return Selector.model_validate(row) if row else None

    async def get_profile(self, entity_id: str) -> EntityProfile | None:
        """Assemble the aggregate dossier for one entity."""
        entity = await self.get_entity(entity_id)
        if entity is None:
            return None

        detail = await self._detail_dict(entity)

        counts_result = await self.session.execute(
            select(MentionTable.mentioned_type, func.count(MentionTable.id))
            .where(MentionTable.entity_id == entity_id)
            .group_by(MentionTable.mentioned_type)
        )
        mention_counts = {str(k): v for k, v in counts_result.all()}

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
                    SelectorTable.selector_kind,
                    SelectorTable.normalized_value,
                ).where(SelectorTable.entity_id.in_([s.id for s in selectors]))
            )
        ).all()
        values = [r.normalized_value for r in rows if r.normalized_value]
        counts: dict[str, int] = {}
        if values:
            count_rows = (
                await self.session.execute(
                    select(MentionTable.normalized_value, func.count(MentionTable.id))
                    .where(MentionTable.normalized_value.in_(values))
                    .group_by(MentionTable.normalized_value)
                )
            ).all()
            counts = {value: count for value, count in count_rows}
        return [
            SelectorMention(
                entity_id=r.entity_id,
                selector_kind=r.selector_kind,
                normalized_value=r.normalized_value,
                mention_count=counts.get(r.normalized_value, 0),
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

        Unions the outbound and inbound legs so an undirected edge (e.g.
        `communicates_with`, stored with a canonical endpoint order) surfaces
        regardless of which side this entity sits on.
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

        total = (
            await self.session.execute(select(func.count()).select_from(joined.subquery()))
        ).scalar_one()

        if params.sort == RelatedEntitySort.WEIGHT:
            joined = joined.order_by(
                desc(func.coalesce(edges.c.weight, 0.0)), asc(EntityTable.display_name_normalized)
            )
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
            detail = {
                c.entity_id: c for c in await self._selector_mention_counts(selector_neighbours)
            }
            for n in neighbours:
                match = detail.get(n.entity.id)
                if match is not None:
                    n.mention_count = match.mention_count
                    n.selector_kind = match.selector_kind
                    n.normalized_value = match.normalized_value

        return PaginatedRelatedEntitiesResponse(
            total=total, page=params.page, limit=params.limit, data=neighbours
        )

    @staticmethod
    def _coerce_relationship_type(value) -> RelationshipType:
        """A unioned subquery drops the Enum type, so the raw stored name comes back."""
        if isinstance(value, RelationshipType):
            return value
        try:
            return RelationshipType(value)
        except ValueError:
            return RelationshipType[value]
