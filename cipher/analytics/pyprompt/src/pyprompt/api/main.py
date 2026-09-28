from loguru import logger

from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)
from pyprompt.api.deps import PromptRunnerDep, runner_lifespan, settings
from pyprompt.errors import PromptError
from pyprompt.schemas import (
    CombinedExtraction,
    EntityExtraction,
    EntityRequest,
    EventExtraction,
    EventRequest,
    ExtractRequest,
    RunRequest,
)

service_info = get_package_info("pyprompt")

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
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
    lifespan=runner_lifespan,
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


@app.post("/entities")
async def entities(request: EntityRequest, runner: PromptRunnerDep) -> EntityExtraction:
    """Extract entity spans + directed relations from `text` (offsets resolved server-side)."""
    try:
        return await runner.extract_entities(
            request.text,
            labels=request.labels,
            relation_labels=request.relation_labels,
            prompt=request.prompt,
            model=request.model,
        )
    except PromptError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/events")
async def events(request: EventRequest, runner: PromptRunnerDep) -> EventExtraction:
    """Extract calendar events (with participants and places) from free text."""
    try:
        return await runner.extract_events(
            request.text,
            reference_date=request.reference_date,
            prompt=request.prompt,
            model=request.model,
        )
    except PromptError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/extract")
async def extract(request: ExtractRequest, runner: PromptRunnerDep) -> CombinedExtraction:
    """Extract entity spans + relations and/or dated events from `text` in one call."""
    try:
        return await runner.extract_all(
            request.text,
            tasks=request.tasks,
            labels=request.labels,
            relation_labels=request.relation_labels,
            reference_date=request.reference_date,
            model=request.model,
        )
    except PromptError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/run")
async def run(request: RunRequest, runner: PromptRunnerDep) -> dict:
    """Run a fully custom prompt. With `json_schema`, returns the parsed object; else `{'text': ...}`."""
    try:
        return await runner.run(
            prompt=request.prompt,
            text=request.text,
            system=request.system,
            json_schema=request.json_schema,
            model=request.model,
        )
    except PromptError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def main():
    """Run the API server."""
    uvicorn.run(
        "pyprompt.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
