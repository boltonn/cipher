"""Tools the chat agent can call to retrieve and cite from the triaged data.

Each tool is a plain async function taking `RunContext[ChatDeps]`; `core.py`
registers them on the agent. Retrieval tools return lists of `ChatCitation`
wire dicts (rendered as source cards by the frontend); the entity/graph tools
return structured dicts the model chains into follow-up calls.
"""

from pydantic_ai import ModelRetry, RunContext
from pydantic_core import to_jsonable_python

from cipher.api.agent.citations import (
    chunk_citation,
    dataset_citation,
    entity_citation,
    mention_citation,
    person_citation,
    top_chunk,
)
from cipher.api.agent.deps import ChatDeps
from cipher.api.services.search import search_chunks
from cipher.schemas.dataset import DatasetsRequest
from cipher.schemas.entity import Entity
from cipher.schemas.mention import MentionSearchParameters
from cipher.schemas.ontology import EntityType, RelationshipType
from cipher.schemas.person import PersonSearchParameters
from cipher.schemas.search import (
    ChunkFilters,
    ChunkSemanticSearchRequest,
    ChunkTextSearchRequest,
)

_MAX_FILE_CHARS = 6000


def _chunk_filters(ctx: RunContext[ChatDeps]) -> ChunkFilters:
    return ChunkFilters(dataset_id=ctx.deps.dataset_id)


async def search_text(ctx: RunContext[ChatDeps], query: str, limit: int = 5) -> list[dict]:
    """Keyword (BM25) search over document and email text.

    Use this when the user's words are likely to appear verbatim -- names,
    quoted phrases, error strings, identifiers, exact terminology. It will not
    match paraphrases or synonyms; for those use `search_semantic`.
    """
    result = await ctx.deps.chunks.search_text(
        ChunkTextSearchRequest(query=query, limit=limit, filters=_chunk_filters(ctx))
    )
    return [chunk_citation(top_chunk(r)) for r in result.data]


async def search_semantic(ctx: RunContext[ChatDeps], query: str, limit: int = 5) -> list[dict]:
    """Meaning-based (vector) search over document and email text.

    Use this for conceptual questions where the wording won't match -- "concerns
    about the merger timeline", "anyone unhappy with the vendor". Matches on
    meaning, not exact words. For verbatim terms use `search_text`; when unsure
    use `search_hybrid`.
    """
    embedding = await ctx.deps.embedding_model.infer(text=query, task="retrieval", prompt="Query: ")
    if embedding is None:
        raise ModelRetry("The embedding model is unavailable, so semantic search can't run right now.")
    result = await ctx.deps.chunks.search_semantic(
        ChunkSemanticSearchRequest(embedding=embedding, limit=limit, filters=_chunk_filters(ctx))
    )
    return [chunk_citation(top_chunk(r)) for r in result.data]


async def search_hybrid(ctx: RunContext[ChatDeps], query: str, limit: int = 5) -> list[dict]:
    """Combined keyword + vector search over documents and emails (RRF fusion).

    The safe default when you want relevant passages to ground an answer and
    don't have a specific reason to prefer keyword-only or meaning-only.
    """
    try:
        result = await search_chunks(
            params=ChunkTextSearchRequest(query=query, limit=limit, filters=_chunk_filters(ctx)),
            datastore=ctx.deps.chunks,
            embedding_model=ctx.deps.embedding_model,
        )
    except RuntimeError as exc:
        raise ModelRetry(str(exc)) from exc
    return [chunk_citation(top_chunk(r)) for r in result.data]


async def find_person(ctx: RunContext[ChatDeps], name: str, limit: int = 5) -> list[dict]:
    """Look up people in the case by name, alias, or note text.

    Returns person records that link to their profile page. Use for "who is X",
    "show me people named Y". This is the analyst-curated `Person` table (faces,
    manual identities) -- distinct from `find_entity`, which covers names
    extracted from document text.
    """
    result = await ctx.deps.persons.search_persons(PersonSearchParameters(query=name, limit=limit))
    return [person_citation(p) for p in result.data]


async def list_datasets(ctx: RunContext[ChatDeps]) -> list[dict]:
    """List the datasets available in this workspace, each linking to its page.

    Use when the user asks what data exists, or to help them pick a dataset to
    scope the conversation to.
    """
    result = await ctx.deps.datasets.get_datasets(DatasetsRequest(limit=100))
    return [dataset_citation(d) for d in result.data]


def _require_dataset(ctx: RunContext[ChatDeps]) -> str:
    if ctx.deps.dataset_id is None:
        raise ModelRetry(
            "This tool needs a dataset. Ask the user to pick one with the dataset selector next "
            "to the chat input, then retry."
        )
    return ctx.deps.dataset_id


