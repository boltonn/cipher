from io import BytesIO
from typing import Annotated

from loguru import logger
from PIL import Image

from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)
from setfitcv.api.deps import ImageEmbeddingModelDep, model_lifespan
from setfitcv.schemas import ClipTextRequest, EmbeddingsClassifyRequest, ImageInference
from setfitcv.settings import Settings
from setfitcv.utils import ImageMetadataExtractor

settings = Settings()
service_info = get_package_info("setfitcv")

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Query, UploadFile
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware
except ImportError:
    logger.error("Failed to import uvicorn and/or fastapi. Please install them with `pip install uvicorn fastapi`")
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
async def infer_text(request: ClipTextRequest, model: ImageEmbeddingModelDep) -> list[float]:
    """Infer embedding for a single text query."""
    return await model.infer_text(text=request.text)


@app.post("/infer/image")
async def infer_image(
    img: UploadFile,
    model: ImageEmbeddingModelDep,
    classify: Annotated[bool | None, Query(description="Include tag head scores; defaults to IMAGE_CLASSIFY")] = None,
) -> ImageInference:
    """Infer the embedding for a single image, plus tag head scores when classification is on."""
    image_bytes = await img.read()
    use_heads = model.heads is not None if classify is None else classify
    if use_heads:
        if model.heads is None:
            raise HTTPException(
                status_code=400, detail="Classification is off (set IMAGE_CLASSIFY and IMAGE_HEADS_DIR)"
            )
        embedding, tag_scores = await model.infer_image_with_tags(image_bytes)
        return ImageInference(embedding=embedding, tag_scores=tag_scores, heads_version=model.heads.version)
    return ImageInference(embedding=await model.infer_image(image_bytes))


@app.post("/classify/embeddings")
async def classify_embeddings(
    request: EmbeddingsClassifyRequest, model: ImageEmbeddingModelDep
) -> list[dict[str, float]]:
    """Score already-computed (normalized) CLIP embeddings with the tag heads -- CPU only, no images."""
    if model.heads is None:
        raise HTTPException(status_code=400, detail="Classification is off (set IMAGE_CLASSIFY and IMAGE_HEADS_DIR)")
    return model.classify_embeddings(request.embeddings)


@app.get("/heads")
async def heads_info(model: ImageEmbeddingModelDep) -> dict:
    """The loaded tag heads: tags, version, embedding model and per-tag training metrics (empty when off)."""
    if model.heads is None:
        return {"enabled": False}
    heads = model.heads
    return {
        "enabled": True,
        "version": heads.version,
        "embeddingModel": heads.embedding_model,
        "metrics": heads.metrics,
    }


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
