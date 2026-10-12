"""AI on the search page, from the backend's default LLM (`LLM__*`): never in front of the results.

- `assist`: a short answer grounded in the search's top passages (questions only), and a narrower
  search read out of the wording (dates, file types, names) -- offered, never applied.
- `brief`: a few sentences on a dataset profile plus starting searches.

See docs/global-search.md §5.2 and §8.
"""

import re
from datetime import UTC, date, datetime

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.settings import ModelSettings

from cipher.api.agent import build_model, resolve_llm_settings
from cipher.api.services.global_search import plan_query, read_query_filters
from cipher.api.settings import Settings
from cipher.datastores.postgres.repositories.entity import PostgresEntityRepository
from cipher.datastores.postgres.repositories.mention import PostgresMentionRepository
from cipher.names import (
    AddressAgreement,
    Level,
    address_name_agreement,
    canonical_forms,
    compare_names,
    fold,
    is_role_address,
)
from cipher.schemas.content.results import FileSearchResult
from cipher.schemas.graph.entity import EntitySearchResult
from cipher.schemas.graph.ontology import EntityType
from cipher.schemas.ingestion.dataset_profile import DatasetProfile
from cipher.schemas.interaction.global_search import (
    AssistCitation,
    DatasetBrief,
    NameChoice,
    NameOption,
    QueryKind,
    SearchAssist,
    SearchSuggestion,
)
from cipher.schemas.interaction.llm import LLMProvider
from cipher.schemas.interaction.search_record import SearchFilters, SearchRecord, SearchRequest

settings = Settings()

PASSAGES = 8
PASSAGE_CHARS = 900
NAME_MATCH = 0.6
NAME_CANDIDATES = 25
PEOPLE_OPTIONS = 8
_GIVEN_AGREES = {"exact", "nickname", "initial", "phonetic"}
_POSSESSIVE = re.compile(r"['’]s$")


class _Reading(BaseModel):
    """What the model reads out of one search; dates, file types and the topic are read by rules instead."""

    answer: str | None = Field(
        default=None,
        description="2-4 plain sentences answering the question using ONLY the numbered passages, citing them "
        "like [2]. Null when the query is not a question or the passages don't answer it.",
    )
    cited_passages: list[int] = Field(default_factory=list, description="Numbers of the passages the answer uses")
    names: list[str] = Field(
        default_factory=list,
        description="People or organizations named in the SEARCH TEXT, copied exactly as written there",
    )
    is_visual: bool = Field(
        default=False,
        description="True when the search is about what something LOOKS like and would be found in photos "
        "(an animal, object, scene, event like a wedding, a place's appearance); false for names, topics, "
        "questions about what was written, dates or identifiers",
    )


_MARKUP = re.compile(r"</?[a-z_]+[^>]*>", re.I)


class _Brief(BaseModel):
    summary: str = Field(
        description="3 short plain sentences: what this collection is, who is central, when and where; no lists of "
        "email addresses"
    )
    suggested_searches: list[str] = Field(
        description="3-5 short searches an analyst could start triage with, in plain words as a person would type "
        "them (a name, an email address, or a topic) -- no OR/AND operators, quotes or date codes"
    )

    @field_validator("summary")
    @classmethod
    def _drop_leaked_markup(cls, summary: str) -> str:
        """Local models sometimes run the next tool argument into the text (`</summary> <parameter ...>`)."""
        return _MARKUP.split(summary, maxsplit=1)[0].strip()


_READ_INSTRUCTIONS = (
    "You help an analyst triage an unknown collection of files. You get their search and the top passages it "
    "found. `answer` and `cited_passages` come from the passages only -- never outside knowledge. `names` come "
    "from the search text only -- never from the passages. `is_visual` is about the search text alone: true "
    "when the thing searched for is something a photo would show (cats, a beach, a wedding, a red car), false "
    "for people's names, written topics, questions about what was said, dates and identifiers."
)
_BRIEF_INSTRUCTIONS = (
    "You summarize what is in a collection of files from statistics about it, for an analyst who has never seen "
    "it. Be concrete and neutral; only state what the statistics show."
)
_reader = Agent(output_type=_Reading, instructions=_READ_INSTRUCTIONS)
_briefer = Agent(output_type=_Brief, instructions=_BRIEF_INSTRUCTIONS)


