"""Chat transport: bridges the CIPHER agent to the frontend's Vercel AI SDK client.

All agent logic (tools, model providers, citation shaping) lives in
`cipher.api.agent`; this module only unpacks the request, builds the agent's
dependencies, and streams the run back.
"""

import json
import traceback
from collections.abc import AsyncIterator

from clir.api.deps import TextEmbeddingModelDep
from fastapi import APIRouter, Header, HTTPException
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.ui.vercel_ai import VercelAIAdapter, VercelAIEventStream
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, ErrorChunk
from starlette.requests import Request
from starlette.responses import Response

from cipher.api.agent import (
    AVAILABLE_MODELS,
    ChatDeps,
    build_agent,
    build_model,
    can_build,
    resolve_llm_settings,
)
from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.api.deps.postgres import (
    DatasetDatastoreDep,
    EntityDatastoreDep,
    EntityMatchDatastoreDep,
    ExtractedTextDatastoreDep,
    GraphDatastoreDep,
    MentionDatastoreDep,
    PersonDatastoreDep,
)
from cipher.api.settings import Settings
from cipher.schemas.interaction.llm import AgentConfig, LLMProvider, ModelOption

router = APIRouter(prefix="/chat", tags=["chat"])

settings = Settings()

# Appended after the short message in an error chunk's `errorText`, ahead of the full
# traceback -- the frontend splits on this to show the short message with the trace collapsed.
TRACE_MARKER = "---TRACEBACK---"

agent = build_agent()


@router.get("/config")
def chat_config() -> AgentConfig:
    """Which models the server already holds a key for, so the UI only prompts when it must.

    `has_key` is recomputed per model: the server's single `LLM__API_KEY` is
    valid for its configured provider only, so picking another provider falls
    back to that provider's own env var (and reports `False` when neither is set).
    """
    models = [
        m.model_copy(update={"has_key": can_build(resolve_llm_settings(settings.llm, m.id))})
        for m in AVAILABLE_MODELS
        if m.provider != LLMProvider.LOCAL
    ]
    # The local entry is whatever model the configured local server hosts.
    local_model = settings.llm.model if settings.llm.provider == LLMProvider.LOCAL else None
    models += [
        m.model_copy(update={"has_key": True})
        if local_model is None
        else ModelOption(
            id=f"local:{local_model}",
            provider=LLMProvider.LOCAL,
            label=f"{local_model.rsplit('/', 1)[-1]} (local)",
            has_key=True,
        )
        for m in AVAILABLE_MODELS
        if m.provider == LLMProvider.LOCAL
    ]
    return AgentConfig(
        has_server_key=can_build(settings.llm),
        models=models,
        default_model_id=f"{settings.llm.provider}:{settings.llm.model}",
    )


class _TracebackVercelAIEventStream(VercelAIEventStream):
    """Appends a full traceback to the error chunk instead of pydantic_ai's default `str(error)`."""

    async def on_error(self, error: Exception) -> AsyncIterator[BaseChunk]:
        yield ErrorChunk(error_text=f"{_short_error(error)}\n\n{TRACE_MARKER}\n{error}\n\n{traceback.format_exc()}")


def _short_error(error: Exception) -> str:
    """One readable line for the banner; the raw provider payload stays in the traceback."""
    if not isinstance(error, ModelHTTPError):
        return str(error)
    body = error.body if isinstance(error.body, dict) else {}
    detail = body.get("error", body) if isinstance(body.get("error", body), dict) else {}
    message = str(detail.get("message") or error.message or "").split("\n")[0].strip()
    if error.status_code == 429:
        return f"{error.model_name} is out of quota or rate limited -- pick another model or retry shortly. {message}"
    if error.status_code >= 500:
        return f"{error.model_name} is unavailable right now (HTTP {error.status_code}) -- retry or pick another model."
    return f"{error.model_name} returned HTTP {error.status_code}: {message}"


class _TracebackVercelAIAdapter(VercelAIAdapter[ChatDeps, str]):
    def build_event_stream(self) -> _TracebackVercelAIEventStream:
        return _TracebackVercelAIEventStream(self.run_input, accept=self.accept)


@router.post("/")
async def chat(
    request: Request,
    chunks: TextChunkDatastoreDep,
    embedding_model: TextEmbeddingModelDep,
    persons: PersonDatastoreDep,
    datasets: DatasetDatastoreDep,
    entities: EntityDatastoreDep,
    entity_matches: EntityMatchDatastoreDep,
    mentions: MentionDatastoreDep,
    graph: GraphDatastoreDep,
    extracted_text: ExtractedTextDatastoreDep,
    x_api_key: str | None = Header(default=None),
) -> Response:
    """Stream a chat response, letting the agent call its tools to ground and cite its answer.

    The request body is the raw Vercel AI SDK payload (`model`, `datasetId`,
    messages). The server uses its own configured key (`LLM__*`) by default;
    `x_api_key`, when sent, overrides it for this request only.
    """
    raw_body = await request.body()
    body = json.loads(raw_body)

    llm_settings = resolve_llm_settings(settings.llm, body.get("model"))
    if x_api_key and x_api_key.strip():
        llm_settings = llm_settings.model_copy(update={"api_key": x_api_key.strip()})
    if not can_build(llm_settings):
        raise HTTPException(
            status_code=401,
            detail=f"No API key configured for {llm_settings.provider}. Add one in the chat model settings.",
        )
    model = build_model(llm_settings)

    deps = ChatDeps(
        chunks=chunks,
        embedding_model=embedding_model,
        persons=persons,
        datasets=datasets,
        entities=entities,
        entity_matches=entity_matches,
        mentions=mentions,
        graph=graph,
        extracted_text=extracted_text,
        dataset_id=body.get("datasetId"),
    )

    run_input = VercelAIAdapter.build_run_input(raw_body)
    adapter = _TracebackVercelAIAdapter(agent=agent, run_input=run_input)
    event_stream = adapter.run_stream(model=model, deps=deps)
    return adapter.streaming_response(event_stream)
