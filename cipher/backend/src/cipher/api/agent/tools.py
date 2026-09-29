"""Tools the chat agent can call to retrieve and cite from the triaged data.

Each tool is a plain async function taking `RunContext[ChatDeps]`; `core.py`
registers them on the agent. `search_passages` returns a list of `ChatCitation`
wire dicts (rendered as source cards by the frontend); the entity/graph/count
tools return structured dicts the model chains into follow-up calls.
"""

from datetime import date
from typing import Literal

from pydantic_ai import ModelRetry, RunContext
from pydantic_core import to_jsonable_python
from pyselectors.extract import extract_selectors

from cipher.api.agent.citations import (
    chunk_citation,
    connection_citation,
    dataset_citation,
    email_count_citation,
    entity_citation,
    mention_citation,
    person_citation,
    top_chunk,
)
from cipher.api.agent.deps import ChatDeps
from cipher.schemas.content.email import EmailCountGroupBy, EmailCountRequest
from cipher.schemas.content.search import ChunkFilters, GraphExpand, RetrievalMode, RetrievalQuery
from cipher.schemas.graph.entity import Entity
from cipher.schemas.graph.entity_relationship import TopConnectionsRequest, TraversalDirection
from cipher.schemas.graph.mention import MentionSearchParameters
from cipher.schemas.graph.ontology import EntityType, RelationshipType, SelectorType
from cipher.schemas.identity.person import PersonSearchParameters
from cipher.schemas.ingestion.dataset import DatasetsRequest

_MAX_FILE_CHARS = 6000
_MAX_HOPS = 3


def _selector_candidates(value: str) -> list[str]:
    """`value` as typed plus every normalized selector pyselectors finds in it."""
    return list(dict.fromkeys([value.strip(), *(s.normalized_value for s in extract_selectors(value))]))


async def _entity_ref(ctx: RunContext[ChatDeps], ref: str) -> str:
    """An entity id, or the id of the selector entity for a raw email / phone / handle."""
    if await ctx.deps.entities.get_entity(ref) is not None:
        return ref
    for candidate in _selector_candidates(ref):
        entity = await ctx.deps.entities.search_by_selector(dataset_id=ctx.deps.dataset_id, normalized_value=candidate)
        if entity is not None:
            return entity.id
    raise ModelRetry(f"{ref!r} is not a known entity id or selector value. Look it up with `find_entity` first.")


async def _entity_refs(ctx: RunContext[ChatDeps], refs: list[str] | None) -> list[str] | None:
    return [await _entity_ref(ctx, r) for r in refs] if refs else None


