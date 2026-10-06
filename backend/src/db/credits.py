"""Credit accounting for signed-in users: the one-time free credits and bought credits.

Kept apart from ``repo.py`` because every function here is a small transaction with a
rule attached, and the rules only hold if they are read together:

* **Free first, then paid.** A new account gets ``FREE_ACCOUNT_CREDITS`` once, never
  topped up. A run uses those while any are left, and a bought credit only after that.
  Runs made anonymously before signing up came out of the visitor allowance and are not
  counted again when they move into the account.
* **Charged with the row, under a lock.** Deciding which allowance pays and inserting
  the analysis happen in one transaction holding a per-user advisory lock, so two runs
  started in the same instant cannot both take the last credit.
* **Every change is a ledger row.** ``credit_transactions`` records each purchase,
  spend and refund with the balance it left. Free runs are recorded too (``free_spend``,
  delta 0), which is what the free credits are counted from: counting ``analyses`` rows
  let a user delete runs to get free credits back.
* **Idempotent.** A purchase is granted once however many times Razorpay or the browser
  confirms it, and a failed run is refunded once however many times it is failed.
* **Test-mode limits hold at the grant, not only at the order.** The shop refuses an
  order that would go over the limit, but someone can open several orders before paying
  any of them. So the limit is checked again under the user's lock when a payment is
  confirmed, and a payment over it is rejected (and refunded by the caller).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from . import repo
from .models import Analysis, CreditPurchase, CreditTransaction, User

# Every ledger kind a user sees in their activity, grouped the way the page filters them.
USAGE_KINDS = ("spend", "refund", "free_spend", "free_refund")
PURCHASE_KINDS = ("purchase",)


async def _lock_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Serialise credit changes for one user until the transaction ends."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"credits:{user_id}"},
    )


async def paid_balance(db: AsyncSession, user_id: uuid.UUID) -> int:
    res = await db.execute(select(User.paid_credits).where(User.id == user_id))
    return int(res.scalar_one_or_none() or 0)


async def free_used(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Free credits this account has used, ever, net of failed runs given back.

    Runs from before the ledger existed have no ``credit_source`` and are counted from
    the analyses table, so shipping the ledger is not a free top-up. Runs that began
    anonymously (``anon_id`` set) are left out: they came out of the visitor allowance.
    """
    legacy = await db.execute(
        select(func.count())
        .select_from(Analysis)
        .where(
            Analysis.user_id == user_id,
            Analysis.anon_id.is_(None),
            Analysis.cached_from.is_(None),
            Analysis.status != "failed",
            Analysis.credit_source.is_(None),
        )
    )
    net = await db.execute(
        select(
            func.count().filter(CreditTransaction.kind == "free_spend")
            - func.count().filter(CreditTransaction.kind == "free_refund")
        ).where(CreditTransaction.user_id == user_id)
    )
    return int(legacy.scalar_one()) + max(int(net.scalar_one() or 0), 0)


async def create_charged_run(
    db: AsyncSession, *, user_id: uuid.UUID, **analysis: object
) -> Analysis | None:
    """Insert a signed-in user's run and charge it, or return None if they have nothing
    left. ``analysis`` is passed through to ``repo.create_analysis``."""
    await _lock_user(db, user_id)

    if await free_used(db, user_id) < settings.free_account_credits:
        source, delta = "free", 0
        balance = await paid_balance(db, user_id)
    else:
        res = await db.execute(
            update(User)
            .where(User.id == user_id, User.paid_credits > 0)
            .values(paid_credits=User.paid_credits - 1)
            .returning(User.paid_credits)
        )
        remaining = res.scalar_one_or_none()
        if remaining is None:
            await db.rollback()
            return None
        source, delta, balance = "paid", -1, int(remaining)

    row = await repo.create_analysis(
        db, user_id=user_id, anon_id=None, credit_source=source, commit=False, **analysis
    )
    db.add(
        CreditTransaction(
            user_id=user_id,
            kind="spend" if source == "paid" else "free_spend",
            delta=delta,
            balance_after=balance,
            analysis_id=row.id,
        )
    )
    await db.commit()
    await db.refresh(row)
    return row


