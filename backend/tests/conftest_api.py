"""API test fixtures.

The API tests need a real Postgres because the schema uses JSONB, arrays, partial
indexes and pgvector — none of which SQLite can stand in for without the tests becoming
a test of the substitute. They are skipped, loudly, when no database is reachable, so a
clone without Docker still gets a green analytics suite.

TEST_DATABASE_URL overrides the target; it defaults to the configured database with a
``_test`` suffix so a careless run cannot touch development data.
"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from src.config import settings


def _test_database_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    url = settings.database_url
    return re.sub(r"/([^/?]+)(\?|$)", r"/\1_test\2", url)


TEST_DB_URL = _test_database_url()


async def _database_reachable() -> bool:
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    try:
        async with engine.connect():
            return True
    except Exception:
        return False
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    if not await _database_reachable():
        pytest.skip(f"no test database at {TEST_DB_URL}")

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    from src.db.models import Base

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def clean_db(db_engine):
    """Truncate between tests so ordering never matters."""
    from sqlalchemy import text

    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE analyses, analysis_events, evidence, usage_ledger, "
                "watchlists, watchlist_items, credit_transactions, credit_purchases, "
                "accounts, users, news_chunks, signup_otps, password_reset_otps "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest_asyncio.fixture
async def client(db_engine, session_factory, clean_db, monkeypatch) -> AsyncIterator:
    """An httpx client bound to the app, with the database and the queue redirected.

    The queue is replaced by a recorder: these tests verify the API contract, not the
    worker, and a real enqueue would need a live Redis and a running worker.
    """
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.session import get_session
    from src.main import app

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as s:
            yield s

    enqueued: list[str] = []

    async def fake_enqueue(analysis_id: str) -> None:
        enqueued.append(analysis_id)

    import src.worker as worker_module

    monkeypatch.setattr(worker_module, "enqueue_analysis", fake_enqueue, raising=False)
    monkeypatch.setattr(settings, "require_email_verification", False)
    app.dependency_overrides[get_session] = override_get_session

    # base_url must match COOKIE_DOMAIN ("localhost" by default): httpx will not store
    # a cookie whose Domain attribute does not cover the request host, so a mismatch
    # here silently breaks every session-dependent test.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://{settings.cookie_domain or 'localhost'}",
        follow_redirects=True,
    ) as c:
        c.enqueued = enqueued  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def fake_redis(monkeypatch):
    """An in-memory stand-in for the Redis calls the API makes.

    Quota counters and the spend guard are the only Redis state the HTTP layer touches,
    and both are simple counters.
    """

    class FakeRedis:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        async def get(self, key):
            return self.store.get(key)

        async def set(self, key, value, ex=None):
            self.store[key] = value

        async def incr(self, key):
            value = int(self.store.get(key, 0)) + 1
            self.store[key] = str(value)
            return value

        async def decr(self, key):
            value = max(int(self.store.get(key, 0)) - 1, 0)
            self.store[key] = str(value)
            return value

        async def incrbyfloat(self, key, amount):
            value = float(self.store.get(key, 0)) + amount
            self.store[key] = str(value)
            return value

        async def expire(self, key, ttl):
            return True

        async def ping(self):
            return True

        async def publish(self, channel, message):
            return 1

        async def aclose(self):
            return None

    fake = FakeRedis()
    import src.core.budget as budget_module
    import src.core.cache as cache_module
    import src.core.ratelimit as ratelimit_module

    for module in (cache_module, budget_module, ratelimit_module):
        monkeypatch.setattr(module, "get_redis", lambda: fake, raising=False)
    yield fake


@pytest.fixture
def sample_result() -> dict:
    """A completed analysis payload, shaped exactly as the worker persists one."""
    return {
        "scorecard": {
            "total": 7.8,
            "rating": "BUY",
            "conviction": "medium",
            "dimension_scores": {
                "profitability": 9.1, "financial_health": 7.5,
                "growth": 8.0, "valuation": 5.5, "sentiment": 6.0,
            },
            "weights_applied": {
                "profitability": 0.25, "financial_health": 0.20,
                "growth": 0.25, "valuation": 0.20, "sentiment": 0.10,
            },
            "thresholds": {"buy": 7.5, "hold": 5.0},
        },
        "memo": {
            "ticker": "AAPL",
            "as_of": "2026-09-11",
            "recommendation": "BUY",
            "conviction": "medium",
            "thesis": "Margins are wide and stable.",
            "valuation_method": "Peer median EV/EBITDA",
            "key_drivers": ["One", "Two", "Three"],
            "key_risks": ["A", "B", "C"],
            "what_would_change_our_mind": ["X"],
            "data_caveats": [],
            "cited_sources": ["S1"],
            "price_target_low": 200.0,
            "price_target_high": 260.0,
        },
        "blocks": {"profitability": {"metrics": {}, "narrative": "", "score": 9.1}, "trace": []},
        "data_quality": {"coverage": 1.0, "warnings": []},
    }
