from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from loguru import logger

from cipher.schemas._base.common import ModelDevice
from nerd.model import NerdModel
from nerd.schemas import EntitySpan
from nerd.settings import Settings

settings = Settings()


class AsyncNerdModel(NerdModel):
    async def infer_async(self, text: str, threshold: float = 0.5) -> list[EntitySpan]:
        """Run the token-classification pipeline off the event loop (CPU/GPU bound)."""
        return await run_in_threadpool(self.infer, text, threshold)

    async def infer_batch_async(self, texts: list[str], threshold: float = 0.5) -> list[list[EntitySpan]]:
        """Packed multi-text inference off the event loop."""
        return await run_in_threadpool(self.infer_batch, texts, threshold)


@asynccontextmanager
async def model_lifespan(app: FastAPI):
    """FastAPI lifespan context manager to load and clean up the model."""
    model = AsyncNerdModel(
        model_dir=settings.resolved_model_dir,
        device=settings.model_device or ModelDevice.CPU,
        aggregation_strategy=settings.aggregation_strategy,
        dtype=settings.model_dtype,
        max_batch_tokens=settings.max_batch_tokens,
    )
    app.state.nerd_model = model
    logger.info("✅ nerd model ready.")
    yield
    model.unload()
    del app.state.nerd_model
    logger.info("🛑 App shutdown. Cleaning up nerd model.")


def get_nerd_model(request: Request) -> AsyncNerdModel:
    """Dependency to get the model from app state.

    Stored under `app.state.nerd_model` -- a name distinct from other analytics
    packages so multiple routers mounted on one app do not clobber each other.
    """
    return request.app.state.nerd_model


NerdModelDep = Annotated[AsyncNerdModel, Depends(get_nerd_model)]
