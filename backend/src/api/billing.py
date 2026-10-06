"""Buying credit packs with Razorpay.

The flow is Razorpay's standard Checkout, confirmed twice:

1. ``POST /billing/orders`` records a purchase and creates a Razorpay order for the
   pack's price. The amount is fixed server-side; the browser only names a pack.
2. The browser opens Checkout with that order. On success Checkout returns the payment
   id and a signature, which the browser sends to ``POST /billing/verify``. A valid
   signature grants the credits immediately, so the balance updates before the popup
   has finished closing.
3. Razorpay also calls ``POST /billing/webhook`` (``payment.captured`` / ``order.paid``).
   That covers a customer who pays and closes the tab before step 2 reaches us.

Both confirmations go through ``credits.grant_purchase``, which locks the purchase row,
so whichever arrives second changes nothing. Credits are only ever granted for a known
order, and the webhook additionally checks the captured amount matches what was quoted.

**Test mode.** This deployment runs on Razorpay test keys (``PAYMENTS_TEST_MODE``), so
every step above is real but no money moves. Each account may buy only a little, since
every credit is a real analysis on the model bill. An order that would break the limit
is refused before Checkout opens; a payment that still lands over it (several orders
opened, then all paid) adds nothing and is refunded, as a real shop would.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core import razorpay
from ..db import credits
from ..db.session import get_session
from ..deps import Requester, get_requester, require_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])


class OrderRequest(BaseModel):
    pack_id: str = Field(max_length=32)


class VerifyRequest(BaseModel):
    razorpay_order_id: str = Field(max_length=64)
    razorpay_payment_id: str = Field(max_length=64)
    razorpay_signature: str = Field(max_length=256)


def _public_pack(pack: dict) -> dict:
    credits_ = int(pack["credits"])
    price = int(pack["price_paise"])
    return {
        "id": pack["id"],
        "name": pack.get("name") or pack["id"].title(),
        "credits": credits_,
        "price_paise": price,
        "currency": settings.currency,
        "per_credit_paise": round(price / credits_) if credits_ else price,
        "popular": bool(pack.get("popular")),
    }


def _require_payments() -> None:
    if not settings.payments_enabled:
        if settings.razorpay_key_id and settings.payments_test_mode:
            log.error(
                "payments are off: PAYMENTS_TEST_MODE is on but RAZORPAY_KEY_ID is not a "
                "test key (rzp_test_...)"
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "payments_disabled",
                "message": "Buying credits is not available yet. Please check back soon.",
            },
        )


def _over_limit(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "test_limit_reached", "message": message},
    )


@router.get("/packs")
async def list_packs(
    requester: Requester = Depends(get_requester),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Public: the shop renders for signed-out visitors too, with a sign-in prompt.
    Signed in, it also says how much of the test-mode limit is left."""
    limits = None
    if requester.is_authenticated:
        limits = credits.test_limits(*await credits.purchase_totals(db, requester.user_id))
    return {
        "enabled": settings.payments_enabled,
        "test_mode": settings.payments_test_mode,
        "currency": settings.currency,
        "packs": [_public_pack(p) for p in settings.credit_packs],
        "limits": limits,
    }


@router.post("/orders")
async def create_order(
    body: OrderRequest,
    requester: Requester = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    _require_payments()
    pack = settings.credit_pack(body.pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="That credit pack does not exist.")

    user = requester.user
    problem = credits.test_limit_problem(
        *await credits.purchase_totals(db, user.id), int(pack["credits"])
    )
    if problem:
        raise _over_limit(problem)

    purchase = await credits.create_purchase(db, user_id=user.id, pack=pack)
    try:
        order = await razorpay.create_order(
            amount_paise=purchase.amount_paise,
            currency=purchase.currency,
            receipt=str(purchase.id),
            notes={"purchase_id": str(purchase.id), "user_id": str(user.id),
                   "pack_id": purchase.pack_id},
        )
    except razorpay.RazorpayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "payment_provider_error",
                "message": "We could not start the payment. Nothing was charged. "
                           "Please try again in a moment.",
            },
        ) from exc

    await credits.attach_order(db, purchase.id, order["id"])
    return {
        "key_id": settings.razorpay_key_id,
        "order_id": order["id"],
        "amount": purchase.amount_paise,
        "currency": purchase.currency,
        "pack": _public_pack(pack),
        "name": settings.app_name,
        "prefill": {"email": user.email, "name": user.name or ""},
        "test_mode": settings.payments_test_mode,
    }


