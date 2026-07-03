from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from cipher.orchestration.settings import Settings
from cipher.datastores.postgres.session import get_async_engine

settings = Settings()


def get_async_engine_from_settings() -> AsyncEngine:
    return get_async_engine(config=settings.postgres)


@asynccontextmanager
async def get_session_context():
    """Context manager that provides a session with automatic commit/rollback/close."""
    engine = get_async_engine_from_settings()
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
