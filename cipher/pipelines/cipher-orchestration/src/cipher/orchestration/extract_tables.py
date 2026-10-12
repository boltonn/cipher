"""Tabular files -> table mappings -> (once verified) mentions, locations and edges.

Two passes, both re-runnable (docs/tabular-mapping.md):

* `map_tables_workflow` profiles every csv/tsv/xlsx/xls/ods/parquet/json(l) file,
  records each sheet's layout on `file.table_sheets`, and stores one proposed
  `table_mapping` per new header layout. Existing mappings are never overwritten,
  except unverified ones with `repropose` (user-set parts stay locked).
* `emit_tables_workflow` streams every row of the files whose layout has a
  *verified* mapping. Identical slot records within a file collapse into one set
  of `structured_field` mentions (field path `table.<sheet>.<slot>`, so
  `resolve-entities` links names to their selectors). Coordinates also become
  `location` points. Edges between two slots that carry selectors (calls,
  messages, payments) are written straight onto the selector entities with
  `weight` = rows, like `emailed`; every other edge is a `mention_relationship`
  that resolution promotes. Re-emitting a file first takes out exactly what it
  wrote before. A coordinate on a dated row is its own point (`date_recorded`,
  `duration_seconds`), so a call log or GPS export becomes a timeline; undated
  coordinates collapse into one point per distinct record with a `rows` count.
"""

import asyncio
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid4, uuid5

from loguru import logger
from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from tqdm import tqdm

from cipher.datastores.postgres.geo import point_to_geom
from cipher.datastores.postgres.repositories import PostgresEnrichmentRepository, PostgresTableMappingRepository
from cipher.datastores.postgres.repositories.enrichment import claiming_run_id
from cipher.datastores.postgres.tables.enrichment import EnrichmentTable
from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.location import LocationTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.mention_relationship import MentionRelationshipTable
from cipher.datastores.postgres.tables.selector import SelectorTable
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas.graph.mention import MentionedType
from cipher.schemas.graph.ontology import (
    EntitySource,
    EntityType,
    LocationSource,
    RelationshipSource,
    RelationshipType,
    SelectorType,
)
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType, ProcessingStatus
from cipher.schemas.ingestion.table_mapping import TableFormat, TableMappingRecord, TableSheetLayout
from cipher.utils.uri import local_copy

if TYPE_CHECKING:
    from pytabular.decide import ProfileConfig
    from pytabular.detectors import Detector
    from pytabular.records import SlotRecord
    from sqlalchemy.ext.asyncio import AsyncSession

EXTRACTOR = "tabular"
TABULAR_FILETYPES: dict[str, TableFormat] = {
    "csv": TableFormat.CSV,
    "tsv": TableFormat.CSV,
    "xlsx": TableFormat.EXCEL,
    "xls": TableFormat.EXCEL,
    "xlsb": TableFormat.EXCEL,
    "ods": TableFormat.EXCEL,
    "parquet": TableFormat.PARQUET,
    "json": TableFormat.JSON,
    "jsonl": TableFormat.JSONL,
}
# Edges between two selector endpoints that are written straight onto the entities (weight = rows).
COMMS_VERBS = frozenset(
    {RelationshipType.EMAILED, RelationshipType.CALLED, RelationshipType.MESSAGED, RelationshipType.PAID}
)
_CHUNK = 2_000
_BATCH_ROWS = 50_000


def sheet_key(sheet: str | None) -> str:
    """A sheet's name as it appears in field paths (`table.<sheet>.<slot>`)."""
    return (sheet or "main").replace(".", "_").replace(" ", "_")[:60]


