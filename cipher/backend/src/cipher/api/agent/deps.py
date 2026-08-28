"""Dependencies injected into every agent tool call."""

from dataclasses import dataclass

from clir.api.deps import AsyncTextEmbeddingModel

from cipher.datastores.elasticsearch.repositories.text_chunk import ElasticsearchTextChunkRepository
from cipher.datastores.postgres.repositories.dataset import PostgresDatasetRepository
from cipher.datastores.postgres.repositories.entity import PostgresEntityRepository
from cipher.datastores.postgres.repositories.entity_relationship import PostgresGraphRepository
from cipher.datastores.postgres.repositories.extracted_text import PostgresExtractedTextRepository
from cipher.datastores.postgres.repositories.mention import PostgresMentionRepository
from cipher.datastores.postgres.repositories.person import PostgresPersonRepository


@dataclass
class ChatDeps:
    """Everything the agent's tools need to answer a turn.

    `dataset_id` scopes retrieval to one dataset when the user picks one in the
    chat UI; it is required for the entity tools (entities are per-dataset) and
    an optional filter for chunk search.
    """

    chunks: ElasticsearchTextChunkRepository
    embedding_model: AsyncTextEmbeddingModel
    persons: PostgresPersonRepository
    datasets: PostgresDatasetRepository
    entities: PostgresEntityRepository
    mentions: PostgresMentionRepository
    graph: PostgresGraphRepository
    extracted_text: PostgresExtractedTextRepository
    dataset_id: str | None = None
