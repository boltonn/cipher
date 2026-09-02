"""Shared vocabulary for analyst-reviewed candidate links.

Face-to-person matches (`face_match`), entity-resolution matches
(`entity_match`), and relationship candidates (`entity_relationship`) are all
the same shape: a system- or analyst-proposed link that sits `pending` until
an analyst confirms or rejects it. They share this status enum, the decision
body an analyst submits, the response-side review-state fields, and the
date/similarity sort axis.

Per-domain modules keep their own `*Method` enum (how the candidate was
proposed differs by domain) and re-export the names below under their old
identifiers for backwards compatibility.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from cipher.schemas._base.base import BaseModel


class ReviewStatus(StrEnum):
    """Review state of a proposed link."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class MatchSortField(StrEnum):
    """Sort axis shared by the match/candidate review queues."""

    DATE_CREATED = "date_created"
    SIMILARITY_SCORE = "similarity_score"


class ReviewDecision(BaseModel):
    """An analyst confirming or rejecting a proposed link."""

    status: ReviewStatus = Field(description="Must be 'confirmed' or 'rejected'")
    reviewed_by: str = Field(description="Id/name of the reviewing user")
    review_note: str | None = None


class ReviewableMixin(BaseModel):
    """Response-side review state carried by every reviewed candidate record."""

    status: ReviewStatus = ReviewStatus.PENDING
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
