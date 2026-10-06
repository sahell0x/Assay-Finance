"""yfinance ingestion.

The whole point of this module is that yfinance row labels are not stable. They differ
between tickers (a bank's income statement has no "Cost Of Revenue"), between sectors,
and between library versions. Indexing a statement DataFrame directly — ``df.loc["Total
Revenue"]`` — is the single most common way a naive implementation breaks on the second
ticker anyone tries.

So: every field goes through :func:`pick`, which walks an alias list, tolerates
duplicate index labels, and returns ``None`` rather than raising when nothing matches.
Absence is a first-class outcome recorded in the data-quality report, not an exception.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# Canonical field -> the labels yfinance has been observed to use for it, most
# authoritative first.
ALIASES: dict[str, list[str]] = {
    "revenue": ["Total Revenue", "Operating Revenue", "Revenues"],
    "cogs": ["Cost Of Revenue", "Cost Of Goods Sold", "Reconciled Cost Of Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": [
        "Operating Income",
        "Total Operating Income As Reported",
        "EBIT",
    ],
    "net_income": [
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income From Continuing Operation Net Minority Interest",
    ],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "tax_provision": ["Tax Provision", "Income Tax Expense"],
    "pretax_income": ["Pretax Income", "Income Before Tax"],
    "current_assets": ["Current Assets", "Total Current Assets"],
    "current_liab": ["Current Liabilities", "Total Current Liabilities"],
    "inventory": ["Inventory"],
    "receivables": ["Accounts Receivable", "Receivables", "Net Receivables"],
    "payables": ["Accounts Payable", "Payables"],
    "cash": [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
    ],
    "total_debt": ["Total Debt"],
    "total_equity": [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Common Stock Equity",
    ],
    "total_assets": ["Total Assets"],
    "total_liabilities": [
        "Total Liabilities Net Minority Interest",
        "Total Liabilities",
    ],
    "retained_earnings": ["Retained Earnings"],
    "ocf": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure", "Purchase Of PPE"],
    "d_and_a": [
        "Depreciation And Amortization",
        "Depreciation Amortization Depletion",
        "Reconciled Depreciation",
    ],
    "shares_diluted": ["Diluted Average Shares"],
    "eps_diluted": ["Diluted EPS"],
}

# Flow items accumulate over a period and are summed to build a TTM figure.
# Stock items are balances at a point in time — TTM takes the most recent one.
FLOW_FIELDS = frozenset(
    {
        "revenue",
        "cogs",
        "gross_profit",
        "operating_income",
        "net_income",
        "ebitda",
        "interest_expense",
        "tax_provision",
        "pretax_income",
        "ocf",
        "capex",
        "d_and_a",
    }
)
STOCK_FIELDS = frozenset(
    {
        "current_assets",
        "current_liab",
        "inventory",
        "receivables",
        "payables",
        "cash",
        "total_debt",
        "total_equity",
        "total_assets",
        "total_liabilities",
        "retained_earnings",
    }
)
# Averaged across the trailing quarters rather than summed or taken latest.
AVERAGED_FIELDS = frozenset({"shares_diluted"})


def _clean(x: Any) -> float | None:
    """Coerce a cell to a float, mapping NaN / NaT / non-numeric to None."""
    if x is None:
        return None
    if isinstance(x, pd.Series):  # duplicate labels collapsed by the caller
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def pick(df: pd.DataFrame | None, key: str) -> pd.Series | None:
    """Return the row for ``key`` as a Series indexed by period, or None.

    Handles three realities of yfinance frames:

    * the label may be absent entirely (different sector, different vintage);
    * the same label may appear more than once, in which case ``.loc`` returns a
      DataFrame — we take the first row that has any data;
    * cells may be NaN, ``None``, or strings.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None

    aliases = ALIASES.get(key, [key])
    index_map = {str(i).strip().lower(): i for i in df.index}

    for alias in aliases:
        label = index_map.get(alias.strip().lower())
        if label is None:
            continue
        row = df.loc[label]
        if isinstance(row, pd.DataFrame):
            # Duplicate labels: prefer the row carrying the most non-null values.
            row = row.iloc[row.notna().sum(axis=1).argmax()]
        series = pd.Series(
            {col: _clean(row[col]) for col in df.columns}, dtype="object"
        )
        if series.notna().any():
            return series
    return None


def _period_label(ts: Any, quarterly: bool = False) -> str:
    try:
        d = pd.Timestamp(ts)
    except (TypeError, ValueError):
        return str(ts)
    if quarterly:
        return f"{d.year}Q{((d.month - 1) // 3) + 1}"
    return f"FY{d.year}"


