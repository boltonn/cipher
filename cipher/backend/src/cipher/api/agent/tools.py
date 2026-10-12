"""Tools the chat agent can call to retrieve and cite from the triaged data.

Each tool is a plain async function taking `RunContext[ChatDeps]`; `core.py`
registers them on the agent. `search_passages` returns a list of `ChatCitation`
wire dicts (rendered as source cards by the frontend); the entity/graph/count
tools return structured dicts the model chains into follow-up calls.
"""

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from pydantic_ai import CallDeferred, ModelRetry, RunContext
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_core import to_jsonable_python
from pyselectors.extract import extract_selectors

from cipher.api.agent.citations import (
    chunk_citation,
    connection_citation,
    dataset_citation,
    email_count_citation,
    entity_citation,
    event_citation,
    file_citation,
    image_citation,
    mention_citation,
    merge_proposal_citation,
    person_citation,
    profile_entity_citation,
    selector_link_proposal_citation,
    top_chunk,
)
from cipher.api.agent.deps import ChatDeps
from cipher.api.services.global_search import images_matching_text
from cipher.names import AddressAgreement, address_name_agreement, is_role_address
from cipher.schemas._base.common import SortOrder
from cipher.schemas._base.review import ReviewStatus
from cipher.schemas.content.email import EmailCategory, EmailCountGroupBy, EmailCountRequest, MessageState
from cipher.schemas.content.search import ChunkFilters, ChunkSortField, GraphExpand, RetrievalMode, RetrievalQuery
from cipher.schemas.graph.entity import Entity
from cipher.schemas.graph.entity_match import EntityMatchCreate, EntityMatchMethod
from cipher.schemas.graph.entity_relationship import TopConnectionsRequest, TraversalDirection
from cipher.schemas.graph.event import EventSearchParameters, EventType
from cipher.schemas.graph.mention import MentionSearchParameters
from cipher.schemas.graph.ontology import EntityType, RelationshipType, SelectorType, WeightedRelationshipType
from cipher.schemas.identity.person import PersonSearchParameters
from cipher.schemas.ingestion.dataset import DatasetsRequest
from cipher.schemas.interaction.chat import ChatAutonomy

