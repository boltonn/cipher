from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel, StrEnum
from cipher.schemas._base.common import PageParams, PaginatedResponse
from cipher.schemas._base.review import MatchSortField, ReviewableMixin, ReviewDecision, ReviewStatus

# Back-compat aliases -- prefer the shared names from `cipher.schemas._base.review`.
FaceMatchStatus = ReviewStatus
FaceMatchSortField = MatchSortField


class FaceMatchMethod(StrEnum):
    """How a candidate match was proposed."""

    AUTOMATIC_SIMILARITY = "automatic_similarity"
    AUTOMATIC_CLUSTERING = "automatic_clustering"
    MANUAL = "manual"


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


class FaceMatchReview(ReviewDecision):
    """Schema for an analyst resolving a candidate match."""

    pass


class FaceMatch(ReviewableMixin, FaceMatchBase):
    """Face match model for API responses."""

    id: str
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


class FaceMatchSearchParameters(PageParams):
    """Parameters for listing/searching face matches."""

    face_id: str | None = None
    person_id: str | None = None
    status: ReviewStatus | None = Field(ReviewStatus.PENDING, description="Filter by review status")
    min_similarity: float | None = Field(default=None, ge=0, le=1)
    limit: int = Field(10, ge=1, le=100)
    sort_by: MatchSortField = Field(MatchSortField.SIMILARITY_SCORE)


class PaginatedFaceMatchesResponse(PaginatedResponse):
    """Paginated response for face matches."""

    data: list[FaceMatch] = Field(..., description="List of face matches")
