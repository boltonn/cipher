import json
import traceback
from collections.abc import AsyncIterator
from dataclasses import dataclass

from clir.api.deps import AsyncTextEmbeddingModel, TextEmbeddingModelDep
from fastapi import APIRouter, Header, HTTPException
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.ui.vercel_ai import VercelAIAdapter, VercelAIEventStream
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, ErrorChunk
from starlette.requests import Request
from starlette.responses import Response

from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.api.services.search import search_chunks
from cipher.datastores.elasticsearch.repositories.text_chunk import (
    ElasticsearchTextChunkRepository,
    ScoredTextChunk,
)
from cipher.schemas.chat import ChatCitation
from cipher.schemas.document import ScoredDocumentTextChunk
from cipher.schemas.search import ChunkFilters, ChunkTextSearchRequest

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)

# Appended after the short message in an error chunk's `errorText`, ahead of the full
# traceback -- the frontend splits on this to show the short message with the trace collapsed.
TRACE_MARKER = "---TRACEBACK---"


@dataclass
class ChatDeps:
    datastore: ElasticsearchTextChunkRepository
    embedding_model: AsyncTextEmbeddingModel
    dataset_id: str | None = None


agent = Agent(
    # "openai-chat:" (not the bare "openai:" prefix) keeps this on the Chat Completions API --
    # pydantic-ai 2.x routes a bare "openai:" model to the Responses API instead.
    "openai-chat:gpt-4o-mini",
    deps_type=ChatDeps,
    instructions=(
        "You are a helpful assistant for exploring a triaged set of documents and emails. "
        "When the user asks anything about their data, call search_documents to find relevant "
        "passages before answering, and ground your answer in what it returns. If nothing "
        "relevant is found, say so instead of guessing."
    ),
    defer_model_check=True,
)


def _to_citation(chunk: ScoredTextChunk) -> dict:
    is_document = isinstance(chunk, ScoredDocumentTextChunk)
    citation = ChatCitation(
        chunk_id=chunk.id,
        file_id=chunk.file_id,
        display_name=chunk.filename if is_document else (chunk.title or "(no subject)"),
        filetype_group="document" if is_document else "email",
        page_number=chunk.page_number if is_document else None,
        heading_path=chunk.heading_path if is_document else None,
        start_offset=chunk.start_offset,
        end_offset=chunk.end_offset,
        snippet=chunk.highlights[0] if chunk.highlights else chunk.text[:280],
        score=chunk.score,
    )
    # Serialize to camelCase explicitly -- pydantic_ai's tool-result JSON dump
    # ignores field aliases, so this is what keeps the wire shape matching the
    # frontend's `ChatCitation` type.
    return citation.model_dump(by_alias=True)


@agent.tool
async def search_documents(ctx: RunContext[ChatDeps], query: str, limit: int = 5) -> list[dict]:
    """Search the user's documents and emails for passages relevant to `query`, to cite in your answer."""
    params = ChunkTextSearchRequest(
        query=query, limit=limit, filters=ChunkFilters(dataset_id=ctx.deps.dataset_id)
    )
    try:
        results = await search_chunks(
            params=params, datastore=ctx.deps.datastore, embedding_model=ctx.deps.embedding_model
        )
    except RuntimeError as exc:
        # Distinguishes an infra failure (embedding model down) from a real empty result --
        # raising ModelRetry tells the agent the tool call itself failed so it can retry or
        # say so, instead of silently returning [] and confidently reporting "nothing found".
        raise ModelRetry(str(exc)) from exc
    return [_to_citation(chunk) for chunk in results.data]


LOCAL_LLM_BASE_URL = "http://localhost:8002/v1"


def get_model(provider: str, model_name: str, api_key: str):
    """Build a pydantic_ai model for the given provider, using the caller's own API key.

    Args:
        provider: One of "openai", "anthropic", "google", "local".
        model_name: Provider-specific model id.
        api_key: The caller's own API key for that provider. Ignored for "local".

    Returns:
        A pydantic_ai model instance ready to pass to `agent.run_stream`.
    """
    if provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(model_name, provider=OpenAIProvider(api_key=api_key))
    elif provider == "local":
        # Temporary: routes to the vLLM OpenAI-compatible server in ~/llm, run locally
        # via `make start` there. No real key is needed -- vLLM doesn't check it.
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            model_name, provider=OpenAIProvider(base_url=LOCAL_LLM_BASE_URL, api_key="local")
        )
    elif provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(model_name, provider=AnthropicProvider(api_key=api_key))
    elif provider == "google":
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleModel(model_name, provider=GoogleProvider(api_key=api_key))
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


class _TracebackVercelAIEventStream(VercelAIEventStream):
    """Appends a full traceback to the error chunk instead of pydantic_ai's default `str(error)`.

    Mirrors the ---TRACEBACK--- pattern from shadowbot's agent route so the frontend can show
    the short message inline and the trace collapsed, rather than swallowing it entirely.
    """

    async def on_error(self, error: Exception) -> AsyncIterator[BaseChunk]:
        yield ErrorChunk(error_text=f"{error}\n\n{TRACE_MARKER}\n{traceback.format_exc()}")


class _TracebackVercelAIAdapter(VercelAIAdapter):
    def build_event_stream(self) -> _TracebackVercelAIEventStream:
        return _TracebackVercelAIEventStream(self.run_input, accept=self.accept)


@router.post("/")
async def chat(
    request: Request,
    datastore: TextChunkDatastoreDep,
    embedding_model: TextEmbeddingModelDep,
    x_api_key: str = Header(...),
) -> Response:
    """Stream a chat response, letting the agent call `search_documents` to ground and cite its answer.

    Args:
        request: Raw Vercel AI SDK request body.
        datastore: Unified document/email chunk index, injected for the `search_documents` tool.
        embedding_model: Text embedding model, injected for the `search_documents` tool.
        x_api_key: The caller's own API key for the requested model's provider.

    Returns:
        A streaming Vercel AI SDK response.
    """
    if not x_api_key.strip():
        raise HTTPException(status_code=401, detail="API key is required")

    raw_body = await request.body()
    body = json.loads(raw_body)

    model_id = body.get("model", "openai:gpt-4o-mini")
    provider, model_name = model_id.split(":", 1)
    model = get_model(provider, model_name, x_api_key)
    dataset_id = body.get("datasetId")

    run_input = VercelAIAdapter.build_run_input(raw_body)
    adapter = _TracebackVercelAIAdapter(
        agent=agent,
        run_input=run_input,
    )
    event_stream = adapter.run_stream(
        model=model,
        deps=ChatDeps(datastore=datastore, embedding_model=embedding_model, dataset_id=dataset_id),
    )

    return adapter.streaming_response(event_stream)