_MAX_FILE_CHARS = 6000
_MAX_HOPS = 3
# Each passage carries a ~700-char excerpt; more per call crowds a small model's context.
_MAX_PASSAGES = 12
# Left out of searches by default. Not Gmail's "updates" tab: it also files bills, itineraries and security codes.
PROMOTION_SOURCE_TAGS = (EmailCategory.PROMOTIONS, EmailCategory.SOCIAL, EmailCategory.FORUMS)
SPAM_MESSAGE_STATES = (MessageState.SPAM,)
STOP_REPEATING = "STOP searching"
CHECK_IN = "Check in"
CHECK_IN_FILES = 50


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
    names: list[str] | None = None,
    connected_hops: int = 0,
    selector_type: SelectorType | None = None,
    sent_from: list[str] | None = None,
    sent_to: list[str] | None = None,
    participants: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    filetype_group: Literal["document", "email"] | None = None,
    tags: list[str] | None = None,
    include_promotions_and_spam: bool = False,
    sort_by: ChunkSortField = ChunkSortField.SCORE,
    limit: int = 8,
) -> dict:
    """Find document and email passages: rank by `query`, narrow by people, addresses, dates and tags.

    All filters combine (AND). Returns `searched`, the number of matching files (`total`) and the
    best passages as `citations` (long `snippet`s; `read_file` one for its full text).

    - `query` -- words that would appear in the answer: the topic and synonyms ("loan owe pay back
      borrowed"), not a person's name (filter people instead). Empty = browse what the filters
      match, newest first ("latest emails from X").
    - `mode` -- "keyword" (exact words, names, codes, ids), "semantic" (the idea, paraphrase),
      "hybrid" (both; default). `sort_by="date_created"` = newest first even with a `query`.
    - `entity_ids` -- ONE person/org/place/selector (id from find_entity, or a raw email/phone) plus
      addresses the user confirmed are theirs: text naming it, or mail it sent/received.
    - `names` -- find_entity's `nameGroup.value`; matches the name as written, resolved or not.
    - `connected_hops` (0-3) -- widen `entity_ids` to everyone within N relationship hops.
    - `selector_type` -- only text containing that kind of identifier (phone, crypto_address...).
    - `sent_from` / `sent_to` (to/cc/bcc) / `participants` (all of them on the email) -- entity
      ids or raw addresses. `date_from` / `date_to` -- inclusive YYYY-MM-DD, sent or authored.
    - `filetype_group` -- "email" or "document"; `tags` -- files labelled with any of these.
    - `include_promotions_and_spam` -- promotions / social / forums mail and spam are left out unless true: set
      it for questions about marketing, vendors, newsletters or spam, or when nothing else turns up.

    Passages, not totals: for "how many" / "who most" use count_emails or top_connections.
    """
    seed_ids = await _entity_refs(ctx, entity_ids) or []
    text = query.strip()
    if text:
        text = await _without_filtered_names(ctx, text=text, names=names or [], entity_ids=seed_ids)
    if repeats := _earlier_identical_calls(ctx):
        return {
            "note": f"{STOP_REPEATING}: you have run this exact search before. Answer now from the results you "
            "already have (say what you couldn't find)."
            if repeats > 1
            else "You already ran this exact search. Change the words or mode, drop a filter, or read_file a "
            "promising hit -- or answer if you have enough."
        }
    filters = ChunkFilters(
        dataset_id=ctx.deps.dataset_id,
        selector_types=[selector_type] if selector_type else None,
        sent_from=await _entity_refs(ctx, sent_from),
        sent_to=await _entity_refs(ctx, sent_to),
        participants=await _entity_refs(ctx, participants),
        date_from=date_from,
        date_to=date_to,
        filetype_group=filetype_group,
        tags=tags or None,
        exclude_source_tags=None if include_promotions_and_spam else list(PROMOTION_SOURCE_TAGS),
        exclude_message_states=None if include_promotions_and_spam else list(SPAM_MESSAGE_STATES),
    )
    graph_expand = None
    if seed_ids or names:
        hops = max(0, min(connected_hops, _MAX_HOPS - 1))
        # The first hop always crosses `has_selector` (a person -> their addresses/phones),
        # so hop 0 = the identity itself; each further hop follows any meaningful edge.
        graph_expand = GraphExpand(
            seed_entity_ids=seed_ids,
            seed_names=names or [],
            max_depth=hops + 1,
            relationship_types=[RelationshipType.HAS_SELECTOR] if hops == 0 else None,
        )
    # No words to rank by: a browse of what the filters match, newest first.
    sort_by = sort_by if text else ChunkSortField.DATE

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
                filters=ctx.deps.access.scoped(filters),
                graph_expand=graph_expand,
                sort_by=sort_by,
                limit=max(1, min(limit, _MAX_PASSAGES)),
            )
        )
    except ValueError as exc:
        raise ModelRetry(str(exc)) from exc
    out: dict = {
        "searched": {
            "query": text or None,
            "mode": mode.value if text else "browse",
            "sortBy": sort_by.value,
            "promotionsAndSpamHidden": not include_promotions_and_spam,
        },
        "total": result.total,
        "citations": [chunk_citation(top_chunk(r)) for r in result.data],
        "openAll": await _open_all(ctx, text=text, mode=mode, filters=filters, graph_expand=graph_expand),
    }
    if not result.data:
        out["note"] = (
            "Nothing matched. Try other words or mode, or drop a filter -- people are often named "
            "differently (first name, nickname, address) or not at all in their own emails."
            + (
                ""
                if include_promotions_and_spam
                else " Promotions and spam were left out; include_promotions_and_spam=true searches them too."
            )
        )
    elif result.total > CHECK_IN_FILES and ctx.deps.autonomy == ChatAutonomy.GUIDED and not _checked_in(ctx):
        out["note"] = (
            f"{CHECK_IN}: {result.total} files match -- more than you can read, so the analyst decides how to go "
            "on. Call ask_user now (other tools are paused until they answer) with 2-4 concrete next steps drawn "
            "from these results: narrow to a period, person, sender or folder you see in them; search a sharper "
            "angle; and always 'Answer from the best matches'. They can also open the full list below your answer."
        )
    return out


