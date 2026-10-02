from fastapi.concurrency import run_in_threadpool
from loguru import logger

from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)
from pygliner.api.deps import PyglinerModelDep, model_lifespan, settings
from pygliner.schemas import ClassifyRequest, EntitySpan, ExtractRequest, ExtractResponse, NerRequest

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
    return await run_in_threadpool(model.infer, request.text, request.labels, request.threshold)


@app.post("/extract")
async def extract(request: ExtractRequest, model: PyglinerModelDep) -> ExtractResponse:
    """Jointly extract entity spans and the ontology-typed relations between them."""
    entities, relations = await run_in_threadpool(
        model.extract, request.text, request.labels, request.relation_labels, request.threshold
    )
    return ExtractResponse(entities=entities, relations=relations)


@app.post("/classify")
async def classify(request: ClassifyRequest, model: PyglinerModelDep) -> list[dict[str, float]]:
    """Score each text against every described label; one `{label: score}` per text."""
    return await run_in_threadpool(model.classify, request.texts, request.labels)


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
