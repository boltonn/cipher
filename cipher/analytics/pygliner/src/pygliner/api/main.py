from loguru import logger

from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)
from pygliner.api.deps import PyglinerModelDep, model_lifespan, settings
from pygliner.schemas import EntitySpan, NerRequest, RelationRequest, RelationSpan

service_info = get_package_info("pygliner")

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
    lifespan=model_lifespan,
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


@app.post("/infer")
async def infer(request: NerRequest, model: PyglinerModelDep) -> list[EntitySpan]:
    """Extract entity spans for the requested zero-shot labels."""
    return await model.infer_entities(
        text=request.text, labels=request.labels, threshold=request.threshold
    )


@app.post("/relations")
async def relations(request: RelationRequest, model: PyglinerModelDep) -> list[RelationSpan]:
    """Extract directed relations between the supplied entity spans (needs the `relations` extra)."""
    return await model.infer_relations(
        text=request.text,
        entities=request.entities,
        labels=request.labels,
        threshold=request.threshold,
    )


def main():
    """Run the API server."""
    uvicorn.run(
        "pygliner.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
