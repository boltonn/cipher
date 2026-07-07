from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from clir.api.deps import model_lifespan
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi_offline import FastAPIOffline
from starlette.middleware.base import BaseHTTPMiddleware

from cipher.api.deps.elasticsearch import elasticsearch_lifespan
from cipher.api.deps.postgres import postgres_lifespan
from cipher.api.routes import chat, comments, datasets, documents, emails, faces, files, images, persons, search, users
from cipher.api.settings import Settings
from cipher.schemas.exceptions import EntityAlreadyExistsError, EntityNotFoundError
from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    entity_exists_handler,
    entity_not_found_handler,
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)

settings = Settings()
service_info = get_package_info(name="cipher-backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Combined startup: Postgres, then Elasticsearch, then the shared text-embedding model.

    documents.router and emails.router both need the same embedding model
    for query-time semantic/hybrid search -- loading it once here (rather
    than per-router) means two routers sharing one model, not two copies of
    it loaded into memory.
    """
    async with postgres_lifespan(app), elasticsearch_lifespan(app), model_lifespan(app):
        yield


app = FastAPIOffline(
    title="Cipher Backend API",
    version=service_info.version,
    description=service_info.description,
    root_path="/api",
    lifespan=lifespan,
)
app.add_middleware(BaseHTTPMiddleware, dispatch=log_middleware)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(EntityAlreadyExistsError, entity_exists_handler)
app.add_exception_handler(EntityNotFoundError, entity_not_found_handler)
app.add_exception_handler(Exception, python_exception_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(emails.router)
app.include_router(datasets.router)
# app.include_router(enrichments.router)
app.include_router(files.router)
app.include_router(images.router)
app.include_router(search.router)
# app.include_router(messages.router)
app.include_router(users.router)
app.include_router(faces.router)
app.include_router(persons.router)
app.include_router(comments.router)
static_path = Path(__file__).parent / "assets"
app.mount(f"/{static_path.name}", StaticFiles(directory=static_path), name="static")


@app.get("/logo.png", include_in_schema=False)
async def favicon():
    """Serve the logo image."""
    return FileResponse(str(static_path / "logo.png"))


@app.get("/health")
async def health() -> ServiceHealthStatus:
    """Health check endpoint."""
    return service_health.status


@app.get("/info")
async def info() -> ServiceInfo:
    """Service information endpoint."""
    return service_info


@app.get("/hello-world")
async def hello_world() -> str:
    """Simple hello world endpoint."""
    return "Hello, World!"


def main():
    """Run the Uvicorn server."""
    kwargs = {"log_config": None} if settings.log.to_json else {}
    uvicorn.run(
        "cipher.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        proxy_headers=True,  # ✅ NOTE: This is required for X-Forwarded-* headers or else frontend will throw http error
        forwarded_allow_ips="*",  # ✅ Trust all proxies (or restrict to ingress IP)
        **kwargs,
    )


if __name__ == "__main__":
    main()
