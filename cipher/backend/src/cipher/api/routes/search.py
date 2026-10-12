"""Unified search API router — BM25/semantic/hybrid search across documents and emails together.

Both content types live in the same `text_chunks` Elasticsearch index, so
this is a single query with a real server-side `total`/`has_more` over the
combined result set -- unlike `/documents/search/*` and `/emails/search/*`,
which force `filetype_group` and only ever see one type's slice, so paging
either of them independently can't tell a caller when *all* matching content
(documents and emails together) has been exhausted.
"""

import time
from typing import Annotated

from clir.api.deps import TextEmbeddingModelDep
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from setfitcv.api.deps import ImageEmbeddingModelDep
from sqlalchemy import text as sa_text

from cipher.api.deps.access import DatasetAccessDep
from cipher.api.deps.elasticsearch import TextChunkDatastoreDep
from cipher.api.deps.postgres import (
    EntityDatastoreDep,
    FileDatastoreDep,
    ImageDatastoreDep,
    MentionDatastoreDep,
    SearchRecordDatastoreDep,
    end_transactions,
    get_session,
)
from cipher.api.services.global_search import run_overview, run_text_search
from cipher.api.services.search import search_chunks
from cipher.api.services.search_assist import PASSAGES, assist
from cipher.api.settings import RetrievalBackend, Settings
from cipher.datastores.postgres.repositories.chunk_retrieval import effective_text_ranker
from cipher.schemas.content.search import (
    ChunkSemanticSearchRequest,
    ChunkTextSearchRequest,
    RetrievalConfigInfo,
    SourceFacets,
)
from cipher.schemas.interaction.global_search import OverviewResponse, SearchAssist
from cipher.schemas.interaction.search_record import (
    PaginatedSearchHistory,
    SaveSearchRequest,
    SearchRecord,
    SearchRequest,
)

router = APIRouter(
    prefix="/search",
    tags=["search"],
    responses={418: {"description": "I'm a teapot"}},
)

settings = Settings()

# Full-text-relevant extensions the retrieval layer knows how to use.
_FTS_EXTENSIONS = ("unaccent", "pg_trgm", "pg_bigm", "pgroonga", "pg_search")


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
        text_ranker_effective=(
            effective_text_ranker(r.text_ranker.value, installed=set(installed))
            if r.backend == RetrievalBackend.POSTGRES
            else "n/a"
        ),
        installed_extensions=installed,
        graph_expand_entity_cap=r.graph_expand_entity_cap,
    )


@router.get(
    "/source-facets",
    summary="Tags and message states that came with the data, with file counts",
    response_model=SourceFacets,
    response_model_by_alias=True,
)
async def source_facets(
    access: DatasetAccessDep,
    datastore: FileDatastoreDep,
    dataset_ids: Annotated[list[str] | None, Query(alias="datasetIds")] = None,
) -> SourceFacets:
    """Values for the "from the data" search filters (e.g. Gmail's `promotions`, `spam`), over searchable files."""
    return await datastore.source_facets(dataset_ids=access.scope(dataset_ids))


@router.post(
    "/text",
    summary="BM25 full-text search across documents and emails",
    response_model_by_alias=True,
)
async def search_text(params: ChunkTextSearchRequest, access: DatasetAccessDep, datastore: TextChunkDatastoreDep):
    """Search chunk text/title by keyword.

    BM25 only ever matches chunks containing a query term, so `has_more`
    naturally goes false once nothing left matches -- no similarity
    threshold needed the way semantic/hybrid search requires one.
    """
    params.filters = access.scoped(params.filters)
    return await datastore.search_text(request=params)