# --------------------------------------------------------------------------- #
# Mapping (profile + propose)                                                 #
# --------------------------------------------------------------------------- #
async def map_tables_workflow(
    session: "AsyncSession",
    dataset_id: str,
    *,
    detectors: "list[Detector]",
    config: "ProfileConfig",
    reprofile: bool = False,
    repropose: bool = False,
) -> dict[str, int]:
    """Profile a dataset's tabular files and store a proposed mapping per new header layout."""
    from pytabular.decide import layout_of, propose, sample_from_stored

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    mapping_repo = PostgresTableMappingRepository(session=session)
    unqueued = await enrichment_repo.get_unqueued_files(
        dataset_id=dataset_id, enrichment_type=EnrichmentType.TABLE_EXTRACTION, filetypes=list(TABULAR_FILETYPES)
    )
    await enrichment_repo.queue_enrichments_for_files(
        file_ids=[f["id"] for f in unqueued], enrichment_type=EnrichmentType.TABLE_EXTRACTION
    )
    await session.commit()

    where = [FileTable.dataset_id == dataset_id, FileTable.filetype.in_(list(TABULAR_FILETYPES))]
    if not reprofile:
        where.append(FileTable.table_sheets.is_(None))
    files = (await session.execute(select(FileTable.id, FileTable.uri, FileTable.filetype).where(*where))).all()

    counts = {"files": 0, "sheets": 0, "mappings_created": 0, "mappings_reproposed": 0, "failed": 0}
    reproposed: set[str] = set()
    for file_id, uri, filetype in tqdm(files, desc="Profiling tables", unit=" file"):
        try:
            with local_copy(uri) as path:
                sheets = await asyncio.to_thread(
                    _profile,
                    path=str(path),
                    table_format=TABULAR_FILETYPES[filetype],
                    detectors=detectors,
                    config=config,
                )
        except Exception as exc:  # noqa: BLE001 -- one unreadable file must not stop the dataset
            logger.warning(f"Profiling {uri} failed: {exc}")
            await mapping_repo.set_file_sheets(file_id=file_id, sheets=[])
            await _mark_file(session, file_id=file_id, status=ProcessingStatus.FAILED, error=str(exc)[:500])
            await session.commit()
            counts["failed"] += 1
            continue

        layouts = []
        for mapping, sample in sheets:
            record, created = await mapping_repo.add_proposal(
                dataset_id=dataset_id, mapping=mapping, sample=sample.stored()
            )
            counts["mappings_created"] += created
            if repropose and not created and not record.is_verified and record.id not in reproposed:
                stored = sample_from_stored(record.mapping, record.sample, region=config.region)
                fresh = await asyncio.to_thread(
                    propose, stored, detectors=detectors, locked=record.mapping, config=config
                )
                await mapping_repo.save(record.id, mapping=fresh)
                reproposed.add(record.id)
                counts["mappings_reproposed"] += 1
            layouts.append(layout_of(mapping, width=len(sample.guess.names)))
        await mapping_repo.set_file_sheets(file_id=file_id, sheets=layouts)
        await session.commit()
        counts["files"] += 1
        counts["sheets"] += len(layouts)

    logger.success(f"Mapped tables for dataset {dataset_id}: {counts}")
    return counts


def _profile(*, path: str, table_format: TableFormat, detectors, config):  # noqa: ANN001, ANN202
    from pytabular.decide import profile_sheets

    return profile_sheets(path, table_format=table_format, detectors=detectors, config=config)


async def _mark_file(
    session: "AsyncSession", *, file_id: str, status: ProcessingStatus, error: str | None = None
) -> None:
    values: dict = {"status": status, "error_message": error}
    if status is ProcessingStatus.PROCESSING:
        values["run_id"] = claiming_run_id.get()
    if status is ProcessingStatus.COMPLETED:
        values["date_completed"] = func.now()
    await session.execute(
        update(EnrichmentTable)
        .where(
            EnrichmentTable.enrichable_id == file_id,
            EnrichmentTable.enrichable_type == EnrichableType.FILE,
            EnrichmentTable.enrichment_type == EnrichmentType.TABLE_EXTRACTION,
        )
        .values(**values)
    )


async def requeue_mapping_files(session: "AsyncSession", record: TableMappingRecord) -> int:
    """Put every file using a mapping back in the emit queue (after it is verified again)."""
    file_ids = await PostgresTableMappingRepository(session=session).file_ids(
        dataset_id=record.dataset_id, fingerprint=record.fingerprint
    )
    return await PostgresEnrichmentRepository(session=session).requeue(
        file_ids, EnrichmentType.TABLE_EXTRACTION, create_missing=True
    )


# --------------------------------------------------------------------------- #
# Emit                                                                        #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class _Seen:
    """One distinct slot record in a file: the rows it appeared on."""

    record: "SlotRecord"
    first_row: int
    rows: int = 0
    undated_rows: int = 0
    anchor_id: str | None = None
    selector_entity_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _Span:
    rows: int = 0
    first: datetime | None = None
    last: datetime | None = None

    def observe(self, date: datetime | None) -> None:
        self.rows += 1
        if date is not None:
            self.first = min(self.first, date) if self.first else date
            self.last = max(self.last, date) if self.last else date