def _this_turn(ctx: RunContext[ChatDeps]) -> list[ModelMessage]:
    """The messages since the analyst's latest prompt."""
    starts = [
        index
        for index, message in enumerate(ctx.messages)
        if isinstance(message, ModelRequest) and any(isinstance(part, UserPromptPart) for part in message.parts)
    ]
    return ctx.messages[starts[-1] :] if starts else ctx.messages


def awaiting_check_in(ctx: RunContext[ChatDeps]) -> bool:
    """Whether the agent was told to check in this turn and the analyst hasn't been asked yet."""
    raised = asked = False
    for message in _this_turn(ctx):
        for part in message.parts:
            raised |= isinstance(part, ToolReturnPart) and CHECK_IN in part.model_response_str()
            asked |= raised and isinstance(part, ToolCallPart) and part.tool_name == "ask_user"
    return raised and not asked


def _checked_in(ctx: RunContext[ChatDeps]) -> bool:
    """Whether this turn already asked the analyst, or was already told to (one check-in per turn)."""
    return any(
        (isinstance(part, ToolCallPart) and part.tool_name == "ask_user")
        or (isinstance(part, ToolReturnPart) and CHECK_IN in part.model_response_str())
        for message in _this_turn(ctx)
        for part in message.parts
    )


async def _open_all(
    ctx: RunContext[ChatDeps],
    *,
    text: str,
    mode: RetrievalMode,
    filters: ChunkFilters,
    graph_expand: GraphExpand | None,
) -> dict:
    """The search as the text-search page runs it, so the user can open every match, not just these few."""
    labels = []
    for entity_id in graph_expand.seed_entity_ids if graph_expand else []:
        entity = await ctx.deps.entities.get_entity(entity_id)
        labels.append(entity.display_name if entity else entity_id)
    labels += graph_expand.seed_names if graph_expand else []
    dataset_ids = ctx.deps.access.dataset_ids
    return {
        "query": text,
        "mode": mode.value,
        "datasetIds": sorted(dataset_ids) if dataset_ids is not None else None,
        "filters": filters.model_dump(mode="json", by_alias=True, exclude_none=True, exclude={"dataset_id"}),
        "graphExpand": graph_expand.model_dump(mode="json", by_alias=True) if graph_expand else None,
        "graphExpandLabel": ", ".join(labels) or None,
    }


def _earlier_identical_calls(ctx: RunContext[ChatDeps]) -> int:
    """How many earlier calls to this tool had exactly these arguments -- small models loop on one search."""
    calls = [
        part
        for message in ctx.messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_name == ctx.tool_name
    ]
    current = next((part for part in calls if part.tool_call_id == ctx.tool_call_id), None)
    if current is None:
        return 0
    return sum(
        part.args_as_dict() == current.args_as_dict() for part in calls if part.tool_call_id != current.tool_call_id
    )