@dataclass(slots=True)
class Statements:
    """Raw statement frames for one ticker, annual and quarterly."""

    income: pd.DataFrame | None = None
    balance: pd.DataFrame | None = None
    cashflow: pd.DataFrame | None = None
    q_income: pd.DataFrame | None = None
    q_balance: pd.DataFrame | None = None
    q_cashflow: pd.DataFrame | None = None

    def frame_for(self, key: str, quarterly: bool = False) -> pd.DataFrame | None:
        if key in {
            "revenue",
            "cogs",
            "gross_profit",
            "operating_income",
            "net_income",
            "ebitda",
            "interest_expense",
            "tax_provision",
            "pretax_income",
            "shares_diluted",
            "eps_diluted",
        }:
            return self.q_income if quarterly else self.income
        if key in {"ocf", "capex", "d_and_a"}:
            return self.q_cashflow if quarterly else self.cashflow
        return self.q_balance if quarterly else self.balance


@dataclass
class Fundamentals:
    """Everything downstream needs, already normalised.

    ``facts`` maps a period label ("TTM", "FY2024") to a flat dict of canonical fields
    plus the derived ones (fcf, nopat, effective_tax_rate, enterprise_value).
    ``periods`` is newest-first and always leads with "TTM" when it could be built.
    """

    ticker: str
    name: str = ""
    sector: str = ""
    industry: str = ""
    currency: str = "USD"
    periods: list[str] = field(default_factory=list)
    annual_periods: list[str] = field(default_factory=list)
    facts: dict[str, dict[str, float | None]] = field(default_factory=dict)
    market: dict[str, Any] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)

    def get(self, period: str, key: str) -> float | None:
        return self.facts.get(period, {}).get(key)

    def latest(self, key: str) -> float | None:
        for p in self.periods:
            v = self.facts.get(p, {}).get(key)
            if v is not None:
                return v
        return None

    def series(self, key: str) -> list[tuple[str, float | None]]:
        """Annual values newest-first, for trend maths."""
        return [(p, self.facts.get(p, {}).get(key)) for p in self.annual_periods]

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "sector": self.sector,
            "industry": self.industry,
            "currency": self.currency,
            "periods": self.periods,
            "annual_periods": self.annual_periods,
            "facts": self.facts,
            "market": self.market,
            "data_quality": self.data_quality,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Fundamentals:
        return cls(
            ticker=d["ticker"],
            name=d.get("name", ""),
            sector=d.get("sector", ""),
            industry=d.get("industry", ""),
            currency=d.get("currency", "USD"),
            periods=d.get("periods", []),
            annual_periods=d.get("annual_periods", []),
            facts=d.get("facts", {}),
            market=d.get("market", {}),
            data_quality=d.get("data_quality", {}),
        )


# --------------------------------------------------------------------------- derived


def effective_tax_rate(pretax: float | None, tax: float | None) -> float | None:
    """Clamped to [0, 0.5]: loss years and one-off benefits produce nonsense otherwise."""
    if pretax is None or tax is None or pretax <= 0:
        return None
    rate = tax / pretax
    return min(max(rate, 0.0), 0.5)


def derive(row: dict[str, float | None]) -> dict[str, float | None]:
    """Fill in the fields that are computed rather than reported.

    ``capex`` is signed inconsistently across tickers and vintages — some report the
    outflow negative, some positive — so free cash flow always uses ``abs``.
    """
    out = dict(row)

    ocf, capex = out.get("ocf"), out.get("capex")
    out["fcf"] = ocf - abs(capex) if ocf is not None and capex is not None else None

    if out.get("ebitda") is None:
        oi, da = out.get("operating_income"), out.get("d_and_a")
        out["ebitda"] = oi + da if oi is not None and da is not None else None

    if out.get("gross_profit") is None:
        rev, cogs = out.get("revenue"), out.get("cogs")
        out["gross_profit"] = rev - cogs if rev is not None and cogs is not None else None

    tr = effective_tax_rate(out.get("pretax_income"), out.get("tax_provision"))
    out["effective_tax_rate"] = tr

    oi = out.get("operating_income")
    out["nopat"] = oi * (1 - tr) if oi is not None and tr is not None else None

    if out.get("total_liabilities") is None:
        ta, te = out.get("total_assets"), out.get("total_equity")
        out["total_liabilities"] = ta - te if ta is not None and te is not None else None

    # Working capital feeds the Altman Z-score.
    ca, cl = out.get("current_assets"), out.get("current_liab")
    out["working_capital"] = ca - cl if ca is not None and cl is not None else None

    return out


def _extract_period(stmts: Statements, col: Any, quarterly: bool) -> dict[str, float | None]:
    row: dict[str, float | None] = {}
    for key in ALIASES:
        frame = stmts.frame_for(key, quarterly=quarterly)
        series = pick(frame, key)
        row[key] = _clean(series.get(col)) if series is not None else None
    return row


