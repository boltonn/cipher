from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.entity_relationship_candidate import (
    EntityRelationshipCandidateTable,
)
from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.mention_relationship import MentionRelationshipTable
from cipher.schemas.graph.entity_relationship import (
    RelationshipCandidateCreate,
    RelationshipCandidateMethod,
)
from cipher.schemas.graph.mention import MANUAL_EXTRACTOR, Mention, MentionedType
from cipher.schemas.graph.mention_relationship import (
    EmailSignature,
    EmailSignatureSearchParameters,
    EmailSignatureSummary,
    EvidenceSpan,
    MentionRelationship,
    MentionRelationshipCreate,
    MentionRelationshipDraft,
    MentionRelationshipUpdate,
    MentionRelationshipView,
    PaginatedEmailSignaturesResponse,
    RelationshipEvidence,
)
from cipher.schemas.graph.ontology import (
    RELATIONSHIPS,
    RelationshipSource,
    RelationshipType,
    validate_relationship,
)

_SIGNATURE_EXTRACTOR = "signature"
# the email-signature review: what the reader proposed plus what analysts drew beside it
_SIGNATURE_REVIEW_EXTRACTORS = (_SIGNATURE_EXTRACTOR, MANUAL_EXTRACTOR)

_EMAIL_SIGNATURES = text(
    """
    WITH relations AS (
        SELECT mr.file_id, mr.dataset_id, count(*) AS relationship_count,
               count(*) FILTER (WHERE mr.date_reviewed IS NULL) AS pending_count
        FROM mention_relationship mr
        WHERE mr.file_id IS NOT NULL AND mr.extractor = ANY(CAST(:extractors AS text[]))
          AND (CAST(:dataset_ids AS text[]) IS NULL OR mr.dataset_id = ANY(CAST(:dataset_ids AS text[])))
        GROUP BY mr.file_id, mr.dataset_id
        HAVING bool_or(mr.extractor = :signature)
    ), rows AS (
        SELECT r.*, et.metadata AS metadata,
               (SELECT m.surface_text FROM mention m WHERE m.file_id = r.file_id AND m.extractor = :signature
                  AND m.field_path = 'signature.person' AND m.entity_type = 'PERSON' LIMIT 1) AS person_name,
               (SELECT array_agg(m.surface_text ORDER BY m.field_path) FROM mention m
                 WHERE m.file_id = r.file_id AND m.extractor = :signature AND m.field_path LIKE 'signature.unit.%'
                   AND m.entity_type = 'ORGANIZATION'
               ) AS organizations
        FROM relations r
        LEFT JOIN LATERAL (
            SELECT et.metadata FROM extracted_text et WHERE et.file_id = r.file_id LIMIT 1
        ) et ON true
    )
    SELECT *, count(*) OVER () AS total FROM rows
    WHERE (CAST(:is_pending AS boolean) IS NULL OR (pending_count > 0) = CAST(:is_pending AS boolean))
      AND (CAST(:query AS text) IS NULL OR concat_ws(' ', person_name, array_to_string(organizations, ' '),
               metadata->>'title', metadata->'sent_from'->>'name', metadata->'sent_from'->>'value')
               ILIKE '%' || CAST(:query AS text) || '%')
    ORDER BY metadata->>'date_sent' DESC NULLS LAST, file_id
    LIMIT :limit OFFSET :offset
    """
)


