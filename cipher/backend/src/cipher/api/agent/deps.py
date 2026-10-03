"""Dependencies injected into every agent tool call."""

from dataclasses import dataclass

from clir.api.deps import AsyncTextEmbeddingModel

from cipher.api.deps.access import DatasetAccess
from cipher.datastores.base.retrieval import ChunkRetrievalRepository
from cipher.datastores.postgres.repositories.dataset import PostgresDatasetRepository
from cipher.datastores.postgres.repositories.entity import PostgresEntityRepository
from cipher.datastores.postgres.repositories.entity_match import PostgresEntityMatchRepository
from cipher.datastores.postgres.repositories.entity_relationship import PostgresGraphRepository
from cipher.datastores.postgres.repositories.extracted_text import PostgresExtractedTextRepository
from cipher.datastores.postgres.repositories.file import PostgresFileRepository
from cipher.datastores.postgres.repositories.mention import PostgresMentionRepository
from cipher.datastores.postgres.repositories.person import PostgresPersonRepository


@dataclass
class ChatDeps:
    """Everything the agent's tools need to answer a turn.

    `access` is the chat's dataset scope, fixed server-side for the whole request: the
    user's access narrowed to the datasets picked in the chat UI (all of theirs when none
    are). Every tool that returns dataset content -- passages, file text, mentions, email
    counts -- reads only those datasets; the tools never take a dataset from the model.
    The entity graph is shared and stays open.
    """

    access: DatasetAccess
    chunks: ChunkRetrievalRepository
    embedding_model: AsyncTextEmbeddingModel
    persons: PostgresPersonRepository
    datasets: PostgresDatasetRepository
    files: PostgresFileRepository
    entities: PostgresEntityRepository
    entity_matches: PostgresEntityMatchRepository
    mentions: PostgresMentionRepository
    graph: PostgresGraphRepository
    extracted_text: PostgresExtractedTextRepository

    @property
    def dataset_id(self) -> str | None:
        """The one dataset the chat is scoped to, if exactly one -- used to focus graph lookups."""
        ids = self.access.dataset_ids
        return next(iter(ids)) if ids is not None and len(ids) == 1 else None