async def find_entity(
    ctx: RunContext[ChatDeps],
    name: str | None = None,
    selector_value: str | None = None,
    entity_type: EntityType | None = None,
    limit: int = 5,
) -> list[dict]:
    """Resolve a name or a strong identifier to entities extracted from the data.

    `selector_value` is a normalized phone/email/passport/handle/etc. Returns
    entity citations; each result's `targetId` is the entity id -- pass it to
    `entity_profile`, `entity_mentions`, or `related_entities`. Requires a
    selected dataset (entities are per-dataset).
    """
    dataset_id = _require_dataset(ctx)
    if not name and not selector_value:
        raise ModelRetry("Provide either `name` or `selector_value`.")
    found: list[Entity] = []
    if selector_value:
        entity = await ctx.deps.entities.search_by_selector(dataset_id=dataset_id, normalized_value=selector_value)
        if entity is not None:
            found.append(entity)
    if name:
        for r in await ctx.deps.entities.search_by_name(
            dataset_id=dataset_id, query=name, limit=limit, entity_type=entity_type
        ):
            full = await ctx.deps.entities.get_entity(r.id)
            if full is not None:
                found.append(full)

    seen: set[str] = set()
    out: list[dict] = []
    for entity in found:
        if entity.id in seen:
            continue
        seen.add(entity.id)
        out.append(entity_citation(entity))
    return out[:limit]


async def entity_profile(ctx: RunContext[ChatDeps], entity_id: str) -> dict:
    """Full dossier for one entity.

    Attributes, linked selectors, mention counts, directly-related entities, and
    a few representative mentions.
    """
    profile = await ctx.deps.entities.get_profile(entity_id)
    if profile is None:
        raise ModelRetry(f"No entity found with id {entity_id!r}. Use `find_entity` to look one up.")
    return to_jsonable_python(profile, by_alias=True)


async def entity_mentions(ctx: RunContext[ChatDeps], entity_id: str, limit: int = 10) -> list[dict]:
    """The evidence spans that mention an entity, as citations back to each file.

    Use this to ground a claim about an entity in specific passages the user can
    open.
    """
    result = await ctx.deps.mentions.list_mentions(
        MentionSearchParameters(entity_id=entity_id, resolved=True, limit=limit)
    )
    return [c for m in result.data if (c := mention_citation(m)) is not None]


async def related_entities(
    ctx: RunContext[ChatDeps],
    entity_id: str,
    relationship_type: RelationshipType | None = None,
    depth: int = 1,
) -> dict:
    """Traverse the knowledge graph from an entity.

    Answers who it communicates with, works for, is a member of, or shares an
    identifier with.
    `depth=1` returns direct neighbours; up to 3 walks further out. Filter with
    `relationship_type` (e.g. `communicates_with` for email/call links,
    `employed_by`/`member_of` for affiliation). Returns `{nodes, edges}`.
    """
    types = [relationship_type] if relationship_type else None
    if depth <= 1:
        graph = await ctx.deps.graph.neighbors(entity_id=entity_id, relationship_types=types)
    else:
        graph = await ctx.deps.graph.traverse(start_entity_id=entity_id, max_depth=depth, relationship_types=types)
    return to_jsonable_python(graph, by_alias=True)


async def read_file(
    ctx: RunContext[ChatDeps],
    file_id: str,
    start_offset: int | None = None,
    end_offset: int | None = None,
) -> dict:
    """Read a file's extracted text, optionally just the span [start_offset, end_offset).

    Use after a search or a mention citation to see the full surrounding context
    rather than only the retrieved snippet. Long reads are truncated.
    """
    extracted = await ctx.deps.extracted_text.get_by_file_id(file_id)
    if extracted is None:
        raise ModelRetry(f"No extracted text for file {file_id!r} -- it may not be a text document.")
    content = extracted.content
    span_start = start_offset if start_offset is not None else 0
    span_end = end_offset if end_offset is not None else len(content)
    text = content[span_start:span_end]
    truncated = len(text) > _MAX_FILE_CHARS
    return {
        "fileId": file_id,
        "startOffset": span_start,
        "endOffset": min(span_end, span_start + _MAX_FILE_CHARS),
        "totalChars": len(content),
        "truncated": truncated,
        "text": text[:_MAX_FILE_CHARS],
    }


ALL_TOOLS = (
    search_text,
    search_semantic,
    search_hybrid,
    find_person,
    list_datasets,
    find_entity,
    entity_profile,
    entity_mentions,
    related_entities,
    read_file,
)
