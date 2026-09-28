import bisect

from sqlalchemy import asc, case, delete, desc, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.utils import strip_null_bytes
from cipher.schemas._base.common import SortOrder
from cipher.schemas.graph.mention import (
    Mention,
    MentionCreate,
    MentionedType,
    MentionProvenance,
    MentionSearchParameters,
    MentionUpdate,
    PaginatedMentionsResponse,
)
from cipher.schemas.graph.ontology import EntityType


def provenance_case():
    """SQL expression mirroring `schemas.graph.mention.mention_provenance` (first match wins)."""
    return case(
        (MentionTable.field_path.like("header.%"), MentionProvenance.EMAIL_HEADER.value),
        (MentionTable.mentioned_type == MentionedType.IMAGE, MentionProvenance.IMAGE.value),
        (MentionTable.bounding_box.is_not(None), MentionProvenance.IMAGE.value),
        (MentionTable.mentioned_type == MentionedType.STRUCTURED_FIELD, MentionProvenance.METADATA.value),
        (MentionTable.extractor == "selectors", MentionProvenance.PATTERN.value),
        else_=MentionProvenance.TEXT.value,
    )


class PostgresMentionRepository:
    """Postgres datastore for named-entity mentions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def entity_rows_for_chunk_sync(self, *, dataset_id: str) -> list[dict]:
        """Every text-anchored mention in a dataset, flat, for `sync-chunk-entities`.

        Only mentions with a real char offset (text/pattern extraction, not
        header/metadata) -- those are the ones that land inside a chunk span.
        """
        rows = (
            await self.session.execute(
                select(
                    MentionTable.file_id,
                    MentionTable.start_offset,
                    MentionTable.entity_id,
                    MentionTable.entity_type,
                    MentionTable.selector_type,
                    MentionTable.selector_subtype,
                ).where(
                    MentionTable.dataset_id == dataset_id,
                    MentionTable.file_id.is_not(None),
                    MentionTable.start_offset.is_not(None),
                )
            )
        ).all()
        return [
            {
                "file_id": r.file_id,
                "start_offset": r.start_offset,
                "entity_id": r.entity_id,
                "entity_type": str(r.entity_type) if r.entity_type is not None else None,
                "selector_type": str(r.selector_type) if r.selector_type is not None else None,
                "selector_subtype": str(r.selector_subtype) if r.selector_subtype is not None else None,
            }
            for r in rows
        ]

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

    async def _assign_chunk_ids(self, mentions: list[MentionCreate]) -> None:
        """Materialize the chunk<->mention join: set `chunk_id` on text-anchored mentions.

        For each distinct `file_id`, one query for the file's chunk spans (through
        `duplicate_file_ids`), then bisect each mention's `start_offset` into a
        chunk. `chunk` rows exist regardless of retrieval backend -- the postgres
        backend's rows carry the searchable text/embedding, the elasticsearch
        backend's are identity+span only (`upsert_chunk_spans`) -- so this is
        backend-agnostic. No-op (chunk_id stays null, backfillable) only for a
        file that hasn't been embedded yet.
        """
        pending: dict[str, list[MentionCreate]] = {}
        for m in mentions:
            if m.chunk_id is None and m.file_id and m.start_offset is not None:
                pending.setdefault(m.file_id, []).append(m)
        for file_id, group in pending.items():
            rows = (
                await self.session.execute(
                    text(
                        "SELECT id, start_offset, end_offset FROM chunk "
                        "WHERE file_id = :f OR duplicate_file_ids @> to_jsonb(cast(:f as text)) "
                        "ORDER BY start_offset"
                    ),
                    {"f": file_id},
                )
            ).all()
            if not rows:
                continue
            starts = [r.start_offset for r in rows]
            ends = [r.end_offset for r in rows]
            for m in group:
                i = bisect.bisect_right(starts, m.start_offset) - 1
                if 0 <= i < len(starts) and starts[i] <= m.start_offset < ends[i]:
                    m.chunk_id = rows[i].id

    async def backfill_chunk_ids(self, *, dataset_id: str) -> int:
        """Set `chunk_id` on a dataset's text-anchored mentions that don't have one.

        Set-based: one UPDATE joining `mention` to `chunk` on file + offset
        containment (through `duplicate_file_ids`). For datasets extracted before
        the extract-time assignment, or re-run after a re-embed. Returns rows set.
        """
        res = await self.session.execute(
            text(
                "UPDATE mention m SET chunk_id = c.id "
                "FROM chunk c "
                "WHERE m.dataset_id = :ds AND m.chunk_id IS NULL AND m.start_offset IS NOT NULL "
                "  AND (c.file_id = m.file_id OR c.duplicate_file_ids @> to_jsonb(m.file_id)) "
                "  AND m.start_offset >= c.start_offset AND m.start_offset < c.end_offset"
            ),
            {"ds": dataset_id},
        )
        await self.session.commit()
        return res.rowcount or 0

    async def chunk_ids_for_filter(
        self,
        *,
        dataset_id: str,
        entity_ids: list[str] | None = None,
        entity_types: list[str] | None = None,
        selector_types: list[str] | None = None,
        selector_subtypes: list[str] | None = None,
        graph_entity_ids: list[str] | None = None,
        limit: int = 10_000,
    ) -> list[str] | None:
        """Chunk ids whose mentions satisfy an entity/selector/graph filter.

        For a retrieval backend (elasticsearch) that needs a materialized id list
        to filter on, rather than the postgres adapter's live `EXISTS` join.
        `entity_ids` is AND (every listed entity must be mentioned in the chunk);
        `entity_types` / `selector_types` / `selector_subtypes` / `graph_entity_ids`
        are OR'd together. Returns `None` when no filter was requested (caller
        should not filter); an empty list is a real "nothing matches".

        Bounded by `limit` -- fine for a specific entity or a graph expansion
        (typically tens to low-thousands of chunks); a broad category filter
        (e.g. every `selector_type=email` chunk in a large dataset) can hit the
        cap and under-filter. Denormalizing broad categories onto the chunk doc
        is the documented upgrade path if that proves to matter in practice.
        """
        if not any([entity_ids, entity_types, selector_types, selector_subtypes, graph_entity_ids]):
            return None

        where = ["dataset_id = :ds", "chunk_id IS NOT NULL"]
        params: dict = {"ds": dataset_id, "limit": limit}

        or_parts = []
        if entity_types:
            params["entity_types"] = [t.upper() for t in entity_types]
            or_parts.append("entity_type = ANY(:entity_types)")
        if selector_types:
            params["selector_types"] = [t.upper() for t in selector_types]
            or_parts.append("selector_type = ANY(:selector_types)")
        if selector_subtypes:
            params["selector_subtypes"] = [t.upper() for t in selector_subtypes]
            or_parts.append("selector_subtype = ANY(:selector_subtypes)")
        if graph_entity_ids:
            params["graph_ids"] = graph_entity_ids
            or_parts.append("entity_id = ANY(:graph_ids)")
        if or_parts:
            where.append("(" + " OR ".join(or_parts) + ")")

        if entity_ids:
            params["entity_ids"] = entity_ids
            params["entity_ids_len"] = len(entity_ids)
            sql = (
                "SELECT chunk_id FROM mention WHERE "
                + " AND ".join([*where, "entity_id = ANY(:entity_ids)"])
                + " GROUP BY chunk_id HAVING count(DISTINCT entity_id) = :entity_ids_len LIMIT :limit"
            )
        else:
            sql = "SELECT DISTINCT chunk_id FROM mention WHERE " + " AND ".join(where) + " LIMIT :limit"

        rows = (await self.session.execute(text(sql), params)).all()
        return [r[0] for r in rows]

    async def add_mentions_batch(self, mentions: list[MentionCreate]) -> int:
        """Bulk-insert mentions, returning the number written."""
        if not mentions:
            return 0
        await self._assign_chunk_ids(mentions)
        self.session.add_all([MentionTable(**strip_null_bytes(m.model_dump(by_alias=False))) for m in mentions])
        await self.session.commit()
        return len(mentions)

    async def add_mentions_returning(self, mentions: list[MentionCreate]) -> list[Mention]:
        """Bulk-insert mentions and return the persisted rows (with ids assigned).

        For callers that need the new mention ids straight away -- e.g. to link
        an extractor's relation spans to the mention rows they connect.
        """
        if not mentions:
            return []
        await self._assign_chunk_ids(mentions)
        rows = [MentionTable(**strip_null_bytes(m.model_dump(by_alias=False))) for m in mentions]
        self.session.add_all(rows)
        await self.session.flush()
        out = [Mention.model_validate(r) for r in rows]
        await self.session.commit()
        return out

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
        if request.provenance:
            where.append(provenance_case() == request.provenance.value)
        if request.entity_type:
            where.append(MentionTable.entity_type == request.entity_type)
        if request.entity_attribute:
            where.append(MentionTable.entity_attribute == request.entity_attribute)
        if request.selector_type:
            where.append(MentionTable.selector_type == request.selector_type)
        if request.selector_subtype:
            where.append(MentionTable.selector_subtype == request.selector_subtype)
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
