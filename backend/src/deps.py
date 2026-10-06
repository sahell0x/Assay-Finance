"""Request-scoped dependencies: who is asking, and are they allowed to.

The identity model has two shapes. A signed-in user is a ``User`` row. An anonymous
visitor is an opaque id in an httpOnly cookie, backed by a Redis counter. Anonymous
visitors get the *full* feature set — every tab, every chart, the trace — limited only
by a run count, because a product whose output you cannot see before signing up has
nothing to sign up for.

A salted IP hash provides a second ceiling so that clearing a cookie does not reset the
allowance. Raw addresses are never stored.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from .api.auth import ANON_COOKIE, current_user_optional
from .config import settings
from .core import ratelimit
from .core.budget import public_budget_state
from .db.models import User
from .db.session import get_session


@dataclass(slots=True)
class Requester:
    """Whoever is making this request, signed in or not."""

    user: User | None
    anon_id: str | None
    ip_hash: str

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.user.id if self.user else None

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None

    @property
    def owner_filter(self) -> dict:
        return (
            {"user_id": self.user_id}
            if self.is_authenticated
            else {"anon_id": self.anon_id}
        )


def client_ip(request: Request) -> str:
    """Trust ``X-Forwarded-For`` only for its first hop, which is what a reverse proxy
    controls; everything after it is client-supplied and forgeable."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


async def get_requester(
    request: Request,
    response: Response,
    user: User | None = Depends(current_user_optional),
) -> Requester:
    """Resolve identity and, for anonymous visitors, issue the cookie if absent."""
    anon_id = request.cookies.get(ANON_COOKIE)

    if user is None and not anon_id:
        anon_id = secrets.token_urlsafe(18)
        response.set_cookie(
            ANON_COOKIE,
            anon_id,
            max_age=settings.anon_cookie_days * 86400,
            httponly=True,
            samesite="lax",
            secure=settings.cookie_secure or settings.is_prod,
            domain=settings.cookie_domain_attr,
            path="/",
        )

    return Requester(
        user=user,
        anon_id=None if user else anon_id,
        ip_hash=ratelimit.hash_ip(client_ip(request)),
    )


async def require_user(
    requester: Requester = Depends(get_requester),
) -> Requester:
    if not requester.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to use this.",
        )
    return requester


async def usage_state(requester: Requester, db: AsyncSession) -> dict:
    """Everything the interface needs to render the usage meter and the quota gate.

    For a signed-in user ``used``/``limit`` describe the one-time free credits that come
    with an account, and ``remaining`` is everything they can still run: free credits
    left plus bought ones.
    """
    from .db import credits

    budget = await public_budget_state()
    paid = 0
    can_buy = False

    if requester.is_authenticated:
        used = await credits.free_used(db, requester.user_id)
        limit = settings.free_account_credits
        paid = await credits.paid_balance(db, requester.user_id)
        can_buy = await can_buy_credits(db, requester.user_id)
        scope = "free"
    else:
        used = await ratelimit.anon_runs_used(requester.anon_id or "")
        limit = settings.anon_run_limit
        scope = "anon"

    free_remaining = max(limit - used, 0)
    remaining = free_remaining + paid
    return {
        "scope": scope,
        "used": used,
        "limit": limit,
        "free_remaining": free_remaining,
        "paid_credits": paid,
        "remaining": remaining,
        "exhausted": remaining == 0,
        "authenticated": requester.is_authenticated,
        # What a new account gets, once, for the "create an account" copy.
        "account_free_credits": settings.free_account_credits,
        "payments_enabled": settings.payments_enabled,
        # Signed in, payments on, and not at the test-mode purchase limit.
        "can_buy": can_buy,
        "budget": budget,
        "signup_benefits": [
            "Your history and watchlist on any device",
            "See how a company's score changes over time",
            "Refresh your whole watchlist in one click",
            f"{settings.free_account_credits} more free credits, on top of your "
            f"{settings.anon_run_limit}",
        ],
    }


async def can_buy_credits(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Whether this user could buy at least the smallest pack right now."""
    from .db import credits

    if not settings.payments_enabled or not settings.credit_packs:
        return False
    smallest = min(int(p["credits"]) for p in settings.credit_packs)
    count, bought = await credits.purchase_totals(db, user_id)
    return credits.test_limit_problem(count, bought, smallest) is None


async def out_of_credits_reason(db: AsyncSession, user_id: uuid.UUID) -> str:
    """What to tell a signed-in user with nothing left, depending on whether buying more
    is still possible for them."""
    can_buy = await can_buy_credits(db, user_id)
    used_up = (
        f"You have used the {settings.free_account_credits} free credits that come with "
        f"your account"
    )
    if can_buy:
        return (
            f"{used_up} and have no bought credits left. Buy a credit pack to keep going. "
            f"Anything you have already analyzed still opens."
        )
    return (
        f"{used_up}, and this demo does not sell any more. Anything you have already "
        f"analyzed still opens, and companies analyzed recently by anyone are free."
    )


async def check_quota(requester: Requester, db: AsyncSession) -> ratelimit.QuotaState:
    """Enforce the run allowance *before* enqueueing anything.

    Cache hits do not consume quota — serving a result someone else already paid for
    costs nothing, and charging for it would make the cache user-hostile.
    """
    from .db import credits

    if requester.is_authenticated:
        # A fast refusal with the right message. The binding check is the one made
        # under a lock when the run is inserted (``credits.create_charged_run``).
        used = await credits.free_used(db, requester.user_id)
        limit = settings.free_account_credits
        allowed = used < limit or await credits.paid_balance(db, requester.user_id) > 0
        return ratelimit.QuotaState(
            allowed=allowed,
            used=used,
            limit=limit,
            scope="free",
            reason=None if allowed else await out_of_credits_reason(db, requester.user_id),
        )

    anon_id = requester.anon_id or ""
    used = await ratelimit.anon_runs_used(anon_id)
    limit = settings.anon_run_limit
    if used >= limit:
        return ratelimit.QuotaState(
            allowed=False, used=used, limit=limit, scope="anon",
            reason=(
                f"You have used your {limit} free credits. Create a free account to get "
                f"{settings.free_account_credits} more. Everything you have analyzed "
                f"comes with you."
            ),
        )

    # Abuse ceiling: clearing the cookie should not reset the allowance.
    ip_used = await ratelimit.ip_runs_used(requester.ip_hash)
    if ip_used >= settings.anon_ip_daily_cap:
        # Report the ceiling that actually blocked the request. Returning the cookie's
        # counters here said "0 of 3 used" next to a refusal, which reads as a bug.
        return ratelimit.QuotaState(
            allowed=False,
            used=ip_used,
            limit=settings.anon_ip_daily_cap,
            scope="ip",
            reason=(
                "This network has reached today's limit for free analyses. Sign in or "
                "create a free account to continue."
            ),
        )

    return ratelimit.QuotaState(allowed=True, used=used, limit=limit, scope="anon")


async def consume_quota(requester: Requester) -> None:
    """Called once a run is actually enqueued."""
    if requester.is_authenticated:
        return  # charged in the ledger when the row was inserted
    if requester.anon_id:
        await ratelimit.consume_anon_run(requester.anon_id)
    await ratelimit.consume_ip_run(requester.ip_hash)


async def release_quota(requester: Requester) -> None:
    """Give the run back when enqueueing fails."""
    if not requester.is_authenticated and requester.anon_id:
        await ratelimit.release_anon_run(requester.anon_id)


DbSession = Depends(get_session)
