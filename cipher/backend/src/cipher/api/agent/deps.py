"""Dependencies injected into every agent tool call."""

import asyncio
from dataclasses import dataclass, field

from clir.api.deps import AsyncTextEmbeddingModel
from setfitcv.api.deps import AsyncImageEmbeddingModel

from cipher.api.deps.access import DatasetAccess
from cipher.api.deps.postgres import end_transactions
from cipher.datastores.base.retrieval import ChunkRetrievalRepository
from cipher.datastores.postgres.repositories.dataset import PostgresDatasetRepository
from cipher.datastores.postgres.repositories.dataset_profile import PostgresDatasetProfileRepository
from cipher.datastores.postgres.repositories.entity import PostgresEntityRepository
from cipher.datastores.postgres.repositories.entity_match import PostgresEntityMatchRepository
from cipher.datastores.postgres.repositories.entity_relationship import PostgresGraphRepository
from cipher.datastores.postgres.repositories.event import PostgresEventRepository
from cipher.datastores.postgres.repositories.extracted_text import PostgresExtractedTextRepository
from cipher.datastores.postgres.repositories.file import PostgresFileRepository
from cipher.datastores.postgres.repositories.image import PostgresImageRepository
from cipher.datastores.postgres.repositories.mention import PostgresMentionRepository
from cipher.datastores.postgres.repositories.person import PostgresPersonRepository
from cipher.schemas.graph.event import EventSearchParameters
from cipher.schemas.ingestion.file import FiletypeCoverage
from cipher.schemas.interaction.chat import ChatAutonomy, RelevanceJudgments


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
    image_model: AsyncImageEmbeddingModel
    persons: PostgresPersonRepository
    datasets: PostgresDatasetRepository
    dataset_profiles: PostgresDatasetProfileRepository
    files: PostgresFileRepository
    images: PostgresImageRepository
    events: PostgresEventRepository
    entities: PostgresEntityRepository
    entity_matches: PostgresEntityMatchRepository
    mentions: PostgresMentionRepository
    graph: PostgresGraphRepository
    extracted_text: PostgresExtractedTextRepository
    autonomy: ChatAutonomy = ChatAutonomy.GUIDED
    relevance: RelevanceJudgments | None = None
    _contents: tuple[list[FiletypeCoverage], int] | None = field(default=None, init=False, repr=False)
    _root: str | None = field(default=None, init=False, repr=False)
    _contents_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    @property
    def dataset_id(self) -> str | None:
        """The one dataset the chat is scoped to, if exactly one -- used to focus graph lookups."""
        ids = self.access.dataset_ids
        return next(iter(ids)) if ids is not None and len(ids) == 1 else None

    @property
    def dataset_ids(self) -> list[str] | None:
        """The chat's datasets as a filter (None = every dataset, admin)."""
        return sorted(self.access.dataset_ids) if self.access.dataset_ids is not None else None

    async def contents(self) -> tuple[list[FiletypeCoverage], int]:
        """What the chat's datasets hold: files per filetype group (and how many are searchable), and events.

        Looked up once per turn; tools that couldn't return anything for this data are hidden by it.
        """
        async with self._contents_lock:
            if self._contents is None:
                coverage = await self.files.searchable_coverage(dataset_ids=self.dataset_ids)
                events = await self.events.list_events(EventSearchParameters(dataset_ids=self.dataset_ids, limit=1))
                self._contents = (coverage, events.total)
                await self.release()
            return self._contents

    async def root(self) -> str:
        """The folder the collection was loaded from (ends in "/"); paths are shown to the model below it."""
        async with self._contents_lock:
            if self._root is None:
                self._root = await self.files.common_folder(dataset_ids=self.dataset_ids)
                await self.release()
            return self._root

    async def release(self) -> None:
        """End every repository's transaction, so none is held while the model thinks."""
        await end_transactions(
            self.chunks,
            self.persons,
            self.datasets,
            self.dataset_profiles,
            self.files,
            self.images,
            self.events,
            self.entities,
            self.entity_matches,
            self.mentions,
            self.graph,
            self.extracted_text,
        )

    async def relative(self, path: str) -> str:
        """`path` as seen from the collection's top folder ("/Pictures/x.jpg")."""
        root = await self.root()
        return "/" + path[len(root) :] if path.startswith(root) else path

    async def absolute(self, path: str) -> str:
        """A path the model gave (relative to the collection's top folder) as stored."""
        root = await self.root()
        return path if path.startswith(root) else root + path.lstrip("/")

    async def file_count(self, filetype_group: str) -> int:
        """How many files of one filetype group the chat's datasets hold."""
        coverage, _ = await self.contents()
        return next((group.file_count for group in coverage if group.filetype_group == filetype_group), 0)