@dataclass(slots=True)
class _EdgeAgg:
    """Every row behind one edge: dates, first-seen attributes, amount total, and the history of `role`."""

    span: _Span = field(default_factory=_Span)
    attributes: dict[str, str] = field(default_factory=dict)
    roles: dict[str, _Span] = field(default_factory=dict)
    amount_total: float = 0.0
    amounts: int = 0

    @property
    def rows(self) -> int:
        return self.span.rows

    def observe(self, date: datetime | None, attributes: dict[str, str]) -> None:
        self.span.observe(date)
        for key, value in attributes.items():
            if key == "role":
                self.roles.setdefault(value, _Span()).observe(date)
            else:
                self.attributes.setdefault(key, value)
        if (amount := _number(attributes.get("amount"))) is not None:
            self.amount_total += amount
            self.amounts += 1

    def as_attributes(self) -> dict:
        out: dict = {**self.attributes, "rows": self.rows}
        if self.amounts:
            out["amount_total"] = round(self.amount_total, 2)
        if self.span.first:
            out["date_first"], out["date_last"] = self.span.first.isoformat(), self.span.last.isoformat()
        if self.roles:
            # A person can hold several roles over time: keep them all, newest as `role`.
            history = sorted(
                self.roles.items(), key=lambda kv: (kv[1].last or datetime.min.replace(tzinfo=UTC), kv[1].rows)
            )
            out["role"] = history[-1][0]
            out["roles"] = [
                {
                    "role": role,
                    "rows": s.rows,
                    **({"first": s.first.isoformat(), "last": s.last.isoformat()} if s.first else {}),
                }
                for role, s in history
            ]
        return out


