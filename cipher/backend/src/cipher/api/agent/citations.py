"""Builders that turn a tool's raw result into `ChatCitation` wire dicts.

Every builder returns `model_dump(by_alias=True)` -- pydantic_ai's tool-result
JSON dump ignores field aliases, so serializing here is what keeps the wire
shape camelCase to match the frontend's `ChatCitation` type.
"""

from cipher.datastores.elasticsearch.repositories.text_chunk import FileSearchResult, ScoredTextChunk
from cipher.schemas.chat import ChatCitation
from cipher.schemas.dataset import Dataset
from cipher.schemas.document import ScoredDocumentTextChunk
from cipher.schemas.entity import Entity
from cipher.schemas.mention import Mention
from cipher.schemas.person import Person


def _dump(citation: ChatCitation) -> dict:
    return citation.model_dump(by_alias=True)


def top_chunk(result: FileSearchResult) -> ScoredTextChunk:
    """The best-matching chunk within a file's grouped search result."""
    return next(c for c in result.chunks if c.id == result.top_chunk_id)


def chunk_citation(chunk: ScoredTextChunk) -> dict:
    """A retrieved passage -- opens the file viewer scrolled to the span."""
    is_document = isinstance(chunk, ScoredDocumentTextChunk)
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
            snippet=chunk.highlights[0] if chunk.highlights else chunk.text[:280],
            score=chunk.score,
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
    """An entity node.

    No detail page exists yet, so it is linkable only when it bridges to a
    person record; otherwise it renders as a static chip.
    """
    href = f"/persons/{entity.person_id}" if entity.person_id else None
    return _dump(
        ChatCitation(
            kind="entity",
            target_id=entity.id,
            href=href,
            display_name=entity.display_name,
            snippet=f"{entity.entity_type}" + (f" · {', '.join(entity.aliases)}" if entity.aliases else ""),
        )
    )
