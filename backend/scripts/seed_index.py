#!/usr/bin/env python
"""Build the retrieval corpus for a set of tickers.

    python scripts/seed_index.py AAPL MSFT NVDA JPM O
    python scripts/seed_index.py --popular --force
    python scripts/seed_index.py --status

Pre-warming matters because the first analysis of an unindexed ticker pays for the
EDGAR fetch, the chunking and the embedding inline. Seeding the names people actually
look up moves that cost off the critical path.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.models import Usage  # noqa: E402
from src.core.budget import add_spend  # noqa: E402
from src.core.cache import close_redis  # noqa: E402
from src.data.news.ingest import index_ticker  # noqa: E402
from src.data.news.store import indexed_tickers  # noqa: E402
from src.db.session import SessionLocal, dispose_engine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("seed")

POPULAR = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "JPM", "BAC", "UNH", "JNJ", "LLY", "XOM", "CVX",
    "WMT", "COST", "HD", "KO", "PEP", "O",
]


async def show_status() -> None:
    async with SessionLocal() as db:
        rows = await indexed_tickers(db)
    if not rows:
        print("Nothing indexed yet.")
        return
    print(f"{'TICKER':<8} {'CHUNKS':>7}  NEWEST")
    for r in rows:
        print(f"{r['ticker']:<8} {r['chunks']:>7}  {r['newest'] or '—'}")
    print(f"\n{len(rows)} tickers, {sum(r['chunks'] for r in rows)} chunks.")


async def seed(tickers: list[str], force: bool) -> int:
    usage = Usage()
    failures = 0

    async with SessionLocal() as db:
        for i, ticker in enumerate(tickers, start=1):
            try:
                report = await index_ticker(db, ticker, usage=usage, force=force)
            except Exception as exc:
                log.error("%s failed: %s", ticker, exc)
                failures += 1
                continue

            detail = ""
            if report.get("by_source"):
                detail = "  " + ", ".join(f"{k}:{v}" for k, v in sorted(report["by_source"].items()))
            log.info(
                "[%d/%d] %-6s %-8s %4d chunks%s",
                i, len(tickers), report["ticker"], report["action"], report["chunks"], detail,
            )
            # SEC allows 10 requests a second; this stays comfortably under it.
            await asyncio.sleep(0.4)

    if usage.cost_usd:
        await add_spend(usage.cost_usd)
    log.info(
        "done: %d tickers, %d failures, %d embedding tokens, $%.4f",
        len(tickers), failures, usage.tokens_in, usage.cost_usd,
    )
    return failures


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="*", help="symbols to index")
    parser.add_argument("--popular", action="store_true", help=f"index {len(POPULAR)} common names")
    parser.add_argument("--force", action="store_true", help="re-index tickers that already exist")
    parser.add_argument("--status", action="store_true", help="show what is indexed and exit")
    args = parser.parse_args()

    try:
        if args.status:
            await show_status()
            return 0

        tickers = [t.upper() for t in args.tickers] or (POPULAR if args.popular else [])
        if not tickers:
            parser.error("name at least one ticker, or pass --popular")

        return 1 if await seed(tickers, args.force) else 0
    finally:
        await close_redis()
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