def build_facts(stmts: Statements, max_annual: int = 5) -> tuple[dict, list[str], list[str]]:
    """Turn raw frames into ``{period: {field: value}}`` plus the period ordering."""
    facts: dict[str, dict[str, float | None]] = {}
    annual_labels: list[str] = []

    if stmts.income is not None and not stmts.income.empty:
        cols = sorted(stmts.income.columns, reverse=True)[:max_annual]
        for col in cols:
            label = _period_label(col)
            if label in facts:
                continue
            facts[label] = derive(_extract_period(stmts, col, quarterly=False))
            annual_labels.append(label)

    ttm = build_ttm(stmts)
    periods: list[str] = []
    if ttm is not None:
        facts["TTM"] = ttm
        periods.append("TTM")
    periods.extend(annual_labels)
    return facts, periods, annual_labels


def build_ttm(stmts: Statements) -> dict[str, float | None] | None:
    """Sum the last four quarters for flows, take the newest balance for stocks.

    Returns None when fewer than four quarters of revenue are available — a partial TTM
    is worse than no TTM because it silently understates every flow metric.
    """
    qi = stmts.q_income
    if qi is None or qi.empty:
        return None

    cols = sorted(qi.columns, reverse=True)[:4]
    if len(cols) < 4:
        return None

    row: dict[str, float | None] = {}
    for key in ALIASES:
        if key in FLOW_FIELDS:
            frame = stmts.frame_for(key, quarterly=True)
            series = pick(frame, key)
            if series is None:
                row[key] = None
                continue
            vals = [_clean(series.get(c)) for c in cols]
            row[key] = sum(v for v in vals if v is not None) if all(
                v is not None for v in vals
            ) else None
        elif key in AVERAGED_FIELDS:
            frame = stmts.frame_for(key, quarterly=True)
            series = pick(frame, key)
            vals = (
                [v for v in (_clean(series.get(c)) for c in cols) if v is not None]
                if series is not None
                else []
            )
            row[key] = sum(vals) / len(vals) if vals else None
        else:  # stock field — newest balance available
            frame = stmts.frame_for(key, quarterly=True)
            series = pick(frame, key)
            val = None
            if series is not None:
                for c in sorted(qi.columns, reverse=True):
                    v = _clean(series.get(c))
                    if v is not None:
                        val = v
                        break
            if val is None:  # fall back to the latest annual balance
                a_series = pick(stmts.frame_for(key, quarterly=False), key)
                if a_series is not None and stmts.balance is not None:
                    for c in sorted(stmts.balance.columns, reverse=True):
                        v = _clean(a_series.get(c))
                        if v is not None:
                            val = v
                            break
            row[key] = val

    if row.get("revenue") is None:
        return None
    return derive(row)


def assess_quality(f: Fundamentals) -> dict:
    """A candid report on what could not be sourced. Surfaced verbatim in the UI."""
    critical = ["revenue", "net_income", "total_assets", "total_equity"]
    important = ["operating_income", "ocf", "capex", "current_assets", "current_liab"]

    latest = f.periods[0] if f.periods else None
    row = f.facts.get(latest, {}) if latest else {}

    missing_critical = [k for k in critical if row.get(k) is None]
    missing_important = [k for k in important if row.get(k) is None]

    warnings: list[str] = []
    if len(f.annual_periods) < 3:
        warnings.append(
            f"Only {len(f.annual_periods)} annual period(s) available; "
            "multi-year growth rates are unavailable or unreliable."
        )
    if "TTM" not in f.periods:
        warnings.append(
            "Trailing-twelve-month figures could not be assembled (fewer than four "
            "quarterly statements); the most recent fiscal year is used instead."
        )
    if missing_critical:
        warnings.append(
            "Missing core statement lines: " + ", ".join(missing_critical) + "."
        )
    if missing_important:
        warnings.append(
            "Some ratios are unavailable; not reported: " + ", ".join(missing_important) + "."
        )

    total = len(critical) + len(important)
    found = total - len(missing_critical) - len(missing_important)
    return {
        "coverage": round(found / total, 3) if total else 0.0,
        "annual_periods": len(f.annual_periods),
        "has_ttm": "TTM" in f.periods,
        "missing_critical": missing_critical,
        "missing_important": missing_important,
        "warnings": warnings,
        "usable": not missing_critical,
    }


# ============================================================================ fetching
#
# Everything above is pure and testable without a network. Everything below talks to
# yfinance and Redis.

import asyncio  # noqa: E402
import time  # noqa: E402

