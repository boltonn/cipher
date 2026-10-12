"""Compute and read `dataset_profile` rows -- the empty-query search briefing (docs/global-search.md §6)."""

from collections import Counter
from datetime import UTC, datetime
from itertools import zip_longest

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.dataset_profile import DatasetProfileTable
from cipher.schemas.content.results import MonthCount
from cipher.schemas.ingestion.dataset_profile import (
    DEFAULT_BULK_MESSAGE_STATES,
    DEFAULT_BULK_SOURCE_TAGS,
    PROFILE_VERSION,
    DatasetProfile,
    ProfileCorrespondent,
    ProfileEntity,
)

TOP_N = 200
IMAGE_SAMPLE_SIZE = 24
_IMAGE_POOL = 2_000
BULK_SENDER_SHARE = 0.9
_ENTITY_LISTS = {"PERSON": "top_people_orgs", "ORGANIZATION": "top_people_orgs", "SELECTOR": "top_selectors"}

# Mentions per entity over the dataset's non-bulk files, ranked within each list
# (people + orgs together, selectors, places). Bulk = the data's own categories
# (Gmail promotions/updates/...): newsletters otherwise outrank every real person.
_TOP_ENTITIES_SQL = """
WITH bulk AS (
    SELECT id FROM file
    WHERE dataset_id = :ds AND (source_tags ?| cast(:bulk_tags AS text[]) OR message_states ?| cast(:bulk_states AS text[]))
),
counts AS (
    SELECT e.id, e.display_name, e.entity_type, count(DISTINCT m.file_id) AS files
    FROM mention m
    JOIN entity e ON e.id = m.entity_id
    LEFT JOIN bulk b ON b.id = m.file_id
    WHERE m.dataset_id = :ds AND m.file_id IS NOT NULL AND b.id IS NULL
    GROUP BY e.id, e.display_name, e.entity_type
)
SELECT id, display_name, entity_type, files FROM (
    SELECT *, row_number() OVER (
        PARTITION BY CASE WHEN entity_type IN ('PERSON', 'ORGANIZATION') THEN 'PERSON' ELSE entity_type END
        ORDER BY files DESC, display_name
    ) AS rank
    FROM counts
) ranked
WHERE rank <= :top
"""

_DATE_HISTOGRAM_SQL = """
SELECT to_char(date_trunc('month', first_date), 'YYYY-MM') AS month, count(*) AS files
FROM (SELECT min(date_content) AS first_date FROM chunk WHERE dataset_id = :ds AND NOT is_summary AND date_content IS NOT NULL GROUP BY file_id) per_file
GROUP BY 1 ORDER BY 1
"""

# `emailed` edges don't record their files, so drop senders that are (almost) only in bulk mail --
# Gmail files a few newsletter emails as `personal`, so "only" is too strict.
_CORRESPONDENTS_SQL = """
WITH bulk AS (
    SELECT id FROM file
    WHERE dataset_id = :ds AND (source_tags ?| cast(:bulk_tags AS text[]) OR message_states ?| cast(:bulk_states AS text[]))
),
bulk_only AS (
    SELECT m.entity_id FROM mention m LEFT JOIN bulk b ON b.id = m.file_id
    WHERE m.dataset_id = :ds AND m.entity_id IS NOT NULL
    GROUP BY m.entity_id HAVING avg((b.id IS NOT NULL)::int) >= :bulk_sender_share
)
SELECT r.src_entity_id, s.display_name AS src_name, r.dst_entity_id, d.display_name AS dst_name, r.weight
FROM entity_relationship r
JOIN entity s ON s.id = r.src_entity_id
JOIN entity d ON d.id = r.dst_entity_id
LEFT JOIN bulk_only bo ON bo.entity_id = r.src_entity_id
WHERE r.dataset_id = :ds AND r.relationship_type = 'EMAILED' AND bo.entity_id IS NULL
ORDER BY r.weight DESC NULLS LAST
LIMIT 100
"""


