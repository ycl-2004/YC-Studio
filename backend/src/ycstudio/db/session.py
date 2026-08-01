"""SQLAlchemy 2.0 async engine and request-scoped session lifecycle.

References:
- https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- https://docs.sqlalchemy.org/en/20/core/pooling.html#disconnect-handling-pessimistic
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ycstudio.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Yield one AsyncSession and roll back errors crossing the request boundary.

    Services own the transaction boundary and commit explicitly. The dependency
    owns failure cleanup; the context manager always closes the session and
    returns its connection to the pool.
    """

    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
