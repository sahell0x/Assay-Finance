"""Daily spend guard.

Spend accumulates in Redis under ``spend:{YYYY-MM-DD}``. Once the cap is hit the system
does not error — it degrades: cached results are still served and the API returns a flag
the UI renders as a banner.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from ..config import settings
from .cache import get_redis

log = logging.getLogger(__name__)

# USD per 1M tokens. Used for the cost estimate written to the ledger and the trace.
# Unknown models fall back to the mid tier rather than recording zero.
PRICING: dict[str, tuple[float, float]] = {
    "gpt-5.6-sol": (1.25, 10.00),
    "gpt-5.6-terra": (0.40, 1.60),
    "gpt-5.6-luna": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}
_DEFAULT_PRICE = (0.40, 1.60)


def price_for(model: str) -> tuple[float, float]:
    if model in PRICING:
        return PRICING[model]
    for known, price in PRICING.items():
        if model.startswith(known):
            return price
    return _DEFAULT_PRICE


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    cin, cout = price_for(model)
    return (tokens_in / 1_000_000) * cin + (tokens_out / 1_000_000) * cout


def _spend_key(day: date | None = None) -> str:
    return f"spend:{(day or datetime.now(UTC).date()).isoformat()}"


async def add_spend(usd: float) -> float:
    """Add to today's total and return the new total. Never raises."""
    if usd <= 0:
        return await current_spend()
    try:
        r = get_redis()
        key = _spend_key()
        total = await r.incrbyfloat(key, usd)
        await r.expire(key, 72 * 3600)
        return float(total)
    except Exception as exc:
        log.warning("could not record spend: %s", exc)
        return 0.0


async def current_spend() -> float:
    try:
        raw = await get_redis().get(_spend_key())
        return float(raw) if raw else 0.0
    except Exception:
        return 0.0


async def budget_state() -> dict:
    spent = await current_spend()
    cap = float(settings.daily_cap_usd)
    return {
        "spent_usd": round(spent, 4),
        "cap_usd": cap,
        "exhausted": spent >= cap,
        "remaining_usd": round(max(cap - spent, 0.0), 4),
    }


async def public_budget_state() -> dict:
    """What a browser may know about the budget: only whether new runs are paused.

    The dollar figures are the operator's spend and cap. They were being returned to
    every visitor on /usage and on every analysis request.
    """
    return {"exhausted": (await budget_state())["exhausted"]}


async def budget_exhausted() -> bool:
    return (await current_spend()) >= float(settings.daily_cap_usd)
