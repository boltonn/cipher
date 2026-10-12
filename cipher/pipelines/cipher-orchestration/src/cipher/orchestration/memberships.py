"""Memberships: the email's recipient `member_of` an organization, as the events LLM pass reads it.

Not a separate concept -- a membership is the ontology's `member_of` edge between a person
and an organization. The events prompt (`extract-events --llm` / `extract-llm`) also lists the
organizations the recipient is confirmed to belong to (a welcome, activation, renewal or dues
receipt -- never an offer to join), with the organization's address when the email gives it.

Each becomes mentions with offsets into the email plus mention relations, like a signature: the
recipient's To address `member_of` the organization, and the organization `located_in` the
address. The membership belongs to the account the email was sent to, so the person end is that
address -- the suggestion on the organization page offers whoever owns it. Needs
`extract-selectors` first (it writes the header address mentions); an email to several To
addresses is ambiguous, so its organization and address are recorded with no edge.
"""

from typing import TYPE_CHECKING

from sqlalchemy import select

from cipher.datastores.postgres.repositories import PostgresMentionRelationshipRepository, PostgresMentionRepository
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas.graph.mention import MentionCreate, MentionedType
from cipher.schemas.graph.mention_relationship import MentionRelationshipCreate
from cipher.schemas.graph.ontology import EntityType, RelationshipType, SelectorType

if TYPE_CHECKING:
    from pyprompt.schemas import LlmMembership
    from sqlalchemy.ext.asyncio import AsyncSession

    from cipher.schemas.content.extraction import ExtractedText

EXTRACTOR = "membership"
_CONTEXT_PAD = 160


def _span(content: str, value: str | None) -> tuple[int, int] | None:
    from pyprompt.offsets import find_span

    return find_span(content, value)


def _mention(
    span: tuple[int, int],
    entity_type: EntityType,
    attribute: str,
    field_path: str,
    *,
    dataset_id: str,
    extracted: "ExtractedText",
    file_id: str,
    context: str,
) -> MentionCreate:
    surface = extracted.content[span[0] : span[1]]
    return MentionCreate(
        dataset_id=dataset_id,
        mentioned_type=MentionedType.EXTRACTED_TEXT,
        mentioned_id=extracted.id,
        file_id=file_id,
        surface_text=surface,
        entity_type=entity_type,
        entity_attribute=attribute,
        normalized_value=normalize_name(surface),
        start_offset=span[0],
        end_offset=span[1],
        field_path=field_path,
        context=context,
        extractor=EXTRACTOR,
        extraction_confidence=0.8,
    )


async def persist_memberships(
    session: "AsyncSession",
    memberships: "list[LlmMembership]",
    *,
    extracted: "ExtractedText",
    dataset_id: str,
    file_id: str,
) -> int:
    """Write one email's memberships as mentions + `member_of` / `located_in` mention relations. Returns count."""
    if not memberships:
        return 0
    to_addresses = (
        (
            await session.execute(
                select(MentionTable.id)
                .where(
                    MentionTable.file_id == file_id,
                    MentionTable.field_path.like("header.to[%"),
                    MentionTable.selector_type == SelectorType.EMAIL,
                )
                .limit(2)
            )
        )
        .scalars()
        .all()
    )
    recipient = to_addresses[0] if len(to_addresses) == 1 else None
    mentions = PostgresMentionRepository(session=session)
    relations = PostgresMentionRelationshipRepository(session=session)
    content = extracted.content
    written = 0
    for membership in memberships:
        org_span = _span(content, membership.organization)
        if org_span is None:
            continue
        address_span = _span(content, membership.address)
        context = content[max(0, org_span[0] - _CONTEXT_PAD) : org_span[1] + _CONTEXT_PAD]

        common_mention = dict(dataset_id=dataset_id, extracted=extracted, file_id=file_id, context=context)
        rows = [_mention(org_span, EntityType.ORGANIZATION, "name", "membership.organization", **common_mention)]
        if address_span:
            rows.append(_mention(address_span, EntityType.LOCATION, "address", "membership.address", **common_mention))
        organization, *address = await mentions.add_mentions_returning(rows)
        common = dict(dataset_id=dataset_id, confidence=0.8, file_id=file_id, context=context, extractor=EXTRACTOR)
        edges = []
        if recipient:
            edges.append(
                MentionRelationshipCreate(
                    src_mention_id=recipient,
                    dst_mention_id=organization.id,
                    relationship_type=RelationshipType.MEMBER_OF,
                    **common,
                )
            )
        if address:
            edges.append(
                MentionRelationshipCreate(
                    src_mention_id=organization.id,
                    dst_mention_id=address[0].id,
                    relationship_type=RelationshipType.LOCATED_IN,
                    **common,
                )
            )
        await relations.add_batch(edges)
        written += 1
    return written
