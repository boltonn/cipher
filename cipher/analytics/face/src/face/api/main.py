from io import BytesIO

from loguru import logger
from PIL import Image, ImageOps

from cipher.schemas.identity.face import FaceAnnotation
from cipher.utils.fastapi.health import ServiceHealthStatus, service_health
from cipher.utils.fastapi.info import ServiceInfo, get_package_info
from cipher.utils.fastapi.middleware import (
    log_middleware,
    python_exception_handler,
    validation_exception_handler,
)
from face.api.deps import FaceModelDep, model_lifespan, settings

service_info = get_package_info("face")

try:
    import uvicorn
    from fastapi import FastAPI, UploadFile
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


@app.post("/infer")
async def infer(
    img: UploadFile,
    model: FaceModelDep,
    min_conf: float = 0.3,
    min_size: int = 30,
) -> list[FaceAnnotation]:
    """Detect and embed faces in a single image."""
    img = await img.read()
    img = Image.open(BytesIO(img)).convert("RGB")
    img = ImageOps.exif_transpose(img)
    return await model.infer_async(img=img, min_conf=min_conf, min_size=min_size)


def main():
    """Run the API server."""
    uvicorn.run(
        "face.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
