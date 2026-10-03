"""Identity: who is calling. Dataset-level permissions live in `deps/access.py`."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from cipher.api.deps.postgres import UserDatastoreDep
from cipher.api.settings import DevelopmentMode, Settings
from cipher.schemas.ingestion.user import User, UserCreate, UserUpdate
from cipher.utils.cache import TTLCache

settings = Settings()

DEV_ADMIN = UserCreate(name="Dev Admin", email="dev-admin@cipher.local", is_admin=True)

_users: TTLCache[str, User] = TTLCache(ttl_seconds=settings.access_cache_seconds)


def forget_users() -> None:
    """Drop cached users so a profile/admin change applies on the next request (user writes are rare)."""
    _users.clear()


async def _dev_admin(datastore: UserDatastoreDep) -> User:
    user = await datastore.get_or_create(user=DEV_ADMIN)
    if not user.is_admin:
        user = await datastore.update(user_id=user.id, data=UserUpdate(is_admin=True))
    return user


async def get_current_user(
    datastore: UserDatastoreDep,
    x_user_id: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> User:
    """The authenticated user, from the `X-User-Id` header set by the auth proxy in front of the API.

    In development the header is optional: without it requests run as the seeded `Dev Admin`
    (an admin, so every dataset is visible); with it you can act as any existing user to try
    their access. In production the header is required. Users are cached briefly per process.
    """
    if x_user_id is None:
        if settings.mode != DevelopmentMode.DEV:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in.")
        return _users.get(DEV_ADMIN.email) or _users.set(DEV_ADMIN.email, await _dev_admin(datastore))

    user = _users.get(x_user_id) or await datastore.get_by_id(user_id=x_user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user. Unable to authenticate.")
    return _users.set(x_user_id, user)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUserDep) -> User:
    """The current user, who must be an admin."""
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an admin can do that.")
    return user


AdminUserDep = Annotated[User, Depends(require_admin)]
AdminOnly = Depends(require_admin)
"""For `dependencies=[AdminOnly]` on routes that don't need the admin user itself."""
