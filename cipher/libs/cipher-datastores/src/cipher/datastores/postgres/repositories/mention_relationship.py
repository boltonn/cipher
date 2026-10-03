from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from cipher.datastores.postgres.tables.entity import EntityTable
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
from cipher.schemas.graph.mention import MentionedType
from cipher.schemas.graph.mention_relationship import (
    EvidenceSpan,
    MentionRelationship,
    MentionRelationshipCreate,
    RelationshipEvidence,
)
from cipher.schemas.graph.ontology import RELATIONSHIPS, RelationshipType, validate_relationship


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

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete all mention relations for a dataset (used by reset-entities)."""
        result = await self.session.execute(
            delete(MentionRelationshipTable).where(MentionRelationshipTable.dataset_id == dataset_id)
        )
        await self.session.commit()
        return result.rowcount or 0


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
