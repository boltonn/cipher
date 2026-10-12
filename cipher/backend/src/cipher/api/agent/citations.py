"""Builders that turn a tool's raw result into `ChatCitation` wire dicts.

Every builder returns `model_dump(by_alias=True)` -- pydantic_ai's tool-result
JSON dump ignores field aliases, so serializing here is what keeps the wire
shape camelCase to match the frontend's `ChatCitation` type.
"""

from datetime import datetime

from cipher.datastores.elasticsearch.repositories.text_chunk import FileSearchResult, ScoredTextChunk
from cipher.schemas.content.document import ScoredDocumentTextChunk
from cipher.schemas.content.email import EmailAddress, EmailCountBucket
from cipher.schemas.content.image import ImagePublic
from cipher.schemas.graph.entity import Entity
from cipher.schemas.graph.entity_relationship import TopConnection
from cipher.schemas.graph.event import Event
from cipher.schemas.graph.mention import Mention
from cipher.schemas.identity.person import Person
from cipher.schemas.ingestion.dataset import Dataset
from cipher.schemas.ingestion.dataset_profile import ProfileEntity
from cipher.schemas.ingestion.file import File
from cipher.schemas.interaction.chat import ChatCitation

_PASSAGE_CHARS = 700


def _dump(citation: ChatCitation) -> dict:
    # Unset fields omitted: tool results share a small model's context window.
    return citation.model_dump(by_alias=True, exclude_none=True)


def top_chunk(result: FileSearchResult) -> ScoredTextChunk:
    """The best-matching chunk within a file's grouped search result."""
    return next(c for c in result.chunks if c.id == result.top_chunk_id)


def _participant(address: EmailAddress) -> str:
    return f"{address.name} <{address.value}>" if address.name else address.value


def chunk_citation(chunk: ScoredTextChunk) -> dict:
    """A retrieved passage -- opens the file viewer scrolled to the span."""
    is_document = isinstance(chunk, ScoredDocumentTextChunk)
    sender = None if is_document else (chunk.sent_from or chunk.sender)
    return _dump(
        ChatCitation(
            kind="document" if is_document else "email",
            filetype_group="document" if is_document else "email",
            chunk_id=chunk.id,
            file_id=chunk.file_id,
            display_name=chunk.filename if is_document else (chunk.title or "(no subject)"),
            page_number=chunk.page_number if is_document else None,
            heading_path=chunk.heading_path if is_document else None,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            # Long enough for the model to reason over; the card clamps it to three lines.
            snippet=" ".join(chunk.text.split())[:_PASSAGE_CHARS],
            score=chunk.score,
            sent_from=_participant(sender) if sender else None,
            sent_to=None if is_document else [_participant(p) for p in (*chunk.sent_to, *chunk.cc)] or None,
            date_sent=None if is_document else chunk.date_sent,
        )
    )


def mention_citation(mention: Mention) -> dict | None:
    """An entity mention anchored in a file -- opens the viewer at the span.

    Returns None for mentions with no owning file or text offsets (e.g. an
    image-box or structured-field mention), which have nowhere to jump to.
    """
    if mention.file_id is None or mention.start_offset is None or mention.end_offset is None:
        return None
    return _dump(
        ChatCitation(
            kind="document",
            filetype_group="document",
            file_id=mention.file_id,
            display_name=mention.surface_text or "(mention)",
            start_offset=mention.start_offset,
            end_offset=mention.end_offset,
            snippet=mention.context or mention.surface_text,
            score=mention.extraction_confidence or 0.0,
        )
    )


def person_citation(person: Person) -> dict:
    """A person record -- navigates to its detail page."""
    return _dump(
        ChatCitation(
            kind="person",
            target_id=person.id,
            href=f"/persons/{person.id}",
            display_name=person.name or "(unnamed person)",
            snippet=person.notes or (", ".join(person.aliases) if person.aliases else ""),
        )
    )


def dataset_citation(dataset: Dataset) -> dict:
    """A dataset record -- navigates to its detail page."""
    return _dump(
        ChatCitation(
            kind="dataset",
            target_id=dataset.id,
            href=f"/datasets/{dataset.id}",
            display_name=dataset.name,
            snippet=dataset.description or "",
        )
    )


def entity_citation(entity: Entity) -> dict:
    """An entity node -- navigates to its dossier page."""
    return _dump(
        ChatCitation(
            kind="entity",
            target_id=entity.id,
            href=f"/entities/{entity.id}",
            display_name=entity.display_name,
            snippet=f"{entity.entity_type}" + (f" · {', '.join(entity.aliases)}" if entity.aliases else ""),
        )
    )


