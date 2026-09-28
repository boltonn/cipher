"""Turn `Message` (SMS / chat dump) sender + recipient phones into selector mentions.

Messages rarely carry a display name, so this feeds the graph, not name
resolution directly: each `sender` / `recipient` becomes a resolved `phone`
selector mention. Once a contact or header resolves a person to one of those
numbers (`has_selector`), the conversation is connected to that person.

A dataset-wide sweep. Re-runnable: skips messages that already have a mention.
"""

from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import exists, select
from tqdm import tqdm

from cipher.datastores.postgres.repositories import PostgresEntityRepository, PostgresMentionRepository
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.message import MessageTable
from cipher.schemas.graph.mention import MentionCreate, MentionedType
from cipher.schemas.graph.ontology import EntityType, SelectorType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_EXTRACTOR = "messages"


async def extract_message_selectors_workflow(session: "AsyncSession", dataset_id: str) -> dict[str, int]:
    """Emit `phone` selector mentions for a dataset's message senders / recipients."""
    mention_repo = PostgresMentionRepository(session=session)
    entity_repo = PostgresEntityRepository(session=session)

    already = exists().where((MentionTable.mentioned_id == MessageTable.id) & (MentionTable.extractor == _EXTRACTOR))
    rows = (
        (
            await session.execute(
                select(MessageTable)
                .outerjoin(FileTable, FileTable.id == MessageTable.file_id)
                .where(FileTable.dataset_id == dataset_id, ~already)
            )
        )
        .scalars()
        .all()
    )

    counts = {"messages": 0, "selector_mentions": 0}
    cache: dict[str, str] = {}
    for row in tqdm(rows, desc="Messages -> selectors", unit=" message"):
        counts["messages"] += 1
        for role, raw in (("message.sender", row.sender), ("message.recipient", row.recipient)):
            value = (raw or "").strip()
            if not value:
                continue
            normalized = value
            if value not in cache:
                entity, _ = await entity_repo.get_or_create_selector(
                    dataset_id=dataset_id,
                    selector_type=SelectorType.PHONE,
                    raw_value=value,
                    normalized_value=normalized,
                )
                cache[value] = entity.id
            await mention_repo.add_mentions_batch(
                [
                    MentionCreate(
                        dataset_id=dataset_id,
                        entity_id=cache[value],
                        mentioned_type=MentionedType.STRUCTURED_FIELD,
                        mentioned_id=row.id,
                        file_id=row.file_id,
                        surface_text=value,
                        entity_type=EntityType.SELECTOR,
                        entity_attribute="value",
                        selector_type=SelectorType.PHONE,
                        normalized_value=normalized,
                        field_path=role,
                        context=row.conversation_id,
                        extractor=_EXTRACTOR,
                        extraction_confidence=1.0,
                    )
                ]
            )
            counts["selector_mentions"] += 1

    logger.success(f"Messages -> selectors for dataset {dataset_id}: {counts}")
    return counts
