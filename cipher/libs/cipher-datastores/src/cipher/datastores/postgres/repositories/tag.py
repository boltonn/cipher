"""Tag repository -- the one write path for tags.

Every decision is a `tag` row (who or what, label and/or score, when). After each
write the affected targets' read copies (`tags` / `negative_tags` / `tag_scores` on image, file,
entity, event, and the person / location mirrors of an entity) are rebuilt from those rows:
the most recent label for a tag wins, and the most recent model score per tag is kept.
"""

from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import array, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.event import EventTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.image import ImageTable
from cipher.datastores.postgres.tables.location import LocationTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.datastores.postgres.tables.tag import TagTable
from cipher.datastores.postgres.tables.user import UserTable
from cipher.schemas._base.common import ModelTagType
from cipher.schemas.interaction.tag import TagPublic, TagSource, TagSourceType, TagTargetType

# Per target: the latest label per tag split into positive / negative lists, and the latest score per tag.
PROJECTION_CTE = """
WITH ids AS (SELECT unnest(cast(:ids AS text[])) AS id),
labels AS (
    SELECT DISTINCT ON (target_id, tag) target_id, tag, label FROM tag
    WHERE target_type = :target_type AND target_id = ANY(cast(:ids AS text[])) AND label IS NOT NULL
    ORDER BY target_id, tag, date_updated DESC
),
scores AS (
    SELECT DISTINCT ON (target_id, tag) target_id, tag, score FROM tag
    WHERE target_type = :target_type AND target_id = ANY(cast(:ids AS text[])) AND score IS NOT NULL
    ORDER BY target_id, tag, date_updated DESC
),
proj AS (
    SELECT ids.id,
        coalesce((SELECT jsonb_agg(l.tag ORDER BY l.tag) FROM labels l
                  WHERE l.target_id = ids.id AND l.label = 'POSITIVE'), '[]'::jsonb) AS tags,
        coalesce((SELECT jsonb_agg(l.tag ORDER BY l.tag) FROM labels l
                  WHERE l.target_id = ids.id AND l.label = 'NEGATIVE'), '[]'::jsonb) AS negative_tags,
        coalesce((SELECT jsonb_object_agg(s.tag, s.score) FROM scores s
                  WHERE s.target_id = ids.id), '{}'::jsonb) AS tag_scores
    FROM ids
)
"""

PROJECTION_UPDATES: dict[TagTargetType, list[str]] = {
    TagTargetType.CONTENT: [
        "UPDATE image t SET tags = p.tags, negative_tags = p.negative_tags, tag_scores = p.tag_scores "
        "FROM proj p WHERE t.id = p.id",
        "UPDATE file t SET tags = p.tags, negative_tags = p.negative_tags, tag_scores = p.tag_scores "
        "FROM proj p WHERE t.sha256 = p.id",
    ],
    TagTargetType.ENTITY: [
        "UPDATE entity t SET tags = p.tags FROM proj p WHERE t.id = p.id",
        "UPDATE person t SET tags = p.tags FROM proj p JOIN entity e ON e.id = p.id WHERE t.id = e.person_id",
        "UPDATE location t SET tags = p.tags FROM proj p JOIN entity e ON e.id = p.id WHERE t.id = e.location_id",
    ],
    TagTargetType.EVENT: ["UPDATE event t SET tags = p.tags FROM proj p WHERE t.id = p.id"],
}


_INSERT_CHUNK = 4000  # rows x 7 columns per INSERT

_MIRROR_COLUMNS: dict[type, list[str]] = {
    ImageTable: ["tags", "negative_tags", "tag_scores"],
    FileTable: ["tags", "negative_tags", "tag_scores"],
    EntityTable: ["tags"],
    PersonTable: ["tags"],
    LocationTable: ["tags"],
    EventTable: ["tags"],
}


