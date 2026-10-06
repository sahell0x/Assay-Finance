"""The analysis endpoints.

Three things here are worth reading carefully.

**Nothing runs in the request handler.** A full analysis takes 60-90 seconds; ``POST
/analyses`` enqueues an ARQ job and returns 202 immediately.

**Cached results still animate.** A cache hit clones the stored run *and its events*,
then replays those events over SSE at roughly an eighth of their recorded timings. The
pipeline visualisation is the most informative thing in the interface and a cached
result that skipped straight to the answer would throw it away. It is badged as cached
with the original date, and a "Run live instead" control is offered.

**Progress replays on connect.** A browser that refreshes mid-run gets the current state
of every node before the live stream starts, so it never shows an empty checklist for a
job that is most of the way done.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.progress import PIPELINE, PIPELINE_NODES, channel
from ..analytics import scenario
from ..config import settings
from ..core.budget import public_budget_state
from ..core.cache import analysis_cache_key, get_redis
from ..db import credits, repo
from ..db.models import Analysis
from ..db.session import get_session
from ..deps import (
    Requester,
    check_quota,
    consume_quota,
    get_requester,
    out_of_credits_reason,
    release_quota,
    require_user,
    usage_state,
)
from .schemas import (
    AnalysisAccepted,
    AnalysisDetail,
    AnalysisRequest,
    AnalysisSummary,
    EvidenceOut,
    ScenarioRequest,
    ShowcaseCard,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["analyses"])

# Cached runs replay at 1/8 of real time: fast enough not to feel like a wait, slow
# enough that the sequence reads as a pipeline rather than a flicker.
REPLAY_SPEEDUP = 8
REPLAY_MIN_MS = 90
REPLAY_MAX_MS = 700


def _owns(analysis: Analysis, requester: Requester) -> bool:
    if requester.is_authenticated and analysis.user_id == requester.user_id:
        return True
    return bool(
        not requester.is_authenticated
        and analysis.anon_id
        and analysis.anon_id == requester.anon_id
    )


def _summary(a: Analysis) -> AnalysisSummary:
    card = a.scorecard or {}
    return AnalysisSummary(
        id=a.id,
        ticker=a.ticker,
        status=a.status,
        rating=card.get("rating"),
        conviction=card.get("conviction"),
        total_score=card.get("total"),
        created_at=a.created_at,
        completed_at=a.completed_at,
        cached=a.cached_from is not None,
        error=a.error,
    )


# Run instrumentation: token counts, model names, per-call cost, node timings. It stays
# in the database for the operator (usage ledger, logs, scripts/doctor.py) and is never
# sent to a browser — end users have no use for it, and anyone could read it from the
# network tab, including on public share links.
_INTERNAL_BLOCKS = frozenset({"cost", "trace"})


async def _detail(db: AsyncSession, a: Analysis, *, owned: bool) -> AnalysisDetail:
    events = await repo.list_events(db, a.id)
    evidence = await repo.list_evidence(db, a.id)

    return AnalysisDetail(
        id=a.id,
        ticker=a.ticker,
        status=a.status,
        current_node=a.current_node,
        peer_tickers=a.peer_tickers,
        weights=a.weights,
        scorecard=a.scorecard,
        memo=a.memo,
        blocks=(
            {k: v for k, v in a.blocks.items() if k not in _INTERNAL_BLOCKS}
            if a.blocks
            else a.blocks
        ),
        data_quality=a.data_quality,
        evidence=[
            EvidenceOut(
                label=e.label,
                source_type=e.source_type,
                section=e.section,
                title=e.title,
                url=e.url,
                published=e.published.isoformat() if e.published else None,
                text=e.text,
                relevance=e.relevance,
            )
            for e in evidence
        ],
        events=[
            {
                "node": e.node,
                "status": e.status,
                "duration_ms": e.duration_ms,
                "detail": e.detail,
                "at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        pipeline=PIPELINE,
        cached=a.cached_from is not None,
        cached_at=a.completed_at if a.cached_from is not None else None,
        public_slug=a.public_slug,
        error=a.error,
        created_at=a.created_at,
        completed_at=a.completed_at,
        owned=owned,
    )


# ------------------------------------------------------------------------- create


@router.post("/analyses", response_model=AnalysisAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    payload: AnalysisRequest,
    response: Response,
    requester: Requester = Depends(get_requester),
    db: AsyncSession = Depends(get_session),
) -> AnalysisAccepted:
    # 0. A company name typed where a ticker belongs ("APPLE") would otherwise queue a
    #    run that can only fail. Refuse it before anything is charged, with the likely
    #    tickers attached so the interface can offer them.
    from .tickers import check_ticker, private_company_named

    listed, suggestions = await check_ticker(payload.ticker)
    private = None if listed else await private_company_named(payload.ticker)
    if private:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "unknown_ticker",
                "message": (
                    f"{private} is a private company, so it is not on the stock market "
                    "and does not publish the financial reports this analysis needs."
                ),
                "suggestions": [],
            },
        )
    if not listed:
        hint = (
            f" Did you mean {suggestions[0]['ticker']} ({suggestions[0]['name']})?"
            if suggestions else " Use its ticker symbol, for example AAPL for Apple."
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "unknown_ticker",
                "message": f"{payload.ticker} is not a stock ticker we recognize.{hint}",
                "suggestions": [
                    {"ticker": s["ticker"], "name": s["name"]} for s in suggestions
                ],
            },
        )

    budget = await public_budget_state()
    cache_key = analysis_cache_key(payload.ticker, payload.peer_tickers, payload.weights)

    # 1. Serve from the global cache when we can. It costs nothing, so it does not
    #    consume quota and it works even with the daily budget exhausted.
    if not payload.force_refresh:
        cached = await repo.find_cached(db, cache_key)
        if cached is not None:
            clone = await repo.clone_from_cache(
                db, cached, user_id=requester.user_id, anon_id=requester.anon_id
            )
            return AnalysisAccepted(
                id=clone.id,
                status="complete",
                ticker=clone.ticker,
                cached=True,
                cached_at=cached.completed_at,
                stream_url=f"/analyses/{clone.id}/stream",
                poll_url=f"/analyses/{clone.id}",
                budget=budget,
                quota=(await usage_state(requester, db)),
            )

    # 2. Budget guard. Never an error — cached results keep flowing and the interface
    #    renders a banner explaining why nothing new is being computed.
    if budget["exhausted"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "budget_exhausted",
                "message": (
                    "Today's compute budget for new analyses is spent. Analyses that "
                    "have already been run are still available, and the budget resets "
                    "at midnight UTC."
                ),
                "budget": budget,
            },
        )

    # 3. Quota.
    quota = await check_quota(requester, db)

    def exhausted(usage: dict, reason: str | None) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "quota_exhausted",
                "message": reason,
                "quota": quota.as_dict(),
                "usage": usage,
            },
        )

    if not quota.allowed:
        raise exhausted(await usage_state(requester, db), quota.reason)

    run = {
        "ticker": payload.ticker,
        "peer_tickers": payload.peer_tickers or None,
        "weights": payload.weights,
        "cache_key": cache_key,
    }
    if requester.is_authenticated:
        # Charged in the same transaction as the insert: free allowance first, then a
        # bought credit. None means a parallel request took the last one.
        row = await credits.create_charged_run(db, user_id=requester.user_id, **run)
        if row is None:
            raise exhausted(
                await usage_state(requester, db),
                await out_of_credits_reason(db, requester.user_id),
            )
    else:
        row = await repo.create_analysis(
            db, user_id=None, anon_id=requester.anon_id, credit_source="anon", **run
        )
    await consume_quota(requester)

    try:
        from ..worker import enqueue_analysis

        await enqueue_analysis(str(row.id))
    except Exception as exc:
        log.exception("could not enqueue %s", row.id)
        await release_quota(requester)
        await repo.set_status(
            db, row.id, status="failed",
            error="The analysis queue is unavailable. Nothing was charged against your allowance.",
        )
        await credits.refund_run(db, row.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The analysis queue is unavailable. Please try again shortly.",
        ) from exc

    return AnalysisAccepted(
        id=row.id,
        status="queued",
        ticker=row.ticker,
        cached=False,
        stream_url=f"/analyses/{row.id}/stream",
        poll_url=f"/analyses/{row.id}",
        budget=budget,
        quota=(await usage_state(requester, db)),
    )


# --------------------------------------------------------------------------- read


@router.get("/analyses", response_model=list[AnalysisSummary])
async def list_analyses(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    requester: Requester = Depends(get_requester),
    db: AsyncSession = Depends(get_session),
) -> list[AnalysisSummary]:
    """History for whoever is asking — account-scoped when signed in, cookie-scoped
    otherwise, so an anonymous visitor can still see what they ran."""
    rows = await repo.list_analyses(
        db,
        user_id=requester.user_id,
        anon_id=requester.anon_id,
        ticker=ticker,
        limit=limit,
        offset=offset,
    )
    return [_summary(r) for r in rows]


@router.get("/analyses/{analysis_id}", response_model=AnalysisDetail)
async def get_analysis(
    analysis_id: uuid.UUID,
    requester: Requester = Depends(get_requester),
    db: AsyncSession = Depends(get_session),
) -> AnalysisDetail:
    a = await repo.get_analysis(db, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="No analysis with that id.")
    return await _detail(db, a, owned=_owns(a, requester))


# ------------------------------------------------------------------------- scenarios


async def _scored_analysis(db: AsyncSession, analysis_id: uuid.UUID) -> Analysis:
    """An analysis that finished with a scorecard, or the reason it cannot be used.

    A scenario is arithmetic over a stored result. There is nothing to vary until the
    run has produced one, and a half-finished analysis should say so rather than hand
    back an empty panel.
    """
    a = await repo.get_analysis(db, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="No analysis with that id.")
    if not (a.scorecard or {}).get("dimension_scores"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This analysis has no scorecard yet, so there is nothing to vary.",
        )
    return a


@router.get("/analyses/{analysis_id}/scenario")
async def scenario_setup(
    analysis_id: uuid.UUID,
    target: str | None = Query(default=None, pattern="^(BUY|HOLD|SELL)$"),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """What can be varied on this analysis, and what would change the rating.

    Readable by whoever can read the analysis itself — a scenario exposes nothing the
    detail endpoint does not already return, because it is computed from it.
    """
    a = await _scored_analysis(db, analysis_id)
    card = a.scorecard or {}
    target_rating = target or scenario.default_target(card.get("rating"))

    return {
        "ticker": a.ticker,
        "baseline": {
            "total": card.get("total"),
            "rating": card.get("rating"),
            "conviction": card.get("conviction"),
            "distance_to_edge": card.get("distance_to_edge"),
            "dimension_scores": card.get("dimension_scores"),
            "weights_applied": card.get("weights_applied"),
            "price_target": card.get("price_target"),
        },
        "thresholds": card.get("thresholds") or {},
        "levers": scenario.levers_for(card),
        "target_rating": target_rating,
        "paths": scenario.solve_paths(card, target_rating=target_rating),
    }


@router.post("/analyses/{analysis_id}/scenario")
async def run_scenario(
    analysis_id: uuid.UUID,
    body: ScenarioRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Re-run the rubric over a stored analysis with some inputs moved.

    No quota, no budget and no queue: this reads one row and folds numbers. It calls the
    same ``scoring.py`` the pipeline called, so a scenario with no overrides returns the
    stored card and the panel can never disagree with the memo about the arithmetic.
    """
    a = await _scored_analysis(db, analysis_id)
    return scenario.recompute(
        a.scorecard or {}, overrides=body.overrides, weights=body.weights
    )


