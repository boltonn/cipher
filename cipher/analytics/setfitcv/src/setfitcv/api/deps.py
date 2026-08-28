from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Annotated

import torch
from fastapi import Depends, FastAPI, Request
from loguru import logger
from PIL import Image, ImageOps

from cipher.utils.fastapi.batch import batch
from setfitcv.model import CLIP
from setfitcv.settings import Settings

settings = Settings()


class AsyncImageEmbeddingModel:
    def __init__(self, model_dir: Path | str, device: str | None = None):
        self._model = CLIP(model_dir=Path(model_dir), device=device)

    def unload(self) -> None:
        """Release the underlying CLIP model."""
        self._model.decommission()

    @batch(
        max_batch_size=settings.max_batch_size,
        batch_wait_timeout_s=settings.batch_timeout,
    )
    async def _handle_image_batch(self, tensor_list: list[torch.Tensor]):
        # Concatenate individual [1, 3, 224, 224] tensors into one [N, 3, 224, 224]
        batched_tensors = torch.cat(tensor_list, dim=0)
        return self._model.embed_imgs_batch(batched_tensors)

    @batch(
        max_batch_size=settings.max_batch_size,
        batch_wait_timeout_s=settings.batch_timeout,
    )
    async def _handle_text_batch(self, tensor_list: list[torch.Tensor]):
        batched_tensors = torch.cat(tensor_list, dim=0)
        return self._model.embed_txt_batch(batched_tensors)

    async def infer_image(self, image_bytes: bytes) -> list[float]:
        """Infer the image embedding for a single image byte input."""
        # 1. CPU-bound Preprocessing (Immediate)
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        img = ImageOps.exif_transpose(img)
        # Returns tensor of shape [1, 3, 224, 224]
        processed_tensor = self._model.preprocess_imgs([img])

        # 2. Queue for GPU Batching
        embedding = await self._handle_image_batch(processed_tensor)
        return embedding

    async def infer_text(self, text: str) -> list[float]:
        """Infer the text embedding for a single text input."""
        # 1. CPU-bound Tokenization
        processed_tensor = self._model.preprocess_txt([text])["input_ids"]

        # 2. Queue for GPU Batching
        embedding = await self._handle_text_batch(processed_tensor)
        return embedding


# Lifespan context manager
@asynccontextmanager
async def model_lifespan(app: FastAPI):
    """Fastapi lifespan context manager to load and cleanup the model."""
    model = AsyncImageEmbeddingModel(model_dir=settings.model_dir, device=settings.device)
    app.state.image_model = model
    logger.info("✅ Image embedding model loaded.")
    yield
    model.unload()
    del app.state.image_model
    logger.info("🛑 App shutdown. Cleaning up model.")


# Dependency to access the model
def get_image_embedding_model(request: Request) -> AsyncImageEmbeddingModel:
    """Dependency to get the model from the app state.

    Stored under a name distinct from face's `app.state.face_model` --
    both routers can be mounted on the same app, and a shared generic
    `app.state.model` attribute would let whichever lifespan runs last
    silently overwrite the other's model reference.
    """
    return request.app.state.image_model


ImageEmbeddingModelDep = Annotated[AsyncImageEmbeddingModel, Depends(get_image_embedding_model)]
