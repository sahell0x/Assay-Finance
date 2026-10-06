"""pgvector-backed chunk store.

Similarity search happens in Postgres, not in Python. That is a deliberate constraint:
loading an index into the worker process would put the entire corpus in the memory of a
box that has 2 GB to share with Postgres connections and the API. The HNSW index on
``halfvec_cosine_ops`` does the work where the data already is.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings

log = logging.getLogger(__name__)


def _as_date(value) -> date | None:
    """asyncpg binds date parameters by type, so an ISO string must be parsed first
    rather than left for Postgres to cast."""
    if value is None or isinstance(value, date):
        return value if not isinstance(value, datetime) else value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _vector_literal(vec: list[float]) -> str:
    """pgvector accepts a bracketed list; asyncpg has no native binding for halfvec."""
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


async def upsert_chunks(db: AsyncSession, rows: list[dict], embeddings: list[list[float]]) -> int:
    """Insert or refresh chunks. Chunk IDs are content-addressed, so re-running an
    ingest for an unchanged filing is a no-op rather than a duplicate."""
    if not rows:
        return 0
    if len(rows) != len(embeddings):
        raise ValueError(f"{len(rows)} rows but {len(embeddings)} embeddings")

    stmt = text(
        """
        INSERT INTO news_chunks
            (chunk_id, ticker, source_type, section, title, url, published, text,
             embedding, model, created_at)
        VALUES
            (:chunk_id, :ticker, :source_type, :section, :title, :url,
             :published, :text, CAST(:embedding AS halfvec), :model, now())
        ON CONFLICT (chunk_id) DO UPDATE SET
            text = EXCLUDED.text,
            embedding = EXCLUDED.embedding,
            published = EXCLUDED.published,
            model = EXCLUDED.model
        """
    )

    written = 0
    for row, vec in zip(rows, embeddings, strict=True):
        await db.execute(
            stmt,
            {
                "chunk_id": row["chunk_id"],
                "ticker": row["ticker"].upper(),
                "source_type": row["source_type"],
                "section": row.get("section"),
                "title": row.get("title"),
                "url": row.get("url"),
                "published": _as_date(row.get("published")),
                "text": row["text"],
                "embedding": _vector_literal(vec),
                "model": settings.embedding_model,
            },
        )
        written += 1
    await db.commit()
    return written


async def search(
    db: AsyncSession,
    *,
    ticker: str,
    embedding: list[float],
    k: int = 6,
    since: date | None = None,
) -> list[dict]:
    """Nearest neighbours for one ticker, newest-biased by the caller, not by SQL."""
    since = since or (date.today() - timedelta(days=730))
    stmt = text(
        """
        SELECT chunk_id, ticker, source_type, section, title, url, published, text,
               1 - (embedding <=> CAST(:q AS halfvec)) AS score
        FROM news_chunks
        WHERE ticker = :ticker
          AND (published IS NULL OR published > :since)
        ORDER BY embedding <=> CAST(:q AS halfvec)
        LIMIT :k
        """
    )
    result = await db.execute(
        stmt,
        {"q": _vector_literal(embedding), "ticker": ticker.upper(), "since": since, "k": k},
    )
    return [dict(r) for r in result.mappings().all()]


async def count_for(db: AsyncSession, ticker: str) -> int:
    result = await db.execute(
        text("SELECT count(*) FROM news_chunks WHERE ticker = :t"), {"t": ticker.upper()}
    )
    return int(result.scalar_one())


async def indexed_tickers(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT ticker, count(*) AS chunks, max(published) AS newest
            FROM news_chunks GROUP BY ticker ORDER BY ticker
            """
        )
    )
    return [dict(r) for r in result.mappings().all()]


async def delete_ticker(db: AsyncSession, ticker: str) -> int:
    result = await db.execute(
        text("DELETE FROM news_chunks WHERE ticker = :t"), {"t": ticker.upper()}
    )
    await db.commit()
    return result.rowcount or 0
