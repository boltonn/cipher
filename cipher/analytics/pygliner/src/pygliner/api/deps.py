from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from loguru import logger

from cipher.schemas._base.common import ModelDevice
from pygliner.model import GlinerModel
from pygliner.settings import Settings

settings = Settings()


@asynccontextmanager
async def model_lifespan(app: FastAPI):
    """FastAPI lifespan context manager: load the GLiNER2.5 checkpoint once."""
    model = GlinerModel(model_dir=settings.resolved_model_dir, device=settings.model_device or ModelDevice.CPU)
    app.state.pygliner_model = model
    yield
    model.unload()
    del app.state.pygliner_model
    logger.info("🛑 App shutdown. Cleaning up pygliner model.")


def get_pygliner_model(request: Request) -> GlinerModel:
    """Dependency to get the model from app state.

    Stored under `app.state.pygliner_model` -- a name distinct from other
    analytics packages so multiple routers mounted on one app do not clobber
    each other.
    """
    return request.app.state.pygliner_model


PyglinerModelDep = Annotated[GlinerModel, Depends(get_pygliner_model)]
