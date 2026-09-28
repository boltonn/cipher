from typing import Annotated

from loguru import logger

from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)
from cipher.utils.fastapi.settings import BaseServiceSettings
from pyxberg.schemas import ExtractedTableResponse, ExtractRequest, ExtractResponse

settings = BaseServiceSettings()
service_info = get_package_info("pyxberg")

try:
    import uvicorn
    from fastapi import Depends, FastAPI, UploadFile
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware
except ImportError:
    logger.error(
        "Failed to import uvicorn and/or fastapi. Please install them with `pip install uvicorn fastapi`"
    )
    exit(1)


app = FastAPI(
    title=service_info.title,
    version=service_info.version,
    description=service_info.description,
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


@app.post("/extract", response_model_exclude_none=True)
async def extract(
    file: UploadFile, options: Annotated[ExtractRequest, Depends()]
) -> ExtractResponse:
    """Extract text, tables, and structure from an uploaded document."""
    from kreuzberg import ExtractionConfig, OcrConfig, extract_bytes

    data = await file.read()
    config = ExtractionConfig(
        disable_ocr=options.disable_ocr,
        ocr=OcrConfig(language=options.ocr_language),
    )
    result = await extract_bytes(
        data, mime_type=file.content_type or "application/octet-stream", config=config
    )
    return ExtractResponse(
        content=result.content,
        tables=[
            ExtractedTableResponse(
                cells=t.cells, markdown=t.markdown, page_number=t.page_number
            )
            for t in (result.tables or [])
        ],
        detected_language=result.get_detected_language(),
        page_count=result.get_page_count(),
    )


def main():
    """Run the API server."""
    uvicorn.run(
        "pyxberg.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
