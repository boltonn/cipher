"""Async HTTP client for the pyocr service."""

import asyncio
from pathlib import Path

import httpx

from pyocr.schemas import OcrRequest, OcrResponse

DEFAULT_BASE_URL = "http://localhost:8010"


class OcrClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 900.0):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def health(self) -> bool:
        """True when the service answers /health."""
        try:
            return (await self._client.get("/health")).is_success
        except httpx.HTTPError:
            return False

    async def ocr(self, path: Path, request: OcrRequest) -> OcrResponse:
        """Upload `path` and OCR the requested pages."""
        params = {"scanned_only": request.scanned_only, "figures": request.figures}
        if request.pages:
            params["pages"] = request.pages
        data = await asyncio.to_thread(path.read_bytes)
        response = await self._client.post("/ocr", params=params, files={"file": (path.name, data)})
        response.raise_for_status()
        return OcrResponse.model_validate(response.json())

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
