"""ARQ worker: where analyses actually run.

``max_jobs = 1``. The box is 2 GB and 2 vCPU running Postgres connections, the API and
this worker; a second concurrent analysis would double the peak memory of the EDGAR
parse and the peer fetch for no throughput gain that matters at this scale.

The worker owns the whole lifecycle: it marks the row running, executes the graph,
persists blocks and evidence, records cost against the daily budget, and publishes a
terminal event so any attached SSE stream closes cleanly rather than hanging.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from .agent.graph import run_analysis
from .agent.progress import publish_done
from .agent.state import block_to_dict
from .config import settings
from .core.cache import close_redis, get_redis
from .db import credits, repo
from .db.session import SessionLocal, dispose_engine

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("worker")

JOB_TIMEOUT = 60 * 8


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def enqueue_analysis(analysis_id: str) -> None:
    """Called from the API. Uses a short-lived pool: the API process should not hold an
    idle ARQ connection open for the life of the container."""
    pool = await create_pool(redis_settings())
    try:
        await pool.enqueue_job("run_analysis_job", analysis_id, _job_id=f"analysis:{analysis_id}")
    finally:
        await pool.aclose()


async def run_analysis_job(ctx: dict, analysis_id: str) -> dict[str, Any]:
    aid = uuid.UUID(analysis_id)

    async with SessionLocal() as db:
        row = await repo.get_analysis(db, aid)
        if row is None:
            log.error("job for unknown analysis %s", analysis_id)
            return {"ok": False, "reason": "not found"}
        ticker = row.ticker
        peers = list(row.peer_tickers or [])
        weights = dict(row.weights or {})
        thread_id = row.thread_id
        anon_id = row.anon_id
        await repo.set_status(db, aid, status="running", current_node="ingest")

    log.info("running analysis %s for %s", analysis_id, ticker)

    try:
        state = await run_analysis(
            analysis_id=analysis_id,
            ticker=ticker,
            peer_tickers=peers,
            weights=weights,
            thread_id=thread_id,
        )
    except asyncio.CancelledError:
        # The worker is shutting down (a deploy or a restart). With max_tries=1 arq will
        # not run this again, so without this the row would say "running" forever and
        # the page would wait on it indefinitely.
        await _fail(aid, anon_id, INTERRUPTED)
        raise
    except Exception as exc:
        log.exception("analysis %s failed", analysis_id)
        message = _friendly_error(exc, ticker)
        await _fail(aid, anon_id, message)
        return {"ok": False, "error": message}

    memo = state.get("memo")
    cost = state.get("cost") or {}

    blocks = {
        "profitability": block_to_dict(state.get("profitability")),
        "liquidity": block_to_dict(state.get("liquidity")),
        "growth": block_to_dict(state.get("growth")),
        "peers": block_to_dict(state.get("peers")),
        "trace": state.get("trace", []),
        "retrieval": state.get("retrieval_stats", {}),
        "critic": state.get("critic_verdict", {}),
        "market": state.get("market", {}),
        "facts": _slim_facts(state.get("facts") or {}),
        "warnings": state.get("warnings", []),
        "cost": cost,
    }

    async with SessionLocal() as db:
        await repo.save_result(
            db,
            aid,
            scorecard=state.get("scorecard"),
            memo=memo.model_dump(mode="json") if memo else None,
            blocks=blocks,
            data_quality=state.get("data_quality"),
            cost_usd=float(cost.get("cost_usd", 0.0)),
        )
        await repo.replace_evidence(
            db,
            aid,
            [
                {
                    "label": e.label,
                    "source_type": e.source_type,
                    "url": e.url,
                    "published": e.published,
                    "text": e.text,
                    "relevance": e.relevance,
                    "title": e.title,
                    "section": e.section,
                }
                for e in (state.get("evidence") or [])
            ],
        )
        row = await repo.get_analysis(db, aid)
        await repo.record_usage(
            db,
            user_id=row.user_id if row else None,
            anon_id=row.anon_id if row else None,
            analysis_id=aid,
            tokens_in=int(cost.get("tokens_in", 0)),
            tokens_out=int(cost.get("tokens_out", 0)),
            cost_usd=float(cost.get("cost_usd", 0.0)),
        )

    await publish_done(analysis_id, status="complete")
    log.info(
        "analysis %s complete: %s %s, $%.4f",
        analysis_id,
        (state.get("scorecard") or {}).get("rating"),
        ticker,
        float(cost.get("cost_usd", 0.0)),
    )
    return {"ok": True, "rating": (state.get("scorecard") or {}).get("rating")}


def _slim_facts(facts: dict) -> dict:
    """Keep the statement values the interface shows for provenance, drop the rest.

    The full fundamentals payload is large and mostly redundant with what the metric
    blocks already carry; storing all of it in JSONB for every run is wasteful.
    """
    keep = {"ticker", "name", "sector", "industry", "currency", "periods", "annual_periods"}
    slim = {k: v for k, v in facts.items() if k in keep}
    periods = facts.get("periods", [])[:6]
    slim["facts"] = {p: facts.get("facts", {}).get(p, {}) for p in periods}
    return slim


INTERRUPTED = (
    "This analysis was interrupted before it finished. Your credit was not used — "
    "please run it again."
)


async def _fail(aid: uuid.UUID, anon_id: str | None, message: str) -> None:
    """Record a failure, give the run back, and tell anyone watching the stream."""
    async with SessionLocal() as db:
        await repo.set_status(db, aid, status="failed", error=message)
        # A run that produced nothing should not cost anything. Signed-in runs get their
        # ledger entry reversed (a bought credit goes back on the balance); anonymous
        # ones live in Redis.
        await credits.refund_run(db, aid)
    if anon_id:
        from .core import ratelimit

        await ratelimit.release_anon_run(anon_id)
    await publish_done(str(aid), status="failed", error=message)


def _friendly_error(exc: Exception, ticker: str) -> str:
    """Errors are for the reader, not the log. Say what happened and what to do.

    Every failure gives the credit back (see ``_fail``), so every message says so. The
    raw exception is logged and never shown: it means nothing to the person reading it.
    """
    text = str(exc)
    refund = " Your credit was not used."
    if "No financial statements" in text:
        return (
            f"We could not find financial reports for {ticker}. This usually means it is "
            f"a fund, an index, a very new listing, or a company that does not file "
            f"reports in the US.{refund}"
        )
    if "missing core statement lines" in text:
        return (
            f"The financial reports for {ticker} are missing too much of the information "
            f"we need, so any score would be unreliable.{refund}"
        )
    if "timeout" in text.lower() or "timed out" in text.lower():
        return (
            f"Our data source took too long to respond while analyzing {ticker}. Running "
            f"it again usually works.{refund}"
        )
    if "rate" in text.lower() and "limit" in text.lower():
        return (
            f"Our data source is busy right now. Wait a minute and run {ticker} "
            f"again.{refund}"
        )
    return f"Something went wrong while analyzing {ticker}. Please try again.{refund}"


async def startup(ctx: dict) -> None:
    log.info("worker starting (max_jobs=1)")
    from .core.monitoring import init_monitoring

    init_monitoring("worker")
    get_redis()
    # A worker killed outright (out of memory, a hard stop) never reaches the cancel
    # handler. Anything still "running" long after the job timeout was one of those.
    try:
        async with SessionLocal() as db:
            stuck = await repo.stuck_runs(db, older_than_s=JOB_TIMEOUT + 120)
        for aid, anon_id in stuck:
            log.warning("marking abandoned analysis %s as failed", aid)
            await _fail(aid, anon_id, INTERRUPTED)
    except Exception as exc:
        log.warning("could not sweep abandoned analyses: %s", exc)


async def shutdown(ctx: dict) -> None:
    await close_redis()
    await dispose_engine()
    log.info("worker stopped")


class WorkerSettings:
    functions = [run_analysis_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    max_jobs = 1
    job_timeout = JOB_TIMEOUT
    keep_result = 3600
    max_tries = 1  # a failed analysis is reported, not silently retried at double cost