async def search_passages(
    ctx: RunContext[ChatDeps],
    query: str = "",
    mode: RetrievalMode = RetrievalMode.HYBRID,
    entity_id: str | None = None,
    connected_hops: int = 0,
    relationship_type: RelationshipType | None = None,
    selector_type: SelectorType | None = None,
    sent_from: list[str] | None = None,
    sent_to: list[str] | None = None,
    participants: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    filetype_group: Literal["document", "email"] | None = None,
    limit: int = 8,
) -> list[dict]:
    """Find document and email passages, ranked by text and/or narrowed by entities and email metadata.

    Every argument is optional and they all combine (AND).

    Ranking (`query` + `mode`):
    - `mode="keyword"` -- BM25 on exact words: names, quoted phrases, ids, codes.
    - `mode="semantic"` -- meaning, for paraphrased/conceptual asks ("worried about money").
    - `mode="hybrid"` -- both fused; the default.
    - `query=""` browses whatever the filters match, newest first.

    Knowledge-graph filters:
    - `entity_id` -- only passages mentioning this entity (a person/org/location, or a
      selector such as an email address or phone). Includes mentions of the entity's own
      selectors. Get ids from `find_entity`; a raw email/phone value also works.
    - `connected_hops` (0-3) -- also include passages mentioning entities connected to
      `entity_id` through the graph: 1 = direct contacts/affiliations, 2-3 = further out.
      `relationship_type` limits which edges are followed (e.g. `emailed`).
    - `selector_type` -- only passages containing that kind of identifier ("phone",
      "crypto_address", "social_handle", ...).

    Email metadata filters (entity ids or raw email addresses; a person matches through
    their addresses):
    - `sent_from` -- the email's sender; `sent_to` -- to/cc/bcc recipients.
    - `participants` -- in any header role; several = emails between all of them.
    - `date_from` / `date_to` -- inclusive ISO dates (YYYY-MM-DD) on when an email was
      sent or a document authored.
    - `filetype_group` -- "email" or "document" only.

    For counting ("who does X email most", "how many emails per month") use
    `count_emails` instead -- this returns passages, not totals.
    """
    filters = ChunkFilters(
        dataset_id=ctx.deps.dataset_id,
        selector_types=[selector_type] if selector_type else None,
        sent_from=await _entity_refs(ctx, sent_from),
        sent_to=await _entity_refs(ctx, sent_to),
        participants=await _entity_refs(ctx, participants),
        date_from=date_from,
        date_to=date_to,
        filetype_group=filetype_group,
    )
    graph_expand = None
    if entity_id:
        hops = max(0, min(connected_hops, _MAX_HOPS))
        # One extra hop always crosses `has_selector`, so a person's own addresses count
        # as "the entity", and their contacts (reached via those addresses) as hop 1.
        graph_expand = GraphExpand(
            seed_entity_id=await _entity_ref(ctx, entity_id),
            max_depth=min(hops + 1, _MAX_HOPS),
            relationship_types=[RelationshipType.HAS_SELECTOR, *([relationship_type] if relationship_type else [])]
            if hops == 0 or relationship_type
            else None,
        )

    text = query.strip()
    embedding = None
    if text and mode != RetrievalMode.KEYWORD:
        try:
            embedding = await ctx.deps.embedding_model.infer(text=text, task="retrieval")
        except Exception as exc:  # noqa: BLE001 -- degrade to keyword rather than fail the turn
            raise ModelRetry(f"Semantic search failed ({type(exc).__name__}); retry with mode='keyword'.") from exc
        if embedding is None:
            raise ModelRetry("The embedding model is unavailable; retry with mode='keyword'.")
    try:
        result = await ctx.deps.chunks.search(
            RetrievalQuery(
                mode=mode,
                text=text or None,
                embedding=embedding,
                filters=filters,
                graph_expand=graph_expand,
                limit=max(1, min(limit, 25)),
            )
        )
    except ValueError as exc:
        raise ModelRetry(str(exc)) from exc
    return [chunk_citation(top_chunk(r)) for r in result.data]


async def count_emails(
    ctx: RunContext[ChatDeps],
    group_by: EmailCountGroupBy,
    sent_from: list[str] | None = None,
    sent_to: list[str] | None = None,
    participants: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 15,
) -> dict:
    """Count emails -- who emails whom most, and when. Returns totals, not passages.

    Filters are the same as `search_passages` (entity ids or raw email addresses; a
    person matches through their addresses). `group_by`:
    - "recipient" -- with `sent_from=[X]`: who X emails most.
    - "sender" -- with `sent_to=[X]`: who emails X most.
    - "correspondent" -- with `participants=[X]`: X's top contacts either direction.
    - "day" / "month" / "year" -- volume over time for the filtered emails.

    `totalEmails` is the count for the filters overall. People come back as entity
    `citations` (`targetId` = entity id, `score` = email count, `snippet` = count, date
    span and addresses used); periods come back as `periods`. Each message is counted
    once even if it appears in several mailboxes.
    """
    counts = await ctx.deps.mentions.count_emails(
        EmailCountRequest(
            dataset_id=ctx.deps.dataset_id,
            sent_from=await _entity_refs(ctx, sent_from),
            sent_to=await _entity_refs(ctx, sent_to),
            participants=await _entity_refs(ctx, participants),
            date_from=date_from,
            date_to=date_to,
            group_by=group_by,
            limit=max(1, min(limit, 100)),
        )
    )
    out: dict = {"totalEmails": counts.total_emails, "groupBy": counts.group_by}
    if group_by in (EmailCountGroupBy.SENDER, EmailCountGroupBy.RECIPIENT, EmailCountGroupBy.CORRESPONDENT):
        out["citations"] = [email_count_citation(b) for b in counts.buckets]
    else:
        out["periods"] = [
            {"period": b.key, "emailCount": b.email_count, "dateFirst": b.date_first, "dateLast": b.date_last}
            for b in counts.buckets
        ]
    return to_jsonable_python(out)


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


