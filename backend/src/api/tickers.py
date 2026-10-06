"""Ticker search and per-ticker score history.

Autocomplete is served from the SEC's own company/ticker file, cached in Redis for a
day. It covers every US registrant, needs no third-party search API, and — unlike
scraping a quote endpoint — will not rate-limit a user who types quickly.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.cache import cache_get, cache_set
from ..db import repo
from ..db.session import get_session
from ..deps import Requester, require_user
from .schemas import HistoryPoint, TickerResolution, TickerSuggestion

log = logging.getLogger(__name__)
router = APIRouter(tags=["tickers"])

TICKER_FILE = "https://www.sec.gov/files/company_tickers_exchange.json"
CACHE_KEY = "tickers:index:v2"  # v2: display-cased names
CACHE_TTL = 86400

# Shown before the user types anything: recognisable names across several sectors, so
# the first thing a visitor sees is not an empty box.
SUGGESTED = [
    ("AAPL", "Apple Inc."),
    ("MSFT", "Microsoft Corporation"),
    ("NVDA", "NVIDIA Corporation"),
    ("JPM", "JPMorgan Chase & Co."),
    ("XOM", "Exxon Mobil Corporation"),
    ("UNH", "UnitedHealth Group Incorporated"),
    ("COST", "Costco Wholesale Corporation"),
    ("O", "Realty Income Corporation"),
]


# Company forms that read wrongly when merely capitalised.
_FORMS = {"INC": "Inc.", "CORP": "Corp.", "CO": "Co.", "LTD": "Ltd.", "PLC": "plc",
          "LLC": "LLC", "LP": "LP", "NV": "NV", "SA": "SA", "AG": "AG", "SE": "SE",
          "ETF": "ETF", "REIT": "REIT", "USA": "USA", "US": "US", "II": "II", "III": "III"}
_SMALL = {"OF", "AND", "THE", "FOR", "IN", "ON", "AT", "DE", "DEL", "LA"}


def display_name(name: str) -> str:
    """"MORGAN STANLEY" -> "Morgan Stanley". Names that already use mixed case are left
    exactly as the company writes them. Short acronyms (HP, 3M) and anything with an
    ampersand (AT&T) stay upper-case, because guessing wrong there looks worse."""
    # SEC state-of-incorporation tags ("/DE/", "/NEW/") mean nothing to a reader.
    name = re.sub(r"\s*/[A-Z]{2,4}/\s*$", "", name or "").strip()
    shouting = [w for w in name.split() if w.upper() not in _FORMS]
    if not name or any(w != w.upper() for w in shouting) or not any(c.isalpha() for c in name):
        return name
    words = []
    for i, raw in enumerate(name.split()):
        core = raw.strip(",.")
        tail = raw[len(core):] if raw.startswith(core) else ""
        key = core.upper()
        if key in _FORMS:
            out = _FORMS[key]
            tail = tail.lstrip(".")
        elif i > 0 and key in _SMALL:
            out = core.lower()
        elif "&" in core or any(ch.isdigit() for ch in core) or len(core) <= 2:
            out = core
        else:
            out = "-".join(p.capitalize() for p in core.split("-"))
            out = "/".join(p[:1].upper() + p[1:] for p in out.split("/"))
        words.append(out + tail)
    return " ".join(words)


async def _load_index() -> list[dict]:
    cached = await cache_get(CACHE_KEY)
    if cached:
        return cached

    import httpx

    from ..config import settings

    rows: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(
                TICKER_FILE,
                headers={"User-Agent": settings.sec_user_agent.strip().strip('"')},
            )
            resp.raise_for_status()
            payload = resp.json()
        fields = payload.get("fields", [])
        idx = {name: i for i, name in enumerate(fields)}
        for row in payload.get("data", []):
            ticker = row[idx["ticker"]] if "ticker" in idx else None
            if not ticker:
                continue
            rows.append(
                {
                    "ticker": str(ticker).upper(),
                    "name": display_name(str(row[idx["name"]])) if "name" in idx else "",
                    "exchange": str(row[idx["exchange"]]) if "exchange" in idx else None,
                }
            )
    except Exception as exc:
        log.warning("could not load the SEC ticker index: %s", exc)
        rows = [{"ticker": t, "name": n, "exchange": None} for t, n in SUGGESTED]

    await cache_set(CACHE_KEY, rows, CACHE_TTL)
    return rows


# People search by the brand they know, which is not always the company that is
# listed. The SEC file only knows "Alphabet Inc.", so "google" found nothing.
BRAND_ALIASES: dict[str, list[str]] = {
    "GOOGLE": ["GOOGL", "GOOG"],
    "YOUTUBE": ["GOOGL"],
    "ALPHABET": ["GOOGL", "GOOG"],
    "FACEBOOK": ["META"],
    "INSTAGRAM": ["META"],
    "WHATSAPP": ["META"],
    "SNAPCHAT": ["SNAP"],
    "JPMORGAN": ["JPM"],
    "CHASE": ["JPM"],
    "WALMART": ["WMT"],
    "BERKSHIRE": ["BRK-B", "BRK-A"],
    "SPACEX": ["SPCX"],
    "STARLINK": ["SPCX"],
}


# Well-known companies people expect to find but cannot, because they are not listed.
# Searching one of these should say so plainly, not offer look-alikes ("mars" would
# otherwise suggest Marsh & McLennan). Keys are _norm()'d queries; values are the name
# to show. Brand names map to their private owner (ChatGPT -> OpenAI).
PRIVATE_COMPANIES: dict[str, str] = {
    "ANTHROPIC": "Anthropic",
    "OPENAI": "OpenAI",
    "CHATGPT": "OpenAI",
    "XAI": "xAI",
    "TWITTER": "X (formerly Twitter)",
    "STRIPE": "Stripe",
    "DATABRICKS": "Databricks",
    "BYTEDANCE": "ByteDance",
    "TIKTOK": "ByteDance (TikTok)",
    "SHEIN": "Shein",
    "EPICGAMES": "Epic Games",
    "FORTNITE": "Epic Games",
    "VALVE": "Valve",
    "MARS": "Mars",
    "IKEA": "IKEA",
    "CARGILL": "Cargill",
    "KOCHINDUSTRIES": "Koch Industries",
    "CHANEL": "Chanel",
    "ROLEX": "Rolex",
    "LEGO": "LEGO",
    "DYSON": "Dyson",
    "BOSE": "Bose",
    "DELOITTE": "Deloitte",
    "PWC": "PwC",
    "KPMG": "KPMG",
    "MCKINSEY": "McKinsey & Company",
    "BLOOMBERG": "Bloomberg",
    "REVOLUT": "Revolut",
    "CANVA": "Canva",
    "DISCORD": "Discord",
    "TELEGRAM": "Telegram",
    "MISTRALAI": "Mistral AI",
    "PERPLEXITY": "Perplexity",
    "ANDURIL": "Anduril",
    "SCALEAI": "Scale AI",
    "NEURALINK": "Neuralink",
    "HUGGINGFACE": "Hugging Face",
    "MIDJOURNEY": "Midjourney",
    "PATAGONIA": "Patagonia",
    "INNOUT": "In-N-Out Burger",
    "CHICKFILA": "Chick-fil-A",
    "PUBLIX": "Publix",
    "TRADERJOES": "Trader Joe's",
    "ALDI": "Aldi",
    "LIDL": "Lidl",
    "SUBWAY": "Subway",
}

# Legal names a private company would list under if it went public, beyond the key
# itself. If one appears in the SEC file, the company is no longer private.
_LISTING_NAMES: dict[str, tuple[str, ...]] = {
    "CHATGPT": ("OPENAI",),
    "TIKTOK": ("BYTEDANCE",),
    "FORTNITE": ("EPICGAMES",),
    "TWITTER": ("XCORP", "XHOLDINGS"),
}

_LEGAL_SUFFIXES = set(_FORMS) | {"CORPORATION", "INCORPORATED", "COMPANY", "LIMITED",
                                 "HOLDINGS", "HOLDING", "GROUP"}


def _bare(name: str) -> str:
    """A listed name without its legal form: "Stripe, Inc." -> "STRIPE"."""
    words = [w.strip(",.").upper() for w in (name or "").split()]
    return _norm(" ".join(w for w in words if w not in _LEGAL_SUFFIXES))


def private_company(rows: list[dict], q: str) -> str | None:
    """The private company ``q`` names, or None.

    A real ticker always wins, and so does a listing under the company's own name: a
    private company that goes public must start showing up without editing this list.
    """
    nq = _norm(q)
    name = PRIVATE_COMPANIES.get(nq)
    if name is None:
        return None
    symbol = q.strip().upper()
    listing_names = {nq, *_LISTING_NAMES.get(nq, ())}
    for row in rows:
        if row["ticker"] == symbol or _bare(row.get("name") or "") in listing_names:
            return None
    return name


def _norm(text: str) -> str:
    """Upper-case with punctuation and spaces removed, so "coca cola" finds
    "COCA-COLA CO" and "mcdonalds" finds "McDONALD'S CORP"."""
    return "".join(c for c in text.upper() if c.isalnum())


def _rank(rows: list[dict], q: str, limit: int) -> list[dict]:
    """Brand alias first, then exact symbol, symbol prefix, name prefix, name substring."""
    q = q.strip().upper()
    if not q:
        return []
    nq = _norm(q)

    aliased = BRAND_ALIASES.get(nq, [])
    by_ticker = {r["ticker"]: r for r in rows} if aliased else {}
    alias_rows = [by_ticker[t] for t in aliased if t in by_ticker]

    exact, sym_prefix, name_prefix, name_contains = [], [], [], []
    for row in rows:
        ticker = row["ticker"]
        name = _norm(row.get("name") or "")
        if ticker == q:
            exact.append(row)
        elif ticker.startswith(q):
            sym_prefix.append(row)
        elif nq and name.startswith(nq):
            name_prefix.append(row)
        elif len(nq) >= 2 and nq in name:
            name_contains.append(row)
        if len(exact) + len(sym_prefix) > limit * 4:
            break

    sym_prefix.sort(key=lambda r: len(r["ticker"]))
    # Ordinary shares before preferreds and units (BAC before BML-PG): a ticker with a
    # dash is almost never the one a person searching by company name means.
    name_prefix.sort(key=lambda r: ("-" in r["ticker"], len(r["ticker"])))
    name_contains.sort(key=lambda r: ("-" in r["ticker"], len(r["ticker"])))
    ordered = alias_rows + [
        r for r in exact + sym_prefix + name_prefix + name_contains if r not in alias_rows
    ]
    return ordered[:limit]


async def private_company_named(q: str) -> str | None:
    return private_company(await _load_index(), q)


async def check_ticker(symbol: str) -> tuple[bool, list[dict]]:
    """Whether ``symbol`` is a listed ticker, and the closest matches when it is not.

    Answers yes when only the fallback list is loaded: an SEC outage must not stop
    people analysing real companies. The SEC file writes class shares with a dash
    (BRK-B) where people type a dot (BRK.B), so both spellings count.
    """
    rows = await _load_index()
    if len(rows) <= len(SUGGESTED):
        return True, []
    symbol = symbol.strip().upper()
    known = {r["ticker"] for r in rows}
    if symbol in known or symbol.replace(".", "-") in known:
        return True, []
    if private_company(rows, symbol):
        return False, []
    return False, _rank(rows, symbol, 3)


@router.get("/tickers/search", response_model=list[TickerSuggestion])
async def search_tickers(
    q: str = Query(default="", max_length=40),
    limit: int = Query(default=8, le=25),
) -> list[TickerSuggestion]:
    if not q.strip():
        return [TickerSuggestion(ticker=t, name=n) for t, n in SUGGESTED[:limit]]
    rows = await _load_index()
    if private_company(rows, q):
        return []
    return [TickerSuggestion(**r) for r in _rank(rows, q, limit)]


@router.get("/tickers/resolve", response_model=TickerResolution)
async def resolve_tickers(
    q: str = Query(default="", max_length=40),
    limit: int = Query(default=8, le=25),
) -> TickerResolution:
    """Search, plus whether the query names a well-known private company.

    The search box needs to tell "we could not find that" apart from "that company is
    not on the stock market", and a bare list cannot carry the difference.
    """
    if not q.strip():
        return TickerResolution(matches=await search_tickers(q=q, limit=limit))
    rows = await _load_index()
    private = private_company(rows, q)
    if private:
        return TickerResolution(private_company=private)
    return TickerResolution(
        matches=[TickerSuggestion(**r) for r in _rank(rows, q, limit)]
    )


@router.get("/tickers/{ticker}/history", response_model=list[HistoryPoint])
async def ticker_history(
    ticker: str,
    requester: Requester = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[HistoryPoint]:
    """Composite score over time for one ticker, oldest first."""
    rows = await repo.ticker_history(db, requester.user_id, ticker)
    out: list[HistoryPoint] = []
    for r in rows:
        card = r.scorecard or {}
        out.append(
            HistoryPoint(
                analysis_id=r.id,
                date=r.completed_at or r.created_at,
                total=card.get("total"),
                rating=card.get("rating"),
                dimension_scores=card.get("dimension_scores"),
            )
        )
    return out
