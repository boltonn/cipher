import bisect
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import asc, case, delete, desc, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.entity_match import EntityMatchTable
from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.utils import normalize_name, strip_null_bytes
from cipher.schemas._base.common import SortOrder
from cipher.schemas.content.email import EmailCountBucket, EmailCountGroupBy, EmailCountRequest, EmailCounts
from cipher.schemas.content.search import CorrespondenceFilters
from cipher.schemas.graph.entity_match import EntityMatchStatus
from cipher.schemas.graph.mention import (
    MANUAL_EXTRACTOR,
    Mention,
    MentionCreate,
    MentionedType,
    MentionProvenance,
    MentionSearchParameters,
    MentionUpdate,
    PaginatedMentionsResponse,
)
from cipher.schemas.graph.ontology import EntityType
from cipher.schemas.graph.selector import SelectorEvidence, SelectorOwner

# Changing any of these is a relabel: the mention becomes analyst-authored.
_LABEL_FIELDS = ("start_offset", "end_offset", "surface_text", "entity_type", "selector_type", "selector_subtype")


def provenance_case():
    """SQL expression mirroring `schemas.graph.mention.mention_provenance` (first match wins)."""
    return case(
        (MentionTable.field_path.like("header.%"), MentionProvenance.EMAIL_HEADER.value),
        (MentionTable.mentioned_type == MentionedType.IMAGE, MentionProvenance.IMAGE.value),
        # jsonb_typeof, not IS NOT NULL: rows written before `none_as_null` hold JSON `null`
        (func.jsonb_typeof(MentionTable.bounding_box) == "object", MentionProvenance.IMAGE.value),
        (MentionTable.mentioned_type == MentionedType.STRUCTURED_FIELD, MentionProvenance.METADATA.value),
        (MentionTable.extractor == "selectors", MentionProvenance.PATTERN.value),
        else_=MentionProvenance.TEXT.value,
    )


# `provenance_case` as raw SQL over alias `m`, for the text()-built queries.
_PROVENANCE_SQL = (
    "CASE WHEN m.field_path LIKE 'header.%' THEN 'email_header' "
    "WHEN m.mentioned_type = 'IMAGE' OR jsonb_typeof(m.bounding_box) = 'object' THEN 'image' "
    "WHEN m.mentioned_type = 'STRUCTURED_FIELD' THEN 'metadata' "
    "WHEN m.extractor = 'selectors' THEN 'pattern' ELSE 'text' END"
)


# ---- correspondence: email header mentions (`field_path` = header.from / header.to[i] / ...) ----

CONTENT_DATE_SQL = "coalesce(et.metadata->>'date_sent', et.metadata->>'date_content_created')"

_ROLE_PATHS = {
    "sender": "m.field_path IN ('header.from', 'header.sender')",
    "recipient": r"m.field_path ~ '^header\.(to|cc|bcc)\['",
    "participant": "m.field_path LIKE 'header.%'",
}
_PARTY_ROLE = {
    EmailCountGroupBy.SENDER: "sender",
    EmailCountGroupBy.RECIPIENT: "recipient",
    EmailCountGroupBy.CORRESPONDENT: "participant",
}
_PERIOD_LENGTH = {EmailCountGroupBy.YEAR: 4, EmailCountGroupBy.MONTH: 7, EmailCountGroupBy.DAY: 10}
_MAX_PERIODS = 1000


def _identity_sql(key: str) -> str:
    """An entity plus the email/phone/... selectors it `has_selector`."""
    return (
        f"SELECT cast(:{key} AS text) UNION SELECT r.dst_entity_id FROM entity_relationship r "
        f"WHERE r.src_entity_id = :{key} AND r.relationship_type = 'HAS_SELECTOR'"
    )