async def refund_run(db: AsyncSession, analysis_id: uuid.UUID) -> bool:
    """Give back whatever a failed run was charged. Safe to call more than once."""
    res = await db.execute(
        select(Analysis.user_id, Analysis.credit_source).where(Analysis.id == analysis_id)
    )
    found = res.first()
    if found is None or found.user_id is None or found.credit_source not in {"free", "paid"}:
        return False
    user_id, source = found.user_id, found.credit_source
    kind = "refund" if source == "paid" else "free_refund"

    await _lock_user(db, user_id)
    already = await db.execute(
        select(CreditTransaction.id).where(
            CreditTransaction.analysis_id == analysis_id, CreditTransaction.kind == kind
        )
    )
    if already.first() is not None:
        await db.rollback()
        return False

    if source == "paid":
        res = await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(paid_credits=User.paid_credits + 1)
            .returning(User.paid_credits)
        )
        delta, balance = 1, int(res.scalar_one())
    else:
        delta, balance = 0, await paid_balance(db, user_id)

    db.add(
        CreditTransaction(
            user_id=user_id, kind=kind, delta=delta, balance_after=balance,
            analysis_id=analysis_id,
        )
    )
    await db.commit()
    return True


# ------------------------------------------------------------------- purchases


async def purchase_totals(db: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    """How many purchases this user has completed, and how many credits they bought."""
    res = await db.execute(
        select(func.count(), func.coalesce(func.sum(CreditPurchase.credits), 0)).where(
            CreditPurchase.user_id == user_id, CreditPurchase.status == "paid"
        )
    )
    count, total = res.one()
    return int(count), int(total)


def test_limit_problem(purchases: int, bought: int, pack_credits: int) -> str | None:
    """Why buying ``pack_credits`` more would break the test-mode limit, or None."""
    if not settings.payments_test_mode:
        return None
    if purchases >= settings.test_max_purchases:
        return (
            f"You have made all {settings.test_max_purchases} test purchases this demo "
            f"allows. Payments here run in Razorpay test mode and never take real money, "
            f"so the amount anyone can buy is kept small."
        )
    room = settings.test_max_credits - bought
    if pack_credits > room:
        return (
            f"This pack would take you past the {settings.test_max_credits}-credit limit "
            f"for test purchases."
            + (f" You can still buy up to {room} more." if room > 0 else "")
            + " Payments here run in Razorpay test mode and never take real money."
        )
    return None


def test_limits(purchases: int, bought: int) -> dict | None:
    """The limit as the shop shows it. None when payments are live."""
    if not settings.payments_test_mode:
        return None
    return {
        "max_purchases": settings.test_max_purchases,
        "max_credits": settings.test_max_credits,
        "purchases_used": purchases,
        "credits_bought": bought,
        "purchases_left": max(settings.test_max_purchases - purchases, 0),
        "credits_left": max(settings.test_max_credits - bought, 0)
        if purchases < settings.test_max_purchases
        else 0,
    }


async def create_purchase(db: AsyncSession, *, user_id: uuid.UUID, pack: dict) -> CreditPurchase:
    purchase = CreditPurchase(
        user_id=user_id,
        pack_id=pack["id"],
        credits=int(pack["credits"]),
        amount_paise=int(pack["price_paise"]),
        currency=settings.currency,
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)
    return purchase


async def attach_order(db: AsyncSession, purchase_id: uuid.UUID, order_id: str) -> None:
    await db.execute(
        update(CreditPurchase)
        .where(CreditPurchase.id == purchase_id)
        .values(razorpay_order_id=order_id)
    )
    await db.commit()


async def get_purchase_by_order(db: AsyncSession, order_id: str) -> CreditPurchase | None:
    res = await db.execute(
        select(CreditPurchase).where(CreditPurchase.razorpay_order_id == order_id)
    )
    return res.scalar_one_or_none()


async def grant_purchase(
    db: AsyncSession, *, order_id: str, payment_id: str
) -> tuple[CreditPurchase | None, str]:
    """Settle a paid order. Returns ``(purchase, outcome)`` where outcome is one of:

    * ``granted`` — the credits were added now;
    * ``already`` — an earlier confirmation already settled it (granted or rejected);
    * ``over_limit`` — paid, but over the test-mode limit: nothing was added and the
      caller should refund the payment;
    * ``unknown`` — not an order this app created.

    The row lock makes the browser callback and the webhook safe to race: the second one
    to arrive finds the purchase settled and changes nothing.
    """
    res = await db.execute(
        select(CreditPurchase)
        .where(CreditPurchase.razorpay_order_id == order_id)
        .with_for_update()
    )
    purchase = res.scalar_one_or_none()
    if purchase is None:
        await db.rollback()
        return None, "unknown"
    if purchase.status != "created":
        # Commit, not rollback: nothing changed, and a rollback would expire the row the
        # caller is about to read.
        await db.commit()
        return purchase, "already"

    await _lock_user(db, purchase.user_id)
    purchase.razorpay_payment_id = payment_id
    purchase.paid_at = datetime.now(UTC)

    count, bought = await purchase_totals(db, purchase.user_id)
    if test_limit_problem(count, bought, purchase.credits):
        purchase.status = "over_limit"
        await db.commit()
        await db.refresh(purchase)
        return purchase, "over_limit"

    purchase.status = "paid"
    res = await db.execute(
        update(User)
        .where(User.id == purchase.user_id)
        .values(paid_credits=User.paid_credits + purchase.credits)
        .returning(User.paid_credits)
    )
    db.add(
        CreditTransaction(
            user_id=purchase.user_id,
            kind="purchase",
            delta=purchase.credits,
            balance_after=int(res.scalar_one()),
            purchase_id=purchase.id,
        )
    )
    await db.commit()
    await db.refresh(purchase)
    return purchase, "granted"


async def mark_refunded(db: AsyncSession, purchase_id: uuid.UUID) -> None:
    await db.execute(
        update(CreditPurchase)
        .where(CreditPurchase.id == purchase_id)
        .values(status="refunded")
    )
    await db.commit()


def _activity_row(tx: CreditTransaction, ticker: str | None, purchase: CreditPurchase | None) -> dict:
    pack = settings.credit_pack(purchase.pack_id) if purchase else None
    return {
        "id": tx.id,
        "kind": tx.kind,
        "source": "free" if tx.kind.startswith("free_") else "bought",
        "delta": tx.delta if not tx.kind.startswith("free_") else (
            -1 if tx.kind == "free_spend" else 1
        ),
        "balance_after": tx.balance_after,
        "created_at": tx.created_at,
        "ticker": ticker,
        "analysis_id": str(tx.analysis_id) if tx.analysis_id else None,
        "pack_name": ((pack or {}).get("name") or purchase.pack_id) if purchase else None,
        "amount_paise": purchase.amount_paise if purchase else None,
        "currency": purchase.currency if purchase else None,
    }


async def activity(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    kind: str = "all",
    limit: int = 25,
    before_id: int | None = None,
) -> tuple[list[dict], int | None]:
    """Every credit movement, newest first, one page at a time.

    ``kind`` is ``all``, ``usage`` or ``purchases``. Free credits appear as -1 / +1 for
    readability even though they are stored as delta 0 (they never touch the bought
    balance). Returns the rows and the cursor for the next page, if there is one.
    """
    kinds = {"usage": USAGE_KINDS, "purchases": PURCHASE_KINDS}.get(
        kind, USAGE_KINDS + PURCHASE_KINDS
    )
    q = (
        select(CreditTransaction, Analysis.ticker, CreditPurchase)
        .outerjoin(Analysis, Analysis.id == CreditTransaction.analysis_id)
        .outerjoin(CreditPurchase, CreditPurchase.id == CreditTransaction.purchase_id)
        .where(CreditTransaction.user_id == user_id, CreditTransaction.kind.in_(kinds))
    )
    if before_id is not None:
        q = q.where(CreditTransaction.id < before_id)
    res = await db.execute(q.order_by(CreditTransaction.id.desc()).limit(limit + 1))
    rows = [_activity_row(tx, ticker, purchase) for tx, ticker, purchase in res.all()]
    more = len(rows) > limit
    rows = rows[:limit]
    return rows, (rows[-1]["id"] if more and rows else None)


async def summary(db: AsyncSession, user_id: uuid.UUID, *, days: int = 30) -> dict:
    """The numbers at the top of the billing page, and a daily series for the chart."""
    res = await db.execute(
        select(
            func.count().filter(CreditTransaction.kind == "spend"),
            func.count().filter(CreditTransaction.kind == "refund"),
            func.count().filter(CreditTransaction.kind == "free_spend"),
            func.count().filter(CreditTransaction.kind == "free_refund"),
        ).where(CreditTransaction.user_id == user_id)
    )
    spend, refund, free_spend, free_refund = (int(v or 0) for v in res.one())

    res = await db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(CreditPurchase.credits), 0),
            func.coalesce(func.sum(CreditPurchase.amount_paise), 0),
        ).where(CreditPurchase.user_id == user_id, CreditPurchase.status == "paid")
    )
    purchases, credits_bought, amount_paise = (int(v or 0) for v in res.one())

    free_total = await free_used(db, user_id)
    bought_used = max(spend - refund, 0)

    # Net credits used per day (a refund cancels its spend on the day it happened).
    today = datetime.now(UTC).date()
    since = datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), UTC)
    # The UTC calendar day, whatever timezone the database session happens to use.
    day = func.date(func.timezone("UTC", CreditTransaction.created_at)).label("day")
    res = await db.execute(
        select(
            day,
            func.count().filter(CreditTransaction.kind == "free_spend")
            - func.count().filter(CreditTransaction.kind == "free_refund"),
            func.count().filter(CreditTransaction.kind == "spend")
            - func.count().filter(CreditTransaction.kind == "refund"),
        )
        .where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.created_at >= since,
            CreditTransaction.kind.in_(USAGE_KINDS),
        )
        .group_by(day)
    )
    by_day = {d: (int(f), int(p)) for d, f, p in res.all()}
    series = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        f, p = by_day.get(d, (0, 0))
        series.append({"date": d.isoformat(), "free": max(f, 0), "bought": max(p, 0)})

    return {
        "credits_used": free_total + bought_used,
        "free_used": free_total,
        "free_total": settings.free_account_credits,
        "bought_used": bought_used,
        "credits_bought": credits_bought,
        "paid_balance": await paid_balance(db, user_id),
        "purchases": purchases,
        "amount_spent_paise": amount_paise,
        "refunds": refund + free_refund,
        "currency": settings.currency,
        "daily": series,
    }


async def payments(db: AsyncSession, user_id: uuid.UUID, *, limit: int = 50) -> list[dict]:
    """Every checkout the user started, newest first, as a receipt list.

    An order that was never paid stays ``created``; after an hour it is shown as not
    completed rather than as pending, which is what a closed payment window means.
    """
    res = await db.execute(
        select(CreditPurchase)
        .where(CreditPurchase.user_id == user_id)
        .order_by(CreditPurchase.created_at.desc())
        .limit(limit)
    )
    stale = datetime.now(UTC) - timedelta(hours=1)
    out = []
    for p in res.scalars():
        status = p.status
        if status == "created":
            status = "abandoned" if p.created_at and p.created_at < stale else "pending"
        pack = settings.credit_pack(p.pack_id)
        out.append(
            {
                "id": str(p.id),
                "created_at": p.created_at,
                "paid_at": p.paid_at,
                "pack_name": (pack or {}).get("name") or p.pack_id,
                "credits": p.credits,
                "amount_paise": p.amount_paise,
                "currency": p.currency,
                "status": status,
                "order_id": p.razorpay_order_id,
                "payment_id": p.razorpay_payment_id,
            }
        )
    return out
