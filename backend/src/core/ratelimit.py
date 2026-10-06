"""Quota and abuse ceilings.

Three independent limits:

* anonymous visitors get ``ANON_RUN_LIMIT`` real runs, tracked per cookie;
* signed-in accounts get ``FREE_ACCOUNT_CREDITS`` once, on top of any bought credits;
* an IP-hash ceiling of ``ANON_IP_DAILY_CAP`` per day stops cookie-clearing loops.

IPs are only ever stored as a salted hash.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from ..config import settings
from .cache import get_redis

log = logging.getLogger(__name__)


def hash_ip(ip: str) -> str:
    return hashlib.sha256(f"{settings.ip_hash_salt}|{ip}".encode()).hexdigest()[:32]


@dataclass(slots=True)
class QuotaState:
    allowed: bool
    used: int
    limit: int
    scope: str  # "anon" | "free" | "ip"
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "used": self.used,
            "limit": self.limit,
            "remaining": max(self.limit - self.used, 0),
            "scope": self.scope,
            "reason": self.reason,
        }


def _anon_key(anon_id: str) -> str:
    return f"quota:anon:{anon_id}"


def _ip_key(ip_hash: str) -> str:
    day = datetime.now(UTC).date().isoformat()
    return f"quota:ip:{day}:{ip_hash}"


async def anon_runs_used(anon_id: str) -> int:
    try:
        raw = await get_redis().get(_anon_key(anon_id))
        return int(raw) if raw else 0
    except Exception:
        return 0


async def consume_anon_run(anon_id: str) -> int:
    try:
        r = get_redis()
        key = _anon_key(anon_id)
        n = await r.incr(key)
        await r.expire(key, settings.anon_cookie_days * 86400)
        return int(n)
    except Exception as exc:
        log.warning("could not record anon run: %s", exc)
        return 0


async def release_anon_run(anon_id: str) -> None:
    """Give a run back when enqueueing fails, so a crash never eats someone's quota."""
    try:
        await get_redis().decr(_anon_key(anon_id))
    except Exception:
        pass


async def consume_ip_run(ip_hash: str) -> int:
    try:
        r = get_redis()
        key = _ip_key(ip_hash)
        n = await r.incr(key)
        await r.expire(key, 86400)
        return int(n)
    except Exception:
        return 0


async def ip_runs_used(ip_hash: str) -> int:
    try:
        raw = await get_redis().get(_ip_key(ip_hash))
        return int(raw) if raw else 0
    except Exception:
        return 0