@router.post(
    "/semantic",
    summary="Semantic search using a natural language query string, across documents and emails",
    response_model_by_alias=True,
)
async def search_semantic(
    params: ChunkTextSearchRequest,
    access: DatasetAccessDep,
    datastore: TextChunkDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and perform kNN search -- no pre-computed embedding needed.

    Set `min_similarity` on the request to give pagination a real stopping
    point: kNN otherwise always returns its requested candidate count
    regardless of relevance, so without a threshold `has_more` would stay
    true well past the point where results still match the query.
    """
    params.filters = access.scoped(params.filters)
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
    access: DatasetAccessDep,
    datastore: TextChunkDatastoreDep,
    model: TextEmbeddingModelDep,
):
    """Embed a query string and run hybrid RRF search -- no pre-computed embedding needed."""
    params.filters = access.scoped(params.filters)
    if not params.query.strip():
        return await datastore.search_text(request=params)  # nothing to embed: browse
    try:
        return await search_chunks(params=params, datastore=datastore, embedding_model=model)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/overview",
    summary="Every search lane at once (text, entities, images, files, events, places), laid out by rules",
    response_model=OverviewResponse,
    response_model_by_alias=True,
)
async def search_overview(
    request: SearchRequest,
    access: DatasetAccessDep,
    chunks: TextChunkDatastoreDep,
    images: ImageDatastoreDep,
    records: SearchRecordDatastoreDep,
    text_model: TextEmbeddingModelDep,
    image_model: ImageEmbeddingModelDep,
) -> OverviewResponse:
    """Run every lane in parallel, each under `SEARCH__LANE_BUDGET_MS`, and store the question.

    A lane that misses its budget comes back `timeout` instead of holding the page. The search is
    recorded (or its existing record bumped) for the user; its id is what `/search/[searchId]` uses.
    See docs/global-search.md.
    """
    started = time.perf_counter()
    record = await records.record(user_id=access.user.id, request=request)
    return await _overview(record.id, request, started, access, chunks, images, text_model, image_model, records)


@router.post(
    "/history/{search_id}/overview",
    summary="Re-run a stored search (Back/forward, reload) without recording it again",
    response_model=OverviewResponse,
    response_model_by_alias=True,
)
async def rerun_search(
    search_id: str,
    access: DatasetAccessDep,
    chunks: TextChunkDatastoreDep,
    images: ImageDatastoreDep,
    records: SearchRecordDatastoreDep,
    text_model: TextEmbeddingModelDep,
    image_model: ImageEmbeddingModelDep,
) -> OverviewResponse:
    """Same as `/search/overview` for a stored search; datasets are re-checked against current access."""
    started = time.perf_counter()
    record = await _readable(search_id, access, records)
    return await _overview(record.id, record, started, access, chunks, images, text_model, image_model, records)


async def _readable(search_id: str, access, records) -> SearchRecord:
    """The owner's (or, for an admin, anyone's) search. Anyone else gets 404, not 403, so ids reveal nothing."""
    record = await records.get(search_id)
    if record is None or (record.user_id != access.user.id and not access.user.is_admin):
        raise HTTPException(status_code=404, detail="Search not found")
    return record


async def _overview(
    search_id: str, request: SearchRequest, started: float, access, chunks, images, text_model, image_model, records
) -> OverviewResponse:
    trail = await records.trail(search_id)
    layout, lanes = await run_overview(
        request=request,
        dataset_ids=access.scope(request.dataset_ids),
        chunks=chunks,
        images=images,
        text_model=text_model,
        image_model=image_model,
        budget_ms=settings.search.lane_budget_ms,
    )
    return OverviewResponse(
        search_id=search_id,
        request=SearchRequest.model_validate(request.model_dump()),
        trail=trail,
        layout=layout,
        **{name.value: lane for name, lane in lanes.items()},
        took_ms=round((time.perf_counter() - started) * 1000),
    )


@router.get(
    "/history",
    summary="Your recent searches, most recently run first",
    response_model=PaginatedSearchHistory,
    response_model_by_alias=True,
)
async def search_history(
    access: DatasetAccessDep,
    records: SearchRecordDatastoreDep,
    saved: Annotated[bool | None, Query(description="Only saved (true) or unsaved (false) searches")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedSearchHistory:
    """Only ever the caller's own searches."""
    return await records.history(user_id=access.user.id, saved=saved, page=page, limit=limit)


@router.put(
    "/history/{search_id}/saved",
    summary="Save one of your searches (kept past pruning), optionally named",
    response_model=SearchRecord,
    response_model_by_alias=True,
)
async def save_search(
    search_id: str, body: SaveSearchRequest, access: DatasetAccessDep, records: SearchRecordDatastoreDep
) -> SearchRecord:
    """Owner only -- an admin can read anyone's search but not save it for them."""
    await _owned(search_id, access, records)
    return await records.set_saved(search_id, saved=True, name=body.name)


@router.delete(
    "/history/{search_id}/saved",
    summary="Unsave one of your searches",
    response_model=SearchRecord,
    response_model_by_alias=True,
)
async def unsave_search(search_id: str, access: DatasetAccessDep, records: SearchRecordDatastoreDep) -> SearchRecord:
    """It goes back to recent searches and is pruned like any other."""
    await _owned(search_id, access, records)
    return await records.set_saved(search_id, saved=False)


async def _owned(search_id: str, access, records) -> SearchRecord:
    record = await records.get(search_id)
    if record is None or record.user_id != access.user.id:
        raise HTTPException(status_code=404, detail="Search not found")
    return record


@router.get(
    "/history/{search_id}",
    summary="One stored search, to re-run it",
    response_model=SearchRecord,
    response_model_by_alias=True,
)
async def get_search(search_id: str, access: DatasetAccessDep, records: SearchRecordDatastoreDep) -> SearchRecord:
    """Private to its owner; admins can read any."""
    return await _readable(search_id, access, records)


@router.post(
    "/history/{search_id}/assist",
    summary="AI answer (for questions) and a suggested narrower search, from the backend's default LLM",
    response_model=SearchAssist,
    response_model_by_alias=True,
)
async def search_assist(
    search_id: str,
    access: DatasetAccessDep,
    records: SearchRecordDatastoreDep,
    chunks: TextChunkDatastoreDep,
    entities: EntityDatastoreDep,
    mentions: MentionDatastoreDep,
    text_model: TextEmbeddingModelDep,
) -> SearchAssist:
    """Grounded only in this search's own top passages; cached on the record, so Back never re-asks.

    Called by the page *after* it renders the results -- the model is never in front of them.
    """
    record = await _readable(search_id, access, records)
    if cached := await records.get_ai(search_id):
        return SearchAssist.model_validate(cached)
    results = await run_text_search(
        request=record,
        dataset_ids=access.scope(record.dataset_ids),
        chunks=chunks,
        text_model=text_model,
        limit=PASSAGES,
    )
    await end_transactions(records, chunks, entities, mentions)
    try:
        reading = await assist(
            record=record, results=results.data if results else [], entities=entities, mentions=mentions
        )
    except Exception as exc:  # noqa: BLE001 -- any model/provider failure is the same "AI unavailable" to the page
        logger.exception(exc)
        raise HTTPException(status_code=503, detail="The AI model is unavailable right now.") from exc
    await records.save_ai(search_id, reading.model_dump(mode="json"))
    return reading
