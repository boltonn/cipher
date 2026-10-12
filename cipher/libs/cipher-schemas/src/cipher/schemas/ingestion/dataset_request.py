"""Schemas for user-submitted dataset ingestion requests.

A dataset request is filed by a triager who wants an unknown dataset pulled
in and processed. It carries the target dataset id, a name, an optional
free-text description, and the set of analytics (with optional typed
parameters) to run against the dataset once it lands. The backend turns
one of these into a GitHub issue; admins then run it (`cipher worker` plans,
`cipher.schemas.ingestion.run_plan`).
"""

import shlex
from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from cipher.schemas._base.base import BaseModel
from cipher.schemas.identity.face import DEFAULT_FACE_SIMILARITY
from cipher.schemas.ingestion.enrichment import DEFAULT_FILETYPE_GROUPS, EnrichmentType
from cipher.schemas.ingestion.file import ArchiveSandbox


class _AnalyticParams(BaseModel):
    """Base for per-analytic parameter blocks: camelCase on the wire, no unknown keys.

    Each field is a `cipher <command>` option of the same name with the same default
    (`tests/test_request_params.py` holds them in step), so a request reads as the run to do.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


def _groups_field(enrichment_type: EnrichmentType, description: str):
    return Field(default_factory=lambda: list(DEFAULT_FILETYPE_GROUPS[enrichment_type]), description=description)


class ArchiveExtractionParams(_AnalyticParams):
    """`cipher extract-archives`."""

    output_uri: str | None = Field(
        None,
        description="Directory or s3://bucket/prefix for files this step creates (default <OUTPUT_URI>/<dataset id>)",
    )
    max_archive_gib: float | None = Field(
        None, gt=0, description="Skip archives bigger than this (default none for local files, 50 for S3)"
    )
    max_depth: int = Field(5, ge=0, le=32, description="Most archives-within-archives levels to open")
    max_total_gib: float = Field(20, gt=0, description="Most GiB one archive may write")
    max_member_gib: float = Field(8, gt=0, description="Most GiB one member may write")
    max_ratio: float = Field(250, gt=1, description="Most bytes written per compressed byte, per member (zip bombs)")
    max_entries: int = Field(1_000_000, ge=1, description="Most members one archive may list")
    min_free_gib: float = Field(10, ge=0, description="Stop an archive when the scratch disk has less free")
    sandbox: ArchiveSandbox = Field(
        ArchiveSandbox.BEST_EFFORT, description="How 7zz is confined: best effort, required, or off"
    )


class TextExtractionParams(_AnalyticParams):
    """`cipher extract-text`."""

    chunker: Literal["kreuzberg", "clir"] = Field(
        "clir", description="Chunker for documents (clir always chunks email)"
    )
    chunk_size: int = Field(256, ge=64, le=4096, description="Token budget per chunk -- keep equal to text embedding's")
    ocr_backend: Literal["none", "easyocr", "tesseract"] = Field(
        "none", description="Inline OCR for image-based PDF pages; `none` leaves them to the OCR analytic"
    )
    filetype_groups: list[str] = _groups_field(
        EnrichmentType.TEXT_EXTRACTION, "Filetype groups to extract (emails always are); add `table` for spreadsheets"
    )
    archives: bool = Field(True, description="Unpack archives first, and again for any found in emails")
    inline_images: bool = Field(
        True, description="Save images email bodies show (cid: links) as files found in the email; never attachments"
    )
    output_uri: str | None = Field(
        None,
        description="Directory or s3://bucket/prefix for files this step creates (default <OUTPUT_URI>/<dataset id>)",
    )


class OcrParams(_AnalyticParams):
    """`cipher ocr`."""

    all_images: bool = Field(False, description="Skip the CLIP text gate and OCR every image")
    clip_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Text-gate score an image needs to be OCR'd")
    min_chars: int = Field(20, ge=0, description="PDF pages with fewer text-layer chars are OCR'd")
    force: bool = Field(False, description="OCR every PDF page, not just image-based ones")
    figures: bool = Field(False, description="Also locate and caption figures")


class TextEmbeddingParams(_AnalyticParams):
    """`cipher embed-text`."""

    chunk_size: int = Field(
        256, ge=64, le=4096, description="Token budget per chunk -- keep equal to text extraction's"
    )
    chunk_overlap: int = Field(0, ge=0, le=1024, description="Token overlap between consecutive chunks")
    max_pages: int | None = Field(None, ge=1, description="Only embed a document's first N pages")
    filetype_groups: list[str] = _groups_field(
        EnrichmentType.TEXT_EMBEDDING, "Filetype groups whose extracted text is chunked and embedded"
    )


class ImageEmbeddingParams(_AnalyticParams):
    """`cipher embed-images`."""

    classify: bool = Field(False, description="Also score every image with the trained tag heads")
    min_image_side: int = Field(64, ge=1, description="Skip images smaller than this (px)")


class FaceDetectionParams(_AnalyticParams):
    """`cipher detect-faces`."""

    min_image_side: int = Field(64, ge=1, description="Skip images smaller than this (px)")


class FaceMatchingParams(_AnalyticParams):
    """`cipher match-faces`."""

    similarity: float = Field(
        DEFAULT_FACE_SIMILARITY, ge=0.0, le=1.0, description="Min cosine similarity to propose a match"
    )
    verified_only: bool = Field(False, description="Match only against analyst-verified people")
    per_face_limit: int = Field(500, ge=1, description="Max candidate faces pulled per representative face")


class FaceClusteringParams(_AnalyticParams):
    """`cipher cluster-faces`."""

    similarity: float = Field(
        DEFAULT_FACE_SIMILARITY, ge=0.0, le=1.0, description="Min cosine similarity for a face-to-face edge"
    )
    min_images: int = Field(3, ge=1, le=1000, description="Distinct images a cluster must span to become a person")
    min_faces: int = Field(2, ge=2, le=1000, description="Faces a cluster must contain to become a person")
    k: int = Field(20, ge=2, le=200, description="Nearest neighbours considered per face")
    no_merge: bool = Field(False, description="Always create a fresh person rather than merging into a nearby one")


class SelectorExtractionParams(_AnalyticParams):
    """`cipher extract-selectors`."""

    filetype_groups: list[str] = _groups_field(
        EnrichmentType.SELECTOR_EXTRACTION, "Filetype groups whose extracted text is scanned for selectors"
    )


class EntityExtractionParams(_AnalyticParams):
    """`cipher extract-entities`."""

    extractor: Literal["nerd", "gliner", "llm"] = Field("nerd", description="NER engine")
    threshold: float | None = Field(
        None, ge=0.0, le=1.0, description="Span score floor (default 0.65 gliner, 0.5 nerd; unused by llm)"
    )
    filetype_groups: list[str] = _groups_field(
        EnrichmentType.ENTITY_EXTRACTION, "Filetype groups whose extracted text goes through NER"
    )


class EventExtractionParams(_AnalyticParams):
    """`cipher extract-events`."""

    llm: bool = Field(False, description="Also read email bodies with the LLM (calendar files alone otherwise)")
    docs: bool = Field(False, description="LLM pass also reads documents, not just email")
    gate: bool = Field(True, description="Send only files GLiNER scores as likely events to the LLM")
    gate_threshold: float = Field(0.4, ge=0.0, le=1.0, description="Gate score a file needs to reach the LLM")
    concurrency: int = Field(8, ge=1, le=64, description="LLM calls in flight at once")


class SignatureExtractionParams(_AnalyticParams):
    """`cipher extract-signatures`."""

    include_bulk: bool = Field(False, description="Also read promotions / updates / social / forums mail")
    concurrency: int = Field(8, ge=1, le=64, description="LLM calls in flight at once")


class TableExtractionParams(_AnalyticParams):
    """`cipher map-tables` (then review on /tables, then `cipher emit-tables`)."""

    detectors: str = Field("header,validators", description="Comma list of: header, validators, gliner, nerd, llm")
    region: str | None = Field(
        None, min_length=2, max_length=2, description="ISO-3166 alpha-2 region for phone numbers"
    )


class SummarizationParams(_AnalyticParams):
    """`cipher summarize`."""

    filetype_groups: list[str] = _groups_field(EnrichmentType.TEXT_SUMMARIZATION, "Filetype groups to summarize")
    language: str = Field("English", description="Language the summaries are written in")
    concurrency: int = Field(8, ge=1, le=64, description="LLM calls in flight at once")


ANALYTIC_PARAM_MODELS: dict[EnrichmentType, type[_AnalyticParams]] = {
    EnrichmentType.ARCHIVE_EXTRACTION: ArchiveExtractionParams,
    EnrichmentType.TEXT_EXTRACTION: TextExtractionParams,
    EnrichmentType.OCR: OcrParams,
    EnrichmentType.TEXT_EMBEDDING: TextEmbeddingParams,
    EnrichmentType.IMAGE_EMBEDDING: ImageEmbeddingParams,
    EnrichmentType.FACE_DETECTION: FaceDetectionParams,
    EnrichmentType.FACE_MATCHING: FaceMatchingParams,
    EnrichmentType.FACE_CLUSTERING: FaceClusteringParams,
    EnrichmentType.SELECTOR_EXTRACTION: SelectorExtractionParams,
    EnrichmentType.ENTITY_EXTRACTION: EntityExtractionParams,
    EnrichmentType.EVENT_EXTRACTION: EventExtractionParams,
    EnrichmentType.SIGNATURE_EXTRACTION: SignatureExtractionParams,
    EnrichmentType.TABLE_EXTRACTION: TableExtractionParams,
    EnrichmentType.TEXT_SUMMARIZATION: SummarizationParams,
}
"""Analytics not listed here (exif_location, contact_extraction, relationship_extraction) take no parameters."""

ANALYTIC_COMMANDS: dict[EnrichmentType, str] = {
    EnrichmentType.ARCHIVE_EXTRACTION: "extract-archives",
    EnrichmentType.TEXT_EXTRACTION: "extract-text",
    EnrichmentType.OCR: "ocr",
    EnrichmentType.TEXT_EMBEDDING: "embed-text",
    EnrichmentType.IMAGE_EMBEDDING: "embed-images",
    EnrichmentType.EXIF_LOCATION: "extract-locations",
    EnrichmentType.FACE_DETECTION: "detect-faces",
    EnrichmentType.FACE_MATCHING: "match-faces",
    EnrichmentType.FACE_CLUSTERING: "cluster-faces",
    EnrichmentType.CONTACT_EXTRACTION: "extract-contact-entities",
    EnrichmentType.SELECTOR_EXTRACTION: "extract-selectors",
    EnrichmentType.ENTITY_EXTRACTION: "extract-entities",
    EnrichmentType.RELATIONSHIP_EXTRACTION: "extract-relationships",
    EnrichmentType.EVENT_EXTRACTION: "extract-events",
    EnrichmentType.SIGNATURE_EXTRACTION: "extract-signatures",
    EnrichmentType.TABLE_EXTRACTION: "map-tables",
    EnrichmentType.TEXT_SUMMARIZATION: "summarize",
}
"""The `cipher` command that runs each requestable analytic."""


class AnalyticRequest(BaseModel):
    """One analytic to run against the requested dataset, with optional tuning."""

    enrichment_type: EnrichmentType
    parameters: dict[str, Any] = Field(default_factory=dict, description="Analytic-specific tuning parameters")

    @model_validator(mode="after")
    def _validate_parameters(self) -> "AnalyticRequest":
        model = ANALYTIC_PARAM_MODELS.get(self.enrichment_type)
        if model is None:
            if self.parameters:
                raise ValueError(f"{self.enrichment_type.value} does not accept parameters")
            return self
        self.parameters = model.model_validate(self.parameters).model_dump(by_alias=True, exclude_none=True)
        return self

    def command(self, *, dataset_id: str) -> str:
        """The `cipher` invocation for this analytic, with only the options that differ from their defaults."""
        from cipher.schemas.ingestion.run_plan import step_command

        return shlex.join(["cipher", *step_command(self.enrichment_type.value, self.parameters, dataset_id=dataset_id)])


class DatasetRequest(BaseModel):
    """A triager's request to ingest and process a dataset."""

    dataset_id: str = Field(min_length=1, max_length=255, description="Identifier of the dataset being requested")
    name: str = Field(min_length=1, max_length=255, description="Human-friendly dataset name")
    description: str | None = Field(None, max_length=5000, description="Optional description of the dataset")
    analytics: list[AnalyticRequest] = Field(
        default_factory=list, description="Analytics to run once the dataset is ingested"
    )

    @model_validator(mode="after")
    def _no_duplicate_analytics(self) -> "DatasetRequest":
        requested = [item.enrichment_type for item in self.analytics]
        if len(requested) != len(set(requested)):
            raise ValueError("The same analytic was requested more than once")
        return self