def _number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(" ", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


async def emit_tables_workflow(session: "AsyncSession", dataset_id: str) -> dict[str, int]:
    """Write every queued file whose layout has a verified mapping. Files still waiting on review stay queued."""
    mapping_repo = PostgresTableMappingRepository(session=session)
    verified = await mapping_repo.verified_fingerprints(dataset_id=dataset_id)
    counts: dict[str, int] = defaultdict(int)
    if not verified:
        logger.info("No verified table mappings -- nothing to emit")
        return dict(counts)

    stmt = (
        select(FileTable.id, FileTable.uri, FileTable.table_sheets)
        .join(
            EnrichmentTable,
            and_(
                EnrichmentTable.enrichable_id == FileTable.id,
                EnrichmentTable.enrichable_type == EnrichableType.FILE,
                EnrichmentTable.enrichment_type == EnrichmentType.TABLE_EXTRACTION,
            ),
        )
        .where(
            FileTable.dataset_id == dataset_id,
            FileTable.table_sheets.is_not(None),
            EnrichmentTable.status.in_([ProcessingStatus.PENDING, ProcessingStatus.FAILED]),
        )
    )
    files = (await session.execute(stmt)).all()
    for file_id, uri, sheets in tqdm(files, desc="Emitting tables", unit=" file"):
        layouts = [TableSheetLayout.model_validate(s) for s in sheets or []]
        ready = [(layout, verified[layout.fingerprint]) for layout in layouts if layout.fingerprint in verified]
        if not ready:
            counts["files_waiting"] += 1
            continue
        await _mark_file(session, file_id=file_id, status=ProcessingStatus.PROCESSING)
        await session.commit()
        try:
            for layout, record in ready:
                for key, value in (
                    await emit_sheet(
                        session, dataset_id=dataset_id, file_id=file_id, uri=uri, layout=layout, record=record
                    )
                ).items():
                    counts[key] += value
            done = len(ready) == len(layouts)
            await _mark_file(
                session, file_id=file_id, status=ProcessingStatus.COMPLETED if done else ProcessingStatus.PENDING
            )
            await session.commit()
            counts["files_emitted"] += 1
        except Exception as exc:
            await session.rollback()
            logger.exception(f"Emitting {uri} failed")
            await _mark_file(session, file_id=file_id, status=ProcessingStatus.FAILED, error=str(exc)[:500])
            await session.commit()
            counts["files_failed"] += 1

    logger.success(f"Emitted tables for dataset {dataset_id}: {dict(counts)}")
    return dict(counts)


async def emit_sheet(
    session: "AsyncSession",
    *,
    dataset_id: str,
    file_id: str,
    uri: str,
    layout: TableSheetLayout,
    record: TableMappingRecord,
) -> dict[str, int]:
    """Stream one sheet's rows through its verified mapping and write the results (replacing a previous emit)."""
    from pytabular.reader import TableSource
    from pytabular.records import RowExtractor, edge_is_emittable

    field_prefix = f"table.{sheet_key(layout.sheet)}."
    await _retract_sheet(session, dataset_id=dataset_id, file_id=file_id, field_prefix=field_prefix)

    mapping = record.mapping
    extractor = RowExtractor(mapping)
    edges = [e for e in mapping.edges if edge_is_emittable(e)]
    seen: dict[tuple, _Seen] = {}
    edge_aggs: dict[tuple[int, tuple, tuple], _EdgeAgg] = defaultdict(_EdgeAgg)

    rows = located = 0
    now = datetime.now(UTC)
    observed: set[tuple] = set()
    # Streamed batch by batch: only distinct slot records, edge aggregates and observation keys are kept.
    with local_copy(uri) as table_file:
        source = TableSource(table_file, table_format=layout.format)
        for batch in source.iter_batches(sheet=layout.sheet, data_start_row=layout.data_start_row, size=_BATCH_ROWS):
            dated: list[dict] = []
            for raw in batch.rows():
                row = ["" if v is None else str(v) for v in raw]
                rows += 1
                out = extractor.extract(row)
                by_slot: dict[str, tuple] = {}
                for slot_record in out.slots:
                    key = slot_record.key()
                    entry = seen.get(key)
                    if entry is None:
                        entry = seen[key] = _Seen(record=slot_record, first_row=layout.data_start_row + rows)
                    entry.rows += 1
                    by_slot[slot_record.slot] = key
                    if slot_record.coordinate is None:
                        continue
                    if out.date is None:
                        entry.undated_rows += 1
                    elif (observation := (key, out.date, out.duration_seconds)) not in observed:
                        observed.add(observation)
                        dated.append(
                            _location_row(
                                slot_record,
                                dataset_id=dataset_id,
                                file_id=file_id,
                                field_prefix=field_prefix,
                                now=now,
                                date_recorded=out.date,
                                duration_seconds=out.duration_seconds,
                            )
                        )
                for i, edge in enumerate(edges):
                    src, dst = by_slot.get(edge.src_slot), by_slot.get(edge.dst_slot)
                    if src and dst:
                        edge_aggs[(i, src, dst)].observe(out.date, extractor.edge_attributes(edge, out))
            for start in range(0, len(dated), _CHUNK):
                await session.execute(pg_insert(LocationTable).values(dated[start : start + _CHUNK]))
            located += len(dated)

    selector_ids = await _selector_entities(session, dataset_id=dataset_id, records=[s.record for s in seen.values()])
    mentions, locations = _mentions(
        dataset_id=dataset_id,
        file_id=file_id,
        field_prefix=field_prefix,
        sheet=layout.sheet,
        seen=seen,
        selector_ids=selector_ids,
        now=now,
    )
    for start in range(0, len(mentions), _CHUNK):
        await session.execute(pg_insert(MentionTable).values(mentions[start : start + _CHUNK]))
    for start in range(0, len(locations), _CHUNK):
        await session.execute(pg_insert(LocationTable).values(locations[start : start + _CHUNK]))

    entity_edges, mention_edges = _edges(
        dataset_id=dataset_id, file_id=file_id, edges=edges, aggs=edge_aggs, seen=seen, now=now
    )
    for start in range(0, len(mention_edges), _CHUNK):
        await session.execute(
            pg_insert(MentionRelationshipTable)
            .values(mention_edges[start : start + _CHUNK])
            .on_conflict_do_nothing(constraint="uq_mention_relationship_triple")
        )
    await _add_entity_edges(session, dataset_id=dataset_id, file_id=file_id, edges=entity_edges, now=now)
    await session.commit()
    if extractor.rejected:
        logger.info(
            f"{uri} [{layout.sheet or 'main'}]: cells failing validation, not emitted: {dict(extractor.rejected)}"
        )
    return {
        "rows": rows,
        "slot_records": len(seen),
        "mentions": len(mentions),
        "locations": located + len(locations),
        "entity_edges": len(entity_edges),
        "mention_edges": len(mention_edges),
        "rejected_cells": sum(extractor.rejected.values()),
    }


def _location_row(
    rec: "SlotRecord",
    *,
    dataset_id: str,
    file_id: str,
    field_prefix: str,
    now: datetime,
    date_recorded: datetime | None = None,
    duration_seconds: float | None = None,
    rows: int | None = None,
) -> dict:
    """A `location` row for a slot record's coordinate: one dated observation, or an undated point with its row count."""
    lat, lon = rec.coordinate
    attributes = {"extractor": EXTRACTOR, "field_path": f"{field_prefix}{rec.slot}"}
    if rows is not None:
        attributes["rows"] = rows
    return {
        "id": str(uuid4()),
        "file_id": file_id,
        "dataset_id": dataset_id,
        "latitude": lat,
        "longitude": lon,
        "geom": point_to_geom(latitude=lat, longitude=lon),
        "name": rec.name,
        "address": rec.address,
        "source": LocationSource.COORDINATE_MENTION,
        "source_id": f"{lat:.6f},{lon:.6f}",
        "date_recorded": date_recorded,
        "duration_seconds": duration_seconds,
        "attributes": attributes,
        "tags": [],
        "date_created": now,
        "date_updated": now,
    }


def _mention_id(file_id: str, field_prefix: str, key: tuple, attribute: str) -> str:
    digest = hashlib.sha1(repr(key).encode()).hexdigest()
    return str(uuid5(NAMESPACE_URL, f"{file_id}:{field_prefix}:{digest}:{attribute}"))


def _mentions(
    *,
    dataset_id: str,
    file_id: str,
    field_prefix: str,
    sheet: str | None,
    seen: dict[tuple, _Seen],
    selector_ids: dict[tuple[SelectorType, str], str],
    now: datetime,
) -> tuple[list[dict], list[dict]]:
    """Mention rows (one set per distinct slot record) and undated location points; sets each record's anchor mention."""
    mentions: list[dict] = []
    locations: list[dict] = []
    for key, entry in seen.items():
        rec = entry.record
        mentioned_id = str(
            uuid5(NAMESPACE_URL, f"{file_id}:{field_prefix}:{hashlib.sha1(repr(key).encode()).hexdigest()}")
        )
        context = f"{sheet or 'table'} row {entry.first_row + 1}" + (
            f" (+{entry.rows - 1} more)" if entry.rows > 1 else ""
        )
        surface = dict(rec.surface)
        base = {
            "dataset_id": dataset_id,
            "mentioned_type": MentionedType.STRUCTURED_FIELD,
            "mentioned_id": mentioned_id,
            "file_id": file_id,
            "field_path": f"{field_prefix}{rec.slot}",
            "context": context,
            "extractor": EXTRACTOR,
            "extraction_confidence": 1.0,
            "selector_type": None,
            "selector_subtype": None,
            "date_created": now,
            "date_updated": now,
        }

        def add(
            attribute: str, value: str, normalized: str, entity_type: EntityType, *, key=key, base=base, **extra
        ) -> str:
            mention_id = _mention_id(file_id, field_prefix, key, f"{attribute}:{normalized}")
            mentions.append(
                {
                    **base,
                    "id": mention_id,
                    "surface_text": value[:2000],
                    "entity_type": entity_type,
                    "entity_attribute": attribute,
                    "normalized_value": normalized,
                    "entity_id": None,
                    **extra,
                }
            )
            return mention_id

        anchor: str | None = None
        if rec.name:
            anchor = add("name", rec.name, normalize_name(rec.name), rec.entity_type)
        if rec.address:
            address_id = add("address", rec.address, normalize_name(rec.address), EntityType.LOCATION)
            anchor = anchor or address_id
        if rec.coordinate:
            lat, lon = rec.coordinate
            normalized = f"{lat:.6f},{lon:.6f}"
            coordinate_id = add("coordinate", surface.get("coordinate", normalized), normalized, EntityType.LOCATION)
            anchor = anchor or coordinate_id
            if entry.undated_rows:
                locations.append(
                    _location_row(
                        rec,
                        dataset_id=dataset_id,
                        file_id=file_id,
                        field_prefix=field_prefix,
                        now=now,
                        rows=entry.undated_rows,
                    )
                )
        for attribute, value in rec.attributes:
            add(attribute, surface.get(attribute, value), value, rec.entity_type)
        for selector in rec.selectors:
            entity_id = selector_ids.get((selector.selector_type, selector.normalized))
            selector_mention = add(
                "value",
                selector.raw,
                selector.normalized,
                EntityType.SELECTOR,
                selector_type=selector.selector_type,
                selector_subtype=selector.selector_subtype,
            )
            mentions[-1]["entity_id"] = entity_id
            if entity_id:
                entry.selector_entity_ids.append(entity_id)
            anchor = anchor or selector_mention
        entry.anchor_id = anchor
    return mentions, locations


def _edges(
    *,
    dataset_id: str,
    file_id: str,
    edges: list,
    aggs: dict[tuple[int, tuple, tuple], _EdgeAgg],
    seen: dict[tuple, _Seen],
    now: datetime,
) -> tuple[list[dict], list[dict]]:
    """(entity-level comms edges between selectors, mention_relationship rows) from aggregated row edges."""
    entity_edges: dict[tuple[str, str, RelationshipType], _Span] = {}
    mention_edges: list[dict] = []
    for (i, src_key, dst_key), agg in aggs.items():
        verb = RelationshipType(edges[i].relationship_type)
        src, dst = seen[src_key], seen[dst_key]
        if verb in COMMS_VERBS and src.selector_entity_ids and dst.selector_entity_ids:
            pair = (src.selector_entity_ids[0], dst.selector_entity_ids[0], verb)
            if pair[0] == pair[1]:
                continue
            total = entity_edges.setdefault(pair, _Span())
            total.rows += agg.rows
            if agg.span.first:
                total.first = min(total.first, agg.span.first) if total.first else agg.span.first
                total.last = max(total.last, agg.span.last) if total.last else agg.span.last
            continue
        if not (src.anchor_id and dst.anchor_id) or src.anchor_id == dst.anchor_id:
            continue
        mention_edges.append(
            {
                "id": str(uuid4()),
                "dataset_id": dataset_id,
                "src_mention_id": src.anchor_id,
                "dst_mention_id": dst.anchor_id,
                "relationship_type": verb,
                "directed": True,
                "confidence": 1.0,
                "file_id": file_id,
                "attributes": agg.as_attributes(),
                "extractor": EXTRACTOR,
                "date_created": now,
            }
        )
    rows = [
        {
            "src_entity_id": src,
            "dst_entity_id": dst,
            "relationship_type": verb,
            "weight": float(agg.rows),
            "first": agg.first,
            "last": agg.last,
        }
        for (src, dst, verb), agg in entity_edges.items()
    ]
    return rows, mention_edges


async def _add_entity_edges(
    session: "AsyncSession", *, dataset_id: str, file_id: str, edges: list[dict], now: datetime
) -> None:
    """Upsert comms edges, recording this file's share under `attributes.by_file` so a re-emit can take it back out."""
    for start in range(0, len(edges), _CHUNK):
        values = []
        for e in edges[start : start + _CHUNK]:
            share = {"n": e["weight"]}
            if e["first"]:
                share |= {"first": e["first"].isoformat(), "last": e["last"].isoformat()}
            values.append(
                {
                    "dataset_id": dataset_id,
                    "src_entity_id": e["src_entity_id"],
                    "dst_entity_id": e["dst_entity_id"],
                    "relationship_type": e["relationship_type"],
                    "directed": True,
                    "weight": e["weight"],
                    "source": RelationshipSource.IMPORT,
                    "attributes": {"by_file": {file_id: share}},
                    "date_observed_start": e["first"],
                    "date_observed_end": e["last"],
                    "date_created": now,
                    "date_updated": now,
                }
            )
        stmt = pg_insert(EntityRelationshipTable).values(values)
        await session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_entity_relationship_triple",
                set_={
                    "weight": func.coalesce(EntityRelationshipTable.weight, 0) + stmt.excluded.weight,
                    "attributes": func.jsonb_set(
                        EntityRelationshipTable.attributes,
                        text("'{by_file}'::text[]"),
                        func.coalesce(EntityRelationshipTable.attributes["by_file"], text("'{}'::jsonb")).op("||")(
                            stmt.excluded.attributes["by_file"]
                        ),
                    ),
                    "date_observed_start": func.least(
                        EntityRelationshipTable.date_observed_start, stmt.excluded.date_observed_start
                    ),
                    "date_observed_end": func.greatest(
                        EntityRelationshipTable.date_observed_end, stmt.excluded.date_observed_end
                    ),
                },
            )
        )


