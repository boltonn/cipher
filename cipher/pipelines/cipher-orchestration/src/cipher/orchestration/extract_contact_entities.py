"""Turn `Contact` (vCard / address-book) rows into resolver-ready mentions.

Structurally the same as an email header: a person name plus the phone/email
selectors it sits next to, all sharing one `field_path` so
`resolve-entities` (`_colocated_selector_values`) links the name to the
identifier and can resolve it. A `Contact.organization` also emits an
organization name mention + a `member_of` `mention_relationship`, so a vCard's
`ORG` field flows exactly like a signature's name<->org link.

First parses the dataset's vCard files into `contact` rows (enrichment-gated per
file, deterministic ids), then sweeps contacts into mentions. Re-runnable: skips
contacts that already have a mention.
"""

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from loguru import logger
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresEntityRepository,
    PostgresMentionRelationshipRepository,
    PostgresMentionRepository,
)
from cipher.datastores.postgres.tables.contact import ContactTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas.graph.mention import MentionCreate, MentionedType
from cipher.schemas.graph.mention_relationship import MentionRelationshipCreate
from cipher.schemas.graph.ontology import EntityType, RelationshipType, SelectorType
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_FIELD_PATH = "contact.name"
_EXTRACTOR = "contacts"
_VCARD_FILETYPES = ["vcard"]


async def load_vcard_contacts(session: "AsyncSession", dataset_id: str, batch_size: int = 50) -> int:
    """Parse a dataset's vCard files into `contact` rows (id = uuid5(file_id, index), so re-runs no-op)."""
    from pyparse.parsers.contacts.vcard import VcardParser

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    unqueued = await enrichment_repo.get_unqueued_files(
        dataset_id=dataset_id, enrichment_type=EnrichmentType.CONTACT_EXTRACTION, filetypes=_VCARD_FILETYPES
    )
    await enrichment_repo.queue_enrichments_for_files(
        file_ids=[f["id"] for f in unqueued], enrichment_type=EnrichmentType.CONTACT_EXTRACTION
    )
    await session.commit()

    count = 0
    while batch := await enrichment_repo.get_pending_batch(
        enrichment_type=EnrichmentType.CONTACT_EXTRACTION,
        enrichable_type=EnrichableType.FILE,
        batch_size=batch_size,
        dataset_id=dataset_id,
        filetype_group_filter="contact",
    ):
        completed, failed = [], []
        for item in batch:
            file_id = item.resource["id"]
            try:
                contacts = VcardParser.parse(Path(item.resource["path"]))
            except Exception as e:
                logger.error(f"vCard parse failed for file {file_id}: {e}")
                failed.append(item.enrichment.id)
                continue
            rows = [
                {**c.model_dump(), "id": str(uuid5(NAMESPACE_URL, f"{file_id}:{i}")), "file_id": file_id}
                for i, c in enumerate(contacts)
            ]
            if rows:
                await session.execute(
                    pg_insert(ContactTable).values(rows).on_conflict_do_nothing(index_elements=["id"])
                )
            completed.append(item.enrichment.id)
            count += len(rows)
        if completed:
            await enrichment_repo.mark_completed_batch(completed)
        if failed:
            await enrichment_repo.mark_failed_batch(failed, increment_retry=True)
        await session.commit()
    logger.info(f"Loaded {count} contacts from vCard files")
    return count


def _contact_name(row) -> str:
    return (row.full_name or " ".join(p for p in (row.first_name, row.last_name) if p) or "").strip()


def _name_mention(
    *, dataset_id: str, contact_id: str, file_id: str | None, name: str, entity_type: EntityType
) -> MentionCreate:
    return MentionCreate(
        dataset_id=dataset_id,
        entity_id=None,
        mentioned_type=MentionedType.STRUCTURED_FIELD,
        mentioned_id=contact_id,
        file_id=file_id,
        surface_text=name,
        entity_type=entity_type,
        entity_attribute="name",
        normalized_value=normalize_name(name),
        field_path=_FIELD_PATH,
        context=name,
        extractor=_EXTRACTOR,
        extraction_confidence=1.0,
    )