@router.delete("/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    analysis_id: uuid.UUID,
    requester: Requester = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    deleted = await repo.delete_analysis(db, analysis_id, requester.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No analysis with that id.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------- SSE


async def _current_progress(db: AsyncSession, analysis_id: uuid.UUID) -> dict:
    """A full snapshot, so a reconnecting browser rebuilds the checklist immediately."""
    a = await repo.get_analysis(db, analysis_id)
    if a is None:
        return {"type": "error", "message": "No analysis with that id."}

    events = await repo.list_events(db, analysis_id)
    by_node: dict[str, dict] = {}
    for e in events:
        by_node[e.node] = {
            "node": e.node,
            "status": e.status,
            "duration_ms": e.duration_ms,
            "detail": e.detail,
        }

    return {
        "type": "snapshot",
        "status": a.status,
        "current_node": a.current_node,
        "cached": a.cached_from is not None,
        "nodes": [by_node.get(n, {"node": n, "status": "pending"}) for n in PIPELINE_NODES],
        "pipeline": PIPELINE,
    }


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


@router.get("/analyses/{analysis_id}/stream")
async def stream_analysis(
    analysis_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    a = await repo.get_analysis(db, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="No analysis with that id.")

    is_cached_or_done = a.status in {"complete", "failed"}
    events = await repo.list_events(db, analysis_id) if is_cached_or_done else []
    snapshot = await _current_progress(db, analysis_id)

    async def generate():
        # Always replay first: a mid-run refresh must not show an empty checklist.
        yield _sse(snapshot)

        if is_cached_or_done:
            # Replay the stored timeline so a cached result still shows its pipeline.
            async for chunk in _replay(analysis_id, events, a.status):
                yield chunk
            return

        redis = get_redis()
        pubsub = redis.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(channel(str(analysis_id)))
        try:
            idle = 0
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(timeout=1.0)
                if message is None:
                    idle += 1
                    # A comment frame keeps proxies from closing an idle connection.
                    yield ": keep-alive\n\n"
                    if idle > 300:  # five minutes with no traffic
                        yield _sse({"type": "done", "status": "timeout"})
                        break
                    continue

                idle = 0
                try:
                    payload = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                yield _sse(payload)
                if payload.get("type") == "done":
                    break
        finally:
            try:
                await pubsub.unsubscribe(channel(str(analysis_id)))
                await pubsub.aclose()
            except Exception:
                pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _replay(analysis_id: uuid.UUID, events, final_status: str):
    """Re-emit a completed run's events at a fraction of their original timings."""
    yield _sse({"type": "replay", "speedup": REPLAY_SPEEDUP, "events": len(events)})

    for e in events:
        delay_ms = (e.duration_ms or 200) / REPLAY_SPEEDUP
        delay_ms = max(REPLAY_MIN_MS, min(REPLAY_MAX_MS, delay_ms))
        if e.status == "start":
            yield _sse({"type": "node", "node": e.node, "status": "start", "replayed": True})
            await asyncio.sleep(delay_ms / 1000)
        else:
            yield _sse(
                {
                    "type": "node",
                    "node": e.node,
                    "status": e.status,
                    "duration_ms": e.duration_ms,
                    "detail": e.detail,
                    "replayed": True,
                }
            )
            await asyncio.sleep(0.04)

    yield _sse({"type": "done", "status": final_status, "replayed": True})


# ------------------------------------------------------------------------ sharing


@router.post("/analyses/{analysis_id}/share")
async def share_analysis(
    analysis_id: uuid.UUID,
    requester: Requester = Depends(get_requester),
    db: AsyncSession = Depends(get_session),
) -> dict:
    a = await repo.get_analysis(db, analysis_id)
    if a is None:
        raise HTTPException(status_code=404, detail="No analysis with that id.")
    if not _owns(a, requester):
        raise HTTPException(status_code=403, detail="This analysis belongs to someone else.")
    if a.status != "complete":
        raise HTTPException(status_code=409, detail="Only completed analyses can be shared.")
    slug = await repo.ensure_public_slug(db, a)
    return {"slug": slug, "url": f"{settings.frontend_url}/m/{slug}"}


# Declared before the /public/{slug} route: a path parameter would otherwise swallow
# "sample" and this would never be reachable.
@router.get("/public/sample/memo", response_model=AnalysisDetail)
async def sample_memo(db: AsyncSession = Depends(get_session)) -> AnalysisDetail:
    """The memo the landing page renders.

    The landing page shows real output rather than a mockup, so it needs a completed
    analysis to serve. Preference order: the configured sample ticker, then any
    completed run, newest first.
    """
    from sqlalchemy import desc, select

    for condition in (
        (Analysis.ticker == settings.sample_ticker.upper(),),
        (),
    ):
        result = await db.execute(
            select(Analysis)
            .where(Analysis.status == "complete", Analysis.memo.isnot(None), *condition)
            .order_by(desc(Analysis.completed_at))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return await _detail(db, row, owned=False)

    raise HTTPException(
        status_code=404,
        detail="No completed analysis is available to show yet.",
    )


@router.get("/public/showcase", response_model=list[ShowcaseCard])
async def showcase(
    limit: int = Query(default=6, ge=1, le=12),
    db: AsyncSession = Depends(get_session),
) -> list[ShowcaseCard]:
    """The companies the landing page offers a visitor to look through.

    One card per ticker, newest first, so a ticker analysed ten times appears once
    rather than filling the row. Declared before ``/public/{slug}`` for the same reason
    the sample route is: a path parameter would otherwise swallow "showcase".
    """
    from sqlalchemy import desc, select

    # Over-fetch, then keep the newest per ticker. DISTINCT ON would push the ordering
    # into the database, but it would also have to order by ticker first, and the row
    # order this page wants is by recency.
    result = await db.execute(
        select(Analysis)
        .where(Analysis.status == "complete", Analysis.memo.isnot(None))
        .order_by(desc(Analysis.completed_at))
        .limit(limit * 6)
    )

    seen: set[str] = set()
    cards: list[ShowcaseCard] = []
    for a in result.scalars().all():
        if a.ticker in seen:
            continue
        seen.add(a.ticker)
        card = a.scorecard or {}
        memo = a.memo or {}
        market = (a.blocks or {}).get("market") or {}
        cards.append(
            ShowcaseCard(
                id=a.id,
                ticker=a.ticker,
                name=market.get("name"),
                sector=market.get("sector"),
                rating=card.get("rating"),
                conviction=card.get("conviction"),
                total_score=card.get("total"),
                dimension_scores=card.get("dimension_scores") or {},
                price=market.get("price"),
                currency=market.get("currency"),
                market_cap=market.get("market_cap"),
                thesis=memo.get("thesis"),
                completed_at=a.completed_at,
            )
        )
        if len(cards) >= limit:
            break

    return cards


@router.get("/public/{slug}", response_model=AnalysisDetail)
async def public_memo(
    slug: str, db: AsyncSession = Depends(get_session)
) -> AnalysisDetail:
    a = await repo.get_analysis_by_slug(db, slug)
    if a is None or a.status != "complete":
        raise HTTPException(status_code=404, detail="No shared memo at that address.")
    return await _detail(db, a, owned=False)


# -------------------------------------------------------------------------- usage


@router.get("/usage")
async def get_usage(
    requester: Requester = Depends(get_requester),
    db: AsyncSession = Depends(get_session),
) -> dict:
    return await usage_state(requester, db)
