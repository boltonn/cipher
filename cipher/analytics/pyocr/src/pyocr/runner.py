"""Render + transcribe a whole source, shared by the API and the CLI."""

import asyncio

from pyocr.engine import OcrEngine
from pyocr.pages import DEFAULT_MAX_SIDE, Source, page_count, render_pages, scanned_pages
from pyocr.parse import parse_page
from pyocr.schemas import OcrPage, OcrRequest, OcrResponse

# Rendered pages waiting on the model, per call -- bounds memory on huge scans
# while staying above the engine's own concurrency so the GPU never starves.
MAX_PAGES_IN_FLIGHT = 96


async def ocr_source(
    engine: OcrEngine, source: Source, request: OcrRequest, max_side: int = DEFAULT_MAX_SIDE
) -> OcrResponse:
    """Transcribe the requested pages of a PDF/image, all pages in flight concurrently."""
    total = await asyncio.to_thread(page_count, source)
    pages = request.pages
    if request.scanned_only:
        scanned = await asyncio.to_thread(scanned_pages, source)
        pages = [p for p in scanned if pages is None or p in pages]
    if pages == []:
        return OcrResponse(model=engine.model_name, page_count=total)

    slots = asyncio.Semaphore(MAX_PAGES_IN_FLIGHT)

    async def transcribe(number: int, image) -> OcrPage:
        try:
            return parse_page(await engine.transcribe(image, figures=request.figures), page_number=number)
        finally:
            slots.release()

    iterator = render_pages(source, pages=pages, max_side=max_side)
    tasks = []
    while True:
        await slots.acquire()
        rendered = await asyncio.to_thread(next, iterator, None)
        if rendered is None:
            slots.release()
            break
        tasks.append(asyncio.create_task(transcribe(*rendered)))

    results = await asyncio.gather(*tasks)
    return OcrResponse(model=engine.model_name, page_count=total, pages=sorted(results, key=lambda p: p.page_number))
