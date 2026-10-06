#!/usr/bin/env python
"""Refresh analyses for popular tickers. Intended for a daily cron.

    python scripts/precompute.py --top 10
    python scripts/precompute.py --tickers AAPL,MSFT --dry-run

Runs the pipeline directly rather than going through the queue, so a cron job does not
compete with live user requests for the single worker slot. Respects the daily budget
cap and stops the moment it is reached: a scheduled job must never be the reason a real
visitor gets a 503.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import desc, func, select  # noqa: E402

from src.agent.graph import run_analysis  # noqa: E402
from src.agent.state import block_to_dict  # noqa: E402
from src.core.budget import budget_exhausted, budget_state  # noqa: E402
from src.core.cache import analysis_cache_key, close_redis  # noqa: E402
from src.db import repo  # noqa: E402
from src.db.models import Analysis  # noqa: E402
from src.db.session import SessionLocal, dispose_engine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("precompute")


async def most_requested(limit: int) -> list[str]:
    """Ticker popularity, by how often it has been analysed."""
    async with SessionLocal() as db:
        result = await db.execute(
            select(Analysis.ticker, func.count().label("n"))
            .group_by(Analysis.ticker)
            .order_by(desc("n"))
            .limit(limit)
        )
        return [row[0] for row in result.all()]


async def refresh(ticker: str) -> str:
    """Run one analysis and store it so today's cache key is warm."""
    cache_key = analysis_cache_key(ticker, None, None)

    async with SessionLocal() as db:
        if await repo.find_cached(db, cache_key):
            return "fresh"
        row = await repo.create_analysis(
            db, ticker=ticker, peer_tickers=None, weights=None,
            user_id=None, anon_id="precompute", cache_key=cache_key,
        )
        aid = row.id
        thread_id = row.thread_id
        await repo.set_status(db, aid, status="running")

    try:
        state = await run_analysis(analysis_id=str(aid), ticker=ticker, thread_id=thread_id)
    except Exception as exc:
        log.warning("%s failed: %s", ticker, exc)
        async with SessionLocal() as db:
            await repo.set_status(db, aid, status="failed", error=str(exc)[:500])
        return "failed"

    memo = state.get("memo")
    cost = state.get("cost") or {}
    async with SessionLocal() as db:
        await repo.save_result(
            db, aid,
            scorecard=state.get("scorecard"),
            memo=memo.model_dump(mode="json") if memo else None,
            blocks={
                "profitability": block_to_dict(state.get("profitability")),
                "liquidity": block_to_dict(state.get("liquidity")),
                "growth": block_to_dict(state.get("growth")),
                "peers": block_to_dict(state.get("peers")),
                "trace": state.get("trace", []),
                "retrieval": state.get("retrieval_stats", {}),
                "critic": state.get("critic_verdict", {}),
                "market": state.get("market", {}),
                "warnings": state.get("warnings", []),
                "cost": cost,
            },
            data_quality=state.get("data_quality"),
            cost_usd=float(cost.get("cost_usd", 0.0)),
        )
        await repo.replace_evidence(
            db, aid,
            [
                {
                    "label": e.label, "source_type": e.source_type, "url": e.url,
                    "published": e.published, "text": e.text, "relevance": e.relevance,
                    "title": e.title, "section": e.section,
                }
                for e in (state.get("evidence") or [])
            ],
        )
    log.info("%s -> %s", ticker, (state.get("scorecard") or {}).get("rating"))
    return "refreshed"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=10, help="how many popular tickers to refresh")
    parser.add_argument("--tickers", type=str, help="comma-separated override")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        tickers = (
            [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
            if args.tickers
            else await most_requested(args.top)
        )
        if not tickers:
            log.info("nothing to refresh yet")
            return 0

        log.info("candidates: %s", ", ".join(tickers))
        if args.dry_run:
            return 0

        outcomes: Counter[str] = Counter()
        for ticker in tickers:
            if await budget_exhausted():
                log.warning("daily budget reached; stopping so live requests keep working")
                outcomes["skipped"] += len(tickers) - sum(outcomes.values())
                break
            outcomes[await refresh(ticker)] += 1

        log.info("%s | budget %s", dict(outcomes), await budget_state())
        return 0
    finally:
        await close_redis()
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
