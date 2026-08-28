"""FastAPI wrapper for pyselectors -- a stateless, model-free service."""

from loguru import logger

from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)
from cipher.utils.fastapi.settings import BaseServiceSettings
from pyselectors.extract import extract_selectors
from pyselectors.schemas import SelectorExtractionRequest, SelectorSpan

settings = BaseServiceSettings()
service_info = get_package_info("pyselectors")

try:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware
except ImportError:
    logger.error("Failed to import uvicorn and/or fastapi. Install with `pip install uvicorn fastapi`")
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


@app.post("/extract")
async def extract(request: SelectorExtractionRequest) -> list[SelectorSpan]:
    """Extract and normalize selectors from a block of text."""
    return extract_selectors(
        request.text, language=request.language, region=request.region
    )


def main():
    """Run the API server."""
    uvicorn.run(
        "pyselectors.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