async def _retract_sheet(session: "AsyncSession", *, dataset_id: str, file_id: str, field_prefix: str) -> None:
    """Remove what a previous emit of this sheet wrote: mentions (their relationships cascade), points, edge shares."""
    await session.execute(
        delete(MentionTable).where(
            MentionTable.file_id == file_id,
            MentionTable.extractor == EXTRACTOR,
            MentionTable.field_path.startswith(field_prefix, autoescape=True),
        )
    )
    await session.execute(
        delete(LocationTable).where(
            LocationTable.file_id == file_id,
            LocationTable.attributes["extractor"].astext == EXTRACTOR,
            LocationTable.attributes["field_path"].astext.startswith(field_prefix, autoescape=True),
        )
    )
    await session.execute(
        text(
            """
            UPDATE entity_relationship
            SET weight = weight - coalesce((attributes->'by_file'->:file_id->>'n')::float, 0),
                attributes = attributes #- ARRAY['by_file', :file_id]
            WHERE dataset_id = :dataset_id AND source = 'IMPORT' AND attributes->'by_file' ? :file_id
            """
        ),
        {"file_id": file_id, "dataset_id": dataset_id},
    )
    await session.execute(
        text(
            """
            UPDATE entity_relationship r
            SET date_observed_start = s.first, date_observed_end = s.last
            FROM (
                SELECT r2.id, min((v->>'first')::timestamptz) AS first, max((v->>'last')::timestamptz) AS last
                FROM entity_relationship r2, jsonb_each(r2.attributes->'by_file') AS x(k, v)
                WHERE r2.dataset_id = :dataset_id AND r2.source = 'IMPORT' AND r2.attributes ? 'by_file'
                GROUP BY r2.id
            ) s
            WHERE r.id = s.id
            """
        ),
        {"dataset_id": dataset_id},
    )
    await session.execute(
        text(
            "DELETE FROM entity_relationship WHERE dataset_id = :dataset_id AND source = 'IMPORT' "
            "AND attributes ? 'by_file' AND (attributes->'by_file' = '{}'::jsonb OR weight <= 0)"
        ),
        {"dataset_id": dataset_id},
    )


