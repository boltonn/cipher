from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import and_, asc, delete, desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories._merge import fold_entity
from cipher.datastores.postgres.tables.entity import EntityTable, is_canonical_entity
from cipher.datastores.postgres.tables.entity_match import EntityMatchTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.schemas._base.common import SortOrder
from cipher.schemas.graph.entity_match import (
    DecisionSource,
    EntityMatch,
    EntityMatchBatchItem,
    EntityMatchCreate,
    EntityMatchGroup,
    EntityMatchReview,
    EntityMatchSearchParameters,
    EntityMatchSortField,
    EntityMatchStatus,
    EntityMergeGroup,
    EntityMergeSearchParameters,
    PaginatedEntityMatchesResponse,
    PaginatedEntityMatchGroupsResponse,
    PaginatedEntityMergeGroupsResponse,
)


class PostgresEntityMatchRepository:
    """Postgres datastore for candidate mention-to-entity resolutions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the entity_match table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(EntityMatchTable.metadata.create_all)

    async def create_match(self, match: EntityMatchCreate) -> EntityMatch:
        """Create a candidate resolution, returning the existing row if already proposed."""
        stmt = (
            pg_insert(EntityMatchTable)
            .values(**match.model_dump(by_alias=False))
            .on_conflict_do_nothing(constraint="uq_entity_match_mention_entity")
            .returning(EntityMatchTable)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        row = result.scalar_one_or_none()
        if row:
            return EntityMatch.model_validate(row)
        existing = await self.session.execute(
            select(EntityMatchTable).where(
                EntityMatchTable.mention_id == match.mention_id,
                EntityMatchTable.entity_id == match.entity_id,
            )
        )
        return EntityMatch.model_validate(existing.scalar_one())

    async def create_matches_batch(self, matches: list[EntityMatchCreate]) -> int:
        """Bulk-propose candidate resolutions, ignoring any already proposed."""
        if not matches:
            return 0
        stmt = (
            pg_insert(EntityMatchTable)
            .values([m.model_dump(by_alias=False) for m in matches])
            .on_conflict_do_nothing(constraint="uq_entity_match_mention_entity")
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return len(matches)

    async def create_name_group_match(self, match: EntityMatchCreate, *, confirmed: bool = False) -> None:
        """Propose (or auto-confirm) a group-level resolution for a whole name group.

        `match.mention_id` must be None and `match.normalized_value` set. A
        `confirmed` row is the audit trail for a system auto-resolve (the sweep
        has already attached the mentions); `reviewed_by` stays null and
        `explanation.band == 'auto'` is the "system did this" marker.

        Idempotent on `(dataset_id, normalized_value, entity_id)`. On a re-run:
        a `confirmed` row updates a still-open (`pending`) row to confirmed so an
        auto-resolved name doesn't linger in the queue; a `pending` proposal only
        refreshes the score/explanation of another still-`pending` row. An
        analyst decision (`confirmed`/`rejected` with `reviewed_by`) is never
        touched.
        """
        values = match.model_dump(by_alias=False, mode="json")
        refresh = {"similarity_score": values["similarity_score"], "match_method": values["match_method"]}
        if "explanation" in values:
            refresh["explanation"] = values["explanation"]
        if confirmed:
            stamp = {
                "status": EntityMatchStatus.CONFIRMED.value,
                "reviewed_at": datetime.now(UTC),
                "decision_source": DecisionSource.SYSTEM_AUTO.value,
            }
            values.update(stamp)
            refresh.update(stamp)
            keep = EntityMatchTable.status != EntityMatchStatus.REJECTED.value
        else:
            keep = EntityMatchTable.status == EntityMatchStatus.PENDING.value

        stmt = (
            pg_insert(EntityMatchTable)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["dataset_id", "normalized_value", "entity_id"],
                index_where=EntityMatchTable.mention_id.is_(None) & EntityMatchTable.normalized_value.is_not(None),
                set_=refresh,
                where=(EntityMatchTable.reviewed_by.is_(None)) & keep,
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def prune_name_group_pending(
        self, *, dataset_id: str, normalized_value: str, keep_entity_ids: set[str]
    ) -> int:
        """Drop stale `pending` group rows a re-run no longer proposes.

        A superseded proposal (the scorer now vetoes it, or ranks it out) is
        deleted, not rejected -- it was never an analyst decision, and keeping it
        as `rejected` would pollute calibration data. Analyst-reviewed rows
        (`reviewed_by` set) are always kept.
        """
        conds = [
            EntityMatchTable.dataset_id == dataset_id,
            EntityMatchTable.normalized_value == normalized_value,
            EntityMatchTable.mention_id.is_(None),
            EntityMatchTable.status == EntityMatchStatus.PENDING.value,
            EntityMatchTable.reviewed_by.is_(None),
        ]
        if keep_entity_ids:
            conds.append(EntityMatchTable.entity_id.notin_(keep_entity_ids))
        result = await self.session.execute(delete(EntityMatchTable).where(*conds))
        await self.session.commit()
        return result.rowcount or 0

    # --- entity->entity merge proposals (dedupe-entities) --------------------

    async def create_merge_match(self, match: EntityMatchCreate) -> None:
        """Propose merging a provisional entity into a canonical one.

        `match.provisional_entity_id` set; `mention_id` / `normalized_value` null.
        Idempotent on `(dataset_id, provisional_entity_id, entity_id)`; a re-run
        refreshes the score/explanation of a still-`pending` row and never
        touches an analyst decision.
        """
        values = match.model_dump(
            by_alias=False, mode="json", exclude={"entity_name", "entity_type", "provisional_name"}
        )
        refresh = {"similarity_score": values["similarity_score"], "match_method": values["match_method"]}
        if "explanation" in values:
            refresh["explanation"] = values["explanation"]
        stmt = (
            pg_insert(EntityMatchTable)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["dataset_id", "provisional_entity_id", "entity_id"],
                index_where=EntityMatchTable.provisional_entity_id.is_not(None),
                set_=refresh,
                where=(EntityMatchTable.reviewed_by.is_(None))
                & (EntityMatchTable.status == EntityMatchStatus.PENDING.value),
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def rejected_merge_targets(
        self, *, dataset_id: str, provisional_entity_id: str, normalized_name: str
    ) -> set[str]:
        """Canonical ids an analyst already declined for this stub.

        Either as a merge, or as a name-group match for the same name.
        `dedupe-entities` skips these.
        """
        rows = (
            await self.session.execute(
                select(EntityMatchTable.entity_id).where(
                    EntityMatchTable.dataset_id == dataset_id,
                    EntityMatchTable.status == EntityMatchStatus.REJECTED.value,
                    or_(
                        EntityMatchTable.provisional_entity_id == provisional_entity_id,
                        EntityMatchTable.normalized_value == normalized_name,
                    ),
                )
            )
        ).scalars()
        return set(rows)

    async def prune_merge_pending(
        self, *, dataset_id: str, provisional_entity_id: str, keep_entity_ids: set[str]
    ) -> int:
        """Drop stale `pending` merge rows a re-run no longer proposes (see `prune_name_group_pending`)."""
        conds = [
            EntityMatchTable.dataset_id == dataset_id,
            EntityMatchTable.provisional_entity_id == provisional_entity_id,
            EntityMatchTable.status == EntityMatchStatus.PENDING.value,
            EntityMatchTable.reviewed_by.is_(None),
        ]
        if keep_entity_ids:
            conds.append(EntityMatchTable.entity_id.notin_(keep_entity_ids))
        result = await self.session.execute(delete(EntityMatchTable).where(*conds))
        await self.session.commit()
        return result.rowcount or 0

    async def list_for_provisional(self, *, provisional_entity_id: str) -> list[EntityMatch]:
        """Merge proposals for one provisional entity (the entity-page panel), best first."""
        canon = EntityTable.__table__.alias("canon")
        rows = (
            await self.session.execute(
                select(EntityMatchTable, canon.c.display_name, canon.c.entity_type, canon.c.person_id)
                .join(canon, canon.c.id == EntityMatchTable.entity_id)
                .where(EntityMatchTable.provisional_entity_id == provisional_entity_id)
                .order_by(desc(EntityMatchTable.similarity_score))
            )
        ).all()
        out = []
        for row, dname, etype, pid in rows:
            m = EntityMatch.model_validate(row).model_copy(
                update={
                    "entity_name": dname,
                    "entity_type": str(etype) if etype is not None else None,
                    "entity_person_id": str(pid) if pid is not None else None,
                }
            )
            out.append(m)
        return out

    async def list_merge_groups(self, request: EntityMergeSearchParameters) -> PaginatedEntityMergeGroupsResponse:
        """Grouped merge-review queue: one card per provisional entity, canonical targets nested."""
        base = [EntityMatchTable.provisional_entity_id.is_not(None)]
        if request.dataset_id:
            base.append(EntityMatchTable.dataset_id == request.dataset_id)
        if request.status:
            base.append(EntityMatchTable.status == request.status)

        grp = (
            select(
                EntityMatchTable.dataset_id,
                EntityMatchTable.provisional_entity_id,
                func.max(EntityMatchTable.similarity_score).label("best"),
                func.min(EntityMatchTable.status).label("st"),
            )
            .where(*base)
            .group_by(EntityMatchTable.dataset_id, EntityMatchTable.provisional_entity_id)
        )
        total = (await self.session.execute(select(func.count()).select_from(grp.subquery()))).scalar_one()
        page_rows = (
            await self.session.execute(
                grp.order_by(desc("best")).offset((request.page - 1) * request.limit).limit(request.limit)
            )
        ).all()
        stub_ids = [r.provisional_entity_id for r in page_rows]
        if not stub_ids:
            return PaginatedEntityMergeGroupsResponse(total=total, page=request.page, limit=request.limit, data=[])

        canon = EntityTable.__table__.alias("canon")
        cand_rows = (
            await self.session.execute(
                select(EntityMatchTable, canon.c.display_name, canon.c.entity_type, canon.c.person_id)
                .join(canon, canon.c.id == EntityMatchTable.entity_id)
                .where(*base, EntityMatchTable.provisional_entity_id.in_(stub_ids))
                .order_by(desc(EntityMatchTable.similarity_score))
            )
        ).all()
        by_stub: dict[str, list[EntityMatch]] = defaultdict(list)
        for row, dname, etype, pid in cand_rows:
            by_stub[row.provisional_entity_id].append(
                EntityMatch.model_validate(row).model_copy(
                    update={
                        "entity_name": dname,
                        "entity_type": str(etype) if etype is not None else None,
                        "entity_person_id": str(pid) if pid is not None else None,
                    }
                )
            )

        stub_meta = {
            r.id: (r.display_name, r.entity_type, r.mc)
            for r in (
                await self.session.execute(
                    select(
                        EntityTable.id,
                        EntityTable.display_name,
                        EntityTable.entity_type,
                        select(func.count())
                        .select_from(MentionTable)
                        .where(MentionTable.entity_id == EntityTable.id)
                        .scalar_subquery()
                        .label("mc"),
                    ).where(EntityTable.id.in_(stub_ids))
                )
            ).all()
        }

        data = []
        for r in page_rows:
            cands = by_stub.get(r.provisional_entity_id, [])
            if not cands:
                continue
            name, etype, mc = stub_meta.get(r.provisional_entity_id, (r.provisional_entity_id, "person", 0))
            data.append(
                EntityMergeGroup(
                    dataset_id=r.dataset_id,
                    provisional_entity_id=r.provisional_entity_id,
                    provisional_name=name,
                    provisional_entity_type=str(etype),
                    mention_count=int(mc or 0),
                    status=r.st,
                    candidates=cands,
                )
            )
        return PaginatedEntityMergeGroupsResponse(total=total, page=request.page, limit=request.limit, data=data)

    async def list_for_name_group(self, *, dataset_id: str, normalized_value: str) -> list[EntityMatch]:
        """Every group-level candidate row for one name group, best score first."""
        rows = await self.session.execute(
            select(EntityMatchTable)
            .where(
                EntityMatchTable.dataset_id == dataset_id,
                EntityMatchTable.normalized_value == normalized_value,
                EntityMatchTable.mention_id.is_(None),
            )
            .order_by(desc(EntityMatchTable.similarity_score))
        )
        return [EntityMatch.model_validate(r) for r in rows.scalars().all()]

    async def list_match_groups(self, request: EntityMatchSearchParameters) -> PaginatedEntityMatchGroupsResponse:
        """Grouped review queue: one card per name group, best candidate + alternatives nested.

        The shape a fast bulk-annotation UI wants -- not N flat rows to group client-side.
        """
        base = [EntityMatchTable.mention_id.is_(None), EntityMatchTable.normalized_value.is_not(None)]
        if request.dataset_id:
            base.append(EntityMatchTable.dataset_id == request.dataset_id)
        if request.status:
            base.append(EntityMatchTable.status == request.status)
        if request.min_similarity is not None:
            base.append(EntityMatchTable.similarity_score >= request.min_similarity)
        unfiltered = list(base)  # before hiding provisional targets -- to report how many are hidden
        if not request.include_provisional_entities:
            base.append(EntityMatchTable.entity_id.in_(select(EntityTable.id).where(is_canonical_entity())))

        def _group_where(conditions: list) -> list:
            if not request.entity_id:
                return list(conditions)
            return [
                *conditions,
                EntityMatchTable.normalized_value.in_(
                    select(EntityMatchTable.normalized_value).where(
                        *conditions, EntityMatchTable.entity_id == request.entity_id
                    )
                ),
            ]

        group_where = _group_where(base)

        name_q = (
            select(
                EntityMatchTable.dataset_id,
                EntityMatchTable.normalized_value,
                func.max(EntityMatchTable.similarity_score).label("best"),
                func.coalesce(func.max(EntityMatchTable.mention_count), 0).label("mc"),
                func.min(EntityMatchTable.status).label("st"),
            )
            .where(*group_where)
            .group_by(EntityMatchTable.dataset_id, EntityMatchTable.normalized_value)
        )
        total = (await self.session.execute(select(func.count()).select_from(name_q.subquery()))).scalar_one()
        hidden_provisional = 0
        if not request.include_provisional_entities:
            everything = (
                select(EntityMatchTable.normalized_value)
                .where(*_group_where(unfiltered))
                .group_by(EntityMatchTable.dataset_id, EntityMatchTable.normalized_value)
            )
            hidden_provisional = (
                await self.session.execute(select(func.count()).select_from(everything.subquery()))
            ).scalar_one() - total

        order = desc("mc") if request.sort_by == EntityMatchSortField.DATE_CREATED else desc("best")
        page_rows = (
            await self.session.execute(
                name_q.order_by(order).offset((request.page - 1) * request.limit).limit(request.limit)
            )
        ).all()
        names = [r.normalized_value for r in page_rows]
        if not names:
            return PaginatedEntityMatchGroupsResponse(
                total=total, page=request.page, limit=request.limit, data=[], hidden_provisional_total=hidden_provisional
            )

        cand_rows = (
            await self.session.execute(
                select(
                    EntityMatchTable,
                    EntityTable.display_name,
                    EntityTable.entity_type,
                    EntityTable.person_id,
                    is_canonical_entity().label("canonical"),
                )
                .join(EntityTable, EntityTable.id == EntityMatchTable.entity_id)
                .where(*base, EntityMatchTable.normalized_value.in_(names))
                .order_by(desc(EntityMatchTable.similarity_score))
            )
        ).all()
        pending_merges = await self._pending_merge_counts(
            {row.entity_id for row, *_, canonical in cand_rows if not canonical}
        )
        by_name: dict[str, list[EntityMatch]] = defaultdict(list)
        for row, display_name, etype, person_id, canonical in cand_rows:
            if row.normalized_value is not None:
                m = EntityMatch.model_validate(row)
                m = m.model_copy(
                    update={
                        "entity_name": display_name,
                        "entity_type": str(etype) if etype is not None else None,
                        "entity_person_id": str(person_id) if person_id is not None else None,
                        "entity_is_provisional": not canonical,
                        "entity_pending_merge_count": None if canonical else pending_merges.get(row.entity_id, 0),
                    }
                )
                by_name[row.normalized_value].append(m)

        # one query for a representative surface form + file count per name
        surf_rows = (
            await self.session.execute(
                select(
                    MentionTable.normalized_value,
                    func.mode().within_group(MentionTable.surface_text).label("surface"),
                    func.count(func.distinct(MentionTable.file_id)).label("files"),
                )
                .where(
                    MentionTable.entity_attribute == "name",
                    MentionTable.normalized_value.in_(names),
                )
                .group_by(MentionTable.normalized_value)
            )
        ).all()
        surface = {r.normalized_value: (r.surface, r.files) for r in surf_rows}

        data = []
        for r in page_rows:
            cands = by_name.get(r.normalized_value, [])
            if not cands:
                continue
            surf, files = surface.get(r.normalized_value, (r.normalized_value, 0))
            data.append(
                EntityMatchGroup(
                    dataset_id=r.dataset_id,
                    normalized_value=r.normalized_value,
                    surface=surf or r.normalized_value,
                    mention_count=cands[0].mention_count or int(r.mc),
                    file_count=files or 0,
                    status=r.st,
                    top=cands[0],
                    alternatives=cands[1:],
                )
            )
        return PaginatedEntityMatchGroupsResponse(
            total=total, page=request.page, limit=request.limit, data=data, hidden_provisional_total=hidden_provisional
        )

    async def _pending_merge_counts(self, provisional_ids: set[str]) -> dict[str, int]:
        """`provisional entity id -> pending merge proposals` filed against it."""
        if not provisional_ids:
            return {}
        rows = await self.session.execute(
            select(EntityMatchTable.provisional_entity_id, func.count())
            .where(
                EntityMatchTable.provisional_entity_id.in_(provisional_ids),
                EntityMatchTable.status == EntityMatchStatus.PENDING,
            )
            .group_by(EntityMatchTable.provisional_entity_id)
        )
        return {pid: n for pid, n in rows.all()}

    async def get_match_by_id(self, match_id: str) -> EntityMatch | None:
        """Retrieve a candidate resolution by ID."""
        result = await self.session.execute(select(EntityMatchTable).where(EntityMatchTable.id == match_id))
        row = result.scalar_one_or_none()
        return EntityMatch.model_validate(row) if row else None

    async def list_matches(self, request: EntityMatchSearchParameters) -> PaginatedEntityMatchesResponse:
        """Query the resolution review queue."""
        where = []
        if request.entity_id:
            where.append(EntityMatchTable.entity_id == request.entity_id)
        if request.mention_id:
            where.append(EntityMatchTable.mention_id == request.mention_id)
        if request.dataset_id:
            where.append(EntityMatchTable.dataset_id == request.dataset_id)
        if request.status:
            where.append(EntityMatchTable.status == request.status)
        if request.min_similarity is not None:
            where.append(EntityMatchTable.similarity_score >= request.min_similarity)

        count_result = await self.session.execute(select(func.count(EntityMatchTable.id)).where(*where))
        total = count_result.scalar_one()

        sort_column = {
            EntityMatchSortField.DATE_CREATED: EntityMatchTable.date_created,
            EntityMatchSortField.SIMILARITY_SCORE: EntityMatchTable.similarity_score,
        }[request.sort_by]
        order = desc(sort_column) if request.sort_order == SortOrder.DESC else asc(sort_column)

        stmt = (
            select(EntityMatchTable)
            .where(*where)
            .order_by(order)
            .offset((request.page - 1) * request.limit)
            .limit(request.limit)
        )
        result = await self.session.execute(stmt)
        data = [EntityMatch.model_validate(m) for m in result.scalars().all()]
        return PaginatedEntityMatchesResponse(total=total, page=request.page, limit=request.limit, data=data)

    async def _apply_decision(
        self, match_id: str, *, status: EntityMatchStatus, reviewed_by: str, review_note: str | None
    ) -> EntityMatchTable | None:
        """Apply one confirm/reject (no commit). Confirming also attaches + rejects siblings."""
        now = datetime.now(UTC)
        row = (
            await self.session.execute(
                update(EntityMatchTable)
                .where(EntityMatchTable.id == match_id)
                .values(
                    status=status,
                    reviewed_by=reviewed_by,
                    reviewed_at=now,
                    review_note=review_note,
                    decision_source=DecisionSource.ANALYST.value,
                )
                .returning(EntityMatchTable)
            )
        ).scalar_one_or_none()
        if row is None:
            return None

        if status != EntityMatchStatus.CONFIRMED:
            return row

        sibling_stamp = {
            "status": EntityMatchStatus.REJECTED.value,
            "reviewed_by": reviewed_by,
            "reviewed_at": now,
            "decision_source": DecisionSource.SIBLING_AUTO.value,
        }
        if row.mention_id:
            await self.session.execute(
                update(MentionTable).where(MentionTable.id == row.mention_id).values(entity_id=row.entity_id)
            )
            await self.session.execute(
                update(EntityMatchTable)
                .where(
                    EntityMatchTable.mention_id == row.mention_id,
                    EntityMatchTable.id != match_id,
                    EntityMatchTable.status == EntityMatchStatus.PENDING,
                )
                .values(**sibling_stamp)
            )
        elif row.normalized_value:
            await self.session.execute(
                update(MentionTable)
                .where(
                    MentionTable.dataset_id == row.dataset_id,
                    MentionTable.entity_id.is_(None),
                    MentionTable.entity_attribute == "name",
                    MentionTable.normalized_value == row.normalized_value,
                )
                .values(entity_id=row.entity_id)
            )
            await self.session.execute(
                update(EntityMatchTable)
                .where(
                    EntityMatchTable.dataset_id == row.dataset_id,
                    EntityMatchTable.normalized_value == row.normalized_value,
                    EntityMatchTable.mention_id.is_(None),
                    EntityMatchTable.id != match_id,
                    EntityMatchTable.status == EntityMatchStatus.PENDING,
                )
                .values(**sibling_stamp)
            )
        if row.provisional_entity_id and row.provisional_entity_id != row.entity_id:
            # other merge proposals for this stub are moot once it's gone
            await self.session.execute(
                delete(EntityMatchTable).where(
                    EntityMatchTable.provisional_entity_id == row.provisional_entity_id,
                    EntityMatchTable.id != match_id,
                )
            )
            await self._merge(canonical_id=row.entity_id, provisional_id=row.provisional_entity_id)
        return row

    async def reopen_match(self, match_id: str) -> EntityMatch | None:
        """Undo a confirmation: back to pending, its mentions unresolved, auto-rejected siblings reopened.

        For a wrong auto-confirmation found after the fact -- it returns to the Resolve
        queue for an analyst to decide, instead of being silently flipped.
        """
        row = (
            await self.session.execute(
                update(EntityMatchTable)
                .where(EntityMatchTable.id == match_id, EntityMatchTable.status == EntityMatchStatus.CONFIRMED)
                .values(status=EntityMatchStatus.PENDING, reviewed_by=None, reviewed_at=None, decision_source=None)
                .returning(EntityMatchTable)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.mention_id:
            mentions = MentionTable.id == row.mention_id
            siblings = EntityMatchTable.mention_id == row.mention_id
        else:
            mentions = and_(
                MentionTable.dataset_id == row.dataset_id,
                MentionTable.entity_attribute == "name",
                MentionTable.normalized_value == row.normalized_value,
            )
            siblings = and_(
                EntityMatchTable.dataset_id == row.dataset_id,
                EntityMatchTable.normalized_value == row.normalized_value,
                EntityMatchTable.mention_id.is_(None),
            )
        await self.session.execute(
            update(MentionTable).where(mentions, MentionTable.entity_id == row.entity_id).values(entity_id=None)
        )
        await self.session.execute(
            update(EntityMatchTable)
            .where(
                siblings,
                EntityMatchTable.id != match_id,
                EntityMatchTable.decision_source == DecisionSource.SIBLING_AUTO.value,
            )
            .values(status=EntityMatchStatus.PENDING, reviewed_by=None, reviewed_at=None, decision_source=None)
        )
        await self.session.commit()
        return EntityMatch.model_validate(row)

    async def resolve_match(self, match_id: str, review: EntityMatchReview) -> EntityMatch | None:
        """Confirm or reject one candidate. On confirm: attach + merge provisional + reject siblings."""
        row = await self._apply_decision(
            match_id, status=review.status, reviewed_by=review.reviewed_by, review_note=review.review_note
        )
        await self.session.commit()
        return EntityMatch.model_validate(row) if row is not None else None

    async def resolve_matches_batch(self, *, reviewed_by: str, decisions: list[EntityMatchBatchItem]) -> dict[str, int]:
        """Apply many confirm/reject decisions in one transaction (fast bulk annotation)."""
        counts = {"confirmed": 0, "rejected": 0, "not_found": 0}
        for item in decisions:
            row = await self._apply_decision(
                item.match_id, status=item.status, reviewed_by=reviewed_by, review_note=item.review_note
            )
            if row is None:
                counts["not_found"] += 1
            else:
                counts["confirmed" if item.status == EntityMatchStatus.CONFIRMED else "rejected"] += 1
        await self.session.commit()
        return counts

    async def dismiss_name_group(
        self, *, dataset_id: str, normalized_value: str, reviewed_by: str, review_note: str | None = None
    ) -> int:
        """'None of these' -- reject every pending group-level row for a name. Returns rows rejected."""
        result = await self.session.execute(
            update(EntityMatchTable)
            .where(
                EntityMatchTable.dataset_id == dataset_id,
                EntityMatchTable.normalized_value == normalized_value,
                EntityMatchTable.mention_id.is_(None),
                EntityMatchTable.status == EntityMatchStatus.PENDING,
            )
            .values(
                status=EntityMatchStatus.REJECTED.value,
                reviewed_by=reviewed_by,
                reviewed_at=datetime.now(UTC),
                review_note=review_note,
                decision_source=DecisionSource.ANALYST.value,
            )
        )
        await self.session.commit()
        return result.rowcount or 0

    async def _merge(self, *, canonical_id: str, provisional_id: str) -> None:
        """Fold a provisional entity into the canonical one, keeping its name as an alias."""
        await fold_entity(self.session, source_id=provisional_id, target_id=canonical_id)

    async def delete_by_dataset_id(self, dataset_id: str) -> int:
        """Delete all candidate resolutions for a dataset (used by reset-entities)."""
        result = await self.session.execute(delete(EntityMatchTable).where(EntityMatchTable.dataset_id == dataset_id))
        await self.session.commit()
        return result.rowcount or 0
