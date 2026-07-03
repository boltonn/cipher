from io import BytesIO
from typing import Annotated

import numpy as np
from loguru import logger
from PIL import Image, ImageOps

from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)
from setfitcv.api.deps import ImageEmbeddingModelDep, model_lifespan
from setfitcv.schemas import ClipTextRequest
from setfitcv.settings import Settings
from setfitcv.utils import ImageMetadataExtractor

settings = Settings()
service_info = get_package_info("setfitcv")

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


@app.post("/infer/text")
async def infer_text(
    request: ClipTextRequest,
    model: Annotated[ImageEmbeddingModelDep, Depends()],
):
    """Infer embedding for a single text query."""
    embedding = model.embed_txt(text=request.text, normalized=request.normalized)
    embedding = np.squeeze(embedding)
    return embedding.tolist()


@app.post("/infer/image")
async def infer_image(
    img: UploadFile,
    model: Annotated[ImageEmbeddingModelDep, Depends()],
):
    """Infer embedding for a single image."""
    img = await img.read()
    img = Image.open(BytesIO(img)).convert("RGB")
    img = ImageOps.exif_transpose(img)
    embedding = await model.infer(image=img, normalized=True)
    embedding = np.squeeze(embedding)
    return embedding.tolist()


@app.post("/exif")
async def extract_exif(
    img: UploadFile,
):
    """Extract EXIF metadata from a single image."""
    img = await img.read()
    img = Image.open(BytesIO(img)).convert("RGB")
    metadata = ImageMetadataExtractor.extract_metadata(img)
    return metadata


def main():
    """Run the API server."""
    uvicorn.run(
        "setfitcv.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
