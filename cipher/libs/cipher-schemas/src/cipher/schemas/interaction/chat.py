from datetime import datetime
from typing import Literal

from pydantic import Field

from cipher.schemas._base.base import BaseModel

# `action`: a proposed change the analyst reviews and confirms on the linked page.
CitationKind = Literal["document", "email", "person", "dataset", "entity", "action"]


class ChatCitation(BaseModel):
    """A source the chat agent grounded its answer in.

    One shape for every kind of source a tool can cite. Two families:

    - `document` / `email` -- a retrieved text passage. Carries `file_id` plus
      `start_offset`/`end_offset` so the frontend opens the file viewer scrolled
      to that span. `page_number`/`heading_path` are document-only.
    - `person` / `dataset` / `entity` -- a database record. Carries `href`, an
      app-relative route (`/persons/{id}`, `/datasets/{id}`) the frontend
      navigates to. `entity` has no detail page yet, so its `href` is set only
      when the entity bridges to a person record.
    """

    kind: CitationKind = Field(default="document", description="Which family of source this is")
    display_name: str = Field(description="Filename, email subject, person name, or dataset name")
    snippet: str = Field(default="", description="A short excerpt or descriptor for the card")
    score: float = Field(default=0.0, description="Relevance/match score; 0 for non-ranked records")

    # Passage citations (kind in {document, email}).
    chunk_id: str | None = Field(default=None)
    file_id: str | None = Field(default=None)
    filetype_group: Literal["document", "email"] | None = Field(
        default=None, description="Kept for the frontend's document/email icon switch"
    )
    page_number: int | None = Field(default=None, description="Document-only: page this passage came from, if known")
    heading_path: list[str] | None = Field(
        default=None, description="Document-only: section heading hierarchy this passage falls under"
    )
    start_offset: int | None = Field(default=None, description="Start char offset within the file's extracted text")
    end_offset: int | None = Field(default=None, description="End char offset within the file's extracted text")
    sent_from: str | None = Field(default=None, description="Email-only: sender, 'Name <address>'")
    sent_to: list[str] | None = Field(default=None, description="Email-only: to / cc recipients")
    date_sent: datetime | None = Field(default=None, description="Email-only: when it was sent")
    count: int | None = Field(default=None, description="For a counted party (count_emails): its email count")

    # Record citations (kind in {person, dataset, entity}).
    target_id: str | None = Field(default=None, description="Id of the linked record")
    href: str | None = Field(default=None, description="App-relative route the frontend navigates to, when linkable")
