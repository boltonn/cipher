from typing import Literal

from pydantic import Field

from cipher.schemas.base import BaseModel


class ChatCitation(BaseModel):
    """A retrieved passage the chat agent grounded its answer in.

    Flattens `ScoredDocumentTextChunk`/`ScoredEmailTextChunk` into one shape
    so the frontend has a single citation contract regardless of source
    type -- document-only fields (`page_number`, `heading_path`) are `None`
    for email citations.
    """

    chunk_id: str
    file_id: str
    display_name: str = Field(description="Filename for documents; subject line for emails")
    filetype_group: Literal["document", "email"]
    page_number: int | None = Field(default=None, description="Document-only: page this passage came from, if known")
    heading_path: list[str] | None = Field(
        default=None, description="Document-only: section heading hierarchy this passage falls under"
    )
    start_offset: int = Field(description="Start character offset within the parent file's extracted text")
    end_offset: int = Field(description="End character offset within the parent file's extracted text")
    snippet: str
    score: float
