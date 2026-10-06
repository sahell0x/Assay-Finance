"""Data access. Every query the app runs lives here, so the API and worker layers stay
free of SQL and the access patterns are auditable in one place.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, delete, desc, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Analysis,
    AnalysisEvent,
    Evidence,
    UsageLedger,
    User,
    Watchlist,
    WatchlistItem,
)

# --------------------------------------------------------------------------- analyses


async def create_analysis(
    db: AsyncSession,
    *,
    ticker: str,
    peer_tickers: list[str] | None,
    weights: dict | None,
    user_id: uuid.UUID | None,
    anon_id: str | None,
    cache_key: str,
    credit_source: str | None = None,
    commit: bool = True,
) -> Analysis:
    """Insert a queued run. ``commit=False`` leaves it to the caller's transaction, which
    is how ``credits.create_charged_run`` charges the run in the same commit."""
    row = Analysis(
        ticker=ticker.upper(),
        peer_tickers=peer_tickers,
        weights=weights,
        user_id=user_id,
        anon_id=anon_id,
        cache_key=cache_key,
        credit_source=credit_source,
        status="queued",
        thread_id=str(uuid.uuid4()),
    )
    db.add(row)
    if not commit:
        await db.flush()
        return row
    await db.commit()
    await db.refresh(row)
    return row


async def get_analysis(db: AsyncSession, analysis_id: uuid.UUID) -> Analysis | None:
    return await db.get(Analysis, analysis_id)


async def get_analysis_by_slug(db: AsyncSession, slug: str) -> Analysis | None:
    res = await db.execute(select(Analysis).where(Analysis.public_slug == slug))
    return res.scalar_one_or_none()


async def find_cached(db: AsyncSession, cache_key: str) -> Analysis | None:
    """Newest completed run for this exact (ticker, peers, weights, day) key.

    The cache is global across users; the caller clones the row so history and deletion
    stay per-user.
    """
    res = await db.execute(
        select(Analysis)
        .where(Analysis.cache_key == cache_key, Analysis.status == "complete")
        .order_by(desc(Analysis.created_at))
        .limit(1)
    )
    return res.scalar_one_or_none()


async def clone_from_cache(
    db: AsyncSession,
    source: Analysis,
    *,
    user_id: uuid.UUID | None,
    anon_id: str | None,
) -> Analysis:
    """Copy a completed analysis to a new row owned by the requester.

    Events are copied too so the UI can replay the pipeline animation for a cached run.
    """
    clone = Analysis(
        ticker=source.ticker,
        peer_tickers=source.peer_tickers,
        weights=source.weights,
        user_id=user_id,
        anon_id=anon_id,
        cache_key=source.cache_key,
        cached_from=source.id,
        status="complete",
        current_node="done",
        thread_id=str(uuid.uuid4()),
        scorecard=source.scorecard,
        memo=source.memo,
        blocks=source.blocks,
        data_quality=source.data_quality,
        token_cost_usd=Decimal("0"),
        completed_at=source.completed_at,
    )
    db.add(clone)
    await db.flush()

    src_events = (
        await db.execute(
            select(AnalysisEvent)
            .where(AnalysisEvent.analysis_id == source.id)
            .order_by(AnalysisEvent.id)
        )
    ).scalars().all()
    for ev in src_events:
        db.add(
            AnalysisEvent(
                analysis_id=clone.id,
                node=ev.node,
                status=ev.status,
                duration_ms=ev.duration_ms,
                detail=ev.detail,
            )
        )

    src_evidence = (
        await db.execute(select(Evidence).where(Evidence.analysis_id == source.id))
    ).scalars().all()
    for e in src_evidence:
        db.add(
            Evidence(
                analysis_id=clone.id,
                label=e.label,
                source_type=e.source_type,
                url=e.url,
                published=e.published,
                text=e.text,
                relevance=e.relevance,
                title=e.title,
                section=e.section,
            )
        )

    await db.commit()
    await db.refresh(clone)
    return clone


async def stuck_runs(db: AsyncSession, *, older_than_s: int) -> list[tuple[uuid.UUID, str | None]]:
    """Runs still marked running long after any job could have finished. Queued rows
    are left alone: their job is still in Redis and will be picked up."""
    cutoff = datetime.now(UTC) - timedelta(seconds=older_than_s)
    res = await db.execute(
        select(Analysis.id, Analysis.anon_id).where(
            Analysis.status == "running",
            Analysis.created_at < cutoff,
        )
    )
    return [(r[0], r[1]) for r in res.all()]


async def set_status(
    db: AsyncSession,
    analysis_id: uuid.UUID,
    *,
    status: str | None = None,
    current_node: str | None = None,
    error: str | None = None,
) -> None:
    values: dict[str, Any] = {}
    if status is not None:
        values["status"] = status
        if status in {"complete", "failed"}:
            values["completed_at"] = datetime.now(UTC)
    if current_node is not None:
        values["current_node"] = current_node
    if error is not None:
        values["error"] = error[:4000]
    if not values:
        return
    await db.execute(update(Analysis).where(Analysis.id == analysis_id).values(**values))
    await db.commit()


async def save_result(
    db: AsyncSession,
    analysis_id: uuid.UUID,
    *,
    scorecard: dict | None,
    memo: dict | None,
    blocks: dict | None,
    data_quality: dict | None,
    cost_usd: float,
) -> None:
    await db.execute(
        update(Analysis)
        .where(Analysis.id == analysis_id)
        .values(
            scorecard=scorecard,
            memo=memo,
            blocks=blocks,
            data_quality=data_quality,
            token_cost_usd=Decimal(str(round(cost_usd, 4))),
            status="complete",
            current_node="done",
            completed_at=datetime.now(UTC),
        )
    )
    await db.commit()


async def list_analyses(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    anon_id: str | None = None,
    ticker: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Analysis]:
    q = select(Analysis)
    if user_id is not None:
        q = q.where(Analysis.user_id == user_id)
    elif anon_id is not None:
        q = q.where(Analysis.anon_id == anon_id)
    else:
        return []
    if ticker:
        q = q.where(Analysis.ticker == ticker.upper())
    q = q.order_by(desc(Analysis.created_at)).limit(limit).offset(offset)
    return list((await db.execute(q)).scalars().all())


async def delete_analysis(db: AsyncSession, analysis_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    res = await db.execute(
        delete(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == user_id)
    )
    await db.commit()
    return res.rowcount > 0


async def ensure_public_slug(db: AsyncSession, analysis: Analysis) -> str:
    if analysis.public_slug:
        return analysis.public_slug
    slug = f"{analysis.ticker.lower()}-{secrets.token_urlsafe(7).rstrip('=').lower()}"
    await db.execute(
        update(Analysis).where(Analysis.id == analysis.id).values(public_slug=slug)
    )
    await db.commit()
    analysis.public_slug = slug
    return slug


async def ticker_history(
    db: AsyncSession, user_id: uuid.UUID, ticker: str, limit: int = 60
) -> list[Analysis]:
    res = await db.execute(
        select(Analysis)
        .where(
            Analysis.user_id == user_id,
            Analysis.ticker == ticker.upper(),
            Analysis.status == "complete",
        )
        .order_by(Analysis.created_at)
        .limit(limit)
    )
    return list(res.scalars().all())


# ----------------------------------------------------------------------------- events


async def add_event(
    db: AsyncSession,
    analysis_id: uuid.UUID,
    *,
    node: str,
    status: str,
    duration_ms: int | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        AnalysisEvent(
            analysis_id=analysis_id,
            node=node,
            status=status,
            duration_ms=duration_ms,
            detail=detail,
        )
    )
    await db.commit()


async def list_events(db: AsyncSession, analysis_id: uuid.UUID) -> list[AnalysisEvent]:
    res = await db.execute(
        select(AnalysisEvent)
        .where(AnalysisEvent.analysis_id == analysis_id)
        .order_by(AnalysisEvent.id)
    )
    return list(res.scalars().all())


# --------------------------------------------------------------------------- evidence


async def replace_evidence(
    db: AsyncSession, analysis_id: uuid.UUID, items: list[dict]
) -> None:
    await db.execute(delete(Evidence).where(Evidence.analysis_id == analysis_id))
    for it in items:
        pub = it.get("published")
        if isinstance(pub, str):
            try:
                pub = date.fromisoformat(pub[:10])
            except ValueError:
                pub = None
        db.add(
            Evidence(
                analysis_id=analysis_id,
                label=it["label"],
                source_type=it.get("source_type", "unknown"),
                url=it.get("url"),
                published=pub,
                text=it.get("text", ""),
                relevance=it.get("relevance"),
                title=it.get("title"),
                section=it.get("section"),
            )
        )
    await db.commit()


async def list_evidence(db: AsyncSession, analysis_id: uuid.UUID) -> list[Evidence]:
    res = await db.execute(
        select(Evidence).where(Evidence.analysis_id == analysis_id).order_by(Evidence.label)
    )
    items = list(res.scalars().all())
    # "S10" must sort after "S9".
    items.sort(key=lambda e: int(e.label.lstrip("S") or 0))
    return items


# ------------------------------------------------------------------------------ usage


async def record_usage(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    anon_id: str | None,
    analysis_id: uuid.UUID | None,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
) -> None:
    db.add(
        UsageLedger(
            user_id=user_id,
            anon_id=anon_id,
            analysis_id=analysis_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=Decimal(str(round(cost_usd, 4))),
        )
    )
    await db.commit()


async def count_runs_for_anon(db: AsyncSession, anon_id: str) -> int:
    res = await db.execute(
        select(func.count())
        .select_from(Analysis)
        .where(Analysis.anon_id == anon_id, Analysis.cached_from.is_(None))
    )
    return int(res.scalar_one())


async def month_cost(db: AsyncSession, user_id: uuid.UUID) -> float:
    since = datetime.now(UTC) - timedelta(days=30)
    res = await db.execute(
        select(func.coalesce(func.sum(UsageLedger.cost_usd), 0)).where(
            UsageLedger.user_id == user_id, UsageLedger.created_at >= since
        )
    )
    return float(res.scalar_one())


# -------------------------------------------------------------------------- watchlist


def _owner_clause(model, user_id: uuid.UUID | None, anon_id: str | None):
    """Scope a query to one owner.

    Signed-in wins when both are present: a request carrying a session cookie *and* a
    stale anonymous cookie belongs to the account, and matching either would let one
    visitor read another's rows after a cookie was reused.
    """
    if user_id is not None:
        return model.user_id == user_id
    if anon_id is not None:
        return and_(model.user_id.is_(None), model.anon_id == anon_id)
    return None


async def get_or_create_watchlist(
    db: AsyncSession,
    user_id: uuid.UUID | None = None,
    anon_id: str | None = None,
) -> Watchlist | None:
    """The owner's single watchlist, created on first use.

    Returns None for a request that identifies nobody, which the callers translate into
    an empty list rather than a row owned by no one.
    """
    clause = _owner_clause(Watchlist, user_id, anon_id)
    if clause is None:
        return None
    res = await db.execute(select(Watchlist).where(clause).limit(1))
    wl = res.scalar_one_or_none()
    if wl is None:
        wl = Watchlist(
            user_id=user_id,
            anon_id=None if user_id is not None else anon_id,
            name="Default",
        )
        db.add(wl)
        await db.commit()
        await db.refresh(wl)
    return wl


async def watchlist_tickers(
    db: AsyncSession,
    user_id: uuid.UUID | None = None,
    anon_id: str | None = None,
) -> list[dict]:
    wl = await get_or_create_watchlist(db, user_id, anon_id)
    if wl is None:
        return []
    res = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.watchlist_id == wl.id)
        .order_by(desc(WatchlistItem.added_at))
    )
    return [{"ticker": i.ticker, "added_at": i.added_at} for i in res.scalars().all()]


async def add_watch(
    db: AsyncSession,
    ticker: str,
    user_id: uuid.UUID | None = None,
    anon_id: str | None = None,
) -> None:
    wl = await get_or_create_watchlist(db, user_id, anon_id)
    if wl is None:
        return
    exists = await db.get(WatchlistItem, (wl.id, ticker.upper()))
    if exists:
        return
    db.add(WatchlistItem(watchlist_id=wl.id, ticker=ticker.upper()))
    await db.commit()


async def remove_watch(
    db: AsyncSession,
    ticker: str,
    user_id: uuid.UUID | None = None,
    anon_id: str | None = None,
) -> None:
    wl = await get_or_create_watchlist(db, user_id, anon_id)
    if wl is None:
        return
    await db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.watchlist_id == wl.id, WatchlistItem.ticker == ticker.upper()
        )
    )
    await db.commit()


async def latest_complete_for_tickers(
    db: AsyncSession,
    tickers: list[str],
    user_id: uuid.UUID | None = None,
    anon_id: str | None = None,
) -> dict[str, Analysis]:
    """Most recent completed analysis per ticker, for watchlist and compare views."""
    if not tickers:
        return {}
    clause = _owner_clause(Analysis, user_id, anon_id)
    if clause is None:
        return {}
    res = await db.execute(
        select(Analysis)
        .where(
            clause,
            Analysis.ticker.in_([t.upper() for t in tickers]),
            Analysis.status == "complete",
        )
        .order_by(Analysis.ticker, desc(Analysis.created_at))
    )
    out: dict[str, Analysis] = {}
    for row in res.scalars().all():
        out.setdefault(row.ticker, row)
    return out


# ----------------------------------------------------------------------- anon -> user


async def migrate_anon_to_user(
    db: AsyncSession, anon_id: str, user_id: uuid.UUID
) -> int:
    """Called on signup/login so a visitor's work follows them into their account.

    Analyses, the usage ledger and the watchlist all move. Whatever a visitor built
    anonymously is what makes the account worth creating, so leaving any of it behind
    turns signing up into a reset.
    """
    res = await db.execute(
        update(Analysis)
        .where(Analysis.anon_id == anon_id, Analysis.user_id.is_(None))
        .values(user_id=user_id)
    )
    await db.execute(
        update(UsageLedger)
        .where(UsageLedger.anon_id == anon_id, UsageLedger.user_id.is_(None))
        .values(user_id=user_id)
    )
    await _migrate_anon_watchlist(db, anon_id, user_id)
    await db.commit()
    return res.rowcount or 0


async def _migrate_anon_watchlist(
    db: AsyncSession, anon_id: str, user_id: uuid.UUID
) -> None:
    """Fold the cookie's watchlist into the account's.

    An account created from a browser that already had a watchlist can end up with two
    rows, and ``get_or_create_watchlist`` would then return an arbitrary one. The items
    are merged into whichever watchlist the user already has and the anonymous row is
    dropped; ``ON CONFLICT DO NOTHING`` covers a ticker present in both.
    """
    anon_wl = (
        await db.execute(
            select(Watchlist)
            .where(Watchlist.anon_id == anon_id, Watchlist.user_id.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()
    if anon_wl is None:
        return

    user_wl = (
        await db.execute(select(Watchlist).where(Watchlist.user_id == user_id).limit(1))
    ).scalar_one_or_none()

    if user_wl is None:
        anon_wl.user_id = user_id
        anon_wl.anon_id = None
        return

    await db.execute(
        pg_insert(WatchlistItem)
        .from_select(
            ["watchlist_id", "ticker", "added_at"],
            select(
                literal(user_wl.id).label("watchlist_id"),
                WatchlistItem.ticker,
                WatchlistItem.added_at,
            ).where(WatchlistItem.watchlist_id == anon_wl.id),
        )
        .on_conflict_do_nothing(index_elements=["watchlist_id", "ticker"])
    )
    await db.delete(anon_wl)


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)
