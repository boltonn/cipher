from sqlalchemy import asc, delete, desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.location import LocationTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.organization import OrganizationTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.datastores.postgres.tables.selector import SelectorTable
from cipher.datastores.postgres.utils import normalize_name, strip_null_bytes
from cipher.schemas.common import SortOrder
from cipher.schemas.entity import (
    Entity,
    EntityCreate,
    EntityProfile,
    EntitySearchParameters,
    EntitySearchResult,
    EntitySortField,
    EntitySummary,
    EntityUpdate,
    PaginatedEntitiesResponse,
    RelatedEntity,
)
from cipher.schemas.location import LocationCreate, LocationUpdate
from cipher.schemas.ontology import LOW_SIGNAL_RELATIONSHIPS, EntitySource, EntityType, SelectorKind
from cipher.schemas.organization import OrganizationCreate, OrganizationUpdate
from cipher.schemas.person import Person
from cipher.schemas.selector import Selector, SelectorCreate, SelectorUpdate

_DETAIL_TABLE = {
    EntityType.ORGANIZATION: OrganizationTable,
    EntityType.LOCATION: LocationTable,
    EntityType.SELECTOR: SelectorTable,
}

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

    async def list_entities(self, request: EntitySearchParameters) -> PaginatedEntitiesResponse:
        """List/filter entity nodes with pagination and sorting."""
        where = []
        if request.dataset_id:
            where.append(EntityTable.dataset_id == request.dataset_id)
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
                    EntityTable.id.in_(
                        select(LocationTable.entity_id).where(LocationTable.country.ilike(request.country))
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
            EntitySortField.DISPLAY_NAME: EntityTable.display_name,
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
        where = [EntityTable.dataset_id == dataset_id, score >= _NAME_TRGM_FLOOR]
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
        if patch:
            await self.session.execute(update(detail_table).where(detail_table.entity_id == entity_id).values(**patch))
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
        from cipher.schemas.mention import Mention

        top_mentions = [Mention.model_validate(m) for m in top_mentions_result.scalars().all()]

        related = await self._related_entities(entity_id)
        selectors = [r.entity for r in related if r.entity.entity_type == EntityType.SELECTOR]

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
            mention_counts=mention_counts,
            related_entities=related,
            top_mentions=top_mentions,
            face_ids=face_ids,
        )

    async def _detail_dict(self, entity: Entity) -> dict | None:
        if entity.entity_type == EntityType.PERSON and entity.person_id:
            result = await self.session.execute(select(PersonTable).where(PersonTable.id == entity.person_id))
            row = result.scalar_one_or_none()
        else:
            detail_table = _DETAIL_TABLE.get(entity.entity_type)
            if detail_table is None:
                return None
            result = await self.session.execute(select(detail_table).where(detail_table.entity_id == entity.id))
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return {c.name: getattr(row, c.name) for c in row.__table__.columns}

    async def _related_entities(self, entity_id: str) -> list[RelatedEntity]:
        out_stmt = (
            select(EntityRelationshipTable.relationship_type, EntityTable)
            .join(EntityTable, EntityTable.id == EntityRelationshipTable.dst_entity_id)
            .where(
                EntityRelationshipTable.src_entity_id == entity_id,
                EntityRelationshipTable.relationship_type.notin_([t.value for t in LOW_SIGNAL_RELATIONSHIPS]),
            )
            .limit(50)
        )
        in_stmt = (
            select(EntityRelationshipTable.relationship_type, EntityTable)
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
            RelatedEntity(relationship_type=rt, direction="out", entity=EntitySummary.model_validate(e))
            for rt, e in out_rows
        ]
        related += [
            RelatedEntity(relationship_type=rt, direction="in", entity=EntitySummary.model_validate(e))
            for rt, e in in_rows
        ]
        return related
