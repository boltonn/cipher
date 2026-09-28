from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from loguru import logger

from pyprompt.runner import PromptRunner
from pyprompt.settings import Settings

settings = Settings()


@asynccontextmanager
async def runner_lifespan(app: FastAPI):
    """FastAPI lifespan: build the shared `PromptRunner` (a stateless HTTP client)."""
    app.state.pyprompt_runner = PromptRunner(settings)
    logger.info("✅ pyprompt ready.")
    yield
    del app.state.pyprompt_runner
    logger.info("🛑 App shutdown. Cleaning up pyprompt runner.")


def get_runner(request: Request) -> PromptRunner:
    """Dependency: the runner from app state (`app.state.pyprompt_runner`)."""
    return request.app.state.pyprompt_runner


PromptRunnerDep = Annotated[PromptRunner, Depends(get_runner)]
