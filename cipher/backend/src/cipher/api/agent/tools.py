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
    merge_proposal_citation,
    person_citation,
    selector_link_proposal_citation,
    top_chunk,
)
from cipher.api.agent.deps import ChatDeps
from cipher.names import AddressAgreement, address_name_agreement
from cipher.schemas._base.review import ReviewStatus
from cipher.schemas.content.email import EmailCountGroupBy, EmailCountRequest
from cipher.schemas.content.search import ChunkFilters, GraphExpand, RetrievalMode, RetrievalQuery
from cipher.schemas.graph.entity import Entity
from cipher.schemas.graph.entity_match import EntityMatchCreate, EntityMatchMethod
from cipher.schemas.graph.entity_relationship import TopConnectionsRequest, TraversalDirection
from cipher.schemas.graph.mention import MentionSearchParameters
from cipher.schemas.graph.ontology import EntityType, RelationshipType, SelectorType, WeightedRelationshipType
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
    entity_ids: list[str] | None = None,
    connected_hops: int = 0,
    selector_type: SelectorType | None = None,
    sent_from: list[str] | None = None,
    sent_to: list[str] | None = None,
    participants: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    filetype_group: Literal["document", "email"] | None = None,
    tags: list[str] | None = None,
    limit: int = 8,
) -> list[dict]:
    """Find document and email passages, ranked by text and/or narrowed by entities and email metadata.

    Every argument is optional and they all combine (AND).

    Ranking (`query` + `mode`):
    - `mode="keyword"` -- BM25 on exact words: names, quoted phrases, ids, codes.
    - `mode="semantic"` -- meaning, for paraphrased/conceptual asks ("worried about money").
    - `mode="hybrid"` -- both fused; the default.
    - `query=""` browses whatever the filters match, newest first.

    Knowledge-graph filter:
    - `entity_ids` -- ONE person/org/location/selector (ids from `find_entity`, or a raw
      email/phone), plus any extra addresses the user confirmed are the same identity.
      Keeps passages that mention it (or its linked addresses/phones) in the text, or
      that are in an email it sent or received.
    - `connected_hops` (0-3) -- widen that to everyone within N relationship hops
      (1 = the people it emails / works with / is family of). Needs `entity_ids`.
    - `selector_type` -- only passages containing that kind of identifier ("phone",
      "crypto_address", "social_handle", ...).

    Email metadata filters (entity ids or raw email addresses; a person matches through
    their linked addresses and their resolved header name):
    - `sent_from` -- sent by any of these; `sent_to` -- to/cc/bcc any of these.
    - `participants` -- ALL of these on the email, in any role ("between X and Y").
    - `date_from` / `date_to` -- inclusive ISO dates (YYYY-MM-DD) on when an email was
      sent or a document authored.
    - `filetype_group` -- "email" or "document" only.

    Tag filter:
    - `tags` -- only files an analyst or model labelled with any of these tags (e.g. "event").

    For counting ("who does X email most", "how many emails per month") use
    `count_emails` / `top_connections` instead -- this returns passages, not totals.
    """
    filters = ctx.deps.access.scoped(
        ChunkFilters(
            dataset_id=ctx.deps.dataset_id,
            selector_types=[selector_type] if selector_type else None,
            sent_from=await _entity_refs(ctx, sent_from),
            sent_to=await _entity_refs(ctx, sent_to),
            participants=await _entity_refs(ctx, participants),
            date_from=date_from,
            date_to=date_to,
            filetype_group=filetype_group,
            tags=tags or None,
        )
    )
    graph_expand = None
    if entity_ids:
        hops = max(0, min(connected_hops, _MAX_HOPS - 1))
        # The first hop always crosses `has_selector` (a person -> their addresses/phones),
        # so hop 0 = the identity itself; each further hop follows any meaningful edge.
        graph_expand = GraphExpand(
            seed_entity_ids=await _entity_refs(ctx, entity_ids),
            max_depth=hops + 1,
            relationship_types=[RelationshipType.HAS_SELECTOR] if hops == 0 else None,
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
        ctx.deps.access.scoped(
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
    )
    out: dict = {
        "totalEmails": counts.total_emails,
        "groupBy": counts.group_by,
        "note": "Answer with the top 3-5 of THESE citations as a ranked list: name -- email count "
        "(date span). List nothing that isn't in this result.",
    }
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
    """List the datasets this conversation can read, each linking to its page.

    Use when the user asks what data exists. Only the datasets the chat is scoped to
    are listed; the user picks them in the chat's dataset selector.
    """
    result = await ctx.deps.datasets.get_datasets(
        DatasetsRequest(limit=100), accessible_ids=ctx.deps.access.dataset_ids
    )
    return [dataset_citation(d) for d in result.data if d.has_access]


async def find_entity(
    ctx: RunContext[ChatDeps],
    name: str | None = None,
    selector_value: str | None = None,
    entity_type: EntityType | None = None,
    limit: int = 5,
) -> dict:
    """Resolve a name or an identifier to knowledge-graph entities.

    `name` fuzzy-matches people, organizations, locations and selectors by display
    name. `selector_value` is an email / phone / handle / crypto address / passport /
    ... as written -- it is normalized for you (phones match best in +E.164). Each
    `citations` item's `targetId` is the entity id for `search_passages`, `count_emails`,
    `top_connections`, `entity_profile`, `entity_mentions` or `related_entities`. Searches the selected
    dataset, or every dataset when none is selected.

    For a `name`, `otherAddresses` lists email addresses seen in headers under a similar
    display name that don't belong to the best match (the first citation): `entityId`,
    `address`, `names`, `emailCount`, `linkedTo` (owning entity, or null if unlinked). The
    person may not be fully resolved yet, or may be resolved to the wrong entity.
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

    unique = list({entity.id: entity for entity in found}.values())[:limit]
    other_addresses = (
        await ctx.deps.mentions.header_addresses_for_name(
            name=name, dataset_id=dataset_id, exclude_owner=unique[0].id if unique else None
        )
        if name
        else []
    )
    # An address that spells someone else ("nbolton04" for Edmond) isn't a lead for this name.
    other_addresses = [
        row
        for row in other_addresses
        if address_name_agreement(row["address"], [name, *(e.display_name for e in unique[:1])])
        != AddressAgreement.CONFLICT
    ]
    out: dict = {"citations": [entity_citation(entity) for entity in unique], "otherAddresses": other_addresses}
    if other_addresses:
        # Small models follow an in-result hint far more reliably than the system prompt.
        out["note"] = (
            "If the user already said which addresses belong to whom, just do that -- don't ask about these. "
            "Otherwise, after answering, list otherAddresses for the user (address, email count, linked to) and ask "
            "whether to include them; flag any linked to a different person as a possible resolution error. "
            "If the user says one is theirs for good, use propose_selector_links (it only proposes)."
        )
    return out


async def propose_selector_links(
    ctx: RunContext[ChatDeps], entity_id: str, address_ids: list[str], reason: str
) -> dict:
    """Suggest that email addresses (or other selectors) belong to an entity. Changes NOTHING.

    Returns a review link to the entity's page, where the analyst sees each address's
    evidence (email count, names used, who it's linked to now) and confirms or dismisses
    it. Use it after the user agrees an address is someone's -- e.g. `otherAddresses`
    from `find_entity` -- or asks to fix a wrong link. `address_ids` are the addresses'
    entity ids (or raw addresses); `reason` is one sentence of evidence for the analyst.
    """
    entity = await ctx.deps.entities.get_entity(await _entity_ref(ctx, entity_id))
    if entity is None:
        raise ModelRetry(f"No entity {entity_id!r}. Look it up with `find_entity` first.")
    if entity.entity_type not in (EntityType.PERSON, EntityType.ORGANIZATION):
        raise ModelRetry(
            f"`entity_id` must be the person or organization that owns the addresses, not a "
            f"{entity.entity_type} ({entity.display_name}). Find the owner with find_entity(name=...) first."
        )
    selector_ids = await _entity_refs(ctx, address_ids) or []
    if not selector_ids:
        raise ModelRetry("Pass at least one address id in `address_ids`.")
    return {
        "citations": [selector_link_proposal_citation(entity, selector_ids, reason)],
        "note": "Nothing has been changed. Tell the user to use the 'Review & confirm' button below your "
        "answer to confirm or dismiss each address. Don't write the link or any URL yourself.",
    }


def _is_curated(entity: Entity) -> bool:
    """An analyst-curated identity (person bridge / verified / dataset-agnostic) -- the one that survives a merge."""
    return bool(entity.person_id or entity.is_verified or entity.dataset_id is None)


async def propose_entity_merge(ctx: RunContext[ChatDeps], entity_a: str, entity_b: str, reason: str) -> dict:
    """Suggest that two entities are the same real-world person/org. Changes NOTHING.

    Files (or finds) a pending merge proposal and returns a review link to the duplicate's
    page, where the analyst merges it or keeps them separate. The curated entity (verified
    or a Persons record) is kept and the other folds into it. Pass entity ids from
    `find_entity`; `reason` is one sentence of evidence for the analyst.
    """
    a = await ctx.deps.entities.get_entity(await _entity_ref(ctx, entity_a))
    b = await ctx.deps.entities.get_entity(await _entity_ref(ctx, entity_b))
    if a is None or b is None:
        raise ModelRetry("Both entities must exist -- look them up with `find_entity` first.")
    if a.id == b.id:
        raise ModelRetry("Those are the same entity already.")
    if a.entity_type != b.entity_type or a.entity_type not in (EntityType.PERSON, EntityType.ORGANIZATION):
        raise ModelRetry("Only two people or two organizations can be merged.")
    if _is_curated(a) and _is_curated(b):
        return {
            "note": f"{a.display_name} and {b.display_name} are both curated identities; merging would delete "
            "one. Tell the user to combine them in Persons instead -- nothing was proposed."
        }
    keep, duplicate = (a, b) if _is_curated(a) or not _is_curated(b) else (b, a)
    dataset_id = duplicate.dataset_id or ctx.deps.dataset_id
    if dataset_id is None:
        raise ModelRetry("Select a dataset first -- merge proposals are reviewed per dataset.")

    existing = next(
        (m for m in await ctx.deps.entity_matches.list_for_provisional(provisional_entity_id=duplicate.id)
         if m.entity_id == keep.id),
        None,
    )  # fmt: skip
    if existing is None:
        await ctx.deps.entity_matches.create_merge_match(
            EntityMatchCreate(
                dataset_id=dataset_id,
                entity_id=keep.id,
                provisional_entity_id=duplicate.id,
                similarity_score=0.5,
                match_method=EntityMatchMethod.ASSISTANT,
            )
        )
    elif existing.status != ReviewStatus.PENDING:
        return {
            "note": f"An analyst already {existing.status} merging {duplicate.display_name} into "
            f"{keep.display_name}. Tell the user; nothing was proposed."
        }
    return {
        "citations": [merge_proposal_citation(duplicate, keep, reason)],
        "note": "Nothing has been changed. Tell the user to use the 'Review & confirm' button below your answer "
        "to merge or keep them separate. Don't write the link or any URL yourself.",
    }


async def entity_profile(ctx: RunContext[ChatDeps], entity_id: str) -> dict:
    """Full dossier for one entity.

    Attributes, linked selectors, mention counts, directly-related entities, and
    a few representative mentions.
    """
    profile = await ctx.deps.entities.get_profile(entity_id)
    if profile is None:
        raise ModelRetry(f"No entity found with id {entity_id!r}. Use `find_entity` to look one up.")
    top_mentions = [m for m in profile.top_mentions if ctx.deps.access.allows(m.dataset_id)]
    return to_jsonable_python(profile.model_copy(update={"top_mentions": top_mentions}), by_alias=True)


async def entity_mentions(ctx: RunContext[ChatDeps], entity_id: str, limit: int = 10) -> list[dict]:
    """The evidence spans that mention an entity, as citations back to each file.

    Use this to ground a claim about an entity in specific passages the user can
    open.
    """
    result = await ctx.deps.mentions.list_mentions(
        ctx.deps.access.scoped(MentionSearchParameters(entity_id=entity_id, resolved=True, limit=limit))
    )
    return [c for m in result.data if (c := mention_citation(m)) is not None]


async def related_entities(
    ctx: RunContext[ChatDeps],
    entity_id: str,
    relationship_type: RelationshipType | None = None,
    depth: int = 1,
) -> dict:
    """Traverse the knowledge graph from an entity.

    Answers who it communicates with, works for, is a member of, shares an
    identifier with, or which events (meetings, trips, calls) it took part in.
    `depth=1` returns direct neighbours; up to 3 walks further out. Filter with
    `relationship_type` (any type in the ontology in your instructions, e.g. `emailed`,
    `employed_by`, `member_of`, `participant_in`). With `participant_in` and `depth=2`
    the event nodes lead on to everyone else who attended them. Returns `{nodes, edges}`. To rank
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
    relationship_type: WeightedRelationshipType | None = None,
    direction: TraversalDirection = TraversalDirection.BOTH,
    limit: int = 15,
) -> dict:
    """Rank who/what is most strongly connected to some nodes, by edge weight -- the generic "most" question.

    `entity_ids`: ids from `find_entity`/`find_person`, or raw emails / phones / handles. Pass a
    person (their resolved addresses are included) and/or the bare selectors themselves -- it
    works before entity resolution. `relationship_type` picks one of the rankable types -- the
    ontology in your instructions marks each with what its [weight] counts and whether it is
    directed (->); omit it to rank all of them together. `direction` applies to directed types:
    "out" = the seeds are the source, "in" = the destination, "both" = either. A neighbour's
    addresses are merged into the one person/org that owns them when known (`via` lists them).
    Weights are all-time totals -- for date ranges or volume over time use `count_emails`.
    """
    result = await ctx.deps.graph.top_connections(
        TopConnectionsRequest(
            entity_ids=await _entity_refs(ctx, entity_ids) or [],
            relationship_types=[RelationshipType(relationship_type)] if relationship_type else None,
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
    if mention is None or not ctx.deps.access.allows(mention.dataset_id):
        raise ModelRetry(f"No mention {mention_id!r} in the datasets this chat can read.")
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
    file = await ctx.deps.files.get_file_by_id(file_id=file_id)
    if file is None or not ctx.deps.access.allows(file.dataset_id):
        raise ModelRetry(f"No file {file_id!r} in the datasets this chat can read.")
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
    propose_selector_links,
    propose_entity_merge,
    read_file,
)
