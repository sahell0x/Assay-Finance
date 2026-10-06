"""Node-level progress: Redis pub/sub for live viewers, Postgres for replay.

Every node transition is written twice. The pub/sub message drives the SSE stream for
whoever is watching right now; the ``analysis_events`` row is what lets a cached result
replay the same pipeline animation later, and what a mid-run page refresh reads to
rebuild the checklist instead of showing an empty one.
"""

from __future__ import annotations

import functools
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from ..core.cache import get_redis

log = logging.getLogger(__name__)

# The pipeline, in order. The interface renders this list before anything has run, so it
# lives here rather than being inferred from events as they arrive.
PIPELINE: list[dict[str, str]] = [
    {"node": "ingest", "label": "Read the reports", "detail": "Latest financial reports and share price"},
    {"node": "validate", "label": "Check the data", "detail": "Make sure enough years are available"},
    {"node": "profitability", "label": "Profitability", "detail": "How much profit it makes"},
    {"node": "liquidity", "label": "Financial health", "detail": "Debt, cash and bills"},
    {"node": "growth", "label": "Growth", "detail": "How fast sales and profit are growing"},
    {"node": "peers", "label": "Compare with peers", "detail": "How it stacks up against similar companies"},
    {"node": "news_rag", "label": "Read filings and news", "detail": "Looking for what explains the numbers"},
    {"node": "scorecard", "label": "Score", "detail": "Overall score and buy, hold or sell rating"},
    {"node": "memo", "label": "Write the summary", "detail": "Explain the rating in plain words"},
    {"node": "critic", "label": "Double-check", "detail": "Every number and source is verified"},
]

PIPELINE_NODES = [p["node"] for p in PIPELINE]


def channel(analysis_id: str) -> str:
    return f"analysis:{analysis_id}"


async def publish(analysis_id: str, payload: dict) -> None:
    """Fire-and-forget. A dead Redis must never take down an analysis."""
    try:
        await get_redis().publish(channel(analysis_id), json.dumps(payload, default=str))
    except Exception as exc:
        log.warning("progress publish failed: %s", exc)


async def record_event(
    analysis_id: str,
    *,
    node: str,
    status: str,
    duration_ms: int | None = None,
    detail: dict | None = None,
) -> None:
    """Persist to Postgres and publish to subscribers."""
    from ..db.repo import add_event, set_status
    from ..db.session import SessionLocal

    payload = {
        "type": "node",
        "node": node,
        "status": status,
        "duration_ms": duration_ms,
        "detail": detail or {},
        "ts": time.time(),
    }
    try:
        async with SessionLocal() as db:
            await add_event(
                db, uuid.UUID(analysis_id), node=node, status=status,
                duration_ms=duration_ms, detail=detail,
            )
            if status == "start":
                await set_status(db, uuid.UUID(analysis_id), current_node=node)
    except Exception as exc:
        log.warning("could not persist event %s/%s: %s", node, status, exc)

    await publish(analysis_id, payload)


async def publish_done(analysis_id: str, *, status: str, error: str | None = None) -> None:
    await publish(
        analysis_id,
        {"type": "done", "status": status, "error": error, "ts": time.time()},
    )


NodeFn = Callable[[dict], Awaitable[dict]]


def node(name: str, *, optional: bool = False) -> Callable[[NodeFn], NodeFn]:
    """Wrap a node with timing, event emission, and a trace entry.

    ``optional=True`` means a failure degrades the analysis instead of ending it: the
    node records an error event, contributes a warning, and the graph continues. That is
    right for retrieval and peers — an analysis without news is still worth having — and
    wrong for ingest.
    """

    def decorator(fn: NodeFn) -> NodeFn:
        @functools.wraps(fn)
        async def wrapper(state: dict) -> dict:
            analysis_id = state.get("analysis_id")
            t0 = time.perf_counter()
            if analysis_id:
                await record_event(analysis_id, node=name, status="start")

            try:
                result = await fn(state)
            except Exception as exc:
                ms = int((time.perf_counter() - t0) * 1000)
                log.exception("node %s failed", name)
                if analysis_id:
                    await record_event(
                        analysis_id, node=name, status="error",
                        duration_ms=ms, detail={"error": str(exc)[:500]},
                    )
                if not optional:
                    raise
                return {
                    "warnings": [f"{name}: {exc}"],
                    "trace": [
                        {"node": name, "status": "error", "duration_ms": ms, "error": str(exc)[:500]}
                    ],
                }

            ms = int((time.perf_counter() - t0) * 1000)
            summary = _summarise(name, result)
            if analysis_id:
                await record_event(
                    analysis_id, node=name, status="ok", duration_ms=ms, detail=summary
                )

            trace_entry = {"node": name, "status": "ok", "duration_ms": ms, **summary}
            result.setdefault("trace", [])
            result["trace"] = list(result["trace"]) + [trace_entry]
            return result

        return wrapper

    return decorator


def _summarise(name: str, result: dict) -> dict[str, Any]:
    """A small, JSON-safe digest of what a node produced, shown live in the interface."""
    out: dict[str, Any] = {}
    block = result.get(name)
    if block is not None and hasattr(block, "score"):
        out["score"] = block.score
        out["metrics"] = len([m for m in block.metrics.values() if m.value is not None])
        if block.warnings:
            out["warnings"] = len(block.warnings)
    if name == "news_rag":
        out["evidence"] = len(result.get("evidence", []) or [])
        stats = result.get("retrieval_stats") or {}
        if stats:
            out["queries"] = stats.get("queries_issued")
    if name == "scorecard":
        card = result.get("scorecard") or {}
        out["rating"] = card.get("rating")
        out["total"] = card.get("total")
    if name == "critic":
        out["verdict"] = (result.get("critic_verdict") or {}).get("verdict")
    if name == "ingest":
        dq = result.get("data_quality") or {}
        out["coverage"] = dq.get("coverage")
        out["periods"] = dq.get("annual_periods")
    return out
