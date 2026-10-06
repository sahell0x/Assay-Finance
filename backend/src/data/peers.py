"""Peer resolution.

Order of preference, per the spec:

1. peers the caller supplied — they know their comparables better than a static map;
2. the shipped ``peers.yaml`` industry map;
3. nothing, with a warning. A percentile rank against an incomparable cohort is worse
   than no rank at all, so the system would rather say "no peer data" than invent one.
"""

from __future__ import annotations

import functools
import logging
import pathlib

import yaml

log = logging.getLogger(__name__)

_PATH = pathlib.Path(__file__).with_name("peers.yaml")


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    try:
        return yaml.safe_load(_PATH.read_text()) or {}
    except Exception as exc:
        log.error("could not load peers.yaml: %s", exc)
        return {}


def groups() -> dict:
    return _load().get("groups", {}) or {}


def resolve_peers(
    ticker: str,
    *,
    sector: str = "",
    industry: str = "",
    supplied: list[str] | None = None,
    limit: int = 8,
) -> tuple[list[str], str]:
    """Return ``(peers, source)`` where source is 'user', 'map', 'fallback' or 'none'."""
    ticker = ticker.upper()

    if supplied:
        cleaned = [p.upper().strip() for p in supplied if p and p.strip()]
        deduped = [p for i, p in enumerate(cleaned) if p != ticker and p not in cleaned[:i]]
        if deduped:
            return deduped[:limit], "user"

    industry_l = (industry or "").lower()
    sector_l = (sector or "").lower()

    for group in groups().values():
        matches = [m.lower() for m in group.get("match", [])]
        if any(m in industry_l for m in matches if m):
            return _clean(group.get("tickers", []), ticker, limit), "map"

    for group in groups().values():
        matches = [m.lower() for m in group.get("match", [])]
        if sector_l and any(m in sector_l for m in matches if m):
            return _clean(group.get("tickers", []), ticker, limit), "map"

    fallback = (_load().get("fallback") or {}).get("tickers", [])
    if fallback:
        return _clean(fallback, ticker, limit), "fallback"

    return [], "none"


def _clean(tickers: list[str], exclude: str, limit: int) -> list[str]:
    out = []
    for t in tickers:
        t = t.upper()
        if t == exclude or t in out:
            continue
        out.append(t)
        if len(out) >= limit:
            break
    return out


def industry_label(sector: str, industry: str) -> str:
    return industry or sector or "the broader market"
