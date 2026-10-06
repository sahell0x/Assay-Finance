"""Build the retrieval corpus for a ticker.

Shared by ``scripts/seed_index.py`` and by the analysis pipeline's just-in-time path,
so a ticker nobody has indexed still gets evidence on its first run.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ...agent.models import Usage
from .chunk import Chunk, chunk_risk_factors, chunk_text
from .edgar import fetch_sections
from .embed import embed_texts
from .rss import fetch_news
from .store import count_for, upsert_chunks

log = logging.getLogger(__name__)


async def build_chunks(ticker: str) -> list[Chunk]:
    """Fetch every source and reduce it to chunks. Never raises."""
    ticker = ticker.upper()
    chunks: list[Chunk] = []

    try:
        sections = await fetch_sections(ticker)
    except Exception as exc:
        log.warning("EDGAR ingest failed for %s: %s", ticker, exc)
        sections = []

    for sec in sections:
        common = {
            "ticker": ticker,
            "source_type": sec["source_type"],
            "title": sec.get("title"),
            "url": sec.get("url"),
            "published": sec.get("published"),
        }
        if sec.get("is_risk_factors"):
            # One chunk per named risk, so a hit returns a whole self-contained risk.
            chunks.extend(chunk_risk_factors(sec["text"], **common))
        else:
            chunks.extend(chunk_text(sec["text"], section=sec.get("section"), **common))

    try:
        news = await fetch_news(ticker)
    except Exception as exc:
        log.warning("news ingest failed for %s: %s", ticker, exc)
        news = []

    for item in news:
        chunks.extend(
            chunk_text(
                item["text"],
                ticker=ticker,
                source_type=item["source_type"],
                section=item.get("section"),
                title=item.get("title"),
                url=item.get("url"),
                published=item.get("published"),
            )
        )

    # Content-addressed IDs make de-duplication free.
    seen: set[str] = set()
    unique: list[Chunk] = []
    for c in chunks:
        if c.chunk_id in seen:
            continue
        seen.add(c.chunk_id)
        unique.append(c)
    return unique


async def index_ticker(
    db: AsyncSession, ticker: str, *, usage: Usage | None = None, force: bool = False
) -> dict:
    """Fetch, chunk, embed and store. Returns a small report."""
    ticker = ticker.upper()
    existing = await count_for(db, ticker)
    if existing and not force:
        return {"ticker": ticker, "chunks": existing, "action": "skipped", "reason": "already indexed"}

    chunks = await build_chunks(ticker)
    if not chunks:
        return {"ticker": ticker, "chunks": 0, "action": "none", "reason": "no source documents found"}

    embeddings = await embed_texts([c.text for c in chunks], usage)
    written = await upsert_chunks(db, [c.as_row() for c in chunks], embeddings)

    by_source: dict[str, int] = {}
    for c in chunks:
        by_source[c.source_type] = by_source.get(c.source_type, 0) + 1

    return {
        "ticker": ticker,
        "chunks": written,
        "action": "indexed",
        "by_source": by_source,
    }