async def _run[T](agent: Agent[None, T], prompt: str, output_type: type[T]) -> tuple[T, str]:
    """Run a one-shot structured call; local models get JSON-schema decoding instead of tool calls.

    vLLM's Qwen tool-call parser can leak markup (`</summary> <parameter ...>`) into string fields;
    constrained JSON output can't.
    """
    llm = resolve_llm_settings(settings.llm, None)
    model_settings = ModelSettings(temperature=0)
    output = output_type
    if llm.provider == LLMProvider.LOCAL:
        # Thinking models (Qwen3) otherwise reason for seconds before a short structured reply.
        model_settings["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        output = NativeOutput(output_type)
    result = await agent.run(prompt, model=build_model(llm), model_settings=model_settings, output_type=output)
    return result.output, f"{llm.provider}:{llm.model}"


def _passages(results: list[FileSearchResult]) -> list[tuple[FileSearchResult, object]]:
    """The best chunk of each top file, best first."""
    passages = []
    for result in results[:PASSAGES]:
        top = next((chunk for chunk in result.chunks if chunk.id == result.top_chunk_id), result.chunks[0])
        passages.append((result, top))
    return passages


def _content_date(chunk) -> datetime:
    """When it was sent / written -- not when it was ingested."""
    return getattr(chunk, "date_sent", None) or chunk.date_created


def _title(chunk) -> str:
    if title := getattr(chunk, "title", None) or getattr(chunk, "filename", None):
        return title
    sender = getattr(chunk, "sent_from", None) or getattr(chunk, "sender", None)
    who = f" from {sender.name or sender.value}" if sender else ""
    return f"Email{who}, {_content_date(chunk):%-d %b %Y}"


async def assist(
    *,
    record: SearchRecord,
    results: list[FileSearchResult],
    entities: PostgresEntityRepository,
    mentions: PostgresMentionRepository,
) -> SearchAssist:
    """Answer (if a question) and suggest a narrower search, from the search's own top passages."""
    passages = _passages(results)
    plan = plan_query(record.query)
    numbered = "\n\n".join(
        f"[{index}] {_title(chunk)} ({_content_date(chunk):%Y-%m-%d})\n{chunk.text[:PASSAGE_CHARS]}"
        for index, (_, chunk) in enumerate(passages, start=1)
    )
    prompt = (
        f"Today is {datetime.now(UTC):%Y-%m-%d}.\nSearch: {record.query!r}\n"
        f"Is it a question: {'yes' if plan.is_question else 'no'}\n"
        "Would the thing it searches for show up in photos (is_visual)?\n\n"
        f"Passages:\n{numbered or '(none)'}"
    )
    reading, model_name = await _run(_reader, prompt, _Reading)

    citations = [
        AssistCitation(number=number, file_id=result.file_id, chunk_id=chunk.id, title=_title(chunk))
        for number in dict.fromkeys(reading.cited_passages)
        if 1 <= number <= len(passages)
        for result, chunk in [passages[number - 1]]
    ]
    typed = [name for name in dict.fromkeys(reading.names) if name.lower() in record.query.lower()]
    dataset_id = record.dataset_ids[0] if len(record.dataset_ids) == 1 else None
    choices = [
        choice
        for name in typed
        if (choice := await name_choice(name=name, dataset_id=dataset_id, entities=entities, mentions=mentions))
    ]
    return SearchAssist(
        answer=reading.answer if plan.is_question and reading.answer else None,
        citations=citations if plan.is_question and reading.answer else [],
        suggestion=_suggestion(record, typed, choices),
        is_visual=reading.is_visual and plan.kind != QueryKind.SELECTOR,
        name_choices=[choice for choice in choices if len(choice.options) > 1],
        model=model_name,
    )


def _spellings(name: str) -> list[str]:
    """The name plus its given-name nickname forms: `nick bolton` -> also `nicholas bolton`."""
    first, _, rest = name.strip().partition(" ")
    return list(dict.fromkeys([name, *(f"{form} {rest}".strip() for form in canonical_forms(first))]))


async def name_choice(
    *, name: str, dataset_id: str | None, entities: PostgresEntityRepository, mentions: PostgresMentionRepository
) -> NameChoice | None:
    """What a typed name could mean, with the very likely ones ticked.

    Ticked: the one canonical person the name fits (nicknames count) and auto-created spellings that look
    like them -- or, with no canonical person, spellings that match a full name outright -- plus addresses
    those own and unlinked addresses that spell the name. Offered unticked: other people and spellings whose
    given name agrees, and other header addresses seen under the name. The user decides; nothing is linked.
    """
    hits: dict[str, EntitySearchResult] = {}
    for spelling in _spellings(name):
        for hit in await entities.search_by_name(
            dataset_id=None, query=spelling, limit=NAME_CANDIDATES, entity_type=EntityType.PERSON
        ):
            hits.setdefault(hit.id, hit)
    people = []
    for hit in hits.values():
        comparison = compare_names(name, hit.display_name)
        if comparison.level >= Level.STRONG or comparison.components.get("given") in _GIVEN_AGREES:
            people.append((hit, comparison.level))
    best_level = max((level for hit, level in people if not hit.is_provisional), default=None)
    leaders = [hit for hit, level in people if not hit.is_provisional and level == best_level]
    anchor = leaders[0] if len(leaders) == 1 else None

    full_name = len(name.split()) > 1

    def looks_like_anchor(hit: EntitySearchResult) -> bool:
        if anchor is None:
            return full_name and compare_names(name, hit.display_name).level >= Level.STRONG
        return hit.id == anchor.id or compare_names(anchor.display_name, hit.display_name).level >= Level.STRONG

    spellings: dict[str, NameOption] = {}
    ranked = sorted(
        people,
        key=lambda pair: (not looks_like_anchor(pair[0]), pair[0].is_provisional, -pair[1], -pair[0].score),
    )
    for hit, _ in ranked:
        option = spellings.setdefault(
            _POSSESSIVE.sub("", fold(hit.display_name)),
            NameOption(
                entity_ids=[],
                display_name=hit.display_name,
                entity_type=EntityType.PERSON,
                is_provisional=True,
                detail="auto-created spelling",
            ),
        )
        option.entity_ids.append(hit.id)
        option.is_suggested = option.is_suggested or looks_like_anchor(hit)
        if not hit.is_provisional:
            option.display_name, option.is_provisional, option.detail = hit.display_name, False, None
    options = list(spellings.values())[:PEOPLE_OPTIONS]

    ticked = {
        entity_id: option.display_name for option in options if option.is_suggested for entity_id in option.entity_ids
    }
    owned = {
        selector_id: (address, ticked[owner_id])
        for owner_id, selector_id, address in await entities.owned_selectors(list(ticked))
    }
    options += [
        NameOption(
            entity_ids=[selector_id],
            display_name=address,
            entity_type=EntityType.SELECTOR,
            detail=f"{owner}'s address",
            is_suggested=True,
        )
        for selector_id, (address, owner) in owned.items()
    ]
    owner_names = [name, *([anchor.display_name] if anchor else [])]
    for row in await mentions.header_addresses_for_name(
        name=name, dataset_id=dataset_id, exclude_owner=anchor.id if anchor else None
    ):
        agreement = address_name_agreement(row["address"], owner_names)
        if row["entityId"] in owned or is_role_address(row["address"]) or agreement == AddressAgreement.CONFLICT:
            continue
        options.append(
            NameOption(
                entity_ids=[row["entityId"]],
                display_name=row["address"],
                entity_type=EntityType.SELECTOR,
                detail=f"{row['emailCount']} emails · "
                + (f"linked to {row['linkedTo']}" if row["linkedTo"] else "not linked to anyone"),
                is_suggested=not row["linkedTo"] and agreement == AddressAgreement.MATCH,
            )
        )
    return NameChoice(name=name, options=options) if options else None


def _suggestion(record: SearchRecord, names: list[str], choices: list[NameChoice]) -> SearchSuggestion | None:
    """The narrower search the wording implies (rules for dates/file types, the ticked name options), if it adds anything."""
    if plan_query(record.query).kind == QueryKind.IMAGE:
        return None
    filters = record.filters
    entity_groups, labels = list(filters.entity_groups), []
    for choice in choices:
        ticked = [option for option in choice.options if option.is_suggested]
        group = [entity_id for option in ticked for entity_id in option.entity_ids]
        if group and group not in entity_groups:
            entity_groups.append(group)
            labels.append(ticked[0].display_name)
    read = read_query_filters(record.query, today=datetime.now(UTC).date(), names=names)
    groups = sorted(set(filters.filetype_groups) | set(read.filetype_groups))
    narrowed = SearchFilters(
        entity_ids=filters.entity_ids,
        entity_groups=entity_groups,
        filetype_groups=groups,
        date_from=read.date_from or filters.date_from,
        date_to=read.date_to or filters.date_to,
    )
    query = read.topic
    if narrowed == filters:
        return None
    parts = [*[group for group in groups if group not in filters.filetype_groups], *labels]
    if narrowed.date_from != filters.date_from or narrowed.date_to != filters.date_to:
        parts.append(_date_label(narrowed.date_from, narrowed.date_to))
    parts.insert(0, f"“{query}”" if query else "everything")
    return SearchSuggestion(
        label=" · ".join(parts),
        request=SearchRequest(query=query, dataset_ids=record.dataset_ids, filters=narrowed, parent_id=record.id),
    )


def _date_label(start: date | None, end: date | None) -> str:
    if start and end:
        return f"{start:%-d %b %Y} – {end:%-d %b %Y}"
    return f"from {start:%-d %b %Y}" if start else f"until {end:%-d %b %Y}"


def _names(entities) -> str:
    return ", ".join(f"{entity.display_name} ({entity.files})" for entity in entities[:10])


async def brief(profile: DatasetProfile) -> DatasetBrief:
    """A short read of a dataset profile, plus starting searches."""
    busiest = sorted(profile.date_histogram, key=lambda bucket: -bucket.files)[:3]
    stats = "\n".join(
        [
            f"Files: {profile.file_count} -- by kind: {profile.filetype_group_counts}",
            f"Dated from {profile.date_histogram[0].month if profile.date_histogram else '?'} to "
            f"{profile.date_histogram[-1].month if profile.date_histogram else '?'}; busiest months: "
            + ", ".join(f"{bucket.month} ({bucket.files})" for bucket in busiest),
            f"People/organizations mentioned in the most (non-newsletter) files: {_names(profile.top_people_orgs)}",
            f"Most frequent identifiers (emails, phones, domains): {_names(profile.top_selectors)}",
            f"Places: {_names(profile.top_places)}",
            "Who emails whom most: "
            + ", ".join(
                f"{edge.src_name} -> {edge.dst_name} ({edge.emails})" for edge in profile.top_correspondents[:5]
            ),
        ]
    )
    result, model_name = await _run(_briefer, stats, _Brief)
    return DatasetBrief(summary=result.summary, suggested_searches=result.suggested_searches[:5], model=model_name)