def correspondence_predicates(
    filters: CorrespondenceFilters, params: dict, *, file_column: str, date_column: str | None = None
) -> list[str]:
    """SQL predicates restricting `file_column` to files matching the correspondence filters.

    Uncorrelated `IN (subquery)` so they sit alongside a pg_search `@@@` or HNSW
    scan in the candidate stage. `date_column` (e.g. `chunk.date_content`) compares
    dates directly instead of through the extracted-text metadata.
    """
    predicates: list[str] = []
    for role, entity_ids in (
        ("sender", filters.sent_from),
        ("recipient", filters.sent_to),
        ("participant", filters.participants),
    ):
        keys = [f"{role}_{index}" for index in range(len(entity_ids or []))]
        params.update(zip(keys, entity_ids or [], strict=True))
        # sender / recipient: any of the ids (one person + their extra addresses);
        # participants: every id must be on the email ("between a and b").
        groups = [keys] if role != "participant" else [[key] for key in keys]
        for group in groups:
            if not group:
                continue
            identity = " UNION ".join(f"({_identity_sql(key)})" for key in group)
            predicates.append(
                f"{file_column} IN (SELECT m.file_id FROM mention m WHERE {_ROLE_PATHS[role]} "
                f"AND m.entity_id IN ({identity}))"
            )

    # The metadata path compares ISO strings (they sort like dates); a timestamptz column takes datetimes.
    def bound(day: date):
        return day.isoformat() if date_column is None else datetime.combine(day, time(), tzinfo=UTC)

    date_value = date_column or CONTENT_DATE_SQL
    date_conditions: list[str] = []
    if filters.date_from:
        params["date_from"] = bound(filters.date_from)
        date_conditions.append(f"{date_value} >= :date_from")
    if filters.date_to:
        params["date_before"] = bound(filters.date_to + timedelta(days=1))
        date_conditions.append(f"{date_value} < :date_before")
    if date_conditions and date_column:
        predicates.extend(date_conditions)
    elif date_conditions:
        predicates.append(
            f"{file_column} IN (SELECT et.file_id FROM extracted_text et WHERE {' AND '.join(date_conditions)})"
        )
    return predicates


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

    async def add_mention(self, mention: MentionCreate, *, reviewed_by: str | None = None) -> Mention:
        """Insert a single analyst-drawn mention, replacing any mentions its span overlaps."""
        await self._assign_chunk_ids([mention])
        row = MentionTable(**strip_null_bytes(mention.model_dump(by_alias=False)))
        self.session.add(row)
        await self.session.flush()
        await self._delete_overlapping(
            mentioned_type=mention.mentioned_type,
            mentioned_id=mention.mentioned_id,
            start_offset=mention.start_offset,
            end_offset=mention.end_offset,
            keep_mention_id=row.id,
        )
        await self._mark_corrected(
            mentioned_type=mention.mentioned_type, mentioned_id=mention.mentioned_id, reviewed_by=reviewed_by
        )
        result = Mention.model_validate(row)
        await self.session.commit()
        return result

    async def _delete_overlapping(
        self,
        *,
        mentioned_type: MentionedType,
        mentioned_id: str,
        start_offset: int | None,
        end_offset: int | None,
        keep_mention_id: str,
    ) -> None:
        """Delete the other mentions on the same source row whose span overlaps `[start_offset, end_offset)`."""
        if start_offset is None or end_offset is None:
            return
        await self.session.execute(
            delete(MentionTable).where(
                MentionTable.mentioned_type == mentioned_type,
                MentionTable.mentioned_id == mentioned_id,
                MentionTable.start_offset < end_offset,
                MentionTable.end_offset > start_offset,
                MentionTable.id != keep_mention_id,
            )
        )

    async def _mark_corrected(
        self, *, mentioned_type: MentionedType, mentioned_id: str, reviewed_by: str | None
    ) -> None:
        """Flag the text an analyst just corrected a mention in -- its mentions are now worth retraining on."""
        if mentioned_type != MentionedType.EXTRACTED_TEXT:
            return
        await self.session.execute(
            update(ExtractedTextTable)
            .where(ExtractedTextTable.id == mentioned_id)
            .values(
                is_mentions_corrected=True,
                mentions_reviewed_by=reviewed_by,
                date_last_updated=ExtractedTextTable.date_last_updated,
            )
        )

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
        # Two equality joins, not one `file_id = ... OR duplicate_file_ids @> ...`: the OR
        # defeats the index and turned a seconds-long update into a many-minute one.
        span = "AND m.start_offset >= c.start_offset AND m.start_offset < c.end_offset"
        unlinked = "m.dataset_id = :ds AND m.chunk_id IS NULL AND m.start_offset IS NOT NULL"
        own = await self.session.execute(
            text(
                f"UPDATE mention m SET chunk_id = c.id FROM chunk c WHERE {unlinked} AND c.file_id = m.file_id {span}"
            ),
            {"ds": dataset_id},
        )
        shared = await self.session.execute(
            text(
                "UPDATE mention m SET chunk_id = c.id "
                "FROM chunk c CROSS JOIN LATERAL jsonb_array_elements_text(c.duplicate_file_ids) AS d(file_id) "
                f"WHERE {unlinked} AND c.dataset_id = :ds AND d.file_id = m.file_id {span}"
            ),
            {"ds": dataset_id},
        )
        await self.session.commit()
        return (own.rowcount or 0) + (shared.rowcount or 0)

    async def chunk_ids_for_filter(
        self,
        *,
        dataset_id: str | None,
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

        where = ["chunk_id IS NOT NULL"]
        params: dict = {"limit": limit}
        if dataset_id:
            where.append("dataset_id = :ds")
            params["ds"] = dataset_id

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

    async def file_ids_for_values(
        self, *, dataset_id: str | None, values: list[str], provenance: list[MentionProvenance] | None = None
    ) -> list[str]:
        """Files with a mention of every one of `values` (by `normalized_value`, resolved or not).

        Each value also matches its folded-name form, so a typed "Nick B" finds the "nick b" name group.
        `provenance` limits which evidence counts -- body text vs email header vs metadata fields.
        """
        params: dict = {
            "raw": values,
            "folded": [normalize_name(value) for value in values],
            "n": len(set(values)),
        }
        dataset_filter = ""
        if dataset_id:
            dataset_filter = "AND m.dataset_id = :ds"
            params["ds"] = dataset_id
        if provenance:
            params["provenance"] = [p.value for p in provenance]
            dataset_filter += f" AND ({_PROVENANCE_SQL}) = ANY(cast(:provenance AS text[]))"
        rows = await self.session.execute(
            text(
                "SELECT m.file_id FROM mention m "
                "JOIN unnest(cast(:raw AS text[]), cast(:folded AS text[])) WITH ORDINALITY AS v(raw, folded, i) "
                "ON m.normalized_value IN (v.raw, v.folded) "
                f"WHERE m.file_id IS NOT NULL {dataset_filter} "
                "GROUP BY m.file_id HAVING count(DISTINCT v.raw) = :n"
            ),
            params,
        )
        return list(rows.scalars().all())

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
        if request.dataset_ids is not None:
            where.append(MentionTable.dataset_id.in_(request.dataset_ids))
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
        self,
        *,
        dataset_id: str,
        query: str | None = None,
        has_resolution: bool | None = None,
        entity_id: str | None = None,
        limit: int = 25,
        page: int = 1,
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
        if has_resolution is not None:
            # a pending name-group resolution (name -> entity) exists for this name
            pending = (
                select(EntityMatchTable.id)
                .where(
                    EntityMatchTable.dataset_id == dataset_id,
                    EntityMatchTable.mention_id.is_(None),
                    EntityMatchTable.normalized_value == MentionTable.normalized_value,
                    EntityMatchTable.status == EntityMatchStatus.PENDING,
                )
                .exists()
            )
            where.append(pending if has_resolution else ~pending)
        if entity_id:
            # only names with a pending resolution to this entity (its "N to resolve" badge)
            where.append(
                select(EntityMatchTable.id)
                .where(
                    EntityMatchTable.dataset_id == dataset_id,
                    EntityMatchTable.mention_id.is_(None),
                    EntityMatchTable.normalized_value == MentionTable.normalized_value,
                    EntityMatchTable.status == EntityMatchStatus.PENDING,
                    EntityMatchTable.entity_id == entity_id,
                )
                .exists()
            )

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

    async def delete_by_entity(self, entity_id: str) -> int:
        """Discard every mention resolved to one entity (analyst marks the entity invalid)."""
        result = await self.session.execute(delete(MentionTable).where(MentionTable.entity_id == entity_id))
        await self.session.commit()
        return result.rowcount or 0

    async def has_extractor_mentions(self, *, mentioned_id: str, extractor: str) -> bool:
        """Whether one extractor already wrote mentions for this evidence row (re-run guard)."""
        stmt = select(
            select(MentionTable.id)
            .where(MentionTable.mentioned_id == mentioned_id, MentionTable.extractor == extractor)
            .exists()
        )
        return bool((await self.session.execute(stmt)).scalar())

    async def update_mention(
        self, mention_id: str, data: MentionUpdate, *, reviewed_by: str | None = None
    ) -> Mention | None:
        """Patch a mention (analyst relabel/correction).

        A changed span or type makes it analyst-authored (`extractor = manual`) and flags its
        text as corrected; a moved span replaces any mentions it now overlaps.
        """
        patch = strip_null_bytes(data.model_dump(exclude_unset=True, by_alias=False))
        current = await self.get_mention(mention_id)
        if current is None or not patch:
            return current
        if any(field in patch and patch[field] != getattr(current, field) for field in _LABEL_FIELDS):
            patch |= {"extractor": MANUAL_EXTRACTOR, "extraction_model": None, "extraction_confidence": None}
            await self._mark_corrected(
                mentioned_type=current.mentioned_type, mentioned_id=current.mentioned_id, reviewed_by=reviewed_by
            )
        if "start_offset" in patch or "end_offset" in patch:
            span = {key: patch.get(key, getattr(current, key)) for key in ("start_offset", "end_offset")}
            moved = MentionCreate.model_validate({**current.model_dump(by_alias=False), **span, "chunk_id": None})
            await self._assign_chunk_ids([moved])
            patch["chunk_id"] = moved.chunk_id
            await self._delete_overlapping(
                mentioned_type=current.mentioned_type,
                mentioned_id=current.mentioned_id,
                keep_mention_id=mention_id,
                **span,
            )
        stmt = update(MentionTable).where(MentionTable.id == mention_id).values(**patch).returning(MentionTable)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        mention = Mention.model_validate(row) if row else None
        await self.session.commit()
        return mention

    async def delete_mention(self, mention_id: str, *, reviewed_by: str | None = None) -> bool:
        """Delete a single mention by id (analyst says it isn't one), flagging its text as corrected."""
        current = await self.get_mention(mention_id)
        if current is None:
            return False
        await self.session.execute(delete(MentionTable).where(MentionTable.id == mention_id))
        await self._mark_corrected(
            mentioned_type=current.mentioned_type, mentioned_id=current.mentioned_id, reviewed_by=reviewed_by
        )
        await self.session.commit()
        return True

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

    async def count_emails(self, request: EmailCountRequest) -> EmailCounts:
        """Count distinct emails matching `request`, bucketed by party or period.

        Reads the `header.*` structured-field mentions `extract-selectors` writes per
        header slot (the address selector + a display-name mention `resolve-entities`
        links to a person/org), so a person or an address can be the filter or bucket.
        """
        params: dict = {"limit": request.limit}
        where = ["f.filetype_group = 'email'", *correspondence_predicates(request, params, file_column="f.id")]
        if request.dataset_id:
            params["dataset_id"] = request.dataset_id
            where.append("f.dataset_id = :dataset_id")
        if request.dataset_ids is not None:
            params["dataset_ids"] = list(request.dataset_ids)
            where.append("f.dataset_id = ANY(cast(:dataset_ids AS text[]))")
        emails_cte = (
            "emails AS (SELECT f.id AS file_id, coalesce(et.metadata->>'message_id', f.sha256) AS message_key, "
            f"{CONTENT_DATE_SQL} AS date_sent FROM file f JOIN extracted_text et ON et.file_id = f.id "
            f"WHERE {' AND '.join(where)})"
        )
        total = (
            await self.session.execute(
                text(f"WITH {emails_cte} SELECT count(DISTINCT message_key) FROM emails"), params
            )
        ).scalar_one()

        if request.group_by in _PERIOD_LENGTH:
            params["period_length"] = _PERIOD_LENGTH[request.group_by]
            sql = (
                f"WITH {emails_cte} SELECT substr(date_sent, 1, :period_length) AS key, "
                "count(DISTINCT message_key) AS email_count, min(date_sent) AS date_first, max(date_sent) AS date_last "
                f"FROM emails WHERE date_sent IS NOT NULL GROUP BY 1 ORDER BY 1 LIMIT {_MAX_PERIODS}"
            )
            rows = (await self.session.execute(text(sql), params)).mappings().all()
            buckets = [EmailCountBucket(label=r["key"], **r) for r in rows]
        else:
            buckets = await self._party_buckets(request, params, emails_cte)
        return EmailCounts(total_emails=total, group_by=request.group_by, buckets=buckets)

    async def _party_buckets(self, request: EmailCountRequest, params: dict, emails_cte: str) -> list[EmailCountBucket]:
        """Group by the entity in each header slot of the grouped role.

        A slot resolves to its named entity (person/org from the display name),
        else the owner of its address (`has_selector`), else the address itself.
        """
        seed_keys = [k for k in params if k.startswith(("sender_", "recipient_", "participant_"))]
        # Exclude the filtered parties themselves -- including the owner of a filtered
        # address, so "who does <address> email" doesn't list the address's own person.
        seeds = (
            " UNION ".join(
                f"({_identity_sql(k)}) UNION (SELECT r.src_entity_id FROM entity_relationship r "
                f"WHERE r.dst_entity_id = :{k} AND r.relationship_type = 'HAS_SELECTOR')"
                for k in seed_keys
            )
            or "SELECT NULL::text WHERE false"
        )
        sql = (
            f"WITH {emails_cte}, "
            "slots AS (SELECT m.file_id, m.field_path, "
            "  max(m.entity_id) FILTER (WHERE m.selector_type IS NULL) AS named_id, "
            "  max(m.entity_id) FILTER (WHERE m.selector_type IS NOT NULL) AS address_id "
            "  FROM mention m JOIN emails e ON e.file_id = m.file_id "
            f"  WHERE {_ROLE_PATHS[_PARTY_ROLE[request.group_by]]} AND m.entity_id IS NOT NULL "
            "  GROUP BY m.file_id, m.field_path), "
            "keyed AS (SELECT s.file_id, s.address_id, coalesce(s.named_id, owner.src_entity_id, s.address_id) AS key "
            "  FROM slots s LEFT JOIN LATERAL (SELECT r.src_entity_id FROM entity_relationship r "
            "    WHERE r.dst_entity_id = s.address_id AND r.relationship_type = 'HAS_SELECTOR' LIMIT 1) owner ON true) "
            "SELECT k.key, ent.display_name AS label, lower(ent.entity_type) AS entity_type, "
            "  count(DISTINCT e.message_key) AS email_count, min(e.date_sent) AS date_first, "
            "  max(e.date_sent) AS date_last, "
            "  coalesce(array_agg(DISTINCT addr.display_name) FILTER (WHERE addr.id IS NOT NULL), '{}') AS addresses "
            "FROM keyed k JOIN emails e ON e.file_id = k.file_id JOIN entity ent ON ent.id = k.key "
            "LEFT JOIN entity addr ON addr.id = k.address_id "
            f"WHERE k.key NOT IN ({seeds}) AND (k.address_id IS NULL OR k.address_id NOT IN ({seeds})) "
            "GROUP BY 1, 2, 3 ORDER BY email_count DESC, label LIMIT :limit"
        )
        rows = (await self.session.execute(text(sql), params)).mappings().all()
        return [EmailCountBucket(**r) for r in rows]

    async def selector_evidence(self, selector_ids: list[str]) -> list[SelectorEvidence]:
        """Header usage and current owners for each selector -- what an analyst weighs before linking it."""
        if not selector_ids:
            return []
        usage = (
            await self.session.execute(
                text(
                    "SELECT a.id, a.display_name, "
                    "(SELECT count(DISTINCT m.file_id) FROM mention m "
                    " WHERE m.entity_id = a.id AND m.field_path LIKE 'header.%') AS email_count, "
                    "(SELECT coalesce((array_agg(n.surface_text ORDER BY n.cnt DESC))[1:4], '{}') FROM ("
                    "   SELECT n.surface_text, count(*) AS cnt FROM mention m JOIN mention n "
                    "   ON n.file_id = m.file_id AND n.field_path = m.field_path AND n.selector_type IS NULL "
                    "   WHERE m.entity_id = a.id AND m.field_path LIKE 'header.%' GROUP BY n.surface_text) n) AS names "
                    "FROM entity a WHERE a.id = ANY(cast(:ids AS text[]))"
                ),
                {"ids": selector_ids},
            )
        ).all()
        owners = (
            await self.session.execute(
                text(
                    "SELECT DISTINCT r.dst_entity_id, o.id, o.display_name, lower(r.source) AS source "
                    "FROM entity_relationship r JOIN entity o ON o.id = r.src_entity_id "
                    "WHERE r.relationship_type = 'HAS_SELECTOR' AND r.dst_entity_id = ANY(cast(:ids AS text[]))"
                ),
                {"ids": selector_ids},
            )
        ).all()
        by_selector: dict[str, list[SelectorOwner]] = {}
        for selector_id, owner_id, owner_name, source in owners:
            by_selector.setdefault(selector_id, []).append(
                SelectorOwner(entity_id=owner_id, display_name=owner_name, source=source)
            )
        order = {selector_id: index for index, selector_id in enumerate(selector_ids)}
        return sorted(
            (
                SelectorEvidence(
                    entity_id=row.id,
                    display_name=row.display_name,
                    email_count=row.email_count,
                    names=list(row.names),
                    linked_to=by_selector.get(row.id, []),
                )
                for row in usage
            ),
            key=lambda evidence: order[evidence.entity_id],
        )

    async def header_addresses_for_name(
        self, *, name: str, dataset_id: str | None, exclude_owner: str | None = None, limit: int = 6
    ) -> list[dict]:
        """Email addresses seen in headers under a display name like `name`, with who owns each.

        The review surface for an identity that isn't (fully) resolved: e.g. "Nick Bolton" as the
        display name on addresses no entity owns, or that are linked to a different entity.
        Addresses owned by `exclude_owner` (the entity already matched) are left out. Each row:
        `entityId` (the address selector), `address`, `names` (display names seen), `emailCount`,
        `linkedTo` (the owning entity's name, or null when unlinked).
        """
        params: dict = {"name": normalize_name(name), "limit": limit, "owner": exclude_owner or ""}
        dataset_filter = ""
        if dataset_id:
            params["dataset_id"] = dataset_id
            dataset_filter = "AND n.dataset_id = :dataset_id"
        sql = f"""
            SELECT a.id AS "entityId", a.display_name AS address,
                   (array_agg(DISTINCT n.surface_text))[1:3] AS names,
                   count(DISTINCT n.file_id) AS "emailCount",
                   (SELECT string_agg(DISTINCT o.display_name, ', ') FROM entity_relationship r
                    JOIN entity o ON o.id = r.src_entity_id
                    WHERE r.dst_entity_id = a.id AND r.relationship_type = 'HAS_SELECTOR') AS "linkedTo"
            FROM mention n
            JOIN mention m ON m.file_id = n.file_id AND m.field_path = n.field_path AND m.selector_type = 'EMAIL'
            JOIN entity a ON a.id = m.entity_id
            WHERE n.field_path LIKE 'header.%' AND n.selector_type IS NULL {dataset_filter}
              AND n.normalized_value % :name AND similarity(n.normalized_value, :name) >= 0.6
              AND a.id <> :owner
              AND a.id NOT IN (SELECT r.dst_entity_id FROM entity_relationship r
                               WHERE r.src_entity_id = :owner AND r.relationship_type = 'HAS_SELECTOR')
            GROUP BY a.id, a.display_name
            ORDER BY "emailCount" DESC
            LIMIT :limit
        """
        return [dict(r) for r in (await self.session.execute(text(sql), params)).mappings().all()]

    async def names_for_entity(self, entity_id: str, *, limit: int = 50) -> list[dict]:
        """Name groups resolved to an entity, most mentions first: `normalized_value`, `surface`, `mention_count`."""
        rows = await self.session.execute(
            select(
                MentionTable.normalized_value,
                func.mode().within_group(MentionTable.surface_text).label("surface"),
                func.count(MentionTable.id).label("mention_count"),
            )
            .where(
                MentionTable.entity_id == entity_id,
                MentionTable.entity_attribute == "name",
                MentionTable.normalized_value.is_not(None),
            )
            .group_by(MentionTable.normalized_value)
            .order_by(desc("mention_count"))
            .limit(limit)
        )
        return [dict(row._mapping) for row in rows]
