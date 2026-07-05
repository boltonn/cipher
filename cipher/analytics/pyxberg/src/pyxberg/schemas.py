from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    """Options for a single extraction call.

    Kept to what this pipeline actually needs, not xberg's full config
    surface -- OCR is explicitly configurable per your requirement (e.g.
    skip it for already-text-layer PDFs where it'd just be slow).
    """

    disable_ocr: bool = Field(False, description="Skip OCR entirely")
    ocr_language: str = Field("eng", description="OCR language code, e.g. 'eng', 'deu'")


class ExtractedTableResponse(BaseModel):
    cells: list[list[str]]
    markdown: str
    page_number: int


class ExtractResponse(BaseModel):
    content: str
    tables: list[ExtractedTableResponse] = Field(default_factory=list)
    detected_language: str | None = None
    page_count: int | None = None