async def find_entity(
    ctx: RunContext[ChatDeps],
    name: str | None = None,
    selector_value: str | None = None,
    entity_type: EntityType | None = None,
    limit: int = 5,
) -> list[dict]:
    """Resolve a name or an identifier to knowledge-graph entities.

    `name` fuzzy-matches people, organizations, locations and selectors by display
    name. `selector_value` is an email / phone / handle / crypto address / passport /
    ... as written -- it is normalized for you (phones match best in +E.164). Each
    result's `targetId` is the entity id for `search_passages`, `count_emails`,
    `top_connections`, `entity_profile`, `entity_mentions` or `related_entities`. Searches the selected
    dataset, or every dataset when none is selected.
    """
    if not name and not selector_value:
        raise ModelRetry("Provide either `name` or `selector_value`.")
    dataset_id = ctx.deps.dataset_id
    found: list[Entity] = []
    for candidate in _selector_candidates(selector_value) if selector_value else []:
        entity = await ctx.deps.entities.search_by_selector(dataset_id=dataset_id, normalized_value=candidate)
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
    `relationship_type` (e.g. `emailed` for sender -> recipient email links,
    `employed_by`/`member_of` for affiliation). Returns `{nodes, edges}`. To rank
    the strongest connections ("who does X talk to most"), use `top_connections`.
    """
    types = [relationship_type] if relationship_type else None
    if depth <= 1:
        graph = await ctx.deps.graph.neighbors(entity_id=entity_id, relationship_types=types)
    else:
        graph = await ctx.deps.graph.traverse(start_entity_id=entity_id, max_depth=depth, relationship_types=types)
    return to_jsonable_python(graph, by_alias=True)


async def top_connections(
    ctx: RunContext[ChatDeps],
    entity_ids: list[str],
    relationship_type: RelationshipType | None = None,
    direction: TraversalDirection = TraversalDirection.BOTH,
    limit: int = 15,
) -> dict:
    """Rank who/what is most strongly connected to some nodes, by edge weight -- the generic "most" question.

    `entity_ids`: ids from `find_entity`/`find_person`, or raw emails / phones / handles. Pass a
    person (their resolved addresses are included) and/or the bare selectors themselves -- it
    works before entity resolution. Filter with `relationship_type`: `emailed` (weight =
    emails, directed sender -> recipient), `appears_in_photo_with` (shared photos), ...;
    default ranks every weighted type. `direction` (directed types like `emailed`): "out" = the
    seeds sent, "in" = they received, "both" = either. A neighbour's addresses are merged into the one person/org
    that owns them when known (`via` lists them). Weights are all-time totals -- for date ranges or
    volume over time use `count_emails`.
    """
    result = await ctx.deps.graph.top_connections(
        TopConnectionsRequest(
            entity_ids=await _entity_refs(ctx, entity_ids) or [],
            relationship_types=[relationship_type] if relationship_type else None,
            direction=direction,
            dataset_id=ctx.deps.dataset_id,
            limit=max(1, min(limit, 100)),
        )
    )
    return to_jsonable_python(
        {
            "seeds": [s.display_name for s in result.seeds],
            "citations": [connection_citation(c) for c in result.connections],
            "edgesWithoutDirection": result.edges_without_direction,
        }
    )


async def explain_entity_resolution(ctx: RunContext[ChatDeps], mention_id: str) -> dict:
    """Why a mention did or didn't resolve to an entity.

    Returns the scored candidates for the mention's name group with the
    per-feature breakdown (shared selector, name structure, trigram, any
    conflict that vetoed a look-alike) and the decision band. An empty
    `candidates` list means nothing blocked or nothing cleared the review floor.
    """
    mention = await ctx.deps.mentions.get_mention(mention_id)
    if mention is None:
        raise ModelRetry(f"No mention {mention_id!r}.")
    candidates = []
    if mention.normalized_value:
        rows = await ctx.deps.entity_matches.list_for_name_group(
            dataset_id=mention.dataset_id, normalized_value=mention.normalized_value
        )
        candidates = [to_jsonable_python(r, by_alias=True) for r in rows]
    return {
        "mentionId": mention_id,
        "normalizedValue": mention.normalized_value,
        "resolvedEntityId": mention.entity_id,
        "candidates": candidates,
    }


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
    search_passages,
    count_emails,
    find_person,
    list_datasets,
    find_entity,
    entity_profile,
    entity_mentions,
    related_entities,
    top_connections,
    explain_entity_resolution,
    read_file,
)
