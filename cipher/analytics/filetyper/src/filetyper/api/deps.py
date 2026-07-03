import io
import tempfile
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from loguru import logger

from filetyper.models.main import FileTyper
from filetyper.schemas import FileTypeInfo, FilteTyperStrategy


class AsyncFileTyper(FileTyper):
    async def infer_async(
        self,
        file: UploadFile,
        strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT,
    ) -> FileTypeInfo:
        """Infer the file type information from an uploaded file."""
        file = file.file  # Get the file-like object from UploadFile
        file_buffer = file
        if isinstance(file, tempfile.SpooledTemporaryFile):
            file_buffer = io.BytesIO(file.read())
            file.seek(0)
        # UploadFile.file is a file-like object. Magika can seek() within it.
        # We run this in a threadpool because Magika's sync call is CPU-bound.
        info = await run_in_threadpool(self.infer_stream, file_buffer, strategy)
        # Reset stream position so other parts of your app can still read the file
        file.seek(0)
        return info


# Lifespan context manager
@asynccontextmanager
async def model_lifespan(app: FastAPI):
    """Fastapi lifespan context manager to load and cleanup the model."""
    model = AsyncFileTyper()
    app.state.model = model
    logger.info("✅ Magika loaded.")
    yield
    # Cleanup if needed
    logger.info("🛑 App shutdown. Cleaning up Magika.")


# Dependency to access the model
def get_filetyper_model(request: Request) -> AsyncFileTyper:
    """Dependency to get the model from the app state."""
    return request.app.state.model


FileTyperDep = Annotated[AsyncFileTyper, Depends(get_filetyper_model)]
