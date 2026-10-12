"""Bring stored keys in line with the current normalization code: `cipher rekey`.

Names, the resolver's blocking index and selector values are all stored already
normalized. After changing the code that normalizes them, run this so existing rows
match what a fresh extraction would write -- otherwise old and new spellings of one
thing stop meeting. Three parts, each idempotent (a re-run finds nothing to change):

* **names** -- `normalize_name` (`cipher.datastores.postgres.utils`): re-keys name
  mentions, entity display keys and name-group resolutions, and trims quotes / a
  possessive off extracted name spans (`"Nick Bolton's"` -> `Nick Bolton`). Name-group
  resolutions that now collide keep the decided one (confirmed, then rejected, then the
  best-scoring pending). Follow with `resolve-entities`, whose same-names step folds
  auto-created duplicates the old keys made.
* **name keys** -- `cipher.names.entity_keys` (transliterated / phonetic / sorted-token /
  surname forms) into `entity_name_key`. Entity writes keep it current; this is for a
  cipher-names change. `purge` empties it first (a `KEYS_VERSION` bump).
* **selectors** -- pyselectors normalization, validation and attributes: refreshes each
  selector's `attributes` (merged over the stored ones) / `region_hint`, and when its value now normalizes differently
  (`(856)697-2400 ext 8200` -> `8566972400`) re-keys it -- folding it into the selector
  that already has the new value, else renaming it -- along with its mentions. A value
  that no longer validates is reported, not deleted. A phone keeps a region only when an
  analyst entered it (`source = manual`); one from extraction is never given a guessed country.
* **filetypes** (opt-in; reads every file) -- filetyper: re-types files (heuristics on the
  file's own name, magika refining generic text) and sets `compression` (`report.csv.gz`
  is a csv found gzipped) and `is_encrypted`. Hashes are untouched.
"""

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import and_, bindparam, delete, func, or_, select, text, update
from tqdm import tqdm

from cipher.datastores.postgres.repositories._merge import fold_entity
from cipher.datastores.postgres.repositories.enrichment import ENCRYPTED_SKIP, READS_ENCRYPTED
from cipher.datastores.postgres.repositories.entity_name_key import (
    EntityKeyInput,
    PostgresEntityNameKeyRepository,
)
from cipher.datastores.postgres.tables.enrichment import EnrichmentTable
from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.selector import SelectorTable
from cipher.datastores.postgres.utils import normalize_name, trim_name_span
from cipher.schemas.graph.ontology import EntitySource, EntityType, SelectorType
from cipher.schemas.ingestion.enrichment import EnrichableType, ProcessingStatus
from cipher.utils.uri import local_copy

if TYPE_CHECKING:
    from filetyper.models.main import FileTyper
    from sqlalchemy.ext.asyncio import AsyncSession

_STATUS_RANK = {"CONFIRMED": 0, "REJECTED": 1, "PENDING": 2}
_BATCH = 5000


async def _rekey(session: "AsyncSession", *, statement: str, pairs: list[tuple[str, str]], scope: dict) -> None:
    for start in range(0, len(pairs), _BATCH):
        chunk = pairs[start : start + _BATCH]
        await session.execute(
            text(statement), {"keys": [k for k, _ in chunk], "values": [v for _, v in chunk], **scope}
        )


