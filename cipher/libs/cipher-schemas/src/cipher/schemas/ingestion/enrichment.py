from collections.abc import Iterable
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
    FACE_CLUSTERING = "face_clustering"
    TEXT_EXTRACTION = "text_extraction"
    OCR = "ocr"
    TEXT_EMBEDDING = "text_embedding"
    SELECTOR_EXTRACTION = "selector_extraction"
    ENTITY_EXTRACTION = "entity_extraction"
    RELATIONSHIP_EXTRACTION = "relationship_extraction"
    EVENT_EXTRACTION = "event_extraction"


# Hard prerequisites: an enrichment reads rows a prior enrichment produces and
# yields nothing without it (e.g. `entity_extraction` reads `ExtractedText`, so
# `text_extraction` must run first). Detectors that stub their own upstream rows
# on demand -- `exif_location`, `face_detection`, `image_embedding` -- have none.
# This map is the single source of truth: `docs/enrichments.md` and
# `GET /enrichments/config` are derived from it. Types absent from the dict have
# no prerequisites.
ENRICHMENT_DEPENDENCIES: dict[EnrichmentType, tuple[EnrichmentType, ...]] = {
    # PDFs only: OCR merges scanned pages into the xberg extraction (images need nothing).
    EnrichmentType.OCR: (EnrichmentType.TEXT_EXTRACTION,),
    EnrichmentType.TEXT_EMBEDDING: (EnrichmentType.TEXT_EXTRACTION,),
    EnrichmentType.SELECTOR_EXTRACTION: (EnrichmentType.TEXT_EXTRACTION,),
    EnrichmentType.ENTITY_EXTRACTION: (EnrichmentType.TEXT_EXTRACTION,),
    EnrichmentType.RELATIONSHIP_EXTRACTION: (
        EnrichmentType.ENTITY_EXTRACTION,
        EnrichmentType.SELECTOR_EXTRACTION,
    ),
    EnrichmentType.FACE_MATCHING: (EnrichmentType.FACE_DETECTION,),
    EnrichmentType.FACE_CLUSTERING: (EnrichmentType.FACE_DETECTION,),
}


def enrichment_prerequisites(enrichment_type: EnrichmentType) -> list[EnrichmentType]:
    """Every enrichment that must complete before `enrichment_type`, transitively.

    Dependency-ordered: each entry precedes anything that depends on it. The
    requested type itself is not included.
    """
    ordered: list[EnrichmentType] = []
    seen: set[EnrichmentType] = set()

    def visit(current: EnrichmentType) -> None:
        for dep in ENRICHMENT_DEPENDENCIES.get(current, ()):
            if dep not in seen:
                seen.add(dep)
                visit(dep)
                ordered.append(dep)

    visit(enrichment_type)
    return ordered


def resolve_enrichment_order(types: Iterable[EnrichmentType]) -> list[EnrichmentType]:
    """`types` plus all their transitive prerequisites, deduped and ordered so
    every prerequisite precedes the enrichment that needs it.
    """
    result: list[EnrichmentType] = []
    seen: set[EnrichmentType] = set()

    def add(current: EnrichmentType) -> None:
        if current in seen:
            return
        for dep in ENRICHMENT_DEPENDENCIES.get(current, ()):
            add(dep)
        seen.add(current)
        result.append(current)

    for enrichment_type in types:
        add(enrichment_type)
    return result


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
