"""Assembles the chat agent: instructions + tool registration."""

from pydantic_ai import Agent

from cipher.api.agent.deps import ChatDeps
from cipher.api.agent.tools import (
    entity_mentions,
    entity_profile,
    find_entity,
    find_person,
    list_datasets,
    read_file,
    related_entities,
    search_hybrid,
    search_semantic,
    search_text,
)
from cipher.schemas.graph.ontology import ontology_summary_for_llm

INSTRUCTIONS = f"""\
You help an analyst explore a triaged set of documents, emails, people, and the \
entities and relationships extracted from them.

Grounding: for anything about the data, call a tool and answer only from what it \
returns. If nothing relevant comes back, say so rather than guessing. Every tool \
result is a citation the user can open -- never invent file names, people, or ids.

Choosing a retrieval tool:
- search_text -- keyword/BM25. Verbatim terms: names, quoted phrases, identifiers, \
error strings.
- search_semantic -- vector/meaning. Conceptual questions where the wording won't \
match ("concerns about the timeline").
- search_hybrid -- both, fused. The default when you have no specific reason to \
prefer one.

People and datasets:
- find_person -- the analyst-curated Person table (faces, manual identities). Links \
to a profile page.
- list_datasets -- what data exists; also use it to help the user scope the chat to \
a dataset.

Entities and the knowledge graph (need a selected dataset):
- find_entity -- resolve a name or a strong identifier (phone/email/passport/handle) \
to entity ids.
- entity_profile -- the full dossier for an entity id.
- entity_mentions -- the evidence passages naming an entity, as openable citations.
- related_entities -- traverse the graph: who communicates with whom, who works for \
whom, who shares an identifier. Use relationship_type to focus (communicates_with \
for email/call links, employed_by / member_of for affiliation).
- read_file -- pull the fuller context around a passage after a search or mention.

{ontology_summary_for_llm()}
"""


def build_agent(*, filter_tools: bool = False) -> Agent[ChatDeps, str]:
    """Construct the chat agent.

    `filter_tools` hides the graph/entity/read tools behind pydantic-ai's built-in
    tool search (`defer_loading=True`) instead of sending every schema up front --
    for a context-constrained model. A deferred tool is still reachable: the model
    calls the framework's own tool search to discover it, at the cost of one round
    trip. Off by default; the retrieval tools are always sent.
    """
    agent: Agent[ChatDeps, str] = Agent(
        # "openai-chat:" (not bare "openai:") keeps this on the Chat Completions API;
        # pydantic-ai routes a bare "openai:" model to the Responses API instead.
        "openai-chat:gpt-4o-mini",
        deps_type=ChatDeps,
        instructions=INSTRUCTIONS,
        defer_model_check=True,
    )

    # Retrieval tools: always sent.
    agent.tool(search_hybrid)
    agent.tool(search_text)
    agent.tool(search_semantic)
    agent.tool(find_person)
    agent.tool(list_datasets)
    # Graph/entity/read tools: deferrable behind tool search when filter_tools is on.
    defer = agent.tool(defer_loading=filter_tools)
    defer(find_entity)
    defer(entity_profile)
    defer(entity_mentions)
    defer(related_entities)
    defer(read_file)

    return agent
