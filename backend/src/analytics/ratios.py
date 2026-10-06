"""Every number the system reports is computed here.

These are pure functions over plain dicts. They import nothing from the agent, the LLM
layer, or the database — that separation is what makes the "the model never computes a
number" rule enforceable rather than aspirational.

The universal convention: a ratio whose inputs are missing, or whose denominator is zero
or economically meaningless (negative equity, negative EBITDA), returns ``None``. It
never returns 0, ``inf``, or ``nan``. Downstream code treats ``None`` as "not available"
and says so in the UI.
"""

from __future__ import annotations

import math

Num = float | None

DAYS_IN_YEAR = 365.0


# ------------------------------------------------------------------------- primitives


def safe_div(numerator: Num, denominator: Num, *, allow_negative_denom: bool = True) -> Num:
    """Division that refuses to produce a misleading number."""
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    if not allow_negative_denom and denominator < 0:
        return None
    try:
        result = numerator / denominator
    except ZeroDivisionError:
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def average(a: Num, b: Num) -> Num:
    """Two-point average for balance-sheet items. Falls back to whichever exists."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2.0


def pct_change(current: Num, prior: Num) -> Num:
    """Growth rate. Undefined from a zero or negative base — a swing from -10 to +5 is
    not a '150% increase' in any useful sense."""
    if current is None or prior is None:
        return None
    if prior <= 0:
        return None
    return (current - prior) / prior


def cagr(latest: Num, earliest: Num, years: float) -> Num:
    """Compound annual growth rate. Requires a positive base and a positive endpoint."""
    if latest is None or earliest is None or years <= 0:
        return None
    if earliest <= 0 or latest <= 0:
        return None
    try:
        return (latest / earliest) ** (1.0 / years) - 1.0
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


# ---------------------------------------------------------------------- profitability


def gross_margin(row: dict) -> Num:
    return safe_div(row.get("gross_profit"), row.get("revenue"))


def operating_margin(row: dict) -> Num:
    return safe_div(row.get("operating_income"), row.get("revenue"))


def net_margin(row: dict) -> Num:
    return safe_div(row.get("net_income"), row.get("revenue"))


def ebitda_margin(row: dict) -> Num:
    return safe_div(row.get("ebitda"), row.get("revenue"))


def fcf_margin(row: dict) -> Num:
    return safe_div(row.get("fcf"), row.get("revenue"))


def roe(row: dict, prior: dict | None = None) -> Num:
    """Return on equity against *average* equity.

    Negative average equity makes this meaningless — a company with a deficit and a loss
    would show a positive ROE. The caller flags it ``unreliable``.
    """
    avg_eq = average(row.get("total_equity"), (prior or {}).get("total_equity"))
    if avg_eq is None or avg_eq <= 0:
        return None
    return safe_div(row.get("net_income"), avg_eq)


def roa(row: dict, prior: dict | None = None) -> Num:
    avg_assets = average(row.get("total_assets"), (prior or {}).get("total_assets"))
    return safe_div(row.get("net_income"), avg_assets, allow_negative_denom=False)


def invested_capital(row: dict) -> Num:
    """Debt + equity - cash. The capital the operating business actually employs."""
    debt, equity, cash = row.get("total_debt"), row.get("total_equity"), row.get("cash")
    if equity is None:
        return None
    return (debt or 0.0) + equity - (cash or 0.0)


def roic(row: dict, prior: dict | None = None) -> Num:
    ic_now = invested_capital(row)
    ic_prior = invested_capital(prior) if prior else None
    avg_ic = average(ic_now, ic_prior)
    if avg_ic is None or avg_ic <= 0:
        return None
    return safe_div(row.get("nopat"), avg_ic)


def asset_turnover(row: dict, prior: dict | None = None) -> Num:
    avg_assets = average(row.get("total_assets"), (prior or {}).get("total_assets"))
    return safe_div(row.get("revenue"), avg_assets, allow_negative_denom=False)


def equity_multiplier(row: dict, prior: dict | None = None) -> Num:
    avg_assets = average(row.get("total_assets"), (prior or {}).get("total_assets"))
    avg_eq = average(row.get("total_equity"), (prior or {}).get("total_equity"))
    if avg_eq is None or avg_eq <= 0:
        return None
    return safe_div(avg_assets, avg_eq)


def dupont(row: dict, prior: dict | None = None) -> dict:
    """ROE decomposed into margin x turnover x leverage.

    ``reconciles`` reports whether the product actually reproduces the directly computed
    ROE within a tolerance; when it does not, something upstream is inconsistent and the
    node says so rather than presenting a tidy identity that does not hold.
    """
    nm = net_margin(row)
    at = asset_turnover(row, prior)
    em = equity_multiplier(row, prior)
    direct = roe(row, prior)

    product = None
    if nm is not None and at is not None and em is not None:
        product = nm * at * em

    reconciles = None
    if product is not None and direct is not None:
        reconciles = abs(product - direct) <= max(0.005, abs(direct) * 0.02)

    return {
        "net_margin": nm,
        "asset_turnover": at,
        "equity_multiplier": em,
        "product": product,
        "roe_direct": direct,
        "reconciles": reconciles,
    }


# ----------------------------------------------------------- liquidity and solvency


def current_ratio(row: dict) -> Num:
    return safe_div(row.get("current_assets"), row.get("current_liab"), allow_negative_denom=False)


def quick_ratio(row: dict) -> Num:
    ca, inv, cl = row.get("current_assets"), row.get("inventory"), row.get("current_liab")
    if ca is None or cl is None or cl <= 0:
        return None
    return (ca - (inv or 0.0)) / cl


def cash_ratio(row: dict) -> Num:
    return safe_div(row.get("cash"), row.get("current_liab"), allow_negative_denom=False)


def debt_to_equity(row: dict) -> Num:
    eq = row.get("total_equity")
    if eq is None or eq <= 0:
        return None
    return safe_div(row.get("total_debt"), eq)


def net_debt(row: dict) -> Num:
    debt, cash = row.get("total_debt"), row.get("cash")
    if debt is None and cash is None:
        return None
    return (debt or 0.0) - (cash or 0.0)


def net_debt_to_ebitda(row: dict) -> Num:
    """Undefined when EBITDA is zero or negative — the ratio would be a sign-flipped
    artefact, not leverage."""
    ebitda = row.get("ebitda")
    if ebitda is None or ebitda <= 0:
        return None
    nd = net_debt(row)
    if nd is None:
        return None
    return nd / ebitda


def interest_coverage(row: dict) -> Num:
    """EBIT over absolute interest expense. ``None`` when there is no interest expense —
    the caller flags that case ``strong`` rather than printing infinity."""
    ie = row.get("interest_expense")
    oi = row.get("operating_income")
    if oi is None or ie is None:
        return None
    if abs(ie) < 1.0:  # sub-dollar values are reporting noise, not real coverage
        return None
    return oi / abs(ie)


def fcf_to_debt(row: dict) -> Num:
    debt = row.get("total_debt")
    if debt is None or debt <= 0:
        return None
    return safe_div(row.get("fcf"), debt)


def dso(row: dict) -> Num:
    """Days sales outstanding."""
    r = safe_div(row.get("receivables"), row.get("revenue"), allow_negative_denom=False)
    return r * DAYS_IN_YEAR if r is not None else None


def dio(row: dict) -> Num:
    """Days inventory outstanding."""
    r = safe_div(row.get("inventory"), row.get("cogs"), allow_negative_denom=False)
    return r * DAYS_IN_YEAR if r is not None else None


def dpo(row: dict) -> Num:
    """Days payables outstanding."""
    r = safe_div(row.get("payables"), row.get("cogs"), allow_negative_denom=False)
    return r * DAYS_IN_YEAR if r is not None else None


def cash_conversion_cycle(row: dict) -> Num:
    a, b, c = dso(row), dio(row), dpo(row)
    if a is None or b is None or c is None:
        return None
    return a + b - c


def altman_z(row: dict) -> Num:
    """Altman Z-score for public manufacturers.

    Z = 1.2(WC/TA) + 1.4(RE/TA) + 3.3(EBIT/TA) + 0.6(MCap/TotalLiab) + 1.0(Rev/TA)

    Calibrated on 1960s manufacturers; it materially misreads banks (no working capital
    in the usual sense) and asset-light software (tiny TA inflates every term). The
    caller attaches that caveat to the output.
    """
    ta = row.get("total_assets")
    if ta is None or ta <= 0:
        return None

    wc = row.get("working_capital")
    re = row.get("retained_earnings")
    ebit = row.get("operating_income")
    mcap = row.get("market_cap")
    tl = row.get("total_liabilities")
    rev = row.get("revenue")

    if any(v is None for v in (wc, re, ebit, rev)) or tl is None or tl <= 0 or mcap is None:
        return None

    return (
        1.2 * (wc / ta)
        + 1.4 * (re / ta)
        + 3.3 * (ebit / ta)
        + 0.6 * (mcap / tl)
        + 1.0 * (rev / ta)
    )


def altman_band(z: Num) -> str | None:
    if z is None:
        return None
    if z > 2.99:
        return "safe"
    if z >= 1.81:
        return "grey"
    return "distress"


# ----------------------------------------------------------------------- valuation


def pe_ratio(row: dict) -> Num:
    ni = row.get("net_income")
    if ni is None or ni <= 0:  # a negative P/E is not a valuation, it is a sign
        return None
    return safe_div(row.get("market_cap"), ni)


def ev_ebitda(row: dict) -> Num:
    ebitda = row.get("ebitda")
    if ebitda is None or ebitda <= 0:
        return None
    return safe_div(row.get("enterprise_value"), ebitda)


def ev_sales(row: dict) -> Num:
    return safe_div(row.get("enterprise_value"), row.get("revenue"), allow_negative_denom=False)


def price_to_book(row: dict) -> Num:
    eq = row.get("total_equity")
    if eq is None or eq <= 0:
        return None
    return safe_div(row.get("market_cap"), eq)


def fcf_yield(row: dict) -> Num:
    return safe_div(row.get("fcf"), row.get("market_cap"), allow_negative_denom=False)


def peg_ratio(row: dict, growth_rate: Num) -> Num:
    """P/E over growth, expressed in percentage points. Requires positive growth."""
    pe = pe_ratio(row)
    if pe is None or growth_rate is None or growth_rate <= 0:
        return None
    return pe / (growth_rate * 100.0)
