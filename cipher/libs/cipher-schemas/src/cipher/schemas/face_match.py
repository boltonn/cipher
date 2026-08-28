from datetime import datetime
from enum import StrEnum

from pydantic import Field

from cipher.schemas.base import BaseModel
from cipher.schemas.common import PaginatedResponse, SortOrder


class FaceMatchStatus(StrEnum):
    """Review state of a candidate face-to-person match."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class FaceMatchMethod(StrEnum):
    """How a candidate match was proposed."""

    AUTOMATIC_SIMILARITY = "automatic_similarity"
    AUTOMATIC_CLUSTERING = "automatic_clustering"
    MANUAL = "manual"


class FaceMatchSortField(StrEnum):
    DATE_CREATED = "date_created"
    SIMILARITY_SCORE = "similarity_score"


class FaceMatchBase(BaseModel):
    """Base face match schema."""

    face_id: str
    person_id: str
    similarity_score: float = Field(
        ge=0,
        le=1,
        description="Similarity between the face embedding and the person's representative embedding",
    )
    match_method: FaceMatchMethod = FaceMatchMethod.AUTOMATIC_SIMILARITY


class FaceMatchCreate(FaceMatchBase):
    """Face match creation schema, produced by the matching pipeline or an analyst."""

    pass


class FaceMatchReview(BaseModel):
    """Schema for an analyst resolving a candidate match."""

    status: FaceMatchStatus = Field(..., description="Must be 'confirmed' or 'rejected'")
    reviewed_by: str = Field(..., description="ID of the reviewing user")
    review_note: str | None = None


class FaceMatch(FaceMatchBase):
    """Face match model for API responses."""

    id: str
    status: FaceMatchStatus = FaceMatchStatus.PENDING
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    date_created: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "faceId": "123e4567-e89b-12d3-a456-426614174001",
                "personId": "123e4567-e89b-12d3-a456-426614174002",
                "similarityScore": 0.86,
                "matchMethod": "automatic_similarity",
                "status": "pending",
                "reviewedBy": None,
                "reviewedAt": None,
                "reviewNote": None,
                "dateCreated": "2024-01-01T12:00:00Z",
            }
        },
    }


class FaceMatchSearchParameters(BaseModel):
    """Parameters for listing/searching face matches."""

    face_id: str | None = None
    person_id: str | None = None
    status: FaceMatchStatus | None = Field(FaceMatchStatus.PENDING, description="Filter by review status")
    min_similarity: float | None = Field(default=None, ge=0, le=1)
    limit: int = Field(10, ge=1, le=100)
    page: int = Field(1, ge=1)
    sort_by: FaceMatchSortField = Field(FaceMatchSortField.SIMILARITY_SCORE)
    sort_order: SortOrder = Field(SortOrder.DESC)


class PaginatedFaceMatchesResponse(PaginatedResponse):
    """Paginated response for face matches."""

    data: list[FaceMatch] = Field(..., description="List of face matches")
