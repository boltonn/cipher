from datetime import datetime
from typing import Literal

from pydantic import Field

from cipher.schemas.base import BaseModel
from cipher.schemas.detection import BoundingBox
from cipher.schemas.email import NamedParticipant
from cipher.schemas.search import TextChunk


class ExtractedTableInfo(BaseModel):
    """A table detected during extraction, mirroring xberg's `ExtractedTable`.

    `bounding_box` is normalized to the shared `[0, 1]` `BoundingBox` standard
    (same as face/image detections) -- xberg reports raw point coordinates,
    so the extractor normalizes them against the page's width/height before
    they land here.
    """

    cells: list[list[str]]
    markdown: str
    page_number: int
    bounding_box: BoundingBox | None = None


class DocumentStructureNode(BaseModel):
    """One node of xberg's hierarchical document structure (heading/paragraph/table/etc).

    A pared-down projection of xberg's `DocumentNode` -- just the fields a
    "highlight this in the original document" UI needs (text, page,
    location) -- not the full tagged `NodeContent` union, since nothing
    downstream needs the other node kinds' extra fields yet.
    """

    id: str
    node_type: str
    text: str | None = None
    parent: int | None = None
    page: int | None = None
    page_end: int | None = None
    bounding_box: BoundingBox | None = None


class DocumentMetadata(BaseModel):
    """Document-level metadata, denormalized onto every chunk of that document.

    `sent_from`/`sent_to` and `tables`/`document_structure` are only
    populated when applicable -- a document known to have arrived as an
    email attachment carries the former (looked up via the file's
    `parent_id`); the latter come from xberg when extraction found them.
    """

    filename: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    date_content_created: datetime | None = None
    date_content_modified: datetime | None = None
    page_count: int | None = Field(default=None, description="Total page count, if the source format has pages")
    detected_language: str | None = Field(default=None, description="Best-guess language of the document's text")
    tables: list[ExtractedTableInfo] | None = Field(
        default=None, description="Structured tables detected during extraction, if any"
    )
    document_structure: list[DocumentStructureNode] | None = Field(
        default=None,
        description="xberg's hierarchical layout nodes (heading/paragraph/table/etc, with page + bounding box), "
        "when extracted with document-structure detection enabled",
    )
    sent_from: NamedParticipant | None = Field(
        default=None, description="Sender, if this document arrived as an email attachment"
    )
    sent_to: list[NamedParticipant] = Field(
        default_factory=list, description="Recipients, if this document arrived as an email attachment"
    )

    model_config = {"populate_by_name": True}


class DocumentTextChunk(DocumentMetadata, TextChunk):
    """Searchable chunk of a document, inheriting metadata for filtering.

    `filetype_group` discriminates document vs. email chunks living side by
    side in the same unified `text_chunks` index/search surface.
    """

    filetype_group: Literal["document"] = "document"
    page_number: int | None = Field(default=None, description="Page this chunk's text came from, if known")
    heading_path: list[str] | None = Field(
        default=None,
        description="Section heading hierarchy this chunk falls under, e.g. ['Introduction', 'Background']",
    )
    token_count: int | None = Field(
        default=None, description="Token count reported by the extractor's own chunker, if used"
    )
    bounding_box: BoundingBox | None = Field(
        default=None, description="Region on the page this chunk's text occupies, if known"
    )


class ScoredDocumentTextChunk(DocumentTextChunk):
    """A `DocumentTextChunk` decorated with its Elasticsearch retrieval score."""

    score: float = Field(..., description="Retrieval score from Elasticsearch")
    highlights: list[str] = Field(
        default_factory=list,
        description="Matched words/phrases from Elasticsearch highlighting; empty for pure kNN results",
    )
