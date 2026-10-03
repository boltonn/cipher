"""Dataset access: which datasets the current user may see, and guards that enforce it.

Only dataset *content* is guarded -- files, extracted text, chunks, images/faces, mentions
(they quote the text) and email counts. The entity graph (entities, relationships, events,
persons, locations) is shared across datasets and open to every user.

Route usage:
    id: DatasetIdDep                 -- `{id}` path param, must be a dataset the user can access
    dataset_id: DatasetIdQueryDep    -- `?datasetId=` query param, same check
    mention: MentionDep              -- `{mention_id}` path param, the mention's dataset must be accessible
    access: DatasetAccessDep         -- for bodies/filters: `access.require(...)`, `access.scoped(model)`

Admins can access every dataset. Everyone else needs membership (`user_dataset_access`), which
is cached briefly per process and dropped immediately when changed through the API.
"""

from dataclasses import dataclass
from typing import Annotated, Protocol, Self

from fastapi import Depends, HTTPException, Query, status

from cipher.api.deps.authentication import CurrentUserDep, forget_users, settings
from cipher.api.deps.postgres import MentionDatastoreDep, UserDatastoreDep
from cipher.datastores.postgres.repositories.file import PostgresFileRepository
from cipher.schemas._base.exceptions import EntityNotFoundError
from cipher.schemas.graph.mention import Mention
from cipher.schemas.ingestion.user import User
from cipher.utils.cache import TTLCache

# Matches no dataset: keeps a "restrict to these datasets" filter non-empty when the user has none,
# since repositories read an empty filter list as "no filter".
NO_DATASET = "__no_dataset__"

class DatasetScopedModel(Protocol):
    """A pydantic request/filter model carrying a `dataset_id` filter and a `dataset_ids` scope."""

    dataset_id: str | None
    dataset_ids: list[str] | None

    def model_copy(self, *, update: dict) -> Self:
        """Pydantic copy with updated fields."""
        ...


_memberships: TTLCache[str, frozenset[str]] = TTLCache(ttl_seconds=settings.access_cache_seconds)


def invalidate_access(user_id: str | None = None) -> None:
    """Make a membership or user change apply on the next request (one user, or everyone)."""
    if user_id is None:
        _memberships.clear()
    else:
        _memberships.pop(user_id)
    forget_users()


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to that dataset.")


@dataclass(frozen=True)
class DatasetAccess:
    """Which datasets the current user may see; `dataset_ids=None` means every dataset (admin)."""

    user: User
    dataset_ids: frozenset[str] | None

    def allows(self, dataset_id: str | None) -> bool:
        """Whether the user can access this dataset."""
        return self.dataset_ids is None or dataset_id in self.dataset_ids

    def require(self, *dataset_ids: str | None) -> None:
        """Raise 403 unless the user can access at least one of these datasets (content can live in several)."""
        if not any(self.allows(dataset_id) for dataset_id in dataset_ids):
            raise _forbidden()

    def scope(self, requested: list[str] | None) -> list[str] | None:
        """A dataset filter limited to what the user can access.

        Explicitly requested datasets must all be accessible (403 otherwise); no request means
        "all of mine" -- `None` (unfiltered) for an admin.
        """
        if requested:
            for dataset_id in requested:
                self.require(dataset_id)
            return requested
        if self.dataset_ids is None:
            return None
        return sorted(self.dataset_ids) or [NO_DATASET]

    def narrow(self, dataset_ids: list[str] | None) -> "DatasetAccess":
        """This access limited to some of its datasets (each must be accessible); none keeps it whole."""
        if not dataset_ids:
            return self
        for dataset_id in dataset_ids:
            self.require(dataset_id)
        return DatasetAccess(user=self.user, dataset_ids=frozenset(dataset_ids))

    def scoped[M: DatasetScopedModel](self, model: M) -> M:
        """A copy of a request/filter model limited to what the user can access.

        Works on any model with an optional `dataset_id` filter and a server-set `dataset_ids`
        scope (chunk filters, mention search, email counts): a requested dataset must be
        accessible, and `dataset_ids` becomes the user's datasets (None for an admin).
        """
        if model.dataset_id:
            self.require(model.dataset_id)
        return model.model_copy(update={"dataset_ids": self.scope(model.dataset_ids)})


async def get_dataset_access(user: CurrentUserDep, datastore: UserDatastoreDep) -> DatasetAccess:
    """The current user's dataset access, from the membership cache when warm."""
    if user.is_admin:
        return DatasetAccess(user=user, dataset_ids=None)
    dataset_ids = _memberships.get(user.id)
    if dataset_ids is None:
        dataset_ids = _memberships.set(user.id, frozenset(await datastore.get_dataset_ids(user_id=user.id)))
    return DatasetAccess(user=user, dataset_ids=dataset_ids)


DatasetAccessDep = Annotated[DatasetAccess, Depends(get_dataset_access)]


async def require_dataset(id: str, access: DatasetAccessDep) -> str:
    """Guard for a `{id}` dataset path param."""
    access.require(id)
    return id


async def require_dataset_query(
    dataset_id: Annotated[str, Query(alias="datasetId")], access: DatasetAccessDep
) -> str:
    """Guard for a `?datasetId=` query param."""
    access.require(dataset_id)
    return dataset_id


DatasetIdDep = Annotated[str, Depends(require_dataset)]
DatasetIdQueryDep = Annotated[str, Depends(require_dataset_query)]


async def require_mention(mention_id: str, access: DatasetAccessDep, datastore: MentionDatastoreDep) -> Mention:
    """Guard for a `{mention_id}` path param: mentions quote file content, so their dataset must be accessible."""
    mention = await datastore.get_mention(mention_id)
    if mention is None:
        raise EntityNotFoundError("Mention", mention_id)
    access.require(mention.dataset_id)
    return mention


MentionDep = Annotated[Mention, Depends(require_mention)]


async def require_content_access(
    *, sha256s: list[str], access: DatasetAccess, file_datastore: PostgresFileRepository
) -> None:
    """403 unless every piece of content (an image, or a face's source image, by sha256) is in the user's datasets."""
    if access.dataset_ids is None or not sha256s:
        return
    visible = await file_datastore.sha256s_in_datasets(sha256s=sha256s, dataset_ids=list(access.dataset_ids))
    if set(sha256s) - visible:
        raise _forbidden()
