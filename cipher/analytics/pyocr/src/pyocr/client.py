"""Async HTTP client for one or more pyocr services (one per GPU)."""

import asyncio
from pathlib import Path

import httpx

from pyocr.schemas import OcrRequest, OcrResponse

DEFAULT_BASE_URL = "http://localhost:8010"


class OcrClient:
    """Routes each file to the service with the fewest pages in flight.

    One vLLM process per GPU scales ~linearly (2x 3090: 10.5 vs 5.6 pages/s) and keeps
    each GPU's replica independent -- a crash or OOM on one doesn't take down the other.
    """

    def __init__(self, base_urls: list[str] | None = None, timeout: float = 900.0):
        self._clients = [httpx.AsyncClient(base_url=url, timeout=timeout) for url in base_urls or [DEFAULT_BASE_URL]]
        self._pages_in_flight = [0] * len(self._clients)

    async def health(self) -> bool:
        """True when every service answers /health."""
        try:
            responses = await asyncio.gather(*(client.get("/health") for client in self._clients))
        except httpx.HTTPError:
            return False
        return all(response.is_success for response in responses)

    async def ocr(self, path: Path, request: OcrRequest) -> OcrResponse:
        """Upload `path` to the least-loaded service and OCR the requested pages."""
        params = {"scanned_only": request.scanned_only, "figures": request.figures}
        if request.pages:
            params["pages"] = request.pages
        weight = len(request.pages) if request.pages else 1
        index = min(range(len(self._clients)), key=self._pages_in_flight.__getitem__)
        self._pages_in_flight[index] += weight
        try:
            data = await asyncio.to_thread(path.read_bytes)
            response = await self._clients[index].post("/ocr", params=params, files={"file": (path.name, data)})
            response.raise_for_status()
            return OcrResponse.model_validate(response.json())
        finally:
            self._pages_in_flight[index] -= weight

    async def aclose(self) -> None:
        """Close the underlying HTTP clients."""
        await asyncio.gather(*(client.aclose() for client in self._clients))