class PostgresDatasetProfileRepository:
    """Compute one dataset's profile (batch-time), and read one or several merged (request-time)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def compute(
        self,
        *,
        dataset_id: str,
        bulk_source_tags: tuple[str, ...] = DEFAULT_BULK_SOURCE_TAGS,
        bulk_message_states: tuple[str, ...] = DEFAULT_BULK_MESSAGE_STATES,
    ) -> DatasetProfile:
        """Recompute and store `dataset_id`'s profile from scratch."""
        ds = {"ds": dataset_id}
        groups = await self._pairs("SELECT filetype_group, count(*) FROM file WHERE dataset_id = :ds GROUP BY 1", ds)
        languages = await self._pairs(
            "SELECT language, count(DISTINCT file_id) FROM chunk WHERE dataset_id = :ds AND NOT is_summary AND language IS NOT NULL "
            "GROUP BY 1",
            ds,
        )
        chunk_count = (
            await self.session.execute(text("SELECT count(*) FROM chunk WHERE dataset_id = :ds AND NOT is_summary"), ds)
        ).scalar()
        months = (await self.session.execute(text(_DATE_HISTOGRAM_SQL), ds)).all()
        bulk = {"bulk_tags": list(bulk_source_tags), "bulk_states": list(bulk_message_states)}
        ranked = await self.session.execute(text(_TOP_ENTITIES_SQL), {**ds, **bulk, "top": TOP_N})
        lists: dict[str, list[dict]] = {"top_people_orgs": [], "top_selectors": [], "top_places": []}
        for row in ranked.mappings():
            entity = ProfileEntity(
                entity_id=row["id"],
                display_name=row["display_name"],
                entity_type=row["entity_type"].lower(),
                files=row["files"],
            )
            lists[_ENTITY_LISTS.get(row["entity_type"], "top_places")].append(entity.model_dump(mode="json"))
        for entities in lists.values():
            entities.sort(key=lambda entity: -entity["files"])
        correspondents = [
            ProfileCorrespondent(
                src_entity_id=row.src_entity_id,
                src_name=row.src_name,
                dst_entity_id=row.dst_entity_id,
                dst_name=row.dst_name,
                emails=int(row.weight or 0),
            ).model_dump(mode="json")
            for row in await self.session.execute(
                text(_CORRESPONDENTS_SQL), {**ds, **bulk, "bulk_sender_share": BULK_SENDER_SHARE}
            )
        ]
        values = {
            "profile_version": PROFILE_VERSION,
            "file_count": sum(groups.values()),
            "chunk_count": chunk_count,
            "filetype_group_counts": groups,
            "language_counts": languages,
            "date_histogram": [{"month": month, "files": files} for month, files in months],
            **lists,
            "top_correspondents": correspondents,
            "image_sample_ids": await self._spread_image_sample(dataset_id),
            "date_computed": datetime.now(UTC),
        }
        await self.session.execute(
            pg_insert(DatasetProfileTable)
            .values(dataset_id=dataset_id, **values)
            .on_conflict_do_update(index_elements=[DatasetProfileTable.dataset_id], set_=values)
        )
        await self.session.commit()
        return await self.get_merged(dataset_ids=[dataset_id])

    async def get_merged(self, *, dataset_ids: list[str] | None) -> DatasetProfile:
        """The profiles of `dataset_ids` (None = every dataset) combined: counts summed, top lists re-ranked."""
        existing = text("SELECT id FROM dataset" + ("" if dataset_ids is None else " WHERE id = ANY(:ids)"))
        dataset_ids = list((await self.session.execute(existing, {"ids": dataset_ids or []})).scalars())
        rows = (
            (
                await self.session.execute(
                    select(DatasetProfileTable).where(DatasetProfileTable.dataset_id.in_(dataset_ids))
                )
            )
            .scalars()
            .all()
        )
        profiled = {row.dataset_id for row in rows}
        months: Counter[str] = Counter()
        groups: Counter[str] = Counter()
        languages: Counter[str] = Counter()
        for row in rows:
            groups.update(row.filetype_group_counts)
            languages.update(row.language_counts)
            months.update({bucket["month"]: bucket["files"] for bucket in row.date_histogram})
        return DatasetProfile(
            dataset_ids=sorted(profiled),
            file_count=sum(row.file_count for row in rows),
            chunk_count=sum(row.chunk_count for row in rows),
            filetype_group_counts=dict(groups.most_common()),
            language_counts=dict(languages.most_common()),
            date_histogram=[MonthCount(month=month, files=files) for month, files in sorted(months.items())],
            top_people_orgs=_merge_entities(row.top_people_orgs for row in rows),
            top_selectors=_merge_entities(row.top_selectors for row in rows),
            top_places=_merge_entities(row.top_places for row in rows),
            top_correspondents=_merge_correspondents(row.top_correspondents for row in rows),
            image_sample_ids=_round_robin([row.image_sample_ids for row in rows])[:IMAGE_SAMPLE_SIZE],
            unprofiled_dataset_ids=sorted(set(dataset_ids) - profiled),
            date_computed=min((row.date_computed for row in rows), default=None),
        )

    async def get_brief(self, dataset_id: str) -> dict | None:
        """The saved AI brief; kept across profile recomputes until someone regenerates it."""
        statement = select(DatasetProfileTable.brief).where(DatasetProfileTable.dataset_id == dataset_id)
        return (await self.session.execute(statement)).scalar()

    async def save_brief(self, dataset_id: str, brief: dict) -> None:
        """Cache the AI brief on the profile row."""
        statement = update(DatasetProfileTable).where(DatasetProfileTable.dataset_id == dataset_id).values(brief=brief)
        await self.session.execute(statement)
        await self.session.commit()

    async def _pairs(self, sql: str, params: dict) -> dict[str, int]:
        return {key: count for key, count in (await self.session.execute(text(sql), params)).all()}

    async def _spread_image_sample(self, dataset_id: str) -> list[str]:
        """Images spread across CLIP space: greedy farthest-point picks from a random pool."""
        await self.session.execute(text("DROP TABLE IF EXISTS profile_image_pool"))
        await self.session.execute(
            text(
                "CREATE TEMP TABLE profile_image_pool AS SELECT i.id, i.embedding FROM image i "
                "WHERE i.embedding IS NOT NULL AND EXISTS ("
                "  SELECT 1 FROM file f WHERE f.sha256 = i.id AND f.dataset_id = :ds AND f.filetype_group = 'image') "
                "ORDER BY random() LIMIT :pool"
            ),
            {"ds": dataset_id, "pool": _IMAGE_POOL},
        )
        first = (await self.session.execute(text("SELECT id FROM profile_image_pool LIMIT 1"))).scalar()
        chosen = [first] if first else []
        while chosen and len(chosen) < IMAGE_SAMPLE_SIZE:
            farthest = (
                await self.session.execute(
                    text(
                        "SELECT p.id FROM profile_image_pool p WHERE p.id <> ALL(cast(:chosen AS text[])) "
                        "ORDER BY (SELECT min(p.embedding <=> c.embedding) FROM profile_image_pool c "
                        "          WHERE c.id = ANY(cast(:chosen AS text[]))) DESC LIMIT 1"
                    ),
                    {"chosen": chosen},
                )
            ).scalar()
            if farthest is None:
                break
            chosen.append(farthest)
        await self.session.execute(text("DROP TABLE profile_image_pool"))
        return chosen


def _round_robin(lists: list[list[str]]) -> list[str]:
    """One from each dataset in turn, so a merged sample shows every dataset, not just the first."""
    return [item for group in zip_longest(*lists) for item in group if item is not None]


def _merge_entities(lists) -> list[ProfileEntity]:
    files: Counter[str] = Counter()
    first_seen: dict[str, dict] = {}
    for entities in lists:
        for entity in entities:
            files[entity["entity_id"]] += entity["files"]
            first_seen.setdefault(entity["entity_id"], entity)
    return [
        ProfileEntity.model_validate({**first_seen[entity_id], "files": count})
        for entity_id, count in files.most_common(TOP_N)
    ]


def _merge_correspondents(lists) -> list[ProfileCorrespondent]:
    emails: Counter[tuple[str, str]] = Counter()
    first_seen: dict[tuple[str, str], dict] = {}
    for edges in lists:
        for edge in edges:
            key = (edge["src_entity_id"], edge["dst_entity_id"])
            emails[key] += edge["emails"]
            first_seen.setdefault(key, edge)
    return [
        ProfileCorrespondent.model_validate({**first_seen[key], "emails": count})
        for key, count in emails.most_common(100)
    ]
