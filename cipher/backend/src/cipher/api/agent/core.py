"""Assembles the chat agent: instructions + tool registration."""

import functools
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import date
from typing import Any

from loguru import logger
from pydantic_ai import Agent, CallDeferred, ModelRetry, RunContext
from pydantic_ai.capabilities import PrepareTools, ProcessHistory
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ThinkingPart, ToolReturnPart
from pydantic_ai.tools import ToolDefinition, ToolPrepareFunc

from cipher.api.agent.deps import ChatDeps
from cipher.api.agent.tools import (
    STOP_REPEATING,
    ask_user,
    awaiting_check_in,
    browse_folders,
    count_emails,
    describe_data,
    entity_mentions,
    entity_profile,
    explain_entity_resolution,
    find_entity,
    find_events,
    find_files,
    find_person,
    list_datasets,
    propose_entity_merge,
    propose_selector_links,
    read_file,
    related_entities,
    search_images,
    search_passages,
    top_connections,
)
from cipher.schemas.graph.ontology import ontology_summary_for_llm
from cipher.schemas.interaction.chat import ChatAutonomy

INSTRUCTIONS = f"""\
You help an analyst triage a collection of data: one person's mailbox, a mail server with many \
mailboxes, a hard drive, a document share, phone photos, or a mix. Never assume whose data it is \
and never call anyone its "owner" or "custodian". Say whose data it appears to be only from evidence \
in the files (most mail sent from one address, a home folder inside it), as what that evidence suggests.

Grounding: for anything about the data, call a tool and answer only from what it \
returns. If nothing relevant comes back, say so rather than guessing. Every tool \
result is a citation the user can open -- never invent file names, people, or ids.

Most data is NOT tagged and its people are NOT fully resolved, so text is your main evidence: \
search it, read it, reason over it. Work like an analyst:
1. Orient when the question is broad ("what is this", "where do I start", "who matters") or you \
don't know what the data holds: describe_data, and browse_folders for how files are organised.
2. Who/what is it about? For a person, org, address or phone, call find_entity once. Resolved \
or not, you can now filter by `entity_ids` (the best match) and/or `names` (its \
`nameGroup.value`, the name as written). Missing resolution never blocks a search.
3. Search the content with search_passages. `query` = words that would appear in or near the \
answer -- the topic and its synonyms, never just the person's name (people go in filters). \
Search more than one angle before concluding: different wordings ("loan", "owe", "pay back", \
"borrowed"), mode "keyword" for exact words / names / codes, "semantic" for the \
idea, "hybrid" when unsure. An empty `query` browses what the filters match, newest first. A \
person filter only keeps text that names them or mail from/to their known addresses, and \
resolution is usually incomplete -- so also run the topic search without it and judge from the \
text who it involves. Other evidence: files by name, folder or type -> find_files; dated \
events -> find_events; photos -> search_images.
4. Read: snippets are excerpts. Before answering, read_file the hits that look most relevant \
when the snippet doesn't settle it, and follow leads (a new name -> search it).
5. Structure: who connects to whom, how often, how many -> top_connections / count_emails / \
related_entities (never estimate counts from search results). These also give leads to search on.
6. Stop when the evidence answers the question; never repeat an identical search.

Use the filters the question implies (people, senders, dates -- turn "last March" into \
YYYY-MM-DD). Only call the tools you were given.

Identities: find_entity's `otherAddresses` are addresses used under that name that don't \
belong to the best match (unlinked, or linked to someone else). Answer first, then list them \
and offer to include them; flag any linked to a different person as a possible resolution \
error. Besides the check-ins below, call ask_user only when the answer depends on a choice you can't \
make from the data (two different people behind one name, say); never just to confirm. When the user confirms, \
pass the chosen addresses' `entityId`s alongside the entity (entity_ids / sent_from / sent_to) \
-- for this conversation only. To make it permanent, or when the user says an address is \
wrongly linked, call propose_selector_links; when the user states which addresses are whose, \
look the owner up and propose exactly those -- don't ask again. When the user says two \
entities are the same, look both up and call propose_entity_merge. Both only propose: never \
claim anything was linked, moved, merged or fixed.

Answering: lead with the direct answer, then the evidence. For count_emails / top_connections \
results give a short ranked list (name -- count, date span) of the top few, not just the first. \
For passages, synthesize: group what was said into a few themes in prose, attributing briefly \
inline ("Ed Bolton, Feb 2016"). Keep what a file states apart from what you infer: a booking or \
a first-hand account shows something happened; an advert, newsletter or invitation does not -- \
say "suggests" when you infer. If something relevant couldn't be searched (describe_data's \
`notSearchable`), say so. Never list per-email metadata fields (subject/snippet/sent \
from/sent to/date), email addresses, ids, URLs or raw JSON -- sources and review buttons \
render below your answer as links.

{ontology_summary_for_llm()}
"""


