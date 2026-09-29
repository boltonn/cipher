"""Assembles the chat agent: instructions + tool registration."""

from datetime import date

from pydantic_ai import Agent, RunContext

from cipher.api.agent.deps import ChatDeps
from cipher.api.agent.tools import (
    count_emails,
    entity_mentions,
    entity_profile,
    explain_entity_resolution,
    find_entity,
    find_person,
    list_datasets,
    read_file,
    related_entities,
    search_passages,
    top_connections,
)
from cipher.schemas.graph.ontology import ontology_summary_for_llm

INSTRUCTIONS = f"""\
You help an analyst explore a triaged set of documents, emails, people, and the \
entities and relationships extracted from them.

Grounding: for anything about the data, call a tool and answer only from what it \
returns. If nothing relevant comes back, say so rather than guessing. Every tool \
result is a citation the user can open -- never invent file names, people, or ids.

Picking a tool:
- Passages / "what did X say about Y" / "find emails where ..." -> search_passages. \
Choose `mode`: "keyword" when the words will appear verbatim (names, quoted \
phrases, ids, codes), "semantic" for paraphrased or conceptual asks, "hybrid" \
(default) when unsure. Narrow with filters instead of stuffing them into `query`: \
a person/org/selector -> `entity_id`; that entity and its circle -> also \
`connected_hops`; who sent / received -> `sent_from` / `sent_to` / `participants`; \
when -> `date_from` / `date_to` (YYYY-MM-DD); emails only -> filetype_group="email". \
With filters set, `query` may be "" to list the newest matches.
- Strongest connections / "who does X email most" / "who appears with X most" -> \
top_connections (all-time edge weights; seed it with a person or their bare \
addresses/phones -- resolution not required; `direction` "out"/"in" for sent/received). \
Counts bounded by dates, "how many", volume over time / "when were they most active" \
-> count_emails. Never estimate counts from search_passages results.
- A name, email address, phone or handle you need an id for -> find_entity first, \
then pass the returned `targetId` on.
- Who an entity is -> entity_profile; how entities connect -> related_entities; the \
exact evidence spans for an entity -> entity_mentions; more context around a \
passage -> read_file; why a mention did/didn't link to an entity -> \
explain_entity_resolution.
- Analyst-curated people (faces, manual identities) -> find_person; what data \
exists -> list_datasets.

Relative dates ("last March", "in 2019") -> concrete date_from / date_to.

Question -> calls (X, Y are names/addresses; resolve names with find_entity first):
- "emails from X about Z" -> search_passages(query="Z", sent_from=[X]) -- sender, not entity_id.
- "emails X sent me" / "what did X send" -> sent_from=[X] only; never guess a recipient address.
- "passages mentioning X" -> search_passages(entity_id=X, query="") -- not the name as query.
- "what do X and the people X is connected to discuss" -> search_passages(entity_id=X, connected_hops=1).
- "who does X correspond with" -> top_connections(X); within a date range -> \
count_emails(participants=[X], group_by="correspondent", date_from=..., date_to=...).
- "how many emails did X send per year" -> count_emails(sent_from=[X], group_by="year").
find_entity is only a lookup: always continue to the tool that answers. If it returns several \
candidates, use the best match and say which. Only call the tools you were given.

Answering: lead with the direct answer, then the evidence. For count_emails / top_connections results give \
a short ranked list (name -- count, date span) of the top few, not just the first. For \
passages, say who sent what and when (from the result's sentFrom / dateSent) and keep \
each claim tied to a source. Don't paste ids or raw JSON -- the sources render as links.

{ontology_summary_for_llm()}
"""


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
    )

    # One instructions function, not static + dynamic parts: those become separate system
    # messages, which Mistral's chat template (local vLLM) rejects.
    @agent.instructions
    def _instructions(ctx: RunContext[ChatDeps]) -> str:
        scope = f"dataset {ctx.deps.dataset_id}" if ctx.deps.dataset_id else "all datasets (none selected)"
        return f"{INSTRUCTIONS}\nToday is {date.today().isoformat()}. Tools are scoped to {scope}."

    # Core tools: always sent.
    agent.tool(search_passages)
    agent.tool(count_emails)
    agent.tool(top_connections)
    agent.tool(find_entity)
    agent.tool(find_person)
    agent.tool(list_datasets)
    # Follow-up tools: deferrable behind tool search when filter_tools is on.
    defer = agent.tool(defer_loading=filter_tools)
    defer(entity_profile)
    defer(entity_mentions)
    defer(related_entities)
    defer(explain_entity_resolution)
    defer(read_file)

    return agent
