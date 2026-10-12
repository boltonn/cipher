from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel, StrEnum


class EnrichmentType(StrEnum):
    ARCHIVE_EXTRACTION = "archive_extraction"
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
    SIGNATURE_EXTRACTION = "signature_extraction"
    TABLE_EXTRACTION = "table_extraction"
    TEXT_SUMMARIZATION = "text_summarization"


# Hard prerequisites: an enrichment reads rows a prior enrichment produces and
# yields nothing without it (e.g. `entity_extraction` reads `ExtractedText`, so
# `text_extraction` must run first). Detectors that stub their own upstream rows
# on demand -- `exif_location`, `face_detection`, `image_embedding` -- need nothing per file.
# `archive_extraction` is dataset-level: it creates the files inside archives (and decodes
# compressed ones), so every analytic that reads files directly runs after it.
# This map is the single source of truth: `docs/enrichments.md` and
# `GET /enrichments/config` are derived from it. Types absent from the dict have
# no prerequisites.
ENRICHMENT_DEPENDENCIES: dict[EnrichmentType, tuple[EnrichmentType, ...]] = {
    EnrichmentType.TEXT_EXTRACTION: (EnrichmentType.ARCHIVE_EXTRACTION,),
    EnrichmentType.IMAGE_EMBEDDING: (EnrichmentType.ARCHIVE_EXTRACTION,),
    EnrichmentType.EXIF_LOCATION: (EnrichmentType.ARCHIVE_EXTRACTION,),
    EnrichmentType.FACE_DETECTION: (EnrichmentType.ARCHIVE_EXTRACTION,),
    EnrichmentType.CONTACT_EXTRACTION: (EnrichmentType.ARCHIVE_EXTRACTION,),
    EnrichmentType.TABLE_EXTRACTION: (EnrichmentType.ARCHIVE_EXTRACTION,),
    # PDFs only: OCR merges scanned pages into the xberg extraction (images need nothing).
    EnrichmentType.OCR: (EnrichmentType.TEXT_EXTRACTION,),
    EnrichmentType.TEXT_EMBEDDING: (EnrichmentType.TEXT_EXTRACTION,),
    EnrichmentType.SELECTOR_EXTRACTION: (EnrichmentType.TEXT_EXTRACTION,),
    EnrichmentType.ENTITY_EXTRACTION: (EnrichmentType.TEXT_EXTRACTION,),
    EnrichmentType.SIGNATURE_EXTRACTION: (EnrichmentType.TEXT_EXTRACTION,),
    EnrichmentType.RELATIONSHIP_EXTRACTION: (
        EnrichmentType.ENTITY_EXTRACTION,
        EnrichmentType.SELECTOR_EXTRACTION,
    ),
    EnrichmentType.FACE_MATCHING: (EnrichmentType.FACE_DETECTION,),
    EnrichmentType.FACE_CLUSTERING: (EnrichmentType.FACE_DETECTION,),
}


# Enrichments that read `ExtractedText.content` but aren't listed above as needing text extraction:
# events also parse `.ics` files directly, and summaries cover mapped tables too.
TEXT_READERS: frozenset[EnrichmentType] = frozenset(
    {EnrichmentType.EVENT_EXTRACTION, EnrichmentType.TEXT_SUMMARIZATION}
)

# Produce text rather than read it: a change to the text is what they would cause, not undo.
TEXT_PRODUCERS: frozenset[EnrichmentType] = frozenset({EnrichmentType.TEXT_EXTRACTION, EnrichmentType.OCR})


def affected_by_text_change() -> frozenset[EnrichmentType]:
    """Every enrichment whose output follows from a file's text, directly or through another one's output."""
    affected = set(TEXT_READERS) | {
        enrichment_type
        for enrichment_type, prerequisites in ENRICHMENT_DEPENDENCIES.items()
        if TEXT_PRODUCERS.intersection(prerequisites)
    }
    affected -= TEXT_PRODUCERS
    while grown := {
        enrichment_type
        for enrichment_type, prerequisites in ENRICHMENT_DEPENDENCIES.items()
        if affected.intersection(prerequisites) and enrichment_type not in affected
    }:
        affected |= grown
    return frozenset(affected)


# Which filetype groups each text analytic reads by default. Tables (`table`) are left out:
# `cipher map-tables` maps them column by column, so running these over their flattened text
# mostly double-counts. Every one of these takes a `filetype_groups` parameter to add them.
# Text extraction: documents + emails (images get text from OCR, not here).
DEFAULT_FILETYPE_GROUPS: dict[EnrichmentType, tuple[str, ...]] = {
    EnrichmentType.TEXT_EXTRACTION: ("document", "email"),
    EnrichmentType.TEXT_EMBEDDING: ("document", "email", "image"),
    EnrichmentType.SELECTOR_EXTRACTION: ("document", "email", "image"),
    EnrichmentType.ENTITY_EXTRACTION: ("document", "email", "image"),
    # Opt-in (an LLM call per file): tables are summarized from their sample + column mapping.
    EnrichmentType.TEXT_SUMMARIZATION: ("document", "email", "image", "table"),
}


# Groups whose files are text-bearing by nature; any other group's files are queued for a text
# analytic only when they actually have extracted text (OCR'd images, opted-in tables).
TEXT_NATIVE_GROUPS: frozenset[str] = frozenset({"document", "email"})


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
    """`types` plus all their transitive prerequisites, deduped, each prerequisite first."""
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


class EnrichmentStageProgress(BaseModel):
    """One pass of a multi-pass analytic, e.g. event extraction's gate and then its LLM read."""

    name: str
    label: str
    total: int
    completed: int
    skipped: int = Field(default=0, description="Filtered out by this pass")
    failed: int = Field(default=0)
    skip_reasons: dict[str, int] = Field(default_factory=dict, description="Why rows were filtered out -> count")


# `enrichment_run.enrichment_type` of the entity-resolution sweep (`cipher resolve-entities`)
RESOLUTION_RUN = "entity_resolution"


class SweepStep(BaseModel):
    """One step of a dataset-wide sweep (entity resolution), as it reports its own progress."""

    name: str
    label: str
    done: int = 0
    total: int = 0
    status: str = Field(default="pending", description="pending | running | completed")


class SweepRun(BaseModel):
    """The latest run of a dataset-wide sweep: its status and each step's progress."""

    status: str = Field(description="running | completed | failed | stopped")
    date_started: datetime
    date_completed: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    steps: list[SweepStep] = Field(default_factory=list)


class DatasetEnrichmentProgress(BaseModel):
    """Progress tracking for enrichments across a dataset."""

    dataset_id: str
    enrichment_type: EnrichmentType
    counts: dict[ProcessingStatus, int]
    total: int
    completed: int
    progress: float
    stages: list[EnrichmentStageProgress] = Field(
        default_factory=list, description="Per-pass progress when the analytic runs in passes"
    )
    skip_reasons: dict[str, int] = Field(default_factory=dict, description="Why rows were skipped -> count")
    date_last_run: datetime | None = Field(
        default=None, description="For dataset-wide passes without per-file rows: when the latest run started"
    )
    is_running: bool = Field(
        default=False,
        description="A worker is on it: the latest recorded run is still open or rows are mid-processing",
    )


class FailedEnrichment(BaseModel):
    """One failed enrichment row, joined to the file it ran against."""

    id: str
    enrichable_id: str
    filename: str
    path: str
    uri: str
    filetype: str
    filetype_group: str
    mime_type: str
    size: int
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
