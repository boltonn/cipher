from fastapi import APIRouter, HTTPException, status

from cipher.api.deps.authentication import CurrentUserDep
from cipher.api.deps.postgres import UserDatastoreDep
from cipher.schemas._base.exceptions import EntityAlreadyExistsError, EntityNotFoundError
from cipher.schemas.ingestion.dataset import Dataset
from cipher.schemas.ingestion.user import User, UserCreate, UserUpdate

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


@router.get("/me", summary="Get current user profile", response_model=User)
async def get_my_profile(current_user: CurrentUserDep):
    """Returns the profile of the authenticated user.

    In dev, this returns the Dev Admin. In prod, it uses the X-User-ID header.
    """
    return current_user


@router.get(
    "/me/datasets", summary="Get current user's datasets", response_model=list[Dataset]
)
async def get_my_datasets(current_user: CurrentUserDep, datastore: UserDatastoreDep):
    """Returns all datasets the current user has access to."""
    return await datastore.get_user_datasets(user_id=current_user.id)


@router.get("/{id}", summary="Get user by ID", response_model=User)
async def get_user_by_id(id: str, datastore: UserDatastoreDep):
    """Admin-level: Get any user's profile by their ID."""
    user = await datastore.get_by_id(user_id=id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User not found: {id}")
    return user


@router.post(
    "",
    summary="Create new user",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(data: UserCreate, datastore: UserDatastoreDep):
    """Create a new user profile."""
    try:
        return await datastore.create(user=data)
    except EntityAlreadyExistsError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch("/{id}", summary="Update user profile", response_model=User)
async def update_user(id: str, data: UserUpdate, datastore: UserDatastoreDep):
    """Update user details (name, email, etc.)."""
    try:
        return await datastore.update(user_id=id, data=data)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{id}", summary="Delete user")
async def delete_user(id: str, datastore: UserDatastoreDep):
    """Remove a user from the system."""
    success = await datastore.delete(user_id=id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"detail": "User deleted successfully"}


# --- Access Management ---


@router.post("/{id}/datasets/{dataset_id}", summary="Grant dataset access")
async def grant_access(
    id: str,
    dataset_id: str,
    current_user: CurrentUserDep,
    datastore: UserDatastoreDep,
    role: str = "member",
):
    """Grant a specific user access to a specific dataset."""
    try:
        return await datastore.grant_dataset_access(
            user_id=id, dataset_id=dataset_id, granted_by=current_user.id, role=role
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{id}/datasets/{dataset_id}", summary="Revoke dataset access")
async def revoke_access(id: str, dataset_id: str, datastore: UserDatastoreDep):
    """Revoke a user's access to a dataset."""
    success = await datastore.revoke_dataset_access(user_id=id, dataset_id=dataset_id)
    if not success:
        raise HTTPException(status_code=404, detail="Access record not found")
    return {"detail": "Access revoked"}
