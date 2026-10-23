"""In-process OCR with Datalab's Indra OCR (`indra-ocr`): CPU-only ONNX models, no server, no HTTP.

Same interface as `pyocr.jina.JinaOcr` (`model`, `health`, `ocr`, `aclose`), so `cipher ocr --engine indra` swaps
it in. Each page is rendered and read inside a pool of worker processes, one single-threaded Indra
converter per process -- Indra's own scaling recipe (`indra_ocr.convert_many`). Its markdown
(tables as HTML) goes through the same `parse_page` as jina-ocr-v1's, so tables come out the same.

Weights come from `INDRA_OCR_MODEL_DIR`, else the Hugging Face cache (`make download-indra` in analytics/pyocr).
"""

import asyncio
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from pyocr.pages import pages_to_read, render_pages
from pyocr.parse import parse_page
from pyocr.schemas import OcrRequest, OcrResponse

INDRA_MODEL = "datalab-to/indra-ocr"
# Indra reads PDFs at 200 dpi: about 2200 px on the long side of a Letter / A4 page.
INDRA_MAX_SIDE = 2200

_converter = None


def _start_worker(model_dir: str | None) -> None:
    global _converter
    import cv2
    import indra_ocr

    cv2.setNumThreads(1)
    _converter = indra_ocr.load(model_dir, threads=1, mode="ocr")


def _read_page(path: str, page_number: int, max_side: int) -> str:
    """Markdown of one page, rendered and OCR'd in this worker."""
    _, image = next(render_pages(Path(path), pages=[page_number], max_side=max_side))
    page = _converter.ocr(np.asarray(image.convert("L")))
    return page.markdown if page.markdown is not None else page.text


class IndraOcr:
    """Reads pages on this machine's CPU cores with Indra OCR."""

    def __init__(self, *, workers: int | None = None, model_dir: str | None = None, max_side: int = INDRA_MAX_SIDE):
        try:
            import indra_ocr
        except ImportError as e:
            raise RuntimeError(
                "Indra OCR is not installed -- `uv sync --extra ocr` (cipher-orchestration) or `pip install pyocr[indra]`"
            ) from e
        self.model = INDRA_MODEL
        self.max_side = max_side
        self.model_dir = model_dir
        self.workers = workers or indra_ocr.usable_cores()
        # spawn, not fork: the parent holds an event loop, DB connections and threads
        self._pool = ProcessPoolExecutor(
            max_workers=self.workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_start_worker,
            initargs=(model_dir,),
        )

    async def health(self) -> bool:
        """True when the model files are on disk (or downloadable)."""
        import indra_ocr

        try:
            await asyncio.to_thread(indra_ocr.model_dir, self.model_dir)
        except indra_ocr.ModelError:
            return False
        return True

    async def ocr(self, path: Path, request: OcrRequest) -> OcrResponse:
        """Transcribe the requested pages of a PDF or image. `request.figures` is ignored (no captions)."""
        total, pages = await asyncio.to_thread(pages_to_read, path, request.pages, request.scanned_only)
        numbers = [page for page in (range(1, total + 1) if pages is None else pages) if 1 <= page <= total]
        loop = asyncio.get_running_loop()
        markdowns = await asyncio.gather(
            *(loop.run_in_executor(self._pool, _read_page, str(path), number, self.max_side) for number in numbers)
        )
        return OcrResponse(
            model=self.model,
            page_count=total,
            pages=[parse_page(markdown, page_number=number) for number, markdown in zip(numbers, markdowns, strict=True)],
        )

    async def aclose(self) -> None:
        """Stop the worker processes."""
        await asyncio.to_thread(self._pool.shutdown, cancel_futures=True)