def selector_link_proposal_citation(entity: Entity, selector_ids: list[str], reason: str) -> dict:
    """A proposed `has_selector` link -- opens the entity's page with the proposal to review and confirm."""
    count = len(selector_ids)
    return _dump(
        ChatCitation(
            kind="action",
            target_id=entity.id,
            href=f"/entities/{entity.id}?propose={','.join(selector_ids)}",
            display_name=f"Review: link {count} address{'es' if count != 1 else ''} to {entity.display_name}",
            snippet=reason,
        )
    )


def merge_proposal_citation(duplicate: Entity, keep: Entity, reason: str) -> dict:
    """A proposed entity merge -- opens the duplicate's page, where the merge panel asks to confirm."""
    return _dump(
        ChatCitation(
            kind="action",
            target_id=duplicate.id,
            href=f"/entities/{duplicate.id}",
            display_name=f"Review: merge {duplicate.display_name} into {keep.display_name}",
            snippet=reason,
        )
    )


def email_count_citation(bucket: EmailCountBucket) -> dict:
    """A sender / recipient / correspondent from `count_emails` -- navigates to its dossier page."""
    span = " → ".join(d.date().isoformat() for d in (bucket.date_first, bucket.date_last) if d)
    return _dump(
        ChatCitation(
            kind="entity",
            target_id=bucket.key,
            href=f"/entities/{bucket.key}",
            display_name=bucket.label,
            snippet=" · ".join(filter(None, [f"{bucket.email_count} emails", span, ", ".join(bucket.addresses)])),
            score=float(bucket.email_count),
            count=bucket.email_count,
        )
    )


def connection_citation(connection: TopConnection) -> dict:
    """A ranked neighbour from `top_connections` -- navigates to its dossier page."""
    entity = connection.entity
    span = " → ".join(d.date().isoformat() for d in (connection.date_first, connection.date_last) if d)
    return _dump(
        ChatCitation(
            kind="entity",
            target_id=entity.id,
            href=f"/entities/{entity.id}",
            display_name=entity.display_name,
            snippet=" · ".join(
                filter(
                    None,
                    [
                        f"weight {connection.weight:g}",
                        ", ".join(connection.relationship_types),
                        span,
                        ", ".join(v.display_name for v in connection.via),
                    ],
                )
            ),
            score=connection.weight,
        )
    )


def _day(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def file_citation(file: File, *, path: str) -> dict:
    """A file found by its metadata -- navigates to the file's page. `path` is as the model should see it."""
    return _dump(
        ChatCitation(
            kind="file",
            file_id=file.id,
            target_id=file.id,
            href=f"/files/{file.id}",
            display_name=" ".join(file.filename.split()),
            snippet=" · ".join(filter(None, [path, file.filetype_group, file.filetype, _day(file.date_created)])),
        )
    )


def event_citation(event: Event) -> dict:
    """An extracted event -- opens the file it was extracted from."""
    span = " → ".join(filter(None, [_day(event.date_start), _day(event.date_end)]))
    return _dump(
        ChatCitation(
            kind="event",
            target_id=event.id,
            file_id=event.file_id,
            display_name=event.title,
            snippet=" · ".join(filter(None, [event.event_type, span, event.summary])),
        )
    )


def image_citation(image: ImagePublic) -> dict:
    """An image -- navigates to the page of a file holding it."""
    place = f"GPS {image.gps_latitude:.4f},{image.gps_longitude:.4f}" if image.gps_latitude is not None else None
    camera = " ".join(filter(None, [image.camera_make, image.camera_model]))
    return _dump(
        ChatCitation(
            kind="image",
            target_id=image.id,
            file_id=image.file_id,
            href=f"/files/{image.file_id}" if image.file_id else None,
            display_name=f"Photo {_day(image.date_taken)}" if image.date_taken else "Image",
            snippet=" · ".join(filter(None, [", ".join(image.tags), camera, place])),
        )
    )


def profile_entity_citation(entity: ProfileEntity) -> dict:
    """A person / org / place / identifier ranked in the dataset profile -- navigates to its dossier page."""
    return _dump(
        ChatCitation(
            kind="entity",
            target_id=entity.entity_id,
            href=f"/entities/{entity.entity_id}",
            display_name=entity.display_name,
            snippet=f"{entity.entity_type} · in {entity.files} files",
            count=entity.files,
        )
    )
