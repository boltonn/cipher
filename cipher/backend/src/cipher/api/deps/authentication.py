from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from cipher.api.deps.postgres import get_user_repository
from cipher.api.settings import DevelopmentMode, Settings
from cipher.datastores.postgres.repositories.user import PostgresUserRepository
from cipher.schemas.ingestion.user import User, UserCreate

settings = Settings()


async def get_current_user(
    repo: Annotated[PostgresUserRepository, Depends(get_user_repository)],
    x_user_id: Annotated[
        str | None,
        Header(include_in_schema=False),
    ] = None,
) -> User:
    """Dependency to get the current authenticated user.

    If in development mode and no user ID header is provided, a default "Dev Admin" user is created/retrieved.
    In production mode, the user ID header is strictly required and validated.
    """
    # 1. DEVELOPMENT MODE - Default user
    if settings.mode == DevelopmentMode.DEV or not x_user_id:
        dev_email = "dev-admin@cipher.local"
        user = await repo.get_by_email(dev_email)

        if not user:
            # Create the dev user on the fly if it doesn't exist
            user = await repo.create(UserCreate(name="Dev Admin", email=dev_email))
        return user

    # 2. PRODUCTION MODE - Strict header check
    try:
        user = await repo.get_by_id(x_user_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid User ID format"
        ) from exc

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found in database. Unable to authenticate.",
        )

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