async def rekey_names(
    session: "AsyncSession", *, dataset_id: str | None = None, dry_run: bool = False
) -> dict[str, int]:
    """Recompute name keys (and trim name spans) for one dataset, or all when `dataset_id` is None.

    Returns:
        dict: rows changed per table, plus name groups before / after.
    """
    scope = {"dataset_id": dataset_id}
    in_scope = "(CAST(:dataset_id AS varchar) IS NULL OR dataset_id = :dataset_id)"
    counts: dict[str, int] = {}

    # extracted spans written with their quotes or possessive
    spans = (
        await session.execute(
            text(
                f"SELECT id, surface_text, start_offset FROM mention WHERE {in_scope} AND entity_attribute = 'name' "
                "AND start_offset IS NOT NULL AND end_offset - start_offset = length(surface_text) "
                "AND surface_text ~ '^[''\"`‘’‚“”„«»‹›[:space:]]|[''\"`‘’‚“”„«»‹›[:space:]]$|[''’ʼ][sS]$'"
            ),
            scope,
        )
    ).all()
    trims = []
    for row in spans:
        lead, trail = trim_name_span(row.surface_text)
        if (lead, trail) != (0, len(row.surface_text)):
            trims.append(
                {
                    "id": row.id,
                    "surface": row.surface_text[lead:trail],
                    "start": row.start_offset + lead,
                    "end": row.start_offset + trail,
                }
            )
    if trims and not dry_run:
        await session.execute(
            text("UPDATE mention SET surface_text = :surface, start_offset = :start, end_offset = :end WHERE id = :id"),
            trims,
        )
    counts["spans_trimmed"] = len(trims)

    # a key written before `Surname, Given` was put in reading order lost its comma, so the
    # surface (not the stored key) says how to re-key it -- only when the key came from the surface
    commas = (
        await session.execute(
            text(
                f"SELECT id, surface_text, normalized_value FROM mention WHERE {in_scope} "
                "AND entity_attribute = 'name' AND position(',' IN surface_text) > 0"
            ),
            scope,
        )
    ).all()
    reordered = [
        {"id": row.id, "value": key}
        for row in commas
        if row.normalized_value == normalize_name(row.surface_text.replace(",", " "))
        and (key := normalize_name(row.surface_text)) != row.normalized_value
    ]
    if reordered and not dry_run:
        await session.execute(text("UPDATE mention SET normalized_value = :value WHERE id = :id"), reordered)
    counts["surname_first_rekeyed"] = len(reordered)

    names = (
        await session.execute(
            text(
                f"SELECT DISTINCT normalized_value FROM mention WHERE {in_scope} "
                "AND entity_attribute = 'name' AND normalized_value IS NOT NULL"
            ),
            scope,
        )
    ).scalars()
    renamed = [(old, new) for old in names if (new := normalize_name(old)) != old]
    entities = (
        await session.execute(
            text(f"SELECT id, display_name, display_name_normalized FROM entity WHERE {in_scope}"), scope
        )
    ).all()
    entity_keys = [
        (e.id, key) for e in entities if (key := normalize_name(e.display_name)[:512]) != e.display_name_normalized
    ]
    if dry_run:
        return {"spans_trimmed": len(trims), "name_values_rekeyed": len(renamed), "entities_rekeyed": len(entity_keys)}
    await _rekey(
        session,
        statement="UPDATE mention m SET normalized_value = r.value FROM unnest(CAST(:keys AS text[]), CAST(:values AS text[])) AS r(key, value) "
        "WHERE m.normalized_value = r.key AND m.entity_attribute = 'name' "
        "AND (CAST(:dataset_id AS varchar) IS NULL OR m.dataset_id = :dataset_id)",
        pairs=renamed,
        scope=scope,
    )
    counts["name_values_rekeyed"] = len(renamed)

    await _rekey(
        session,
        statement="UPDATE entity e SET display_name_normalized = r.value FROM unnest(CAST(:keys AS text[]), CAST(:values AS text[])) AS r(key, value) "
        "WHERE e.id = r.key",
        pairs=entity_keys,
        scope={},
    )
    counts["entities_rekeyed"] = len(entity_keys)

    counts.update(await _rekey_name_group_matches(session, in_scope=in_scope, scope=scope))
    await session.commit()
    return counts