class PostgresMentionRelationshipRepository:
    """Datastore for extractor-asserted relations between mention spans."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the mention_relationship table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(MentionRelationshipTable.metadata.create_all)

    async def add_batch(self, relations: list[MentionRelationshipCreate]) -> int:
        """Bulk-insert mention relations, ignoring any already recorded. Returns rows written."""
        if not relations:
            return 0
        stmt = (
            pg_insert(MentionRelationshipTable)
            .values([r.model_dump(by_alias=False) for r in relations])
            .on_conflict_do_nothing(constraint="uq_mention_relationship_triple")
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return len(relations)

    async def list_by_dataset(self, dataset_id: str, *, limit: int = 500) -> list[MentionRelationship]:
        """Every mention relation in a dataset (for inspection / tests)."""
        rows = (
            (
                await self.session.execute(
                    select(MentionRelationshipTable)
                    .where(MentionRelationshipTable.dataset_id == dataset_id)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [MentionRelationship.model_validate(r) for r in rows]

    async def promote_to_candidates(self, dataset_id: str) -> int:
        """Emit a `RelationshipCandidate` for every mention relation whose endpoints both resolved.

        Reads mention relations where both the src and dst mention now carry an
        `entity_id`, validates the endpoint entity types against the ontology
        (flipping a symmetric edge if that is what makes it legal), and inserts
        the resulting candidates. Idempotent -- the candidate triple constraint
        drops repeats, so this is safe to run after every resolution sweep.
        Returns the number of candidate rows offered for insert.
        """
        src = aliased(MentionTable)
        dst = aliased(MentionTable)
        src_entity = aliased(EntityTable)
        dst_entity = aliased(EntityTable)

        rows = (
            await self.session.execute(
                select(
                    MentionRelationshipTable.relationship_type,
                    MentionRelationshipTable.confidence,
                    MentionRelationshipTable.src_mention_id,
                    MentionRelationshipTable.attributes,
                    MentionRelationshipTable.extractor,
                    src.entity_id,
                    dst.entity_id,
                    src_entity.entity_type,
                    dst_entity.entity_type,
                )
                .join(src, src.id == MentionRelationshipTable.src_mention_id)
                .join(dst, dst.id == MentionRelationshipTable.dst_mention_id)
                .join(src_entity, src_entity.id == src.entity_id)
                .join(dst_entity, dst_entity.id == dst.entity_id)
                .where(
                    MentionRelationshipTable.dataset_id == dataset_id,
                    MentionRelationshipTable.date_reviewed.is_(None),
                )
            )
        ).all()

        candidates: list[RelationshipCandidateCreate] = []
        seen: set[tuple[str, str, str]] = set()
        for (
            rel_type,
            confidence,
            evidence_mention_id,
            attributes,
            extractor,
            src_eid,
            dst_eid,
            src_type,
            dst_type,
        ) in rows:
            if not src_eid or not dst_eid or src_eid == dst_eid:
                continue

            ordered = _legal_endpoints(rel_type, src_eid, dst_eid, src_type, dst_type)
            if ordered is None:
                continue
            a_eid, b_eid = ordered

            key = (a_eid, b_eid, rel_type)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                RelationshipCandidateCreate(
                    dataset_id=dataset_id,
                    src_entity_id=a_eid,
                    dst_entity_id=b_eid,
                    relationship_type=rel_type,
                    confidence=float(confidence),
                    method=_EXTRACTOR_METHOD.get(extractor, RelationshipCandidateMethod.LLM),
                    evidence_mention_id=evidence_mention_id,
                    attributes=attributes or {},
                )
            )

        if not candidates:
            return 0
        stmt = (
            pg_insert(EntityRelationshipCandidateTable)
            .values([c.model_dump(by_alias=False) for c in candidates])
            .on_conflict_do_nothing(constraint="uq_entity_relationship_candidate_triple")
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return len(candidates)

    async def evidence_for(
        self,
        *,
        src_entity_id: str | None = None,
        dst_entity_id: str | None = None,
        relationship_type: RelationshipType | None = None,
        mention_relationship_ids: list[str] | None = None,
        dataset_ids: list[str] | None = None,
        limit: int = 25,
    ) -> list[RelationshipEvidence]:
        """The mention relations behind an edge, with a source-text snippet each.

        Either the entity-level edge (`src_entity_id`/`dst_entity_id`/`relationship_type`, either
        direction) or explicit `mention_relationship_ids` (a name-level suggestion).
        """
        src = aliased(MentionTable)
        dst = aliased(MentionTable)
        relation = MentionRelationshipTable
        stmt = (
            select(relation, src, dst, ExtractedTextTable.content, ExtractedTextTable.metadata_)
            .join(src, src.id == relation.src_mention_id)
            .join(dst, dst.id == relation.dst_mention_id)
            .outerjoin(
                ExtractedTextTable,
                and_(src.mentioned_type == MentionedType.EXTRACTED_TEXT, ExtractedTextTable.id == src.mentioned_id),
            )
            .where(
                relation.id.in_(mention_relationship_ids)
                if mention_relationship_ids is not None
                else and_(
                    relation.relationship_type == relationship_type,
                    or_(
                        and_(src.entity_id == src_entity_id, dst.entity_id == dst_entity_id),
                        and_(src.entity_id == dst_entity_id, dst.entity_id == src_entity_id),
                    ),
                )
            )
            .order_by(relation.confidence.desc(), relation.date_created)
            .limit(limit)
        )
        if dataset_ids is not None:
            stmt = stmt.where(relation.dataset_id.in_(dataset_ids))
        return [
            _evidence(relation_row, src_row, dst_row, content, metadata)
            for relation_row, src_row, dst_row, content, metadata in (await self.session.execute(stmt)).all()
        ]

    async def emails_from(
        self, addresses: list[str], *, dataset_ids: list[str] | None = None, limit: int = 25
    ) -> list[RelationshipEvidence]:
        """Emails sent from `addresses`, newest first, as whole-email evidence (the opening of each body)."""
        sender = func.lower(ExtractedTextTable.metadata_["sent_from"]["value"].astext)
        stmt = (
            select(ExtractedTextTable, FileTable.dataset_id)
            .join(FileTable, FileTable.id == ExtractedTextTable.file_id)
            .where(sender.in_([a.lower() for a in addresses]))
            .order_by(ExtractedTextTable.metadata_["date_sent"].astext.desc().nulls_last())
            .limit(limit)
        )
        if dataset_ids is not None:
            stmt = stmt.where(FileTable.dataset_id.in_(dataset_ids))
        return [
            RelationshipEvidence(
                dataset_id=dataset_id,
                file_id=row.file_id,
                extractor="email header",
                confidence=1.0,
                snippet=row.content[: _SNIPPET_PAD * 3],
                **_email_fields(row.metadata_),
            )
            for row, dataset_id in (await self.session.execute(stmt)).all()
        ]

    async def list_for_file(self, file_id: str) -> list[MentionRelationshipView]:
        """Every relationship drawn between two mentions of a file, with both mentions."""
        return await self._views(or_(MentionRelationshipTable.file_id == file_id, _SRC.file_id == file_id))

    async def get_view(self, relation_id: str) -> MentionRelationshipView | None:
        """One relationship with both of its mentions, or None."""
        views = await self._views(MentionRelationshipTable.id == relation_id)
        return views[0] if views else None

    async def _views(self, condition) -> list[MentionRelationshipView]:
        rows = (
            await self.session.execute(
                select(MentionRelationshipTable, _SRC, _DST)
                .join(_SRC, _SRC.id == MentionRelationshipTable.src_mention_id)
                .join(_DST, _DST.id == MentionRelationshipTable.dst_mention_id)
                .where(condition)
                .order_by(MentionRelationshipTable.date_created)
            )
        ).all()
        twins = await self._resolved_twins([m for _, src, dst in rows for m in (src, dst) if m.entity_id is None])
        return [
            MentionRelationshipView(
                **MentionRelationship.model_validate(relation).model_dump(),
                src=_with_twin(src, twins),
                dst=_with_twin(dst, twins),
            )
            for relation, src, dst in rows
        ]

    async def _resolved_twins(self, mentions: list[MentionTable]) -> dict[str, str]:
        """Entity of a resolved twin -- same text, same name key, overlapping span -- for unresolved `mentions`.

        Two extractors often label one name (NER `AAA Club Alliance Inc`, the email-signature reader
        `AAA Club Alliance Inc.`); the relationship may hang off the unresolved copy while its twin
        is already resolved. Returns mention id -> entity id.
        """
        pending = [m for m in mentions if m.start_offset is not None and m.normalized_value]
        if not pending:
            return {}
        rows = (
            await self.session.execute(
                select(
                    MentionTable.mentioned_id,
                    MentionTable.normalized_value,
                    MentionTable.start_offset,
                    MentionTable.end_offset,
                    MentionTable.entity_id,
                )
                .where(
                    MentionTable.mentioned_id.in_({m.mentioned_id for m in pending}),
                    MentionTable.normalized_value.in_({m.normalized_value for m in pending}),
                    MentionTable.entity_id.is_not(None),
                )
                .order_by((MentionTable.extractor == MANUAL_EXTRACTOR).desc())  # an analyst's resolution wins
            )
        ).all()
        twins: dict[str, str] = {}
        for m in pending:
            for text_id, value, start, end, entity_id in rows:
                overlaps = start is not None and start < m.end_offset and m.start_offset < end
                if text_id == m.mentioned_id and value == m.normalized_value and overlaps:
                    twins[m.id] = entity_id
                    break
        return twins

    async def create_manual(self, draft: MentionRelationshipDraft) -> MentionRelationshipView:
        """Record an analyst-drawn relationship between two mentions of one text.

        Raises:
            ValueError: an end is missing, the mentions are in different texts, the ontology
                forbids the type between them, or the relationship already exists.
        """
        src, dst = await self._ends(draft.src_mention_id, draft.dst_mention_id)
        _check_types(draft.relationship_type, src, dst)
        exists = await self.session.scalar(
            select(MentionRelationshipTable.id).where(
                MentionRelationshipTable.src_mention_id == src.id,
                MentionRelationshipTable.dst_mention_id == dst.id,
                MentionRelationshipTable.relationship_type == draft.relationship_type,
            )
        )
        if exists:
            raise ValueError("That relationship is already there")
        row = MentionRelationshipTable(
            dataset_id=src.dataset_id,
            src_mention_id=src.id,
            dst_mention_id=dst.id,
            relationship_type=draft.relationship_type,
            directed=True,
            confidence=1.0,
            file_id=src.file_id,
            attributes=draft.attributes,
            extractor=MANUAL_EXTRACTOR,
        )
        self.session.add(row)
        await self.session.commit()
        return await self.get_view(row.id)

    async def update_relation(
        self, relation_id: str, patch: MentionRelationshipUpdate
    ) -> MentionRelationshipView | None:
        """Correct a pending relationship's type, attributes or direction.

        Raises:
            ValueError: it was already reviewed, or the ontology forbids the result.
        """
        row = await self.session.get(MentionRelationshipTable, relation_id)
        if row is None:
            return None
        if row.date_reviewed is not None:
            raise ValueError("Reopen it before changing it")
        if patch.reverse:
            row.src_mention_id, row.dst_mention_id = row.dst_mention_id, row.src_mention_id
        if patch.relationship_type is not None:
            row.relationship_type = patch.relationship_type
        if patch.attributes is not None:
            row.attributes = {k: v for k, v in patch.attributes.items() if v not in (None, "")}
        src, dst = await self._ends(row.src_mention_id, row.dst_mention_id)
        _check_types(row.relationship_type, src, dst)
        await self.session.commit()
        return await self.get_view(relation_id)

    async def accept(self, relation_id: str, *, reviewed_by: str | None) -> MentionRelationshipView | None:
        """Turn a relationship into an entity edge (both ends must be resolved) and mark it accepted.

        Raises:
            ValueError: an end is not resolved to an entity yet, or the ontology forbids the edge.
        """
        from cipher.datastores.postgres.repositories.entity import PostgresEntityRepository

        view = await self.get_view(relation_id)
        if view is None:
            return None
        if not (view.src.entity_id and view.dst.entity_id):
            raise ValueError("Resolve both ends to an entity first")
        # an end resolved only through its twin joins the twin's entity
        for end in (view.src, view.dst):
            await self.session.execute(
                update(MentionTable)
                .where(MentionTable.id == end.id, MentionTable.entity_id.is_(None))
                .values(entity_id=end.entity_id)
            )
        types = dict(
            (
                await self.session.execute(
                    select(EntityTable.id, EntityTable.entity_type).where(
                        EntityTable.id.in_([view.src.entity_id, view.dst.entity_id])
                    )
                )
            ).all()
        )
        ordered = _legal_endpoints(
            view.relationship_type,
            view.src.entity_id,
            view.dst.entity_id,
            types.get(view.src.entity_id),
            types.get(view.dst.entity_id),
        )
        if ordered is None:
            raise ValueError(f"{view.relationship_type.value} can't join these two entities")
        src_id, dst_id = ordered
        if view.relationship_type == RelationshipType.PART_OF:
            await PostgresEntityRepository(session=self.session).set_organization_parent(src_id, dst_id)
        else:
            insert = pg_insert(EntityRelationshipTable).values(
                dataset_id=view.dataset_id,
                src_entity_id=src_id,
                dst_entity_id=dst_id,
                relationship_type=view.relationship_type,
                directed=True,
                source=RelationshipSource.MANUAL,
                attributes=view.attributes,
            )
            await self.session.execute(
                insert.on_conflict_do_update(
                    constraint="uq_entity_relationship_triple",
                    set_={"attributes": EntityRelationshipTable.attributes.op("||")(insert.excluded.attributes)},
                )
            )
        await self._review([relation_id], is_accepted=True, reviewed_by=reviewed_by)
        return await self.get_view(relation_id)

    async def reject(self, relation_id: str, *, reviewed_by: str | None) -> MentionRelationshipView | None:
        """Mark a relationship rejected; it is never offered again."""
        await self._review([relation_id], is_accepted=False, reviewed_by=reviewed_by)
        return await self.get_view(relation_id)

    async def reopen(self, relation_id: str) -> MentionRelationshipView | None:
        """Back to pending; an accepted one's edge comes out again (an analyst-made one only)."""
        view = await self.get_view(relation_id)
        if view is None:
            return None
        if view.is_accepted and view.src.entity_id and view.dst.entity_id:
            if view.relationship_type == RelationshipType.PART_OF:
                from cipher.datastores.postgres.repositories.entity import PostgresEntityRepository

                await PostgresEntityRepository(session=self.session).set_organization_parent(view.src.entity_id, None)
            else:
                await self.session.execute(
                    delete(EntityRelationshipTable).where(
                        EntityRelationshipTable.relationship_type == view.relationship_type,
                        EntityRelationshipTable.source == RelationshipSource.MANUAL,
                        or_(
                            and_(
                                EntityRelationshipTable.src_entity_id == view.src.entity_id,
                                EntityRelationshipTable.dst_entity_id == view.dst.entity_id,
                            ),
                            and_(
                                EntityRelationshipTable.src_entity_id == view.dst.entity_id,
                                EntityRelationshipTable.dst_entity_id == view.src.entity_id,
                            ),
                        ),
                    )
                )
        await self.session.execute(
            update(MentionRelationshipTable)
            .where(MentionRelationshipTable.id == relation_id)
            .values(date_reviewed=None, is_accepted=None, reviewed_by=None)
        )
        await self.session.commit()
        return await self.get_view(relation_id)

    async def delete_manual(self, relation_id: str) -> bool:
        """Delete an analyst-drawn relationship (extracted ones are rejected instead)."""
        result = await self.session.execute(
            delete(MentionRelationshipTable).where(
                MentionRelationshipTable.id == relation_id, MentionRelationshipTable.extractor == MANUAL_EXTRACTOR
            )
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def _review(self, ids: list[str], *, is_accepted: bool, reviewed_by: str | None) -> int:
        result = await self.session.execute(
            update(MentionRelationshipTable)
            .where(MentionRelationshipTable.id.in_(ids))
            .values(date_reviewed=datetime.now(UTC), is_accepted=is_accepted, reviewed_by=reviewed_by)
        )
        await self.session.commit()
        return result.rowcount or 0

    async def _ends(self, src_id: str, dst_id: str) -> tuple[MentionTable, MentionTable]:
        rows = {
            m.id: m
            for m in (
                await self.session.execute(select(MentionTable).where(MentionTable.id.in_([src_id, dst_id])))
            ).scalars()
        }
        src, dst = rows.get(src_id), rows.get(dst_id)
        if src is None or dst is None:
            raise ValueError("Both ends must be mentions")
        if src_id == dst_id:
            raise ValueError("A relationship needs two different mentions")
        if (src.mentioned_type, src.mentioned_id) != (dst.mentioned_type, dst.mentioned_id):
            raise ValueError("Both mentions must be in the same text")
        return src, dst

    async def list_email_signatures(self, params: EmailSignatureSearchParameters) -> PaginatedEmailSignaturesResponse:
        """Emails whose email signature was read, newest first, with how many relationships await review."""
        rows = (
            (
                await self.session.execute(
                    _EMAIL_SIGNATURES,
                    {
                        "extractors": list(_SIGNATURE_REVIEW_EXTRACTORS),
                        "signature": _SIGNATURE_EXTRACTOR,
                        "dataset_ids": params.dataset_ids,
                        "is_pending": params.is_pending,
                        "query": (params.query or "").strip() or None,
                        "limit": params.limit,
                        "offset": (params.page - 1) * params.limit,
                    },
                )
            )
            .mappings()
            .all()
        )
        return PaginatedEmailSignaturesResponse(
            total=rows[0]["total"] if rows else 0,
            page=params.page,
            limit=params.limit,
            data=[
                EmailSignatureSummary(
                    file_id=r["file_id"],
                    dataset_id=r["dataset_id"],
                    person_name=r["person_name"],
                    organizations=r["organizations"] or [],
                    relationship_count=r["relationship_count"],
                    pending_count=r["pending_count"],
                    **_email_fields(r["metadata"]),
                )
                for r in rows
            ],
        )

    async def get_email_signature(self, file_id: str) -> EmailSignature | None:
        """Where the email signature sits in a file's text: the lines its mentions cover."""
        row = (
            await self.session.execute(
                select(
                    MentionTable.mentioned_id,
                    MentionTable.dataset_id,
                    func.min(MentionTable.start_offset),
                    func.max(MentionTable.end_offset),
                )
                .where(
                    MentionTable.file_id == file_id,
                    MentionTable.extractor == _SIGNATURE_EXTRACTOR,
                    MentionTable.mentioned_type == MentionedType.EXTRACTED_TEXT,
                    MentionTable.start_offset.is_not(None),
                )
                .group_by(MentionTable.mentioned_id, MentionTable.dataset_id)
                .limit(1)
            )
        ).first()
        if row is None:
            return None
        text_id, dataset_id, start, end = row
        extracted = await self.session.get(ExtractedTextTable, text_id)
        content = extracted.content if extracted else ""
        start = content.rfind("\n", 0, start) + 1
        line_end = content.find("\n", end)
        return EmailSignature(
            file_id=file_id,
            dataset_id=dataset_id,
            extracted_text_id=text_id,
            start_offset=start,
            end_offset=len(content) if line_end < 0 else line_end,
            **_email_fields(extracted.metadata_ if extracted else None),
        )

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete all mention relations for a dataset (used by reset-entities)."""
        result = await self.session.execute(
            delete(MentionRelationshipTable).where(MentionRelationshipTable.dataset_id == dataset_id)
        )
        await self.session.commit()
        return result.rowcount or 0


def _with_twin(mention: MentionTable, twins: dict[str, str]) -> Mention:
    """The mention, resolved through a resolved twin when it isn't itself."""
    out = Mention.model_validate(mention)
    if out.entity_id is None:
        out.entity_id = twins.get(mention.id)
    return out


_SRC = aliased(MentionTable, name="src_mention")
_DST = aliased(MentionTable, name="dst_mention")


def _check_types(relationship_type: RelationshipType, src: MentionTable, dst: MentionTable) -> None:
    """Refuse a type the ontology forbids between the two mentions' types (untyped ends pass)."""
    if src.entity_type is None or dst.entity_type is None:
        return
    if _legal_endpoints(relationship_type, src.id, dst.id, src.entity_type, dst.entity_type) is None:
        raise ValueError(
            f"{relationship_type.value} can't go from {_a(src.entity_type.value)} to {_a(dst.entity_type.value)}"
        )


def _a(noun: str) -> str:
    return f"{'an' if noun[0] in 'aeiou' else 'a'} {noun}"


def _legal_endpoints(rel_type, src_eid, dst_eid, src_type, dst_type):
    """Return `(src_entity_id, dst_entity_id)` in a direction the ontology allows, or None."""
    try:
        validate_relationship(relationship_type=rel_type, src_type=src_type, dst_type=dst_type)
        return src_eid, dst_eid
    except ValueError:
        pass
    spec = RELATIONSHIPS.get(rel_type)
    if spec is not None and spec.symmetric:
        try:
            validate_relationship(relationship_type=rel_type, src_type=dst_type, dst_type=src_type)
            return dst_eid, src_eid
        except ValueError:
            return None
    return None


_SNIPPET_PAD = 160
_EXTRACTOR_METHOD = {"signature": RelationshipCandidateMethod.SIGNATURE}


def _span(mention: MentionTable) -> EvidenceSpan:
    return EvidenceSpan(
        mention_id=mention.id,
        surface_text=mention.surface_text,
        start_offset=mention.start_offset,
        end_offset=mention.end_offset,
    )


def _evidence(relation, src: MentionTable, dst: MentionTable, content: str | None, metadata: dict | None):
    """A relation's evidence row: both spans plus the text around them (or the stored context)."""
    offsets = [o for o in (src.start_offset, src.end_offset, dst.start_offset, dst.end_offset) if o is not None]
    if content and offsets:
        start = max(0, min(offsets) - _SNIPPET_PAD)
        snippet, snippet_offset = content[start : max(offsets) + _SNIPPET_PAD], start
    else:
        snippet, snippet_offset = relation.context or src.context or "", 0
    return RelationshipEvidence(
        mention_relationship_id=relation.id,
        dataset_id=relation.dataset_id,
        file_id=relation.file_id or src.file_id,
        extractor=relation.extractor,
        confidence=relation.confidence,
        attributes=relation.attributes or {},
        src=_span(src),
        dst=_span(dst),
        snippet=snippet,
        snippet_offset=snippet_offset,
        **_email_fields(metadata),
    )


def _email_fields(metadata: dict | None) -> dict:
    """Subject / sender / date of an email's extracted-text metadata (all None for non-email sources)."""
    metadata = metadata or {}
    sender = metadata.get("sent_from") or metadata.get("from") or metadata.get("sender") or {}
    label = " ".join(p for p in (sender.get("name"), f"<{sender['value']}>" if sender.get("value") else None) if p)
    return {"subject": metadata.get("title"), "sender": label or None, "date_sent": metadata.get("date_sent")}
