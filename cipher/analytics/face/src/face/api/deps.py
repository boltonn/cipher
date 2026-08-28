from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from loguru import logger
from PIL import Image

from cipher.schemas.common import ModelDevice
from cipher.schemas.face import FaceAnnotation
from face.model import InsightFaceModel
from face.settings import Settings

settings = Settings()


class AsyncInsightFaceModel(InsightFaceModel):
    async def infer_async(self, img: Image.Image, min_conf: float = 0.3, min_size: int = 30) -> list[FaceAnnotation]:
        """Run face detection/embedding off the event loop (CPU/GPU bound)."""
        return await run_in_threadpool(self.infer, img, min_conf, min_size)


@asynccontextmanager
async def model_lifespan(app: FastAPI):
    """Fastapi lifespan context manager to load and cleanup the model."""
    model = AsyncInsightFaceModel(
        model_dir=settings.model_dir,
        device=settings.model_device or ModelDevice.CPU,
    )
    app.state.face_model = model
    logger.info("✅ InsightFace model loaded.")
    yield
    model.unload()
    del app.state.face_model
    logger.info("🛑 App shutdown. Cleaning up InsightFace model.")


# Dependency to access the model
def get_face_model(request: Request) -> AsyncInsightFaceModel:
    """Dependency to get the model from the app state.

    Stored under a name distinct from setfitcv's `app.state.image_model` --
    both routers can be mounted on the same app, and a shared generic
    `app.state.model` attribute would let whichever lifespan runs last
    silently overwrite the other's model reference.
    """
    return request.app.state.face_model


FaceModelDep = Annotated[AsyncInsightFaceModel, Depends(get_face_model)]
