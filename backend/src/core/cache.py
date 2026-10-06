"""Redis helpers: a JSON blob cache and the analysis cache key.

One shared client per process. ``redis.asyncio.from_url`` is already pooled, so nothing
here opens connections eagerly — important because the worker and the API run side by
side on a small box.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from typing import Any

import redis.asyncio as aioredis

from ..config import settings

log = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_keepalive=True,
            health_check_interval=30,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def cache_get(key: str) -> Any | None:
    try:
        raw = await get_redis().get(key)
    except Exception as exc:  # a cold cache must never fail a run
        log.warning("cache get failed for %s: %s", key, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    try:
        await get_redis().set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:
        log.warning("cache set failed for %s: %s", key, exc)


def canonical_weights(weights: dict | None) -> str:
    """Stable string for a weight dict so 0.25 and 0.250 hash identically."""
    if not weights:
        return "default"
    return ",".join(f"{k}={round(float(v), 4)}" for k, v in sorted(weights.items()))


def analysis_cache_key(
    ticker: str, peers: list[str] | None, weights: dict | None, day: date | None = None
) -> str:
    """Global (cross-user) cache key. Same inputs on the same day -> same analysis."""
    day = day or date.today()
    peer_part = ",".join(sorted(p.upper() for p in (peers or [])))
    raw = f"{ticker.upper()}|{peer_part}|{canonical_weights(weights)}|{day.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()
