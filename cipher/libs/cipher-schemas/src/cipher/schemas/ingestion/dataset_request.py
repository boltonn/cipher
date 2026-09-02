"""Schemas for user-submitted dataset ingestion requests.

A dataset request is filed by a triager who wants an unknown dataset pulled
in and processed. It carries the target dataset id, an optional name, a
free-text justification, and the set of analytics (with optional typed
parameters) to run against the dataset once it lands. The backend turns
one of these into a GitHub issue.
"""

from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from cipher.schemas._base.base import BaseModel
from cipher.schemas.ingestion.enrichment import EnrichmentType


class _AnalyticParams(BaseModel):
    """Base for per-analytic parameter blocks: camelCase on the wire, no unknown keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class TextExtractionParams(_AnalyticParams):
    chunker: Literal["kreuzberg", "clir"] = Field(
        "kreuzberg", description="Chunker that splits extracted document text"
    )
    chunk_size: int = Field(512, ge=64, le=4096, description="Token budget per chunk")
    max_pages: int | None = Field(None, ge=1, description="Cap on pages extracted per document")


class TextEmbeddingParams(_AnalyticParams):
    chunk_size: int = Field(512, ge=64, le=4096, description="Token budget per chunk")
    max_pages: int | None = Field(None, ge=1, description="Cap on pages embedded per document")


class ImageEmbeddingParams(_AnalyticParams):
    batch_size: int = Field(32, ge=1, le=512, description="Images encoded per batch")


class FaceDetectionParams(_AnalyticParams):
    batch_size: int = Field(25, ge=1, le=512, description="Images fetched and decoded per batch")


class FaceMatchingParams(_AnalyticParams):
    similarity_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum cosine similarity to call a match")
    top_k: int = Field(10, ge=1, le=100, description="Candidate matches kept per face")


class MessageTranslationParams(_AnalyticParams):
    target_language: str = Field("en", min_length=2, max_length=8, description="ISO code to translate messages into")
    batch_size: int = Field(16, ge=1, le=256, description="Messages translated per batch")


ANALYTIC_PARAM_MODELS: dict[EnrichmentType, type[_AnalyticParams]] = {
    EnrichmentType.TEXT_EXTRACTION: TextExtractionParams,
    EnrichmentType.TEXT_EMBEDDING: TextEmbeddingParams,
    EnrichmentType.IMAGE_EMBEDDING: ImageEmbeddingParams,
    EnrichmentType.FACE_DETECTION: FaceDetectionParams,
    EnrichmentType.FACE_MATCHING: FaceMatchingParams,
    EnrichmentType.MESSAGE_TRANSLATION: MessageTranslationParams,
}
"""Analytics not listed here (e.g. contact_extraction) take no parameters."""


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


class DatasetRequest(BaseModel):
    """A triager's request to ingest and process a dataset."""

    dataset_id: str = Field(min_length=1, max_length=255, description="Identifier of the dataset being requested")
    name: str | None = Field(None, max_length=255, description="Human-friendly dataset name")
    reason: str = Field(min_length=10, max_length=5000, description="Why this dataset is needed")
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
    """Where dataset-request issues live, so the UI can link out to them."""

    repo: str = Field(description="owner/repo that receives dataset-request issues")
    issues_url: str = Field(description="URL listing every open dataset-request issue")