async def _rekey_name_group_matches(session: "AsyncSession", *, in_scope: str, scope: dict) -> dict[str, int]:
    """Re-key name-group resolutions; where two now share (dataset, name, entity), keep the decided one."""
    rows = (
        await session.execute(
            text(
                f"SELECT id, dataset_id, normalized_value, entity_id, status, similarity_score FROM entity_match "
                f"WHERE {in_scope} AND mention_id IS NULL AND normalized_value IS NOT NULL"
            ),
            scope,
        )
    ).all()
    by_key = defaultdict(list)
    for row in rows:
        by_key[(row.dataset_id, normalize_name(row.normalized_value), row.entity_id)].append(row)
    drop, rekey = [], []
    for (_, key, _), group in by_key.items():
        keep, *rest = sorted(group, key=lambda r: (_STATUS_RANK.get(str(r.status), 3), -r.similarity_score))
        drop += [r.id for r in rest]
        if keep.normalized_value != key:
            rekey.append((keep.id, key))
    if drop:
        await session.execute(
            text("DELETE FROM entity_match WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
            {"ids": drop},
        )
    await _rekey(
        session,
        statement="UPDATE entity_match em SET normalized_value = r.value FROM unnest(CAST(:keys AS text[]), CAST(:values AS text[])) AS r(key, value) "
        "WHERE em.id = r.key",
        pairs=rekey,
        scope={},
    )
    return {"name_group_matches_rekeyed": len(rekey), "name_group_matches_merged": len(drop)}


_KEYED_TYPES = (EntityType.PERSON, EntityType.ORGANIZATION, EntityType.LOCATION)


async def rekey_name_keys(
    session: "AsyncSession",
    *,
    dataset_id: str | None = None,
    batch_size: int = 1000,
    purge: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    """Recompute `entity_name_key` for keyed entities. Returns per-outcome counts.

    Delete-then-insert per entity, so a re-run heals drift; `purge` (no dataset scope only)
    empties the index first, for a cipher-names `KEYS_VERSION` bump.
    """
    repo = PostgresEntityNameKeyRepository(session=session)
    if dry_run:
        query = select(func.count()).select_from(EntityTable).where(EntityTable.entity_type.in_(_KEYED_TYPES))
        if dataset_id is not None:
            query = query.where(EntityTable.dataset_id == dataset_id)
        return {"entities_to_key": await session.scalar(query)}

    if purge and dataset_id is None:
        removed = await repo.delete_all()
        logger.info(f"Purged {removed} existing key rows")

    scanned = keyed = written = 0
    last_id = ""
    with tqdm(desc="Keying entities", unit=" entity") as bar:
        while True:
            query = (
                select(EntityTable.id, EntityTable.entity_type, EntityTable.display_name, EntityTable.aliases)
                .where(EntityTable.entity_type.in_(_KEYED_TYPES), EntityTable.id > last_id)
                .order_by(EntityTable.id)
                .limit(batch_size)
            )
            if dataset_id is not None:
                query = query.where(EntityTable.dataset_id == dataset_id)
            rows = (await session.execute(query)).all()
            if not rows:
                break

            items = [
                EntityKeyInput(
                    entity_id=r.id,
                    entity_type=r.entity_type,
                    display_name=r.display_name or "",
                    aliases=tuple(r.aliases or ()),
                )
                for r in rows
            ]
            result = await repo.refresh_batch(items)
            scanned += len(items)
            keyed += result["entities_keyed"]
            written += result["keys_written"]
            last_id = rows[-1].id
            bar.update(len(items))

    counts = {"entities_scanned": scanned, "entities_keyed": keyed, "keys_written": written}
    logger.success(f"Backfilled entity_name_key ({dataset_id or 'all datasets'}): {counts}")
    return counts


async def rekey_selectors(
    session: "AsyncSession", *, dataset_id: str | None = None, dry_run: bool = False
) -> dict[str, int]:
    """Re-run pyselectors over each stored selector's raw value; refresh or re-key it."""
    from pyselectors import resolve_selector

    query = select(SelectorTable, EntityTable.source).join(EntityTable, EntityTable.id == SelectorTable.entity_id)
    if dataset_id is not None:
        query = query.where(SelectorTable.dataset_id == dataset_id)
    rows = (await session.execute(query)).all()
    by_value = {(s.dataset_id, s.selector_type, s.normalized_value): s.entity_id for s, _ in rows}

    counts = dict.fromkeys(("selectors", "refreshed", "renamed", "folded", "no_longer_valid"), 0)
    counts["selectors"] = len(rows)
    for selector, source in tqdm(rows, desc="Re-keying selectors", unit=" selector"):
        # an analyst's region is a verified fact; one from extraction may be an old guess
        trusted_region = selector.region_hint if source == EntitySource.MANUAL else None
        region = trusted_region if selector.selector_type == SelectorType.PHONE else selector.region_hint
        spans = resolve_selector(
            selector.raw_value,
            selector_type=selector.selector_type,
            selector_subtype=selector.selector_subtype,
            region=region,
        )
        if not spans:
            counts["no_longer_valid"] += 1
            logger.warning(
                f"selector {selector.entity_id} ({selector.selector_type}) no longer validates: {selector.raw_value!r}"
            )
            continue
        span = spans[0]
        value, attributes, region_hint = span.normalized_value, dict(span.attributes), span.region_hint
        if value == selector.normalized_value:
            # merged: a bare value can't re-derive what its text match knew (a handle's platform)
            attributes = {**selector.attributes, **attributes}
            if (attributes, region_hint) != (dict(selector.attributes), selector.region_hint):
                counts["refreshed"] += 1
                if not dry_run:
                    await session.execute(
                        update(SelectorTable)
                        .where(SelectorTable.id == selector.id)
                        .values(attributes=attributes, region_hint=region_hint)
                    )
            continue

        target = by_value.get((selector.dataset_id, selector.selector_type, value))
        counts["folded" if target else "renamed"] += 1
        if dry_run:
            continue
        await session.execute(
            update(MentionTable).where(MentionTable.entity_id == selector.entity_id).values(normalized_value=value)
        )
        if target:
            await fold_entity(session, source_id=selector.entity_id, target_id=target)
        else:
            await session.execute(
                update(SelectorTable)
                .where(SelectorTable.id == selector.id)
                .values(normalized_value=value, attributes=attributes, region_hint=region_hint)
            )
            await session.execute(
                update(EntityTable).where(EntityTable.id == selector.entity_id).values(display_name_normalized=value)
            )
            by_value[(selector.dataset_id, selector.selector_type, value)] = selector.entity_id

    if not dry_run:
        await session.commit()
    logger.success(f"Selectors re-keyed ({dataset_id or 'all datasets'}): {counts}")
    return counts


async def rekey_filetypes(
    session: "AsyncSession", *, dataset_id: str | None, dry_run: bool, batch_size: int = 500
) -> dict[str, int]:
    """Re-type files with the current filetyper (after a filetyper or registry change).

    Updates the type fields and `compression` where they differ; hashes are untouched. A file
    already decoded out of its compression keeps the `compression` it was found with. A retyped
    file's failed enrichments are dropped: they failed as the old type, and whichever step suits
    the new one queues it afresh. When `is_encrypted` changes, its queued and encrypted-skipped
    rows go too, so steps that skipped it as unreadable read it now (and vice versa).
    """
    from filetyper.models.main import FileTyper

    file_typer = FileTyper()
    stmt = select(
        FileTable.id,
        FileTable.uri,
        FileTable.md5,
        FileTable.sha256,
        FileTable.size,
        FileTable.filetype,
        FileTable.filetype_group,
        FileTable.filetype_name,
        FileTable.mime_type,
        FileTable.compression,
        FileTable.is_encrypted,
        FileTable.filename,
    ).order_by(FileTable.id)
    if dataset_id:
        stmt = stmt.where(FileTable.dataset_id == dataset_id)
    rows = (await session.execute(stmt)).all()

    counts = {"files": len(rows), "retyped": 0, "compressed": 0, "unreadable": 0}
    for i, row in enumerate(tqdm(rows, desc="Re-typing files", unit=" file"), start=1):
        try:
            changes = await asyncio.to_thread(_retype, file_typer, row)
        except OSError as e:
            logger.warning(f"Re-typing {row.uri} failed: {e}")
            counts["unreadable"] += 1
            continue
        if changes:
            counts["retyped"] += 1
            counts["compressed"] += bool(changes.get("compression"))
            if not dry_run:
                await session.execute(update(FileTable).where(FileTable.id == row.id).values(**changes))
                if "filetype" in changes or "is_encrypted" in changes:
                    await session.execute(_stale_enrichments(row.id, encryption_changed="is_encrypted" in changes))
        if not dry_run and i % batch_size == 0:
            await session.commit()

    if not dry_run:
        await session.commit()
    logger.success(f"Filetypes re-keyed ({dataset_id or 'all datasets'}): {counts}")
    return counts


def _stale_enrichments(file_id: str, *, encryption_changed: bool):  # noqa: ANN202 -- SQL statement
    """A retyped file's rows that no longer hold, so each step queues it again as it now is.

    Failed ones always; queued and encrypted-skipped ones too when its encryption changed.
    """
    stale = EnrichmentTable.status == ProcessingStatus.FAILED
    if encryption_changed:
        stale = or_(
            stale,
            EnrichmentTable.status == ProcessingStatus.PENDING,
            and_(EnrichmentTable.status == ProcessingStatus.SKIPPED, EnrichmentTable.error_message == ENCRYPTED_SKIP),
        )
    return delete(EnrichmentTable).where(
        EnrichmentTable.enrichable_type == EnrichableType.FILE,
        EnrichmentTable.enrichable_id == file_id,
        EnrichmentTable.enrichment_type.not_in(READS_ENCRYPTED) if encryption_changed else True,
        stale,
    )


def _retype(file_typer: "FileTyper", row) -> dict:  # noqa: ANN001 -- a selected Row
    from filetyper.encryption import READER_DECIDES_FILETYPES

    decoded = row.compression is not None and row.compression["sha256"] != row.sha256
    name = Path(row.filename).stem if decoded else row.filename  # report.csv.gz's bytes are now the csv
    with local_copy(row.uri) as path:
        described = file_typer.describe(md5=row.md5, sha256=row.sha256, size=row.size, path=path, name=name)
    fresh = {
        "filetype": described["filetype"],
        "filetype_group": described["filetype_group"],
        "filetype_name": described.get("filetype_name", row.filetype_name),
        "mime_type": described["mime_type"] or row.mime_type,
        "is_encrypted": described["is_encrypted"],
    }
    if described["filetype"] in READER_DECIDES_FILETYPES:
        fresh["is_encrypted"] = row.is_encrypted
    if described["compression"] is not None:
        fresh["compression"] = described["compression"].model_dump(mode="json")
    return {key: value for key, value in fresh.items() if getattr(row, key) != value}


REKEY_PARTS = ("names", "name_keys", "selectors")
REKEY_OPT_IN_PARTS = ("filetypes",)


async def rekey_workflow(
    session: "AsyncSession",
    *,
    dataset_id: str | None = None,
    parts: tuple[str, ...] = REKEY_PARTS,
    dry_run: bool = False,
    purge_name_keys: bool = False,
) -> dict[str, dict[str, int]]:
    """Run the chosen parts in order (names before name keys, which read the names)."""
    out: dict[str, dict[str, int]] = {}
    if "names" in parts:
        out["names"] = await rekey_names(session, dataset_id=dataset_id, dry_run=dry_run)
    if "name_keys" in parts:
        out["name_keys"] = await rekey_name_keys(session, dataset_id=dataset_id, purge=purge_name_keys, dry_run=dry_run)
    if "selectors" in parts:
        out["selectors"] = await rekey_selectors(session, dataset_id=dataset_id, dry_run=dry_run)
    if "filetypes" in parts:
        out["filetypes"] = await rekey_filetypes(session, dataset_id=dataset_id, dry_run=dry_run)
    return out