class PostgresTagRepository:
    """Records tag decisions with their source and keeps the denormalized tag columns in sync."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def label(
        self,
        *,
        target_type: TagTargetType,
        target_ids: list[str],
        tag: str,
        label: ModelTagType | None,
        source: TagSource,
        commit: bool = True,
    ) -> None:
        """Label targets positive / negative as `source`; `None` removes the tag's label from every source."""
        if not target_ids:
            return
        if label is None:
            await self._clear_labels(target_type=target_type, target_ids=target_ids, tag=tag)
        else:
            now = datetime.now(UTC)
            rows = [
                {
                    "target_type": target_type,
                    "target_id": target_id,
                    "tag": tag,
                    "label": label,
                    "source_type": source.type,
                    "source_name": source.name,
                    "date_updated": now,
                }
                for target_id in dict.fromkeys(target_ids)
            ]
            stmt = pg_insert(TagTable).values(rows)
            await self.session.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_tag",
                    set_={"label": stmt.excluded.label, "date_updated": stmt.excluded.date_updated},
                )
            )
        await self.refresh(target_type=target_type, target_ids=target_ids)
        if commit:
            await self.session.commit()

    async def score(self, *, target_type: TagTargetType, tag: str, scores: dict[str, float], model: str) -> None:
        """Record a model's confidence that `tag` applies, keyed by target id."""
        if not scores:
            return
        now = datetime.now(UTC)
        stmt = pg_insert(TagTable).values(
            [
                {
                    "target_type": target_type,
                    "target_id": target_id,
                    "tag": tag,
                    "score": score,
                    "source_type": TagSourceType.MODEL,
                    "source_name": model,
                    "date_updated": now,
                }
                for target_id, score in scores.items()
            ]
        )
        await self.session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_tag",
                set_={"score": stmt.excluded.score, "date_updated": stmt.excluded.date_updated},
            )
        )
        await self.refresh(target_type=target_type, target_ids=list(scores))
        await self.session.commit()

    async def replace_scores(
        self,
        *,
        target_type: TagTargetType,
        target_ids: list[str],
        scores: dict[str, dict[str, float]],
        model: str,
        replaces: str,
    ) -> None:
        """Swap a model family's scores on these targets for a new version's, in one write + one refresh.

        Rows from any `source_name` starting with `replaces` (e.g. `setfitcv-heads:`) for these targets and
        tags are dropped first, so a target the new version scores below its floor loses the stale score.
        `scores` is `{tag: {target_id: score}}`.
        """
        if not target_ids:
            return
        await self.session.execute(
            delete(TagTable).where(
                TagTable.target_type == target_type,
                TagTable.target_id.in_(target_ids),
                TagTable.tag.in_(list(scores)),
                TagTable.source_type == TagSourceType.MODEL,
                TagTable.source_name.startswith(replaces),
            )
        )
        now = datetime.now(UTC)
        rows = [
            {
                "target_type": target_type,
                "target_id": target_id,
                "tag": tag,
                "score": score,
                "source_type": TagSourceType.MODEL,
                "source_name": model,
                "date_updated": now,
            }
            for tag, by_target in scores.items()
            for target_id, score in by_target.items()
        ]
        for start in range(0, len(rows), _INSERT_CHUNK):  # stays under Postgres' bind-parameter limit
            await self.session.execute(pg_insert(TagTable).values(rows[start : start + _INSERT_CHUNK]))
        await self.refresh(target_type=target_type, target_ids=target_ids)
        await self.session.commit()

    async def set_tags(
        self,
        *,
        target_type: TagTargetType,
        target_id: str,
        tags: list[str],
        source: TagSource,
    ) -> None:
        """Make a target's positive tags exactly `tags` (a free-form tag list edit), recording only the changes."""
        current = set(await self._positive_tags(target_type=target_type, target_id=target_id))
        wanted = {tag.strip() for tag in tags if tag.strip()}
        for tag in sorted(wanted - current):
            await self.label(
                target_type=target_type,
                target_ids=[target_id],
                tag=tag,
                label=ModelTagType.POSITIVE,
                source=source,
            )
        for tag in sorted(current - wanted):
            await self.label(
                target_type=target_type,
                target_ids=[target_id],
                tag=tag,
                label=None,
                source=source,
            )

    async def list_for_target(self, *, target_type: TagTargetType, target_id: str) -> list[TagPublic]:
        """Every source's decision on a target, newest first, with users' display names."""
        result = await self.session.execute(
            select(TagTable, UserTable.name)
            .outerjoin(
                UserTable,
                and_(
                    TagTable.source_type == TagSourceType.USER,
                    UserTable.id == TagTable.source_name,
                ),
            )
            .where(TagTable.target_type == target_type, TagTable.target_id == target_id)
            .order_by(TagTable.date_updated.desc())
        )
        return [
            TagPublic.model_validate({**row.__dict__, "source_display_name": user_name or row.source_name})
            for row, user_name in result.all()
        ]

    async def label_authors(
        self, *, target_type: TagTargetType, target_ids: list[str], tag: str, exclude_user_id: str
    ) -> list[str]:
        """Names of the other users holding a label for `tag` on these targets -- what a clear would remove."""
        result = await self.session.execute(
            select(UserTable.name)
            .join(TagTable, UserTable.id == TagTable.source_name)
            .where(
                TagTable.target_type == target_type,
                TagTable.target_id.in_(target_ids),
                TagTable.tag == tag,
                TagTable.label.is_not(None),
                TagTable.source_type == TagSourceType.USER,
                TagTable.source_name != exclude_user_id,
            )
            .distinct()
            .order_by(UserTable.name)
        )
        return list(result.scalars().all())

    async def names(self, *, target_type: TagTargetType, query: str | None = None, limit: int = 50) -> list[str]:
        """Tag names in use on this kind of target, most used first, optionally containing `query`."""
        stmt = select(TagTable.tag).where(TagTable.target_type == target_type)
        if query:
            stmt = stmt.where(TagTable.tag.icontains(query, autoescape=True))
        result = await self.session.execute(
            stmt.group_by(TagTable.tag).order_by(func.count().desc(), TagTable.tag).limit(limit)
        )
        return list(result.scalars().all())

    async def file_tags(self, file_ids: list[str]) -> dict[str, list[str]]:
        """Current positive tags of these files (their content's), for decorating search results."""
        if not file_ids:
            return {}
        rows = await self.session.execute(
            select(FileTable.id, FileTable.tags).where(FileTable.id.in_(list(dict.fromkeys(file_ids))))
        )
        return dict(rows.tuples().all())

    async def tagged_content(self, tags: list[str]) -> list[str]:
        """sha256s of content carrying any of these positive tags (GIN-indexed on `image.tags` / `file.tags`)."""
        rows = await self.session.execute(
            select(FileTable.sha256).where(FileTable.tags.has_any(array(tags))).distinct()
        )
        return list(rows.scalars().all())

    async def retarget(self, *, target_type: TagTargetType, source_id: str, target_id: str) -> None:
        """Move one target's tags onto another (an entity merge); the target's own decisions win on conflict.

        Doesn't commit -- it runs inside the caller's merge transaction.
        """
        await self.session.execute(
            text(
                "UPDATE tag a SET target_id = :target_id WHERE target_type = :target_type "
                "AND target_id = :source_id AND NOT EXISTS (SELECT 1 FROM tag b "
                "WHERE b.target_type = a.target_type AND b.target_id = :target_id AND b.tag = a.tag "
                "AND b.source_type = a.source_type AND b.source_name = a.source_name)"
            ),
            {"target_type": target_type.name, "source_id": source_id, "target_id": target_id},
        )
        await self.delete_for_targets(target_type=target_type, target_ids=[source_id])
        await self.refresh(target_type=target_type, target_ids=[target_id])

    async def delete_for_targets(self, *, target_type: TagTargetType, target_ids: list[str]) -> None:
        """Purge the tags of deleted targets (no FK -- `target_id` is polymorphic). Caller commits."""
        await self.session.execute(
            delete(TagTable).where(TagTable.target_type == target_type, TagTable.target_id.in_(target_ids))
        )

    async def refresh(self, *, target_type: TagTargetType, target_ids: list[str]) -> None:
        """Rebuild the denormalized tag columns of these targets from their `tag` rows. Caller commits."""
        params = {"ids": list(dict.fromkeys(target_ids)), "target_type": target_type.name}
        for statement in PROJECTION_UPDATES[target_type]:
            await self.session.execute(text(PROJECTION_CTE + statement), params)
        # Raw UPDATEs bypass the ORM: expire the tag columns of rows already loaded in this session
        # so the next read sees the new tags (only those columns -- callers may still hold the rows).
        for row in list(self.session.identity_map.values()):
            columns = _MIRROR_COLUMNS.get(type(row))
            if columns:
                self.session.expire(row, columns)

    async def _clear_labels(self, *, target_type: TagTargetType, target_ids: list[str], tag: str) -> None:
        scope = (
            TagTable.target_type == target_type,
            TagTable.target_id.in_(target_ids),
            TagTable.tag == tag,
        )
        await self.session.execute(update(TagTable).where(*scope).values(label=None))
        await self.session.execute(delete(TagTable).where(*scope, TagTable.score.is_(None)))

    async def _positive_tags(self, *, target_type: TagTargetType, target_id: str) -> list[str]:
        rows = await self.session.execute(
            text(PROJECTION_CTE + "SELECT tags FROM proj"),
            {"ids": [target_id], "target_type": target_type.name},
        )
        return rows.scalar_one()
