from pathlib import Path

from loguru import logger

from filetyper.api.deps import FileTyperDep, model_lifespan
from filetyper.schemas import FilteTyperStrategy
from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)
from cipher.utils.fastapi.settings import BaseServiceSettings

settings = BaseServiceSettings()
service_info = get_package_info("filetyper")

try:
    import uvicorn
    from fastapi import FastAPI, UploadFile
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
async def filetype(
    file: UploadFile,
    typer: FileTyperDep,
    strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT,
):
    """Infer the file type information from an uploaded file."""
    if strategy == FilteTyperStrategy.EXTENSION:
        # For extension-based inference, we can use the filename from UploadFile
        ext = Path(file.filename).suffix
        return typer.custom.match_extension(ext)
    return await typer.infer_async(file=file, strategy=strategy)


def main():
    """Run the API server."""
    uvicorn.run(
        "filetyper.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
