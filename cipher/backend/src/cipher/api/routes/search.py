"""Unified search API router — BM25/semantic/hybrid search across documents and emails together.

Both content types live in the same `text_chunks` Elasticsearch index, so
this is a single query with a real server-side `total`/`has_more` over the
combined result set -- unlike `/documents/search/*` and `/emails/search/*`,
which force `filetype_group` and only ever see one type's slice, so paging
either of them independently can't tell a caller when *all* matching content
(documents and emails together) has been exhausted.
"""

from clir.api.deps import TextEmbeddingModelDep
from fastapi import APIRouter, HTTPException
from sqlalchemy import text as sa_text

from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.api.deps.postgres import get_session
from cipher.api.services.search import search_chunks
from cipher.api.settings import RetrievalBackend, Settings, TextRanker
from cipher.schemas.content.search import (
    ChunkSemanticSearchRequest,
    ChunkTextSearchRequest,
    RetrievalConfigInfo,
)

router = APIRouter(
    prefix="/search",
    tags=["search"],
    responses={418: {"description": "I'm a teapot"}},
)

settings = Settings()

# Full-text-relevant extensions the retrieval layer knows how to use.
_FTS_EXTENSIONS = ("unaccent", "pg_trgm", "pg_bigm", "pgroonga", "pg_search")


def _effective_ranker(configured: TextRanker, installed: set[str]) -> str:
    """The ranker that will actually run -- downgrade if its extension is absent."""
    if settings.retrieval.backend != RetrievalBackend.POSTGRES:
        return "n/a"
    ladder = {
        TextRanker.PG_SEARCH: ("pg_search", TextRanker.PGROONGA),
        TextRanker.PGROONGA: ("pgroonga", TextRanker.BIGM),
        TextRanker.BIGM: ("pg_bigm", TextRanker.CORE),
        TextRanker.CORE: (None, None),
    }
    current = configured
    while current != TextRanker.CORE:
        needed, fallback = ladder[current]
        if needed in installed:
            return current.value
        current = fallback
    return TextRanker.CORE.value


@router.get(
    "/config",
    summary="Which store and keyword ranker back chunk search right now",
    response_model_by_alias=True,
)
async def search_config() -> RetrievalConfigInfo:
    """Report the active retrieval backend and full-text ranker.

    Returns the configured vs. effective keyword ranker and which full-text
    extensions are installed -- so the running configuration is never a guess.
    See docs/retrieval-workflow.md and docs/postgres-extensions.md.
    """
    r = settings.retrieval
    async with get_session() as session:
        rows = await session.execute(
            sa_text("SELECT extname FROM pg_extension WHERE extname = ANY(:names)"),
            {"names": list(_FTS_EXTENSIONS)},
        )
        installed = sorted(row[0] for row in rows)
    return RetrievalConfigInfo(
        backend=r.backend.value,
        text_ranker=r.text_ranker.value,
        text_ranker_effective=_effective_ranker(r.text_ranker, set(installed)),
        installed_extensions=installed,
        graph_expand_entity_cap=r.graph_expand_entity_cap,
    )


@router.post(
    "/text",
    summary="BM25 full-text search across documents and emails",
    response_model_by_alias=True,
)
async def search_text(params: ChunkTextSearchRequest, datastore: TextChunkDatastoreDep):
    """Search chunk text/title by keyword.

    BM25 only ever matches chunks containing a query term, so `has_more`
    naturally goes false once nothing left matches -- no similarity
    threshold needed the way semantic/hybrid search requires one.
    """
    return await datastore.search_text(request=params)


@router.post(
    "/semantic",
    summary="Semantic search using a natural language query string, across documents and emails",
    response_model_by_alias=True,
)
async def search_semantic(
    params: ChunkTextSearchRequest,
    datastore: TextChunkDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and perform kNN search -- no pre-computed embedding needed.

    Set `min_similarity` on the request to give pagination a real stopping
    point: kNN otherwise always returns its requested candidate count
    regardless of relevance, so without a threshold `has_more` would stay
    true well past the point where results still match the query.
    """
    if not params.query.strip():
        return await datastore.search_text(request=params)  # nothing to embed: browse
    embedding = await model.infer(text=params.query, task="retrieval")
    if embedding is None:
        raise HTTPException(status_code=503, detail="Embedding model unavailable")

    request = ChunkSemanticSearchRequest.model_validate(
        {**params.model_dump(exclude={"query"}, exclude_none=True), "embedding": embedding}
    )
    return await datastore.search_semantic(request=request)


@router.post(
    "/hybrid",
    summary="Hybrid search using a natural language query string, across documents and emails",
    response_model_by_alias=True,
)
async def search_hybrid(
    params: ChunkTextSearchRequest,
    datastore: TextChunkDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and run hybrid RRF search -- no pre-computed embedding needed."""
    if not params.query.strip():
        return await datastore.search_text(request=params)  # nothing to embed: browse
    try:
        return await search_chunks(params=params, datastore=datastore, embedding_model=model)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
