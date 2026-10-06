"""Async engine + session factory.

Pool sizing is deliberate: Neon's free tier bills compute while a connection keeps the
endpoint awake, so a persistent idle pool burns the monthly CU-hour allowance around the
clock. In production we use ``NullPool`` (connect per request, let the endpoint sleep);
locally a tiny recycled pool is faster.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ..config import settings


def _engine_kwargs() -> dict:
    if settings.is_prod:
        return {"poolclass": NullPool}
    return {"pool_size": 2, "max_overflow": 2, "pool_recycle": 240, "pool_pre_ping": True}


engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    **_engine_kwargs(),
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    await engine.dispose()
