"""Alembic environment.

The project only carries the asyncpg driver, so migrations run through an async engine
and ``connection.run_sync`` rather than pulling in a second, sync-only Postgres driver.
"""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.db.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
DB_URL = settings.database_url


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    # pgvector installs catalog types of its own; autogenerate must not touch them.
    if type_ == "table" and name in {"vector", "halfvec", "sparsevec"}:
        return False
    return True


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        compare_type=True,
    )


def run_migrations_offline() -> None:
    context.configure(
        url=DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(DB_URL, poolclass=NullPool, future=True)
    async with engine.connect() as connection:
        await connection.run_sync(lambda conn: _configure(conn))
        await connection.run_sync(lambda conn: context.run_migrations())
        await connection.commit()
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
