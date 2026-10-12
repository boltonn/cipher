from fastapi import APIRouter

from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.postgres import UserDatastoreDep
from cipher.schemas.ingestion.user import SelectedDatasetsUpdate, User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", summary="Get current user profile", response_model=User)
async def get_my_profile(current_user: CurrentUserDep) -> User:
    """The authenticated user (the seeded Dev Admin in development unless `X-User-Id` is sent)."""
    return current_user


@router.get("/me/datasets", summary="IDs of the datasets the current user is a member of", response_model=list[str])
async def get_my_datasets(current_user: CurrentUserDep, datastore: UserDatastoreDep) -> list[str]:
    """Explicit memberships only -- an admin sees every dataset regardless."""
    return await datastore.get_dataset_ids(user_id=current_user.id)


@router.get("/me/selected-datasets", summary="The datasets the current user is working in", response_model=list[str])
async def get_my_selected_datasets(current_user: CurrentUserDep, datastore: UserDatastoreDep) -> list[str]:
    """Only datasets that still exist and that the user can access -- never a stale id."""
    return await datastore.get_selected_dataset_ids(user=current_user)


@router.put(
    "/me/selected-datasets", summary="Set the datasets the current user is working in", response_model=list[str]
)
async def set_my_selected_datasets(
    body: SelectedDatasetsUpdate, current_user: CurrentUserDep, datastore: UserDatastoreDep
) -> list[str]:
    """Replaces the selection; missing or inaccessible datasets are dropped. Returns what was stored."""
    return await datastore.set_selected_dataset_ids(user=current_user, dataset_ids=body.dataset_ids)