async def _selector_entities(
    session: "AsyncSession", *, dataset_id: str, records: "list[SlotRecord]"
) -> dict[tuple[SelectorType, str], str]:
    """Selector entity id per (type, normalized value): existing ones (dataset or global) looked up in bulk, the rest created."""
    wanted = {}
    for rec in records:
        for s in rec.selectors:
            wanted.setdefault((s.selector_type, s.normalized), s)
    found: dict[tuple[SelectorType, str], str] = {}
    keys = list(wanted)
    for start in range(0, len(keys), _CHUNK):
        chunk = keys[start : start + _CHUNK]
        rows = await session.execute(
            select(SelectorTable.selector_type, SelectorTable.normalized_value, SelectorTable.entity_id)
            .where(
                SelectorTable.normalized_value.in_([v for _, v in chunk]),
                or_(SelectorTable.dataset_id == dataset_id, SelectorTable.dataset_id.is_(None)),
            )
            .order_by(SelectorTable.dataset_id.is_(None))
        )
        for selector_type, value, entity_id in rows.all():
            found.setdefault((selector_type, value), entity_id)

    missing = [wanted[k] for k in keys if k not in found]
    now = datetime.now(UTC)
    for start in range(0, len(missing), _CHUNK):
        chunk = missing[start : start + _CHUNK]
        entities, details = [], []
        for s in chunk:
            entity_id = str(uuid4())
            found[(s.selector_type, s.normalized)] = entity_id
            entities.append(
                {
                    "id": entity_id,
                    "dataset_id": dataset_id,
                    "entity_type": EntityType.SELECTOR,
                    "display_name": s.raw[:512],
                    "display_name_normalized": normalize_name(s.raw)[:512],
                    "source": EntitySource.EXTRACTION,
                    "aliases": [],
                    "tags": [],
                    "is_verified": False,
                    "date_created": now,
                    "date_updated": now,
                }
            )
            details.append(
                {
                    "entity_id": entity_id,
                    "dataset_id": dataset_id,
                    "selector_type": s.selector_type,
                    "selector_subtype": s.selector_subtype,
                    "raw_value": s.raw,
                    "normalized_value": s.normalized,
                    "region_hint": s.region_hint,
                    "attributes": {},
                    "date_created": now,
                    "date_updated": now,
                }
            )
        await session.execute(pg_insert(EntityTable).values(entities))
        await session.execute(pg_insert(SelectorTable).values(details))
    return found
