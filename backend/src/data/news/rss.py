"""Headlines: yfinance's news endpoint plus Yahoo Finance's per-ticker RSS.

Lower signal than a filing and treated as such — these carry a recency bonus in
retrieval but never outweigh a 10-K risk factor on the same subject. Both sources fail
open: no news is a degraded analysis, not a failed one.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from xml.etree import ElementTree

import httpx

log = logging.getLogger(__name__)

YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"

TAG = re.compile(r"<[^>]+>")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", TAG.sub(" ", text)).strip()


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value, tz=UTC).date().isoformat()
        except (OSError, ValueError, OverflowError):
            return None
    if isinstance(value, str):
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(value.strip(), fmt).date().isoformat()
            except ValueError:
                continue
        # yfinance sometimes hands back an ISO string with sub-second precision.
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return None
    return None


def _yf_news_sync(ticker: str) -> list[dict]:
    import yfinance as yf

    try:
        raw = yf.Ticker(ticker).news or []
    except Exception as exc:
        log.info("yfinance news unavailable for %s: %s", ticker, exc)
        return []

    items: list[dict] = []
    for entry in raw:
        # yfinance has moved this payload around between versions; accept both shapes.
        content = entry.get("content") if isinstance(entry, dict) else None
        if isinstance(content, dict):
            title = _clean(content.get("title"))
            summary = _clean(content.get("summary") or content.get("description"))
            published = _iso(content.get("pubDate") or content.get("displayTime"))
            url = (
                (content.get("canonicalUrl") or {}).get("url")
                or (content.get("clickThroughUrl") or {}).get("url")
            )
            publisher = ((content.get("provider") or {}).get("displayName")) or "Yahoo Finance"
        else:
            title = _clean(entry.get("title"))
            summary = _clean(entry.get("summary"))
            published = _iso(entry.get("providerPublishTime"))
            url = entry.get("link")
            publisher = entry.get("publisher") or "Yahoo Finance"

        body = " ".join(p for p in (title, summary) if p).strip()
        if len(body) < 60:
            continue
        items.append(
            {
                "source_type": "yf_news",
                "section": publisher,
                "title": title or publisher,
                "url": url,
                "published": published,
                "text": body,
            }
        )
    return items


async def yf_news(ticker: str) -> list[dict]:
    return await asyncio.to_thread(_yf_news_sync, ticker)


async def yahoo_rss(ticker: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                YAHOO_RSS.format(ticker=ticker),
                headers={"User-Agent": "Mozilla/5.0 (compatible; equity-research-agent)"},
            )
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
    except Exception as exc:
        log.info("Yahoo RSS unavailable for %s: %s", ticker, exc)
        return []

    items: list[dict] = []
    for item in root.iter("item"):
        title = _clean(item.findtext("title"))
        desc = _clean(item.findtext("description"))
        body = " ".join(p for p in (title, desc) if p).strip()
        if len(body) < 60:
            continue
        items.append(
            {
                "source_type": "rss",
                "section": "Yahoo Finance",
                "title": title,
                "url": item.findtext("link"),
                "published": _iso(item.findtext("pubDate")),
                "text": body,
            }
        )
    return items


async def fetch_news(ticker: str) -> list[dict]:
    """Both sources, de-duplicated by URL then by headline."""
    results = await asyncio.gather(
        yf_news(ticker), yahoo_rss(ticker), return_exceptions=True
    )
    merged: list[dict] = []
    for r in results:
        if isinstance(r, Exception):
            log.info("a news source failed for %s: %s", ticker, r)
            continue
        merged.extend(r)

    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out: list[dict] = []
    for item in merged:
        url = (item.get("url") or "").split("?")[0]
        key = (item.get("title") or "").lower()[:90]
        if url and url in seen_urls:
            continue
        if key and key in seen_titles:
            continue
        if url:
            seen_urls.add(url)
        if key:
            seen_titles.add(key)
        out.append(item)
    return out