async def extract_contact_entities_workflow(session: "AsyncSession", dataset_id: str) -> dict[str, int]:
    """Load the dataset's vCards, then emit name + selector mentions (and a member_of relation) per contact."""
    await load_vcard_contacts(session=session, dataset_id=dataset_id)
    mention_repo = PostgresMentionRepository(session=session)
    entity_repo = PostgresEntityRepository(session=session)
    rel_repo = PostgresMentionRelationshipRepository(session=session)

    already = exists().where(
        (MentionTable.mentioned_id == ContactTable.id) & (MentionTable.mentioned_type == MentionedType.STRUCTURED_FIELD)
    )
    rows = (
        (
            await session.execute(
                select(ContactTable)
                .outerjoin(FileTable, FileTable.id == ContactTable.file_id)
                .where((FileTable.dataset_id == dataset_id) | (ContactTable.file_id.is_(None)), ~already)
            )
        )
        .scalars()
        .all()
    )

    counts = {"contacts": 0, "name_mentions": 0, "selector_mentions": 0, "org_relations": 0}
    for row in tqdm(rows, desc="Contacts -> mentions", unit=" contact"):
        name = _contact_name(row)
        if not name:
            continue
        counts["contacts"] += 1
        person = await mention_repo.add_mentions_returning(
            [
                _name_mention(
                    dataset_id=dataset_id,
                    contact_id=row.id,
                    file_id=row.file_id,
                    name=name,
                    entity_type=EntityType.PERSON,
                )
            ]
        )
        counts["name_mentions"] += 1

        for selector_type, raw in [
            *((SelectorType.EMAIL, e) for e in (row.emails or [])),
            *((SelectorType.PHONE, p["value"] if isinstance(p, dict) else p.value) for p in (row.phone_numbers or [])),
        ]:
            normalized = raw.strip().lower() if selector_type == SelectorType.EMAIL else raw.strip()
            if not normalized:
                continue
            entity, _ = await entity_repo.get_or_create_selector(
                dataset_id=dataset_id, selector_type=selector_type, raw_value=raw, normalized_value=normalized
            )
            await mention_repo.add_mentions_batch(
                [
                    MentionCreate(
                        dataset_id=dataset_id,
                        entity_id=entity.id,
                        mentioned_type=MentionedType.STRUCTURED_FIELD,
                        mentioned_id=row.id,
                        file_id=row.file_id,
                        surface_text=raw,
                        entity_type=EntityType.SELECTOR,
                        entity_attribute="value",
                        selector_type=selector_type,
                        normalized_value=normalized,
                        field_path=_FIELD_PATH,
                        context=name,
                        extractor=_EXTRACTOR,
                        extraction_confidence=1.0,
                    )
                ]
            )
            counts["selector_mentions"] += 1

        if row.organization and row.organization.strip():
            org = await mention_repo.add_mentions_returning(
                [
                    _name_mention(
                        dataset_id=dataset_id,
                        contact_id=row.id,
                        file_id=row.file_id,
                        name=row.organization.strip(),
                        entity_type=EntityType.ORGANIZATION,
                    )
                ]
            )
            counts["name_mentions"] += 1
            if person and org:
                await rel_repo.add_batch(
                    [
                        MentionRelationshipCreate(
                            dataset_id=dataset_id,
                            src_mention_id=person[0].id,
                            dst_mention_id=org[0].id,
                            relationship_type=RelationshipType.MEMBER_OF,
                            file_id=row.file_id,
                            extractor=_EXTRACTOR,
                        )
                    ]
                )
                counts["org_relations"] += 1

    logger.success(f"Contacts -> mentions for dataset {dataset_id}: {counts}")
    return counts
