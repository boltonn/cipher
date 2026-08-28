from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from loguru import logger

from cipher.schemas.common import ModelDevice
from pygliner.model import GlinerModel, GlirelModel
from pygliner.schemas import EntitySpan, RelationSpan
from pygliner.settings import Settings

settings = Settings()


@dataclass
class PyglinerModels:
    """The loaded GLiNER model, plus GLiREL loaded lazily on first relation call."""

    entities: GlinerModel
    _relation_dir: str
    _device: ModelDevice
    relations: GlirelModel | None = None

    async def infer_entities(
        self, text: str, labels: list[str] | None = None, threshold: float = 0.5
    ) -> list[EntitySpan]:
        """Run GLiNER off the event loop."""
        return await run_in_threadpool(self.entities.infer, text, labels, threshold)

    async def infer_relations(
        self,
        text: str,
        entities: list[EntitySpan],
        labels: list[str] | None = None,
        threshold: float = 0.5,
    ) -> list[RelationSpan]:
        """Run GLiREL off the event loop, loading it on first use."""
        if self.relations is None:
            self.relations = await run_in_threadpool(
                GlirelModel, self._relation_dir, self._device
            )
        return await run_in_threadpool(
            self.relations.infer, text, entities, labels, threshold
        )

    def unload(self) -> None:
        """Release both models."""
        self.entities.unload()
        if self.relations is not None:
            self.relations.unload()


@asynccontextmanager
async def model_lifespan(app: FastAPI):
    """FastAPI lifespan context manager: load GLiNER now, defer GLiREL."""
    device = settings.model_device or ModelDevice.CPU
    models = PyglinerModels(
        entities=GlinerModel(model_dir=settings.resolved_model_dir, device=device),
        _relation_dir=settings.resolved_relation_model_dir,
        _device=device,
    )
    app.state.pygliner_model = models
    logger.info("✅ pygliner ready (GLiNER loaded; GLiREL lazy).")
    yield
    models.unload()
    del app.state.pygliner_model
    logger.info("🛑 App shutdown. Cleaning up pygliner models.")


def get_pygliner_model(request: Request) -> PyglinerModels:
    """Dependency to get the models from app state.

    Stored under `app.state.pygliner_model` -- a name distinct from other
    analytics packages so multiple routers mounted on one app do not clobber
    each other.
    """
    return request.app.state.pygliner_model


PyglinerModelDep = Annotated[PyglinerModels, Depends(get_pygliner_model)]
