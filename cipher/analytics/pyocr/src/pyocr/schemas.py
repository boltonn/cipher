from enum import StrEnum

from pydantic import BaseModel, Field

from cipher.schemas._base.detection import BoundingBox
from cipher.schemas.content.document import ExtractedTableInfo


class OcrBackend(StrEnum):
    """Inference runtime. VLLM is the fast path (continuous batching + FastMTP speculative decoding)."""

    VLLM = "vllm"
    TRANSFORMERS = "transformers"


class OcrRegion(BaseModel):
    """A located region on a page -- currently figures, when requested with `figures=True`."""

    label: str = Field(default="figure")
    text: str | None = Field(default=None, description="Model-written caption (AI description, not document text)")
    bounding_box: BoundingBox


class OcrPage(BaseModel):
    page_number: int = Field(description="1-indexed page (PDF page or image frame)")
    markdown: str = Field(description="Transcribed page text as markdown; empty when the page has no text")
    tables: list[ExtractedTableInfo] = Field(default_factory=list, description="Tables, also inlined as pipe tables")
    regions: list[OcrRegion] = Field(default_factory=list)


class OcrRequest(BaseModel):
    """Options for one OCR call over a PDF or image."""

    pages: list[int] | None = Field(default=None, description="1-indexed pages to OCR; None means every page")
    scanned_only: bool = Field(
        default=False, description="PDFs only: restrict to pages with no usable text layer (image-based pages)"
    )
    figures: bool = Field(
        default=False,
        description="Use the grounding prompt so figures come back located + captioned. "
        "Trades some markdown structure (headings) for figure regions",
    )


class OcrResponse(BaseModel):
    model: str
    page_count: int = Field(description="Total pages/frames in the source, OCR'd or not")
    pages: list[OcrPage] = Field(default_factory=list, description="Only the pages that were OCR'd")