_GUIDED = (
    "Check-ins (the analyst steers this triage): when a broad question's search matches more than ~50 files, "
    "call ask_user before reading through them, offering 2-4 concrete next steps drawn from the results -- e.g. "
    "read the top 10, narrow to a period / person / folder you saw in them, or open the full list (the analyst "
    "can open any search in full below your answer). Also ask before proposing changes to more than 3 items. "
    "Otherwise proceed and say what you assumed."
)
_AUTO = "The analyst wants answers without check-ins: proceed on your best reading and say what you assumed."


def _steering(deps: ChatDeps) -> str:
    """How much to check in, and which earlier sources the analyst judged relevant or not."""
    lines = [_GUIDED if deps.autonomy == ChatAutonomy.GUIDED else _AUTO]
    if feedback := deps.relevance:
        if feedback.relevant:
            lines.append(
                "The analyst marked these earlier sources RELEVANT -- build on them, look for more like them: "
                + "; ".join(source.display_name for source in feedback.relevant)
            )
        if feedback.not_relevant:
            lines.append(
                "The analyst marked these earlier sources NOT RELEVANT -- don't rely on them or cite them again: "
                + "; ".join(source.display_name for source in feedback.not_relevant)
            )
    return "\n".join(lines)


# Tool results + this turn's reasoning: ~13k tokens at the ~2.3 chars/token measured on id-heavy JSON
# (entity profiles). The local model's 24k window also holds ~6.5-7.5k of prompt + tool schemas and each
# step's thinking (capped at 1k) + answer.
_CONTEXT_BUDGET_CHARS = 30_000
_KEPT_THINKING_STEPS = 2
# Card-only citation fields: the model reasons over the passage and ids, not ranking scores or links.
_UI_ONLY_KEYS = frozenset({"score", "chunkId", "filetypeGroup", "headingPath", "href", "openAll"})
_MAX_RECIPIENTS = 3
_ELIDED = (
    "[Earlier result omitted to save context; the user still sees its sources. Don't re-run it: rely on what "
    "you concluded from it, or read_file a specific hit.]"
)


def _compact(value: Any) -> Any:
    """A tool result as the model needs it: citations without card-only fields or long recipient lists."""
    if isinstance(value, list):
        return [_compact(item) for item in value]
    if not isinstance(value, dict):
        return value
    out = {key: _compact(item) for key, item in value.items() if key not in _UI_ONLY_KEYS}
    if isinstance(recipients := out.get("sentTo"), list) and len(recipients) > _MAX_RECIPIENTS:
        out["sentTo"] = [*recipients[:_MAX_RECIPIENTS], f"+{len(recipients) - _MAX_RECIPIENTS} more"]
    return out


