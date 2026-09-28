"""Shared chunk-retrieval backend configuration (`RETRIEVAL__*`).

Lives here (not in the backend package) so orchestration workflows can read the
same config without depending on the API. See docs/retrieval-architecture.md.
"""

import os
from enum import StrEnum

from pydantic import BaseModel, Field


class RetrievalBackend(StrEnum):
    POSTGRES = "postgres"
    ELASTICSEARCH = "elasticsearch"


class TextRanker(StrEnum):
    """Keyword-ranking engine for the Postgres retrieval backend.

    `core` = built-in `tsvector` (+ `unaccent`), always available. `bigm` adds a
    `pg_bigm` bigram index for CJK/Farsi. `pgroonga` / `pg_search` are heavier
    extensions with near-BM25 multilingual ranking. A missing extension downgrades
    one rung -- see `GET /search/config`. `docs/postgres-extensions.md`.
    """

    CORE = "core"
    BIGM = "bigm"
    PGROONGA = "pgroonga"
    PG_SEARCH = "pg_search"


class RetrievalConfig(BaseModel):
    """Which store backs chunk search, and how. Populated from ``RETRIEVAL__*``."""

    backend: RetrievalBackend = Field(
        RetrievalBackend.POSTGRES,
        description="Store that answers keyword/semantic/entity/graph chunk search",
    )
    text_ranker: TextRanker = Field(
        TextRanker.PG_SEARCH,
        description="Keyword ranker for the postgres backend; ignored for elasticsearch. "
        "Default pg_search (ICU tokenizer, BM25) -- built into the ParadeDB image.",
    )
    graph_expand_entity_cap: int = Field(
        10_000, description="Max entities a graph_expand may fan out to before the filter is truncated"
    )


def load_retrieval_config() -> RetrievalConfig:
    """`RetrievalConfig` from ``RETRIEVAL__*`` env vars, for code with no `Settings` object."""
    return RetrievalConfig(
        backend=os.getenv("RETRIEVAL__BACKEND", RetrievalBackend.POSTGRES.value),
        text_ranker=os.getenv("RETRIEVAL__TEXT_RANKER", TextRanker.PG_SEARCH.value),
        graph_expand_entity_cap=int(os.getenv("RETRIEVAL__GRAPH_EXPAND_ENTITY_CAP", "10000")),
    )