from ..config import settings  # noqa: E402
from ..core.cache import cache_get, cache_set  # noqa: E402


def _safe_info(tk) -> dict:
    """``Ticker.info`` is rate-limited and throws on a bad day. It is never load-bearing."""
    try:
        info = tk.info or {}
        return info if isinstance(info, dict) else {}
    except Exception as exc:
        log.info("info unavailable: %s", exc)
        return {}


def _market_snapshot(tk, ticker: str) -> dict:
    """Price/shares/market cap from ``fast_info``, which is the reliable endpoint."""
    snap: dict[str, Any] = {
        "price": None,
        "market_cap": None,
        "shares_out": None,
        "currency": "USD",
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
    }
    try:
        fi = tk.fast_info
        for key, attr in (
            ("price", "last_price"),
            ("market_cap", "market_cap"),
            ("shares_out", "shares"),
            ("fifty_two_week_high", "year_high"),
            ("fifty_two_week_low", "year_low"),
        ):
            try:
                snap[key] = _clean(getattr(fi, attr, None))
            except Exception:
                snap[key] = None
        try:
            snap["currency"] = getattr(fi, "currency", None) or "USD"
        except Exception:
            pass
    except Exception as exc:
        log.warning("fast_info failed for %s: %s", ticker, exc)

    info = _safe_info(tk)
    snap.setdefault("name", "")
    snap["name"] = info.get("longName") or info.get("shortName") or ticker
    snap["sector"] = info.get("sector") or ""
    snap["industry"] = info.get("industry") or ""
    # The currency the statements are written in, which for a foreign filer's US
    # listing (SONY, TM) differs from the currency its shares trade in.
    snap["financial_currency"] = info.get("financialCurrency") or None
    if snap["market_cap"] is None:
        snap["market_cap"] = _clean(info.get("marketCap"))
    if snap["price"] is None:
        snap["price"] = _clean(info.get("currentPrice") or info.get("regularMarketPrice"))
    if snap["shares_out"] is None:
        snap["shares_out"] = _clean(info.get("sharesOutstanding"))
    return snap


def fetch_statements_sync(ticker: str) -> tuple[Statements, dict]:
    """Blocking yfinance fetch. Called from a thread; never from the event loop."""
    import yfinance as yf

    tk = yf.Ticker(ticker)

    def _frame(attr: str) -> pd.DataFrame | None:
        try:
            df = getattr(tk, attr)
            return df if isinstance(df, pd.DataFrame) and not df.empty else None
        except Exception as exc:
            log.info("%s.%s unavailable: %s", ticker, attr, exc)
            return None

    stmts = Statements(
        income=_frame("income_stmt"),
        balance=_frame("balance_sheet"),
        cashflow=_frame("cashflow"),
        q_income=_frame("quarterly_income_stmt"),
        q_balance=_frame("quarterly_balance_sheet"),
        q_cashflow=_frame("quarterly_cashflow"),
    )
    return stmts, _market_snapshot(tk, ticker)


def build_fundamentals_sync(ticker: str) -> Fundamentals:
    ticker = ticker.upper().strip()
    t0 = time.perf_counter()
    stmts, market = fetch_statements_sync(ticker)
    facts, periods, annual = build_facts(stmts)

    f = Fundamentals(
        ticker=ticker,
        name=market.get("name") or ticker,
        sector=market.get("sector") or "",
        industry=market.get("industry") or "",
        currency=market.get("currency") or "USD",
        periods=periods,
        annual_periods=annual,
        facts=facts,
        market=market,
    )

    # Enterprise value needs the market cap, so it is derived here rather than in
    # ``derive`` which only sees statement rows.
    mcap = market.get("market_cap")
    for period in f.periods:
        row = f.facts[period]
        debt, cash = row.get("total_debt"), row.get("cash")
        row["market_cap"] = mcap
        row["enterprise_value"] = (
            mcap + (debt or 0.0) - (cash or 0.0) if mcap is not None else None
        )

    f.data_quality = assess_quality(f)
    f.data_quality["fetch_ms"] = int((time.perf_counter() - t0) * 1000)
    return f


async def get_fundamentals(ticker: str, *, use_cache: bool = True) -> Fundamentals:
    """Cached, non-blocking entry point. 12-hour TTL — statements change quarterly."""
    ticker = ticker.upper().strip()
    key = f"fund:v2:{ticker}"

    if use_cache:
        cached = await cache_get(key)
        if cached:
            return Fundamentals.from_dict(cached)

    f = await asyncio.to_thread(build_fundamentals_sync, ticker)
    if f.data_quality.get("usable"):
        await cache_set(key, f.to_dict(), settings.fundamentals_cache_ttl)
    return f
