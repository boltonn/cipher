from contextlib import asynccontextmanager
from typing import Annotated

import numpy as np
import torch
from fastapi import Depends, FastAPI, Request
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from clir.models.pytorch import TextEmbeddingPytorchModel
from clir.settings import Settings
from clir.utils.chunk import get_chunker
from clir.utils.embedding import normalize, pool_np
from cipher.utils.fastapi.batch import batch

settings = Settings()


class AsyncTextEmbeddingModel:
    def __init__(self, model_dir: str, device: str):
        self._model = TextEmbeddingPytorchModel(model_dir=model_dir, device=device)
        # self._collator = DataCollatorWithPadding(
        #     tokenizer=self._model.tokenizer,
        #     max_length=self._model.default_max_seq_length,
        # )

    async def infer(
        self,
        text: str,
        chunk_size: int = None,
        chunk_overlap: int = 0,
        max_chunks: int = 10,
        normalized: bool = True,
        average: bool = True,
        prompt: str | None = None,
        task: str | None = None,
    ) -> list[float]:
        """Batch inference for text embedding model."""

        @batch(
            max_batch_size=settings.max_batch_size,
            batch_wait_timeout_s=settings.batch_timeout,
        )
        async def handle_batch(batch: dict[str, torch.Tensor]) -> np.ndarray:
            """WIP: Handle a batch of preprocessed model inputs and return embeddings."""
            # collated_batch = self._collator(batch)
            return self._model.infer(inputs=batch)

        chunker: RecursiveCharacterTextSplitter = get_chunker(
            tokenizer=self._model.tokenizer,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        chunks = chunker.split_text(text=text)[:max_chunks]
        logger.debug(f"Split text into {len(chunks)} chunks")
        model_inputs = self._model.preprocess(chunks, prompt=prompt)
        embeddings = self._model.infer(model_inputs, task=task)
        # embeddings = [await handle_batch(c) for c in model_inputs]

        if normalized:
            embeddings = np.array([normalize(e) for e in embeddings])

        if average:
            embeddings = pool_np(embeddings)

        return embeddings.tolist()


@asynccontextmanager
async def model_lifespan(app: FastAPI):
    """Load the model on startup and store it in the app state."""
    model = AsyncTextEmbeddingModel(
        model_dir=settings.model_dir, device=settings.model_device
    )
    app.state.text_embedding_model = model
    logger.info("✅ Transformer model loaded.")
    yield
    # Cleanup if needed
    logger.info("🛑 App shutdown. Cleaning up model.")


def get_text_embedding_model(request: Request) -> AsyncTextEmbeddingModel:
    """Get the model from the app state.

    Stored under a name distinct from other packages' model dependencies
    (e.g. setfitcv's `app.state.image_model`, face's `app.state.face_model`)
    -- multiple routers can be mounted on the same app, and a shared generic
    `app.state.model` attribute would let whichever lifespan runs last
    silently overwrite the others' model references.
    """
    return request.app.state.text_embedding_model


TextEmbeddingModelDep = Annotated[
    AsyncTextEmbeddingModel, Depends(get_text_embedding_model)
]
