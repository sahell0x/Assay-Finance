"""Watchlist and side-by-side comparison.

Both are scoped to whoever is asking rather than to an account. An anonymous visitor
keeps a watchlist against their cookie exactly as they keep history, and it follows them
into an account on signup — see ``repo.migrate_anon_to_user``. The identity model in
``deps.py`` says anonymous visitors get the full feature set; these two endpoints used
to be the exception.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repo
from ..db.session import get_session
from ..deps import Requester, get_requester
from .schemas import WatchlistEntry

router = APIRouter(tags=["watchlist"])


@router.get("/watchlist", response_model=list[WatchlistEntry])
async def get_watchlist(
    requester: Requester = Depends(get_requester),
    db: AsyncSession = Depends(get_session),
) -> list[WatchlistEntry]:
    """Each ticker with its most recent completed score, so the list is worth looking at
    rather than being a bare list of symbols."""
    items = await repo.watchlist_tickers(
        db, user_id=requester.user_id, anon_id=requester.anon_id
    )
    latest = await repo.latest_complete_for_tickers(
        db,
        [i["ticker"] for i in items],
        user_id=requester.user_id,
        anon_id=requester.anon_id,
    )

    out: list[WatchlistEntry] = []
    for item in items:
        a = latest.get(item["ticker"])
        card = (a.scorecard or {}) if a else {}
        out.append(
            WatchlistEntry(
                ticker=item["ticker"],
                added_at=item["added_at"],
                rating=card.get("rating"),
                total_score=card.get("total"),
                analysis_id=a.id if a else None,
                last_run=a.completed_at if a else None,
            )
        )
    return out


@router.post("/watchlist/{ticker}", status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    ticker: str,
    requester: Requester = Depends(get_requester),
    db: AsyncSession = Depends(get_session),
) -> dict:
    ticker = ticker.strip().upper()
    if not ticker or len(ticker) > 12:
        raise HTTPException(status_code=422, detail="Enter a valid ticker symbol.")
    await repo.add_watch(
        db, ticker, user_id=requester.user_id, anon_id=requester.anon_id
    )
    return {"ticker": ticker, "watching": True}


@router.delete("/watchlist/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    ticker: str,
    requester: Requester = Depends(get_requester),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await repo.remove_watch(
        db,
        ticker.strip().upper(),
        user_id=requester.user_id,
        anon_id=requester.anon_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/compare")
async def compare(
    tickers: str = Query(description="Comma-separated symbols, up to six"),
    requester: Requester = Depends(get_requester),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Latest completed scorecard per ticker, aligned for side-by-side reading."""
    wanted = [t.strip().upper() for t in tickers.split(",") if t.strip()][:6]
    if not wanted:
        raise HTTPException(status_code=422, detail="Name at least one ticker to compare.")

    latest = await repo.latest_complete_for_tickers(
        db, wanted, user_id=requester.user_id, anon_id=requester.anon_id
    )

    columns = []
    for t in wanted:
        a = latest.get(t)
        if a is None:
            columns.append({"ticker": t, "available": False})
            continue
        card = a.scorecard or {}
        memo = a.memo or {}
        columns.append(
            {
                "ticker": t,
                "available": True,
                "analysis_id": str(a.id),
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                "rating": card.get("rating"),
                "conviction": card.get("conviction"),
                "total": card.get("total"),
                "dimension_scores": card.get("dimension_scores"),
                "price_target": card.get("price_target"),
                "thesis": memo.get("thesis"),
                "key_risks": memo.get("key_risks", [])[:3],
            }
        )

    missing = [c["ticker"] for c in columns if not c["available"]]
    return {
        "columns": columns,
        "missing": missing,
        "dimensions": ["profitability", "financial_health", "growth", "valuation", "sentiment"],
    }