async def _without_filtered_names(
    ctx: RunContext[ChatDeps], *, text: str, names: list[str], entity_ids: list[str]
) -> str:
    """`text` minus the names already applied as filters -- a name in every hit's text drowns out the topic."""
    filtered = list(names)
    for entity_id in entity_ids:
        if (entity := await ctx.deps.entities.get_entity(entity_id)) is not None:
            filtered.append(entity.display_name)
    tokens = {token for name in filtered for token in re.findall(r"\w+", name.lower()) if len(token) > 1}
    if not tokens:
        return text
    pattern = rf"\b(?:{'|'.join(map(re.escape, sorted(tokens, key=len, reverse=True)))})(?:'s)?\b"
    stripped = " ".join(re.sub(pattern, " ", text, flags=re.IGNORECASE).split())
    return stripped if re.search(r"\w", stripped) else text


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

    For a `name`, `nameGroup` is how that name is written across the data, resolved or not:
    `value` (pass it to search_passages' `names`), `mentions`, `files`, `unresolvedMentions`,
    and `pendingCandidates` (entities the resolver proposed, still awaiting review).

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
    # An address that spells someone else ("nbolton04" for Edmond) isn't a lead for this name, nor is a
    # shared mailbox that sends under the recipient's name ("Nick Bolton <info@cvent.com>").
    other_addresses = [
        row
        for row in other_addresses
        if not is_role_address(row["address"])
        and address_name_agreement(row["address"], [name, *(e.display_name for e in unique[:1])])
        != AddressAgreement.CONFLICT
    ]
    name_group = await ctx.deps.mentions.name_group(name=name, dataset_id=dataset_id) if name else None
    out: dict = {
        "citations": [entity_citation(entity) for entity in unique],
        "nameGroup": name_group,
        "otherAddresses": other_addresses,
    }
    # Small models follow an in-result hint far more reliably than the system prompt.
    notes = []
    if name_group and name_group["unresolvedMentions"]:
        notes.append(
            f"{name_group['unresolvedMentions']} mentions of {name_group['value']!r} aren't resolved to one entity "
            "yet. Don't wait on that: search with names=[nameGroup.value] (plus the best entity and any addresses "
            "that are clearly theirs). Mention afterwards that the name group is pending review."
        )
    if other_addresses:
        notes.append(
            "If the user already said which addresses belong to whom, just do that -- don't ask about these. "
            "Otherwise answer first, then list otherAddresses (address, email count, linked to) and offer to include "
            "them; flag any linked to a different person as a possible resolution error. Use ask_user only if the "
            "answer would be wrong without knowing. If the user says one is theirs for good, use "
            "propose_selector_links (it only proposes)."
        )
    if notes:
        out["note"] = " ".join(notes)
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
    top_mentions = [
        c for m in profile.top_mentions if ctx.deps.access.allows(m.dataset_id) and (c := mention_citation(m))
    ]
    # Face ids are for the profile page, not the model (it has no face tool): a count, not 100+ uuids.
    return to_jsonable_python(
        profile.model_copy(update={"top_mentions": [], "face_ids": []}), by_alias=True, exclude_none=True
    ) | {"topMentions": top_mentions, "faceCount": len(profile.face_ids)}


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
    # Notes rather than ModelRetry: a turn that runs out of retries on one bad read loses everything else.
    if _earlier_identical_calls(ctx):
        return {"note": "You already read this exact span above. Use what you learned, read another span, or answer."}
    file = await ctx.deps.files.get_file_by_id(file_id=file_id)
    if file is None or not ctx.deps.access.allows(file.dataset_id):
        return {"note": f"No file {file_id!r} in the datasets this chat can read. Use a `fileId` from a result."}
    extracted = await ctx.deps.extracted_text.get_by_file_id(file_id)
    if extracted is None:
        return {"note": f"File {file_id!r} has no extracted text (an image, archive or binary). Skip it."}
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


def _span(first: datetime | date | str | None, last: datetime | date | str | None) -> str | None:
    """`first → last` as days (months stay as given); a single value when both are the same."""
    days = [
        d.date().isoformat() if isinstance(d, datetime) else d if isinstance(d, str) else d.isoformat()
        for d in (first, last)
        if d
    ]
    return " → ".join(dict.fromkeys(days)) or None


def _day_range(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    """Inclusive days as UTC datetimes, `to` exclusive (the start of the day after `date_to`)."""
    start = datetime.combine(date_from, time.min, tzinfo=UTC) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC) if date_to else None
    return start, end


async def describe_data(ctx: RunContext[ChatDeps]) -> dict:
    """What this collection holds: kinds of files, what can't be searched, dates, people, places, mail flows.

    Dates are both when content was written or sent and when photos were taken.
    Call it first for broad questions ("what is this", "where do I start", "who matters") or when you
    don't yet know whether the data is mail, documents, photos or a mix. The collection may be one
    person's account, many mailboxes from a server, a hard drive or a document share -- describe it
    from these facts, never assume an owner. `notSearchable` lists files text search can't reach
    (no extracted text: archives, audio, images without OCR...).
    """
    profile = await ctx.deps.dataset_profiles.get_merged(dataset_ids=ctx.deps.dataset_ids)
    coverage, event_count = await ctx.deps.contents()
    photo_months, undated_photos = (
        await ctx.deps.images.capture_months(datasets=ctx.deps.dataset_ids)
        if await ctx.deps.file_count("image")
        else ([], 0)
    )
    months = sorted(profile.date_histogram, key=lambda bucket: -bucket.files)
    out: dict = {
        "files": {group.filetype_group: group.file_count for group in coverage},
        "notSearchable": [
            f"{group.file_count - group.searchable_count} of {group.file_count} {group.filetype_group} files"
            for group in coverage
            if group.searchable_count < group.file_count
        ],
        "contentDates": _span(
            *(
                (profile.date_histogram[0].month, profile.date_histogram[-1].month)
                if profile.date_histogram
                else (None, None)
            )
        ),
        "busiestMonths": [f"{bucket.month}: {bucket.files} files" for bucket in months[:6]],
        "events": event_count,
        "photosTaken": {
            "span": _span(photo_months[0].month, photo_months[-1].month),
            "busiestMonths": [f"{m.month}: {m.files}" for m in sorted(photo_months, key=lambda m: -m.files)[:6]],
            "withoutCaptureDate": undated_photos,
        }
        if photo_months
        else None,
        "topMailFlows": [f"{c.src_name} -> {c.dst_name}: {c.emails} emails" for c in profile.top_correspondents[:10]],
        "topPlaces": [f"{p.display_name} ({p.files} files)" for p in profile.top_places[:8]],
        "topIdentifiers": [f"{s.display_name} ({s.files} files)" for s in profile.top_selectors[:8]],
        "citations": [profile_entity_citation(entity) for entity in profile.top_people_orgs[:12]],
        "note": "People and orgs are ranked in `citations` (snippet = files mentioning them, promotions and spam excluded). "
        "Don't call anyone the owner; say whose data it appears to be only from evidence such as most mail "
        "being sent from one address. Mention what can't be searched if it matters to the question.",
    }
    if profile.unprofiled_dataset_ids:
        out["note"] += (
            f" {len(profile.unprofiled_dataset_ids)} dataset(s) have no profile yet, so the lists are partial."
        )
    return out


async def browse_folders(ctx: RunContext[ChatDeps], path: str | None = None) -> dict:
    """How the files are organised: the subfolders of `path`, largest first, with file kinds and dates.

    Paths start at the collection's top folder ("/"); where it was loaded from on disk is left out and
    says nothing about whose data it is. Leave `path` empty to start at the top. Folder names often
    say what a collection is (a mailbox per person, "Documents", "Taxes", a phone's DCIM, a trash
    folder). Go deeper by passing a folder's `path`; list or filter its files with
    `find_files(folder=...)`. Dates are the files' own timestamps, not when an email was sent.
    """
    current = await ctx.deps.absolute(path or "/")
    for _ in range(16):
        folders, folder_count, loose = await ctx.deps.files.folder_summary(
            dataset_ids=ctx.deps.dataset_ids, path=current
        )
        if path or folder_count != 1 or loose:
            break
        current = folders[0].path  # one lone subfolder: skip to where the collection actually branches
    out: dict = {
        "path": await ctx.deps.relative(current.rstrip("/") + "/"),
        "folders": [
            {
                "path": await ctx.deps.relative(folder.path),
                "files": folder.file_count,
                "kinds": folder.filetype_group_counts,
                "fileDates": _span(folder.date_first, folder.date_last),
            }
            for folder in folders
        ],
        "filesDirectlyHere": loose,
    }
    if folder_count > len(folders):
        out["note"] = f"Showing the {len(folders)} largest of {folder_count} folders."
    if not folders and not loose:
        out["note"] = "No files under that path. Start from the top with no `path`."
    return out


async def find_files(
    ctx: RunContext[ChatDeps],
    name: str | None = None,
    folder: str | None = None,
    filetype_group: str | None = None,
    extensions: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 15,
) -> dict:
    """Find files by what they are, not what they say: name, folder, kind or extension, and file date.

    - `name` -- text anywhere in the filename or folder path ("lease", "passport", "backup", "password").
    - `folder` -- only files under this folder (a path from `browse_folders`, starting at "/").
    - `filetype_group` -- e.g. "document", "email", "image", "table", "archive", "video", "audio", "code".
    - `extensions` -- e.g. ["xlsx", "csv"], ["kdbx"], ["pst", "ost"].
    - `date_from` / `date_to` -- the file's own timestamp (YYYY-MM-DD, inclusive).
    Returns how many match (`total`) and the newest as `citations` (`fileId` works with `read_file`
    when the file has text). To search what files say, use `search_passages`.
    """
    start, end = _day_range(date_from, date_to)
    files, total = await ctx.deps.files.find_files(
        dataset_ids=ctx.deps.dataset_ids,
        name=name.strip() if name else None,
        path_prefix=await ctx.deps.absolute(folder) if folder else None,
        filetype_groups=[filetype_group] if filetype_group else None,
        filetypes=[extension.lstrip(".") for extension in extensions] if extensions else None,
        date_from=start,
        date_to=end,
        limit=max(1, min(limit, 30)),
    )
    out: dict = {
        "total": total,
        "citations": [file_citation(file, path=await ctx.deps.relative(file.path)) for file in files],
    }
    if not files:
        out["note"] = "No files matched. Try a shorter name, another spelling, or drop a filter."
    return out


async def find_events(
    ctx: RunContext[ChatDeps],
    query: str | None = None,
    entity_ids: list[str] | None = None,
    names: list[str] | None = None,
    event_type: EventType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 15,
) -> dict:
    """Dated events extracted from the data (trips, bookings, meetings, gatherings, deliveries), in date order.

    For "what happened when", timelines, trips and who met whom. `query` matches words in the
    title; `entity_ids` / `names` keep events a person or org took part in; `event_type` is one of
    travel, lodging, reservation, meeting, gathering, delivery, other. Events were extracted by a
    model and are incomplete: back them up with `search_passages` and cite the source file (each
    citation's `fileId`).
    """
    start, end = _day_range(date_from, date_to)
    result = await ctx.deps.events.list_events(
        EventSearchParameters(
            dataset_ids=ctx.deps.dataset_ids,
            query=query or None,
            participant_entity_ids=await _entity_refs(ctx, entity_ids),
            participant_names=names or None,
            event_type=event_type,
            date_from=start,
            date_to=end,
            sort_order=SortOrder.ASC,
            limit=max(1, min(limit, 30)),
        )
    )
    out: dict = {"total": result.total, "citations": [event_citation(event) for event in result.data]}
    if not result.data:
        out["note"] = "No extracted events matched -- that doesn't mean nothing happened. Search the text too."
    return out


async def search_images(
    ctx: RunContext[ChatDeps],
    query: str,
    date_from: date | None = None,
    date_to: date | None = None,
    tags: list[str] | None = None,
    limit: int = 12,
) -> dict:
    """Find photos and images by what they show ("a boat", "a passport", "a receipt", "people at a beach").

    `query` describes the picture in plain English. Only images that clearly match come back, so an
    empty result means nothing looked like it. `date_from` / `date_to` filter on when the photo was
    taken; `tags` on labels an analyst or model gave. Each citation's snippet has its tags, camera
    and GPS when known.
    """
    start, end = _day_range(date_from, date_to)
    images = await images_matching_text(
        text=query,
        images=ctx.deps.images,
        image_model=ctx.deps.image_model,
        dataset_ids=ctx.deps.dataset_ids,
        date_from=start,
        date_to=end,
        tags=tags or None,
    )
    if images is None:
        return {"note": "Image search is unavailable right now (the image model isn't loaded)."}
    out: dict = {"total": len(images), "citations": [image_citation(image) for image in images[: max(1, limit)]]}
    if not images:
        out["note"] = "No image clearly showed that. Try a simpler description."
    return out


ALL_TOOLS = (
    describe_data,
    browse_folders,
    find_files,
    find_events,
    search_images,
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


async def ask_user(ctx: RunContext[ChatDeps], question: str, options: list[str]) -> dict:
    """Ask the user to pick one option (or type their own) and wait for the answer.

    When the answer would be wrong without their choice (two different people share the name
    and the results differ), or when a tool result says to check in. Otherwise answer with
    your best reading and say what you assumed. 2-5 short, concrete `options`; the user can
    always write something else. The result is `{"answer": "..."}`.
    """
    if not 2 <= len(options) <= 5:
        raise ModelRetry("Give 2-5 options.")
    raise CallDeferred
