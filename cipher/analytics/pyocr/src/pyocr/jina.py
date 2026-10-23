"""jina-ocr-v1 engine: render pages here, transcribe each on pyvllm's local `ocr` server (vLLM, GPU).

jina-ocr-v1 is a generative vision-language model; vLLM's continuous batching and its FastMTP
speculative heads make it ~30-90x faster than transformers `generate()`, which reads one page
per call -- hence a local server rather than loading the model in this process.

Throughput comes from keeping many pages in flight -- vLLM batches every concurrent
request into shared GPU steps -- so pages of every file being OCR'd are sent together,
bounded by `MAX_PAGES_IN_FLIGHT` rendered pages held in memory.
"""

import asyncio
import base64
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image
from pyvllm.models import MODELS
from pyvllm.settings import settings

from pyocr.pages import DEFAULT_MAX_SIDE, pages_to_read, render_pages
from pyocr.parse import DEFAULT_PROMPT, FIGURE_PROMPT, parse_page
from pyocr.schemas import OcrPage, OcrRequest, OcrResponse

MAX_PAGES_IN_FLIGHT = 96
MAX_TOKENS_PER_PAGE = 4096
# jina-ocr-v1's own decoding defaults (deepseek_ocr_mtp.vllm_sampling_params): greedy, a light
# repetition penalty, vLLM's n-gram loop stopper, and special tokens kept for figure tags.
_SAMPLING = {
    "temperature": 0.0,
    "repetition_penalty": 1.05,
    "skip_special_tokens": False,
    "repetition_detection": {"max_pattern_size": 35, "min_pattern_size": 35, "min_count": 10},
}


def _data_url(image: Image.Image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"


class JinaOcr:
    """Sends each page to the `ocr` server with the fewest pages in flight (one server per GPU scales ~linearly)."""

    def __init__(self, base_urls: list[str] | None = None, timeout: float = 900.0, max_side: int = DEFAULT_MAX_SIDE):
        urls = base_urls or [MODELS["ocr"].base_url]
        self.model = MODELS["ocr"].served_name
        self.max_side = max_side
        self._clients = [
            httpx.AsyncClient(base_url=url, timeout=timeout, headers=settings.auth_headers) for url in urls
        ]
        self._pages_in_flight = [0] * len(self._clients)
        self._slots = asyncio.Semaphore(MAX_PAGES_IN_FLIGHT)

    async def health(self) -> bool:
        """True when every server answers /health."""
        try:
            responses = await asyncio.gather(*(client.get("/health") for client in self._clients))
        except httpx.HTTPError:
            return False
        return all(response.is_success for response in responses)

    async def transcribe(self, image: Image.Image, figures: bool = False) -> str:
        """Raw model output for one page image."""
        index = min(range(len(self._clients)), key=self._pages_in_flight.__getitem__)
        self._pages_in_flight[index] += 1
        try:
            url = await asyncio.to_thread(_data_url, image)
            content = [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": FIGURE_PROMPT if figures else DEFAULT_PROMPT},
            ]
            response = await self._clients[index].post(
                "/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": MAX_TOKENS_PER_PAGE,
                    **_SAMPLING,
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"] or ""
        finally:
            self._pages_in_flight[index] -= 1

    async def ocr(self, path: Path, request: OcrRequest) -> OcrResponse:
        """Transcribe the requested pages of a PDF or image."""
        total, pages = await asyncio.to_thread(pages_to_read, path, request.pages, request.scanned_only)
        if pages == []:
            return OcrResponse(model=self.model, page_count=total)

        async def one(number: int, image: Image.Image) -> OcrPage:
            try:
                return parse_page(await self.transcribe(image, figures=request.figures), page_number=number)
            finally:
                self._slots.release()

        iterator = render_pages(path, pages=pages, max_side=self.max_side)
        tasks = []
        while True:
            await self._slots.acquire()
            rendered = await asyncio.to_thread(next, iterator, None)
            if rendered is None:
                self._slots.release()
                break
            tasks.append(asyncio.create_task(one(*rendered)))
        results = await asyncio.gather(*tasks)
        return OcrResponse(model=self.model, page_count=total, pages=sorted(results, key=lambda p: p.page_number))

    async def aclose(self) -> None:
        """Close the HTTP clients."""
        await asyncio.gather(*(client.aclose() for client in self._clients))
