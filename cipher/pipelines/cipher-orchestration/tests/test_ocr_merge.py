from datetime import UTC, datetime

from pyvllm.ocr.schemas import OcrPage, OcrRegion, OcrResponse

from cipher.orchestration.ocr import build_ocr_extracted_text
from cipher.schemas._base.detection import BoundingBox
from cipher.schemas.content.document import DocumentMetadata, ExtractedTableInfo
from cipher.schemas.content.extraction import ExtractedText, TextExtractor

FILE = {"id": "f1", "filename": "mixed.pdf"}
BOX = BoundingBox(xmin=0.1, ymin=0.1, xmax=0.5, ymax=0.4)


def _existing() -> ExtractedText:
    now = datetime.now(UTC)
    return ExtractedText(
        id="x1",
        file_id="f1",
        content="native page three",
        extractor=TextExtractor.KREUZBERG,
        metadata=DocumentMetadata(
            filename="mixed.pdf",
            title="Kept title",
            tables=[
                ExtractedTableInfo(cells=[["old"]], markdown="| old |", page_number=1),
                ExtractedTableInfo(cells=[["keep"]], markdown="| keep |", page_number=3),
            ],
        ),
        date_created=now,
        date_last_updated=now,
    )


def test_ocr_pages_merge_over_native_text_with_page_spans():
    response = OcrResponse(
        model="jinaai/jina-ocr-v1",
        page_count=3,
        pages=[
            OcrPage(
                page_number=1,
                markdown="# Scanned one",
                tables=[ExtractedTableInfo(cells=[["new"]], markdown="| new |", page_number=1)],
                regions=[OcrRegion(text="A chart", bounding_box=BOX)],
            ),
            OcrPage(page_number=2, markdown=""),
        ],
    )
    merged = build_ocr_extracted_text(FILE, response, _existing(), native_pages={3: "native page three"})

    assert merged.content == "# Scanned one\n\nnative page three"
    assert merged.extractor == TextExtractor.PYVLLM
    assert [(s.first_page, merged.content[s.start_offset : s.end_offset]) for s in merged.prechunked] == [
        (1, "# Scanned one"),
        (3, "native page three"),
    ]
    metadata = merged.metadata
    assert metadata.title == "Kept title"
    assert metadata.ocr_pages == [1, 2] and metadata.ocr_model == "jinaai/jina-ocr-v1"
    assert sorted(t.cells[0][0] for t in metadata.tables) == ["keep", "new"]
    (figure,) = metadata.document_structure
    assert (figure.node_type, figure.page, figure.text, figure.bounding_box) == ("figure", 1, "A chart", BOX)


def test_image_without_text_writes_nothing():
    response = OcrResponse(model="m", page_count=1, pages=[OcrPage(page_number=1, markdown="")])
    assert build_ocr_extracted_text({"id": "f2", "filename": "cat.jpg"}, response, None, native_pages={}) is None
