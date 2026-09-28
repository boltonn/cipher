from contextlib import asynccontextmanager
from typing import Annotated

from loguru import logger

from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)
from pyocr.engine import build_engine
from pyocr.runner import ocr_source
from pyocr.schemas import OcrRequest, OcrResponse
from pyocr.settings import Settings

settings = Settings()
service_info = get_package_info("pyocr")

try:
    import uvicorn
    from fastapi import FastAPI, Query, Request, UploadFile
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware
except ImportError:
    logger.error("Failed to import uvicorn and/or fastapi. Please install them with `pip install uvicorn fastapi`")
    exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the OCR engine once for the app's lifetime."""
    app.state.ocr_engine = build_engine(settings.ocr)
    logger.info(f"✅ OCR engine ready ({settings.ocr.model}, {settings.ocr.backend})")
    yield
    app.state.ocr_engine.close()


app = FastAPI(
    title=service_info.title,
    version=service_info.version,
    description=service_info.description,
    lifespan=lifespan,
)
app.add_middleware(BaseHTTPMiddleware, dispatch=log_middleware)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, python_exception_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> ServiceHealthStatus:
    """Get the health status of the service."""
    return service_health.status


@app.get("/info")
async def info() -> ServiceInfo:
    """Get the service information."""
    return service_info


@app.post("/ocr")
async def ocr(
    request: Request,
    file: UploadFile,
    pages: Annotated[list[int] | None, Query(description="1-indexed pages; omit for all")] = None,
    scanned_only: Annotated[bool, Query()] = False,
    figures: Annotated[bool, Query()] = False,
) -> OcrResponse:
    """OCR a PDF or image (incl. HEIF); every requested page is decoded concurrently."""
    options = OcrRequest(pages=pages, scanned_only=scanned_only, figures=figures)
    return await ocr_source(
        engine=request.app.state.ocr_engine, source=await file.read(), request=options, max_side=settings.max_side
    )


def main():
    """Run the API server."""
    uvicorn.run("pyocr.api.main:app", host=settings.host, port=settings.port, reload=settings.reload)


if __name__ == "__main__":
    main()
