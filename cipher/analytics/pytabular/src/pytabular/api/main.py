"""FastAPI wrapper for pytabular: upload a table, get its proposed `TableMapping`s back."""

import json
from pathlib import Path
from typing import Annotated

from loguru import logger
from pydantic import Field, TypeAdapter

from cipher.schemas._base.common import ModelDevice
from cipher.schemas.ingestion.table_mapping import TableMapping
from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)
from cipher.utils.fastapi.settings import BaseServiceSettings
from pytabular.build import ModelEndpoints, build_detectors
from pytabular.decide import ProfileConfig, profile_table
from pytabular.reader import spooled_copy


class Settings(BaseServiceSettings):
    gliner_url: str | None = Field(default=None, alias="PYTABULAR_GLINER_URL")
    nerd_url: str | None = Field(default=None, alias="PYTABULAR_NERD_URL")
    llm_model: str | None = Field(default=None, alias="PYTABULAR_LLM_MODEL")


settings = Settings()
service_info = get_package_info("pytabular")

try:
    import uvicorn
    from fastapi import FastAPI, File, Form, UploadFile
    from fastapi.concurrency import run_in_threadpool
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware
except ImportError:
    logger.error("Failed to import uvicorn and/or fastapi. Install with `pip install uvicorn fastapi`")
    exit(1)


app = FastAPI(title=service_info.title, version=service_info.version, description=service_info.description)
app.add_middleware(BaseHTTPMiddleware, dispatch=log_middleware)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, python_exception_handler)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


@app.get("/health")
async def health() -> ServiceHealthStatus:
    """Get the health status of the service."""
    return service_health.status


@app.get("/info")
async def info() -> ServiceInfo:
    """Get the service information."""
    return service_info


@app.post("/profile")
async def profile(
    file: Annotated[UploadFile, File(description="csv/tsv/xlsx/xls/ods/parquet/json/jsonl")],
    detectors: Annotated[
        str, Form(description="Comma list of: header, validators, gliner, nerd, llm")
    ] = "header,validators",
    region: Annotated[str | None, Form(description="ISO-3166 alpha-2 default region for phones")] = None,
    mapping: Annotated[str | None, Form(description="Edited mapping(s) JSON; user-set parts stay locked")] = None,
) -> list[TableMapping]:
    """Propose a mapping per sheet; with `mapping`, re-evaluate around the user's edits."""
    locked = None
    if mapping:
        raw = json.loads(mapping)
        locked = TypeAdapter(list[TableMapping]).validate_python(raw if isinstance(raw, list) else [raw])
    endpoints = ModelEndpoints(
        gliner_url=settings.gliner_url, nerd_url=settings.nerd_url, llm_model=settings.llm_model, device=ModelDevice.CPU
    )
    built = build_detectors([d.strip() for d in detectors.split(",") if d.strip()], endpoints=endpoints)
    path = await run_in_threadpool(spooled_copy, file.file, suffix=Path(file.filename or "upload.csv").suffix)
    try:
        return await run_in_threadpool(
            profile_table, path, detectors=built, locked=locked, config=ProfileConfig(region=region)
        )
    finally:
        path.unlink(missing_ok=True)


def main():
    """Run the API server."""
    uvicorn.run("pytabular.api.main:app", host=settings.host, port=settings.port, reload=settings.reload)


if __name__ == "__main__":
    main()