def fit_context(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Shrink what the model sees so a long tool loop stays inside a small model's context window.

    Compacts every tool result, keeps only the latest steps' reasoning, then replaces the oldest tool
    results with a stub until the rest fits. Citations already streamed to the user are untouched.
    """
    thinking_steps = [
        m for m in messages if isinstance(m, ModelResponse) and any(isinstance(p, ThinkingPart) for p in m.parts)
    ]
    stale_thinking = {id(m) for m in thinking_steps[:-_KEPT_THINKING_STEPS]}
    messages = [
        replace(
            m, parts=[replace(p, content=_compact(p.content)) if isinstance(p, ToolReturnPart) else p for p in m.parts]
        )
        if isinstance(m, ModelRequest)
        else replace(m, parts=[p for p in m.parts if not isinstance(p, ThinkingPart)])
        if id(m) in stale_thinking
        else m
        for m in messages
    ]

    returns = [p for m in messages if isinstance(m, ModelRequest) for p in m.parts if isinstance(p, ToolReturnPart)]
    thinking = [p for m in messages if isinstance(m, ModelResponse) for p in m.parts if isinstance(p, ThinkingPart)]
    total = sum(len(p.model_response_str()) for p in returns) + sum(len(p.content) for p in thinking)
    elided: set[int] = set()
    for part in returns[:-1]:
        if total <= _CONTEXT_BUDGET_CHARS:
            break
        total -= len(part.model_response_str()) - len(_ELIDED)
        elided.add(id(part))
    if not elided:
        return messages
    return [
        replace(m, parts=[replace(p, content=_ELIDED) if id(p) in elided else p for p in m.parts])
        if isinstance(m, ModelRequest)
        else m
        for m in messages
    ]


async def _unless_looping(ctx: RunContext[ChatDeps], tool_def: ToolDefinition) -> ToolDefinition | None:
    """Withdraw a tool the model keeps re-calling identically after being told to stop -- it must answer instead."""
    stops = sum(
        isinstance(part, ToolReturnPart) and part.tool_name == tool_def.name and STOP_REPEATING in str(part.content)
        for message in ctx.messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )
    return None if stops >= 2 else tool_def


def _resilient[**P](tool: Callable[P, Awaitable[Any]]) -> Callable[P, Awaitable[Any]]:
    """A tool that reports an unexpected failure to the model instead of ending the analyst's whole turn."""

    @functools.wraps(tool)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        try:
            return await tool(*args, **kwargs)
        except (ModelRetry, CallDeferred):
            raise
        except Exception as exc:  # noqa: BLE001 -- logged; the model answers from what it has
            logger.exception(f"Chat tool {tool.__name__} failed")
            return {
                "note": f"{tool.__name__} failed ({type(exc).__name__}). Use another tool or answer from what you have."
            }
        finally:
            ctx = next((arg for arg in args if isinstance(arg, RunContext)), None)
            if ctx is not None:
                await ctx.deps.release()

    return wrapper


async def _without_type_docs(ctx: RunContext[ChatDeps], tool_defs: list[ToolDefinition]) -> list[ToolDefinition]:
    """Drop enum/model class docstrings from tool schemas: the model needs the allowed values, not why they exist."""
    return [
        replace(
            tool_def,
            parameters_json_schema={
                **tool_def.parameters_json_schema,
                "$defs": {
                    name: {key: value for key, value in schema.items() if key != "description"}
                    for name, schema in tool_def.parameters_json_schema["$defs"].items()
                },
            },
        )
        if "$defs" in tool_def.parameters_json_schema
        else tool_def
        for tool_def in tool_defs
    ]


def _paused_for_check_in(then: ToolPrepareFunc[ChatDeps] | None) -> ToolPrepareFunc[ChatDeps]:
    """Hold every tool but ask_user while a guided check-in waits for the analyst, then apply `then`."""

    async def prepare(ctx: RunContext[ChatDeps], tool_def: ToolDefinition) -> ToolDefinition | None:
        if tool_def.name != "ask_user" and awaiting_check_in(ctx):
            return None
        return await then(ctx, tool_def) if then else tool_def

    return prepare


def _only_if(holds: Callable[[ChatDeps], Awaitable[bool]]) -> ToolPrepareFunc[ChatDeps]:
    """Offer a tool only when the chat's data has something for it (no email tools for a hard drive of photos)."""

    async def prepare(ctx: RunContext[ChatDeps], tool_def: ToolDefinition) -> ToolDefinition | None:
        return tool_def if await holds(ctx.deps) else None

    return prepare


async def _has_email(deps: ChatDeps) -> bool:
    return await deps.file_count("email") > 0


async def _has_images(deps: ChatDeps) -> bool:
    return await deps.file_count("image") > 0


async def _has_events(deps: ChatDeps) -> bool:
    return (await deps.contents())[1] > 0


async def _after_an_entity(ctx: RunContext[ChatDeps], tool_def: ToolDefinition) -> ToolDefinition | None:
    """Offer the entity follow-up tools once a lookup has returned an entity id to follow up on."""
    found = any(
        isinstance(part, ToolReturnPart) and '"targetId"' in part.model_response_str()
        for message in ctx.messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )
    return tool_def if found else None


def build_agent(*, filter_tools: bool = False) -> Agent[ChatDeps, str]:
    """Construct the chat agent.

    `filter_tools` hides the follow-up entity/graph/read tools behind pydantic-ai's built-in
    tool search (`defer_loading=True`) instead of sending every schema up front --
    for a context-constrained model. A deferred tool is still reachable: the model
    calls the framework's own tool search to discover it, at the cost of one round
    trip. Off by default; search, counting and entity lookup are always sent.
    """
    agent: Agent[ChatDeps, str] = Agent(
        # "openai-chat:" (not bare "openai:") keeps this on the Chat Completions API;
        # pydantic-ai routes a bare "openai:" model to the Responses API instead.
        "openai-chat:gpt-4o-mini",
        deps_type=ChatDeps,
        defer_model_check=True,
        # Smaller models occasionally return an empty turn or a bad tool arg; give them a few tries.
        retries=3,
        capabilities=[ProcessHistory(processor=fit_context), PrepareTools(_without_type_docs)],
    )

    # One instructions function, not static + dynamic parts: those become separate system
    # messages, which Mistral's chat template (local vLLM) rejects.
    @agent.instructions
    def _instructions(ctx: RunContext[ChatDeps]) -> str:
        ids = ctx.deps.access.dataset_ids
        scope = "every dataset" if ids is None else f"the {len(ids)} dataset(s) picked for this chat"
        return (
            f"{INSTRUCTIONS}\n{_steering(ctx.deps)}\nToday is {date.today().isoformat()}. Passages, files, "
            f"mentions and email counts come only from {scope}; nothing outside them exists for this conversation."
        )

    # Tools share ChatDeps' repositories (one DB session each), and an AsyncSession can't
    # run two queries at once -- so when the model asks for several calls in one turn,
    # run them one after another rather than in parallel.
    def register(
        tool: Callable[..., Awaitable[Any]], prepare: ToolPrepareFunc[ChatDeps] | None = None, **options: Any
    ) -> None:
        agent.tool(sequential=True, prepare=_paused_for_check_in(prepare), **options)(_resilient(tool))

    register(describe_data)
    register(browse_folders)
    register(find_files)
    register(search_passages, prepare=_unless_looping)
    register(count_emails, prepare=_only_if(_has_email))
    register(find_events, prepare=_only_if(_has_events))
    register(search_images, prepare=_only_if(_has_images))
    for tool in (top_connections, find_entity, find_person, list_datasets, ask_user, read_file):
        register(tool)
    # Follow-up tools, offered once an entity has turned up; deferrable behind tool search too.
    for tool in (
        entity_profile,
        entity_mentions,
        related_entities,
        explain_entity_resolution,
        propose_selector_links,
        propose_entity_merge,
    ):
        register(tool, defer_loading=filter_tools, prepare=_after_an_entity)

    return agent
