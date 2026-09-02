from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from cipher.schemas._base.base import BaseModel


class EnrichmentType(StrEnum):
    IMAGE_EMBEDDING = "image_embedding"
    EXIF_LOCATION = "exif_location"
    CONTACT_EXTRACTION = "contact_extraction"
    MESSAGE_TRANSLATION = "message_translation"
    FACE_DETECTION = "face_detection"
    FACE_MATCHING = "face_matching"
    TEXT_EXTRACTION = "text_extraction"
    TEXT_EMBEDDING = "text_embedding"
    SELECTOR_EXTRACTION = "selector_extraction"
    ENTITY_EXTRACTION = "entity_extraction"
    RELATIONSHIP_EXTRACTION = "relationship_extraction"
    EVENT_EXTRACTION = "event_extraction"


class ProcessingStatus(StrEnum):
    """Processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EnrichableType(StrEnum):
    """Types of resources that can be enriched."""

    FILE = "file"
    MESSAGE = "message"
    CONTACT = "contact"
    IMAGE = "image"
    FACE = "face"


class EnrichmentBase(BaseModel):
    """Base enrichment schema."""

    enrichable_type: EnrichableType
    enrichable_id: str
    enrichment_type: EnrichmentType
    status: ProcessingStatus = ProcessingStatus.PENDING
    error_message: str | None = None
    retry_count: int = 0


class EnrichmentCreate(EnrichmentBase):
    """Enrichment creation schema."""

    pass


class EnrichmentUpdate(BaseModel):
    """Enrichment update schema."""

    status: ProcessingStatus | None = None
    date_started: datetime | None = None
    date_completed: datetime | None = None
    error_message: str | None = None
    retry_count: int | None = None


class Enrichment(EnrichmentBase):
    """Enrichment model for API responses."""

    id: str
    date_started: datetime | None = None
    date_completed: datetime | None = None
    date_created: datetime
    date_updated: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "enrichable_type": "file",
                "enrichable_id": "123e4567-e89b-12d3-a456-426614174001",
                "enrichment_type": "image_embedding",
                "status": "completed",
                "date_started": "2024-01-01T12:00:00Z",
                "date_completed": "2024-01-01T12:00:05Z",
                "date_created": "2024-01-01T11:59:00Z",
                "date_updated": "2024-01-01T12:00:05Z",
            }
        },
    }


class DatasetEnrichmentProgress(BaseModel):
    """Progress tracking for enrichments across a dataset."""

    dataset_id: str
    enrichment_type: EnrichmentType
    counts: dict[ProcessingStatus, int]
    total: int
    completed: int
    progress: float


class FailedEnrichment(BaseModel):
    """One failed enrichment row, joined to the file it ran against."""

    id: str
    enrichable_id: str
    filename: str
    path: str
    error_message: str | None = None
    retry_count: int = 0
    date_updated: datetime


class EnrichmentFailureReason(BaseModel):
    """A distinct error message and how many failures share it."""

    error_message: str | None = None
    count: int


class DatasetEnrichmentFailures(BaseModel):
    """Failed enrichments for one dataset + analytic: aggregate reasons plus rows."""

    dataset_id: str
    enrichment_type: EnrichmentType
    total: int
    returned: int
    reasons: list[EnrichmentFailureReason]
    items: list[FailedEnrichment]


@dataclass(frozen=True, slots=True)
class EnrichmentBatchItem:
    """Batch item for processing enrichments."""

    enrichment: Enrichment
    resource: dict  # The actual resource data (file, message, etc.)
