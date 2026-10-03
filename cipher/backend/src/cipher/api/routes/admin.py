"""Admin-only management. Every route here requires `user.is_admin`; add sub-areas as `/admin/<area>`."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from cipher.api.deps.access import invalidate_access
from cipher.api.deps.authentication import AdminOnly, AdminUserDep
from cipher.api.deps.postgres import DatabaseMetricsDatastoreDep, UserDatastoreDep
from cipher.schemas.ingestion.database_metrics import DatabaseMetrics, DatasetDatabaseUsage
from cipher.schemas.ingestion.user import (
    PaginatedUsersResponse,
    User,
    UserCreate,
    UserDatasetsUpdate,
    UsersRequest,
    UserUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[AdminOnly])


async def _existing_user(id: str, datastore: UserDatastoreDep) -> str:
    if await datastore.get_by_id(user_id=id) is None:
        raise HTTPException(status_code=404, detail=f"User not found: {id}")
    return id


ExistingUserIdDep = Annotated[str, Depends(_existing_user)]


@router.get("/users", summary="List users", response_model=PaginatedUsersResponse)
async def list_users(params: Annotated[UsersRequest, Depends()], datastore: UserDatastoreDep):
    """Page through users, optionally matching name or email."""
    return await datastore.list_users(request=params)


@router.post("/users", summary="Create a user", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, datastore: UserDatastoreDep) -> User:
    """Add a user (duplicate emails are rejected)."""
    return await datastore.create(user=data)


@router.get("/users/{id}", summary="Get user by ID", response_model=User)
async def get_user_by_id(id: ExistingUserIdDep, datastore: UserDatastoreDep) -> User | None:
    """Any user's profile."""
    return await datastore.get_by_id(user_id=id)


@router.patch("/users/{id}", summary="Update a user", response_model=User)
async def update_user(id: ExistingUserIdDep, data: UserUpdate, admin: AdminUserDep, datastore: UserDatastoreDep):
    """Change a user's name, email or admin flag (you can't remove your own admin)."""
    if id == admin.id and data.is_admin is False:
        raise HTTPException(status_code=400, detail="You can't remove your own admin access.")
    user = await datastore.update(user_id=id, data=data)
    invalidate_access(user_id=id)
    return user


@router.delete("/users/{id}", summary="Delete a user", status_code=204)
async def delete_user(id: ExistingUserIdDep, admin: AdminUserDep, datastore: UserDatastoreDep) -> None:
    """Remove a user and their dataset memberships."""
    if id == admin.id:
        raise HTTPException(status_code=400, detail="You can't delete yourself.")
    await datastore.delete(user_id=id)
    invalidate_access(user_id=id)


@router.get("/users/{id}/datasets", summary="IDs of the datasets a user is a member of", response_model=list[str])
async def get_user_datasets(id: ExistingUserIdDep, datastore: UserDatastoreDep) -> list[str]:
    """A user's dataset memberships."""
    return await datastore.get_dataset_ids(user_id=id)


@router.put("/users/{id}/datasets", summary="Replace a user's dataset memberships", response_model=list[str])
async def set_user_datasets(id: ExistingUserIdDep, data: UserDatasetsUpdate, datastore: UserDatastoreDep) -> list[str]:
    """Make the user a member of exactly these datasets (unknown dataset IDs are ignored)."""
    dataset_ids = await datastore.set_dataset_access(user_id=id, dataset_ids=data.dataset_ids)
    invalidate_access(user_id=id)
    return dataset_ids


@router.put("/users/{id}/datasets/{dataset_id}", summary="Add a user to a dataset", status_code=204)
async def grant_dataset_access(id: ExistingUserIdDep, dataset_id: str, datastore: UserDatastoreDep) -> None:
    """Grant one dataset membership (no-op if it exists)."""
    await datastore.grant_dataset_access(user_id=id, dataset_ids=[dataset_id])
    invalidate_access(user_id=id)


@router.delete("/users/{id}/datasets/{dataset_id}", summary="Remove a user from a dataset", status_code=204)
async def revoke_dataset_access(id: ExistingUserIdDep, dataset_id: str, datastore: UserDatastoreDep) -> None:
    """Revoke one dataset membership."""
    if not await datastore.revoke_dataset_access(user_id=id, dataset_ids=[dataset_id]):
        raise HTTPException(status_code=404, detail="That user isn't a member of that dataset.")
    invalidate_access(user_id=id)


@router.get("/database", summary="Database metrics", response_model=DatabaseMetrics)
async def get_database_metrics(datastore: DatabaseMetricsDatastoreDep) -> DatabaseMetrics:
    """Postgres size, each table's footprint and row count, and an estimated breakdown by dataset."""
    return await datastore.get_metrics()


@router.get(
    "/database/datasets/{dataset_id}", summary="One dataset's database usage", response_model=DatasetDatabaseUsage
)
async def get_dataset_database_usage(dataset_id: str, datastore: DatabaseMetricsDatastoreDep) -> DatasetDatabaseUsage:
    """A dataset's rows and estimated bytes (including indexes) in each table it has data in."""
    usage = await datastore.get_dataset_usage(dataset_id=dataset_id)
    if usage is None:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")
    return usage
