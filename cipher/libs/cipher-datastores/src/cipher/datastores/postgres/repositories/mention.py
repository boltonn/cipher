from sqlalchemy import asc, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.utils import strip_null_bytes
from cipher.schemas._base.common import SortOrder
from cipher.schemas.graph.mention import (
    Mention,
    MentionCreate,
    MentionedType,
    MentionSearchParameters,
    MentionUpdate,
    PaginatedMentionsResponse,
)
from cipher.schemas.graph.ontology import EntityType


class PostgresMentionRepository:
    """Postgres datastore for named-entity mentions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the mention table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(MentionTable.metadata.create_all)

    async def get_count(self) -> int:
        """Get total count of mentions."""
        result = await self.session.execute(select(func.count(MentionTable.id)))
        return result.scalar_one()

    async def add_mention(self, mention: MentionCreate) -> Mention:
        """Insert a single mention."""
        row = MentionTable(**strip_null_bytes(mention.model_dump(by_alias=False)))
        self.session.add(row)
        result = Mention.model_validate(row)
        await self.session.commit()
        return result

    async def add_mentions_batch(self, mentions: list[MentionCreate]) -> int:
        """Bulk-insert mentions, returning the number written."""
        if not mentions:
            return 0
        self.session.add_all([MentionTable(**strip_null_bytes(m.model_dump(by_alias=False))) for m in mentions])
        await self.session.commit()
        return len(mentions)

    async def get_mention(self, mention_id: str) -> Mention | None:
        """Retrieve a mention by ID."""
        result = await self.session.execute(select(MentionTable).where(MentionTable.id == mention_id))
        row = result.scalar_one_or_none()
        return Mention.model_validate(row) if row else None

    async def list_mentions(self, request: MentionSearchParameters) -> PaginatedMentionsResponse:
        """Query mentions with filtering, pagination, and sorting."""
        where = []
        if request.entity_id:
            where.append(MentionTable.entity_id == request.entity_id)
        if request.file_id:
            where.append(MentionTable.file_id == request.file_id)
        if request.dataset_id:
            where.append(MentionTable.dataset_id == request.dataset_id)
        if request.mentioned_type:
            where.append(MentionTable.mentioned_type == request.mentioned_type)
        if request.entity_type:
            where.append(MentionTable.entity_type == request.entity_type)
        if request.entity_attribute:
            where.append(MentionTable.entity_attribute == request.entity_attribute)
        if request.selector_kind:
            where.append(MentionTable.selector_kind == request.selector_kind)
        if request.normalized_value:
            where.append(MentionTable.normalized_value == request.normalized_value)
        if request.resolved is True:
            where.append(MentionTable.entity_id.is_not(None))
        elif request.resolved is False:
            where.append(MentionTable.entity_id.is_(None))

        count_result = await self.session.execute(select(func.count(MentionTable.id)).where(*where))
        total = count_result.scalar_one()

        sort_column = MentionTable.date_created
        order = desc(sort_column) if request.sort_order == SortOrder.DESC else asc(sort_column)
        stmt = (
            select(MentionTable)
            .where(*where)
            .order_by(order)
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )
        result = await self.session.execute(stmt)
        data = [Mention.model_validate(m) for m in result.scalars().all()]
        return PaginatedMentionsResponse(total=total, page=request.page, limit=request.limit, data=data)

    async def get_unresolved_batch(self, *, dataset_id: str, limit: int = 200) -> list[Mention]:
        """Claim a batch of unresolved mentions for the resolution sweep."""
        stmt = (
            select(MentionTable)
            .where(MentionTable.dataset_id == dataset_id, MentionTable.entity_id.is_(None))
            .order_by(asc(MentionTable.date_created))
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        return [Mention.model_validate(m) for m in result.scalars().all()]

    async def attach_to_entity(self, mention_id: str, entity_id: str) -> None:
        """Resolve a mention to a canonical entity."""
        await self.session.execute(
            update(MentionTable).where(MentionTable.id == mention_id).values(entity_id=entity_id)
        )
        await self.session.commit()

    async def attach_many(self, mention_ids: list[str], entity_id: str) -> int:
        """Resolve a batch of mentions to one entity. Returns rows updated."""
        if not mention_ids:
            return 0
        result = await self.session.execute(
            update(MentionTable).where(MentionTable.id.in_(mention_ids)).values(entity_id=entity_id)
        )
        await self.session.commit()
        return result.rowcount or 0

    async def unresolved_name_groups(self, *, dataset_id: str, entity_types: list[EntityType]) -> list[dict]:
        """Group a dataset's unresolved `name` mentions by (entity_type, normalized_value).

        Includes untyped name mentions (`entity_type IS NULL`) -- an email-header
        display name whose person-vs-organization kind is unknown. The grouping
        key is the resolution blocking key. `from_structured` flags a group with
        at least one `structured_field` mention (e.g. an email header). Each
        dict: `entity_type` (may be None), `normalized_value`, `mention_ids`,
        `surface_texts`, `from_structured`.
        """
        stmt = (
            select(
                MentionTable.entity_type,
                MentionTable.normalized_value,
                func.array_agg(MentionTable.id).label("mention_ids"),
                func.array_agg(MentionTable.surface_text).label("surface_texts"),
                func.bool_or(MentionTable.mentioned_type == MentionedType.STRUCTURED_FIELD).label("from_structured"),
            )
            .where(
                MentionTable.dataset_id == dataset_id,
                MentionTable.entity_id.is_(None),
                or_(MentionTable.entity_type.in_(entity_types), MentionTable.entity_type.is_(None)),
                MentionTable.entity_attribute == "name",
                MentionTable.normalized_value.is_not(None),
            )
            .group_by(MentionTable.entity_type, MentionTable.normalized_value)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "entity_type": r.entity_type,
                "normalized_value": r.normalized_value,
                "mention_ids": list(r.mention_ids),
                "surface_texts": list(r.surface_texts),
                "from_structured": bool(r.from_structured),
            }
            for r in rows
        ]

    async def unresolved_name_group_page(
        self, *, dataset_id: str, query: str | None = None, limit: int = 25, page: int = 1
    ) -> dict:
        """Paginated distinct-name view of the review queue.

        One row per `normalized_value` of an unresolved `name` mention, with the
        most common surface form, how many mentions and files it spans, and one
        context snippet. Ordered by mention count (noisiest first). Returns
        `{total, page, limit, data}`.
        """
        where = [
            MentionTable.dataset_id == dataset_id,
            MentionTable.entity_id.is_(None),
            MentionTable.entity_attribute == "name",
            MentionTable.normalized_value.is_not(None),
        ]
        if query and query.strip():
            where.append(MentionTable.normalized_value.ilike(f"%{query.strip().lower()}%"))

        grouped = (
            select(
                MentionTable.normalized_value.label("normalized_value"),
                func.mode().within_group(MentionTable.surface_text).label("surface"),
                func.count(MentionTable.id).label("mention_count"),
                func.count(func.distinct(MentionTable.file_id)).label("file_count"),
                func.min(MentionTable.context).label("sample_context"),
            )
            .where(*where)
            .group_by(MentionTable.normalized_value)
        )

        total = (await self.session.execute(select(func.count()).select_from(grouped.subquery()))).scalar_one()

        rows = (
            await self.session.execute(
                grouped.order_by(desc("mention_count"), asc("normalized_value")).offset((page - 1) * limit).limit(limit)
            )
        ).all()
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "data": [
                {
                    "normalized_value": r.normalized_value,
                    "surface": r.surface,
                    "mention_count": r.mention_count,
                    "file_count": r.file_count,
                    "sample_context": r.sample_context,
                }
                for r in rows
            ],
        }

    async def attach_names(self, *, dataset_id: str, normalized_value: str, entity_id: str) -> int:
        """Resolve every unresolved `name` mention of one normalized value to an entity."""
        result = await self.session.execute(
            update(MentionTable)
            .where(
                MentionTable.dataset_id == dataset_id,
                MentionTable.entity_id.is_(None),
                MentionTable.entity_attribute == "name",
                MentionTable.normalized_value == normalized_value,
            )
            .values(entity_id=entity_id)
        )
        await self.session.commit()
        return result.rowcount or 0

    async def delete_names(self, *, dataset_id: str, normalized_value: str) -> int:
        """Discard every unresolved `name` mention of one normalized value (analyst says 'not an entity')."""
        result = await self.session.execute(
            delete(MentionTable).where(
                MentionTable.dataset_id == dataset_id,
                MentionTable.entity_id.is_(None),
                MentionTable.entity_attribute == "name",
                MentionTable.normalized_value == normalized_value,
            )
        )
        await self.session.commit()
        return result.rowcount or 0

    async def update_mention(self, mention_id: str, data: MentionUpdate) -> Mention | None:
        """Patch a mention (analyst relabel/correction)."""
        patch = strip_null_bytes(data.model_dump(exclude_unset=True, by_alias=False))
        if not patch:
            return await self.get_mention(mention_id)
        stmt = update(MentionTable).where(MentionTable.id == mention_id).values(**patch).returning(MentionTable)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        mention = Mention.model_validate(row) if row else None
        await self.session.commit()
        return mention

    async def delete_mention(self, mention_id: str) -> bool:
        """Delete a single mention by id."""
        result = await self.session.execute(delete(MentionTable).where(MentionTable.id == mention_id))
        await self.session.commit()
        return bool(result.rowcount)

    async def count_unresolved(self, dataset_id: str) -> int:
        """Count mentions still awaiting resolution in a dataset."""
        result = await self.session.execute(
            select(func.count(MentionTable.id)).where(
                MentionTable.dataset_id == dataset_id, MentionTable.entity_id.is_(None)
            )
        )
        return result.scalar_one()

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete all mentions for a dataset (used by reset-entities)."""
        result = await self.session.execute(delete(MentionTable).where(MentionTable.dataset_id == dataset_id))
        await self.session.commit()
        return result.rowcount or 0