@router.post("/verify")
async def verify_payment(
    body: VerifyRequest,
    requester: Requester = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    _require_payments()
    if not razorpay.verify_payment_signature(
        body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_signature",
                "message": "We could not confirm this payment. If money left your "
                           "account, your credits will arrive within a few minutes.",
            },
        )

    purchase = await credits.get_purchase_by_order(db, body.razorpay_order_id)
    if purchase is None or purchase.user_id != requester.user_id:
        raise HTTPException(status_code=404, detail="That payment is not one of yours.")

    purchase, outcome = await _settle(
        db, order_id=body.razorpay_order_id, payment_id=body.razorpay_payment_id
    )
    if purchase.status in {"over_limit", "refunded"}:
        raise _over_limit(
            "This payment went over the test-mode limit, so no credits were added and "
            "the test payment has been refunded. No real money was involved."
        )
    return {
        "credits_added": purchase.credits,
        "newly_granted": outcome == "granted",
        "paid_credits": await credits.paid_balance(db, requester.user_id),
    }


async def _settle(db: AsyncSession, *, order_id: str, payment_id: str):
    """Grant the order, or refund it if it landed over the test-mode limit."""
    purchase, outcome = await credits.grant_purchase(
        db, order_id=order_id, payment_id=payment_id
    )
    if outcome == "over_limit":
        log.warning("purchase %s is over the test limit; refunding", purchase.id)
        if await razorpay.refund_payment(payment_id, purchase.amount_paise):
            await credits.mark_refunded(db, purchase.id)
            purchase.status = "refunded"
    return purchase, outcome


@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request, db: AsyncSession = Depends(get_session)) -> dict:
    """Razorpay's server-to-server confirmation. Always 200 for anything we do not act
    on, or Razorpay retries it and eventually disables the webhook."""
    body = await request.body()
    if not razorpay.verify_webhook_signature(
        body, request.headers.get("x-razorpay-signature", "")
    ):
        raise HTTPException(status_code=400, detail="bad signature")

    try:
        event = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad body") from None

    if event.get("event") not in {"payment.captured", "order.paid"}:
        return {"ok": True, "ignored": event.get("event")}

    payment = (event.get("payload", {}).get("payment") or {}).get("entity") or {}
    order_id, payment_id = payment.get("order_id"), payment.get("id")
    if not order_id or not payment_id:
        return {"ok": True, "ignored": "no order"}

    purchase = await credits.get_purchase_by_order(db, order_id)
    if purchase is None:
        # An order this app did not create (another integration on the same account).
        log.warning("webhook for unknown order %s", order_id)
        return {"ok": True, "ignored": "unknown order"}
    if payment.get("amount") != purchase.amount_paise or (
        (payment.get("currency") or "").upper() != purchase.currency.upper()
    ):
        log.error(
            "webhook amount mismatch on %s: paid %s %s, expected %s %s",
            order_id, payment.get("amount"), payment.get("currency"),
            purchase.amount_paise, purchase.currency,
        )
        return {"ok": True, "ignored": "amount mismatch"}

    _, outcome = await _settle(db, order_id=order_id, payment_id=payment_id)
    return {"ok": True, "granted": outcome == "granted", "outcome": outcome}


@router.get("/summary")
async def billing_summary(
    requester: Requester = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    return await credits.summary(db, requester.user_id)


@router.get("/activity")
async def credit_activity(
    kind: Literal["all", "usage", "purchases"] = "all",
    limit: int = Query(default=25, ge=1, le=100),
    before: int | None = Query(default=None, ge=1),
    requester: Requester = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Every credit movement, free and bought, newest first. Pass ``next`` back as
    ``before`` for the following page."""
    rows, cursor = await credits.activity(
        db, requester.user_id, kind=kind, limit=limit, before_id=before
    )
    return {"items": rows, "next": cursor}


@router.get("/activity.csv")
async def credit_activity_csv(
    requester: Requester = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """The whole activity log as a spreadsheet, for anyone who keeps their own books."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["date_utc", "activity", "credit_type", "credits", "company", "pack",
         "amount", "currency", "bought_balance_after"]
    )
    cursor = None
    while True:
        rows, cursor = await credits.activity(
            db, requester.user_id, limit=100, before_id=cursor
        )
        for r in rows:
            writer.writerow([
                r["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                r["kind"],
                r["source"],
                r["delta"],
                r["ticker"] or "",
                r["pack_name"] or "",
                f"{r['amount_paise'] / 100:.2f}" if r["amount_paise"] is not None else "",
                r["currency"] or "",
                r["balance_after"],
            ])
        if cursor is None:
            break
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="credit-activity.csv"'},
    )


@router.get("/payments")
async def payment_history(
    requester: Requester = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    return {
        "test_mode": settings.payments_test_mode,
        "items": await credits.payments(db, requester.user_id),
    }
