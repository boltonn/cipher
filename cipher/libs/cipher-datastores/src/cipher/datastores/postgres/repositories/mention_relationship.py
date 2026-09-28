from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.entity_relationship_candidate import (
    EntityRelationshipCandidateTable,
)
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.mention_relationship import MentionRelationshipTable
from cipher.schemas.graph.entity_relationship import (
    RelationshipCandidateCreate,
    RelationshipCandidateMethod,
)
from cipher.schemas.graph.mention_relationship import (
    MentionRelationship,
    MentionRelationshipCreate,
)
from cipher.schemas.graph.ontology import RELATIONSHIPS, validate_relationship


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
                    src.entity_id,
                    dst.entity_id,
                    src_entity.entity_type,
                    dst_entity.entity_type,
                )
                .join(src, src.id == MentionRelationshipTable.src_mention_id)
                .join(dst, dst.id == MentionRelationshipTable.dst_mention_id)
                .join(src_entity, src_entity.id == src.entity_id)
                .join(dst_entity, dst_entity.id == dst.entity_id)
                .where(MentionRelationshipTable.dataset_id == dataset_id)
            )
        ).all()

        candidates: list[RelationshipCandidateCreate] = []
        seen: set[tuple[str, str, str]] = set()
        for rel_type, confidence, evidence_mention_id, src_eid, dst_eid, src_type, dst_type in rows:
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
                    method=RelationshipCandidateMethod.LLM,
                    evidence_mention_id=evidence_mention_id,
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