class DatasetRequestResult(BaseModel):
    """The GitHub issue created for a dataset request."""

    issue_number: int = Field(description="Number of the created GitHub issue")
    issue_url: str = Field(description="Web URL of the created GitHub issue")
    issues_url: str = Field(description="URL listing every open dataset-request issue")


class DatasetRequestConfig(BaseModel):
    """Whether dataset requests can be filed, and where the issues live.

    Backed by an optional GitHub integration -- `configured=False` is a normal
    result (nothing to report yet), not an error, so the UI can say so plainly
    instead of a request silently failing.
    """

    configured: bool = Field(description="Whether the GitHub integration is set up")
    repo: str | None = Field(None, description="owner/repo that receives dataset-request issues")
    issues_url: str | None = Field(None, description="URL listing every open dataset-request issue")


class EnrichmentRequest(BaseModel):
    """A triager's request to run more analytics on an already-loaded dataset."""

    dataset_id: str = Field(min_length=1, max_length=255, description="Dataset to enrich")
    analytics: list[AnalyticRequest] = Field(min_length=1, description="Analytics to run")
    note: str | None = Field(default=None, max_length=5000, description="Why these analytics are wanted")

    @model_validator(mode="after")
    def _no_duplicate_analytics(self) -> "EnrichmentRequest":
        requested = [item.enrichment_type for item in self.analytics]
        if len(requested) != len(set(requested)):
            raise ValueError("The same analytic was requested more than once")
        return self


class EnrichmentRequestResult(BaseModel):
    """The rendered enrichment request, plus the GitHub issue when the integration is configured."""

    title: str = Field(description="Issue title")
    body: str = Field(description="Issue body (markdown) -- copyable when no issue was filed")
    issue_number: int | None = Field(default=None, description="Number of the created GitHub issue")
    issue_url: str | None = Field(default=None, description="Web URL of the created GitHub issue")
