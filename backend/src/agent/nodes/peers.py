"""Node 6: peer comparison and valuation.

This node runs last because it writes back. Once peer values exist, every metric
produced by nodes 3-5 gets a ``peer_percentile`` stamped onto it, which turns "operating
margin is 31%" into "operating margin is 31%, better than 88% of its comparables" — a
far more useful sentence, and one the memo can lean on.

Peers are fetched concurrently but with a small pool: yfinance is a scraper with rate
limits, and eight parallel requests is a reliable way to get throttled.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, wait

from ...analytics import ratios as r
from ...analytics import scoring as sc
from ...analytics import trends as t
from ...config import settings
from ...data.fundamentals import Fundamentals, build_fundamentals_sync
from ...data.peers import industry_label, resolve_peers
from ..progress import node
from ..state import MetricBlock, MetricValue, flag_from_score, metric
from ._shared import narrate, usage_from

log = logging.getLogger(__name__)

# (metric key, whether a higher reading is better) for the cross-block percentile pass.
RANKABLE: dict[str, bool] = {
    "gross_margin": True,
    "operating_margin": True,
    "net_margin": True,
    "ebitda_margin": True,
    "fcf_margin": True,
    "roe": True,
    "roa": True,
    "roic": True,
    "asset_turnover": True,
    "current_ratio": True,
    "quick_ratio": True,
    "interest_coverage": True,
    "fcf_to_debt": True,
    "altman_z": True,
    "debt_to_equity": False,
    "net_debt_ebitda": False,
    "ccc": False,
    "dso": False,
    "rev_yoy": True,
    "rev_cagr_3y": True,
    "eps_growth": True,
    "fcf_cagr_3y": True,
}

VALUATION_METRICS: dict[str, bool] = {
    "pe": False,
    "ev_ebitda": False,
    "ev_sales": False,
    "price_to_book": False,
    "fcf_yield": True,
    "peg": False,
}


def _snapshot(f: Fundamentals) -> dict:
    """Flatten a company into the comparable numbers, all from the same period."""
    period = f.periods[0] if f.periods else None
    if period is None:
        return {}
    row = f.facts.get(period, {})
    prior_label = f.annual_periods[0] if period == "TTM" and f.annual_periods else None
    prior = f.facts.get(prior_label, {}) if prior_label else {}
    rev_series = f.series("revenue")

    return {
        "ticker": f.ticker,
        "name": f.name,
        "period": period,
        "market_cap": row.get("market_cap"),
        "revenue": row.get("revenue"),
        "ebitda": row.get("ebitda"),
        # valuation
        "pe": r.pe_ratio(row),
        "ev_ebitda": r.ev_ebitda(row),
        "ev_sales": r.ev_sales(row),
        "price_to_book": r.price_to_book(row),
        "fcf_yield": r.fcf_yield(row),
        "peg": r.peg_ratio(row, t.yoy(rev_series)),
        # quality
        "gross_margin": r.gross_margin(row),
        "operating_margin": r.operating_margin(row),
        "net_margin": r.net_margin(row),
        "ebitda_margin": r.ebitda_margin(row),
        "fcf_margin": r.fcf_margin(row),
        "roe": r.roe(row, prior),
        "roa": r.roa(row, prior),
        "roic": r.roic(row, prior),
        "asset_turnover": r.asset_turnover(row, prior),
        # health
        "current_ratio": r.current_ratio(row),
        "quick_ratio": r.quick_ratio(row),
        "interest_coverage": r.interest_coverage(row),
        "fcf_to_debt": r.fcf_to_debt(row),
        "altman_z": r.altman_z(row),
        "debt_to_equity": r.debt_to_equity(row),
        "net_debt_ebitda": r.net_debt_to_ebitda(row),
        "ccc": r.cash_conversion_cycle(row),
        "dso": r.dso(row),
        # growth
        "rev_yoy": t.yoy(rev_series),
        "rev_cagr_3y": t.cagr_over(rev_series, 3),
        "eps_growth": t.eps_growth([(p, t.derive_eps(f.facts.get(p, {}))) for p in f.annual_periods]),
        "fcf_cagr_3y": t.cagr_over(f.series("fcf"), 3),
    }


# One budget for the whole peer fetch. The per-future timeout alone was not enough: a
# `with ThreadPoolExecutor` block waits for every thread on exit, so a single hung data
# request held the analysis until the job's 8-minute limit killed it and the page sat
# on "running" for good. Peers that are not back in time are simply left out.
PEER_FETCH_BUDGET_S = 90


def _fetch_many(tickers: list[str]) -> dict[str, dict]:
    """Blocking, pooled peer fetch. Called once, off the event loop."""
    out: dict[str, dict] = {}
    if not tickers:
        return out
    pool = ThreadPoolExecutor(max_workers=4)
    futures = {pool.submit(_fetch_one, tk): tk for tk in tickers}
    try:
        done, pending = wait(futures, timeout=PEER_FETCH_BUDGET_S)
        for fut in done:
            tk = futures[fut]
            try:
                snap = fut.result()
            except Exception as exc:
                log.warning("peer %s failed: %s", tk, exc)
                continue
            if snap:
                out[tk] = snap
        for fut in pending:
            log.warning("peer %s skipped: no data within %ss", futures[fut], PEER_FETCH_BUDGET_S)
    finally:
        # Do not wait for stragglers: their threads finish in the background and their
        # results are discarded.
        pool.shutdown(wait=False, cancel_futures=True)
    return out


def _fetch_one(tk: str) -> dict | None:
    try:
        f = build_fundamentals_sync(tk)
    except Exception as exc:
        log.warning("peer %s fetch error: %s", tk, exc)
        return None
    if not f.periods:
        return None
    # Statements in yen against a price in dollars make every multiple nonsense (Sony
    # printed an EV/EBITDA of -0.06x). There is no FX conversion here, so such a peer
    # is left out rather than compared.
    reporting = f.market.get("financial_currency")
    if reporting and reporting != (f.market.get("currency") or "USD"):
        log.info("peer %s skipped: reports in %s, trades in %s", tk, reporting, f.market.get("currency"))
        return None
    return _snapshot(f)


@node("peers", optional=True)
async def peers(state: dict) -> dict:
    f = Fundamentals.from_dict(state["facts"])
    supplied = state.get("peer_tickers") or []
    peer_list, source = resolve_peers(
        f.ticker, sector=f.sector, industry=f.industry,
        supplied=supplied, limit=settings.max_peers,
    )

    warnings: list[str] = []

    target = _snapshot(f)
    peer_snaps = await asyncio.to_thread(_fetch_many, peer_list) if peer_list else {}

    # Every name the user typed failed — usually a company name rather than a ticker
    # ("GOOGLE" for GOOGL). Comparing against nothing would quietly drop the peer
    # medians and the price target, so fall back to the industry cohort instead.
    if source == "user" and not peer_snaps:
        unknown = peer_list
        peer_list, source = resolve_peers(
            f.ticker, sector=f.sector, industry=f.industry, limit=settings.max_peers,
        )
        peer_snaps = await asyncio.to_thread(_fetch_many, peer_list) if peer_list else {}
        warnings.append(
            f"None of the companies you entered to compare against ({', '.join(unknown)}) "
            f"could be found, so it is compared with similar companies in its industry "
            f"instead."
        )

    if source == "none":
        warnings.append(
            "No similar companies could be found, so this company's valuation is shown "
            "on its own, without a comparison."
        )
    elif source == "fallback":
        warnings.append(
            "No close industry match was found, so this company is compared with a general "
            "group of large companies. Treat the comparison as rough context only."
        )

    if peer_list and len(peer_snaps) < len(peer_list):
        missing = sorted(set(peer_list) - set(peer_snaps))
        warnings.append(
            f"Usable financial data was not available for {', '.join(missing)}, so "
            f"{'it was' if len(missing) == 1 else 'they were'} left out of the comparison."
        )

    period = target.get("period", "")
    metrics: dict[str, MetricValue] = {}
    for key, higher_better in VALUATION_METRICS.items():
        peer_values = [s.get(key) for s in peer_snaps.values()]
        value = target.get(key)
        pctl = t.percentile_rank(value, peer_values, higher_is_better=higher_better)
        med = t.median(peer_values)
        metrics[key] = metric(
            key, value, unit=_unit_for(key), period=period,
            formula=_formula_for(key), label=_label_for(key),
            inputs={
                "market_cap": target.get("market_cap"),
                "enterprise_value": f.facts.get(period, {}).get("enterprise_value"),
                "peer_median": med,
                "peers_with_data": len([v for v in peer_values if v is not None]),
            },
            note=None if value is not None else _absent_reason(key),
        )
        metrics[key].peer_percentile = pctl

    score, detail = sc.score_dimension("valuation", {k: m.value for k, m in metrics.items()})
    for name, m in metrics.items():
        m.flag = m.flag or flag_from_score(detail.get(name, {}).get("score"))

    # --- write percentiles back onto the earlier blocks ---------------------
    updates: dict[str, MetricBlock] = {}
    for dim in ("profitability", "liquidity", "growth"):
        block = state.get(dim)
        if block is None:
            continue
        changed = False
        for key, m in block.metrics.items():
            if key not in RANKABLE or m.value is None:
                continue
            peer_values = [s.get(key) for s in peer_snaps.values()]
            pctl = t.percentile_rank(m.value, peer_values, higher_is_better=RANKABLE[key])
            if pctl is not None:
                m.peer_percentile = pctl
                changed = True
        if changed:
            updates[dim] = block

    raw_multiples = [s.get("ev_ebitda") for s in peer_snaps.values()]
    peer_median_ev_ebitda, excluded_multiples = t.trimmed_median(
        raw_multiples, cap=t.NOT_MEANINGFUL_ABOVE["ev_ebitda"]
    )
    contributing = len([v for v in raw_multiples if v is not None]) - len(excluded_multiples)
    untrimmed_median = t.median(raw_multiples)
    if excluded_multiples:
        warnings.append(
            f"{len(excluded_multiples)} similar "
            f"{'company was' if len(excluded_multiples) == 1 else 'companies were'} left out "
            f"of the fair value estimate because "
            f"{'its' if len(excluded_multiples) == 1 else 'their'} valuation reading "
            f"({', '.join(f'{v:.0f}x' for v in sorted(excluded_multiples))} EV/EBITDA) comes "
            f"from unusually low profits rather than from how the market values the "
            f"business. The estimate uses the other {max(contributing, 0)}."
        )
    if peer_median_ev_ebitda is not None and contributing < 3:
        warnings.append(
            f"Only {max(contributing, 0)} similar "
            f"{'company' if contributing == 1 else 'companies'} had usable valuation data, "
            f"so the fair value range is less reliable than usual."
        )

    row = f.facts.get(period, {})
    target_price = sc.price_target(
        peer_median_ev_ebitda=peer_median_ev_ebitda,
        company_ebitda=row.get("ebitda"),
        total_debt=row.get("total_debt"),
        cash=row.get("cash"),
        shares=f.market.get("shares_out") or row.get("shares_diluted"),
        current_price=f.market.get("price"),
    )
    if target_price.get("stretched"):
        warnings.append(target_price["caveat"])

    usage = usage_from(state)
    narrative = await narrate(
        company=f.name or f.ticker,
        section=f"Valuation against {industry_label(f.sector, f.industry)} peers",
        metrics=metrics,
        extra_context=_peer_context(peer_snaps, source, peer_median_ev_ebitda),
        warnings=warnings,
        usage=usage,
    )

    block = MetricBlock(
        dimension="peers",
        metrics=metrics,
        narrative=narrative,
        score=score if score is not None else 0.0,
        warnings=warnings,
        extras={
            "period": period,
            "source": source,
            "requested": peer_list,
            "resolved": sorted(peer_snaps),
            "peer_rows": _peer_table(target, peer_snaps),
            "peer_median_ev_ebitda": peer_median_ev_ebitda,
            "peer_median_ev_ebitda_untrimmed": untrimmed_median,
            "excluded_multiples": excluded_multiples,
            "multiples_contributing": max(contributing, 0),
            "scatter": _scatter(target, peer_snaps),
            "score_detail": detail,
        },
    )

    return {
        "peers": block,
        "price_target": target_price,
        "cost": usage.as_dict(),
        "warnings": warnings,
        **updates,
    }


def _peer_table(target: dict, peer_snaps: dict[str, dict]) -> list[dict]:
    """Target first, then peers by market cap. Used directly by the comparison table."""
    keys = [
        "ticker", "name", "market_cap", "pe", "ev_ebitda", "ev_sales",
        "price_to_book", "fcf_yield", "operating_margin", "roic", "rev_yoy",
    ]
    rows = [{**{k: target.get(k) for k in keys}, "is_target": True}]
    ordered = sorted(
        peer_snaps.values(), key=lambda s: s.get("market_cap") or 0, reverse=True
    )
    rows += [{**{k: s.get(k) for k in keys}, "is_target": False} for s in ordered]
    return rows


def _scatter(target: dict, peer_snaps: dict[str, dict]) -> dict:
    """Valuation against quality: EV/EBITDA on y, ROIC on x, bubble by market cap.

    Non-meaningful multiples are excluded here for the same reason they are excluded
    from the median. One peer at 2,900x EBITDA sets the y-axis to four figures and
    flattens every real company onto the baseline, so the plot stops saying anything.
    The target is always kept, even if its own multiple is extreme, because a chart of
    a company's peers that omits the company is worse than a stretched axis.
    """
    cap = t.NOT_MEANINGFUL_ABOVE["ev_ebitda"]
    points: list[dict] = []
    excluded: list[str] = []

    for s in [target, *peer_snaps.values()]:
        if s.get("ev_ebitda") is None or s.get("roic") is None:
            continue
        is_target = s["ticker"] == target.get("ticker")
        if s["ev_ebitda"] > cap and not is_target:
            excluded.append(s["ticker"])
            continue
        points.append(
            {
                "ticker": s["ticker"],
                "x": s["roic"],
                "y": s["ev_ebitda"],
                "size": s.get("market_cap"),
                "is_target": is_target,
            }
        )
    return {"points": points, "excluded": sorted(excluded), "cap": cap}


def _peer_context(peer_snaps: dict, source: str, median_ev_ebitda: float | None) -> str:
    if not peer_snaps:
        return "No peer data was available, so the multiples above have no relative context."
    bits = [f"Compared against {len(peer_snaps)} companies ({'caller-supplied' if source == 'user' else source} cohort)."]
    if median_ev_ebitda is not None:
        bits.append(f"Peer median EV/EBITDA is {median_ev_ebitda:.1f}x.")
    bits.append("A high percentile on a multiple means the company trades more expensively than its peers.")
    return " ".join(bits)


def _unit_for(key: str) -> str:
    return {"fcf_yield": "percent"}.get(key, "x")


def _label_for(key: str) -> str:
    return {
        "pe": "Price / earnings",
        "ev_ebitda": "EV / EBITDA",
        "ev_sales": "EV / sales",
        "price_to_book": "Price / book",
        "fcf_yield": "Free cash flow yield",
        "peg": "PEG ratio",
    }[key]


def _formula_for(key: str) -> str:
    return {
        "pe": "market_cap / net_income",
        "ev_ebitda": "enterprise_value / ebitda, where enterprise_value = market_cap + total_debt - cash",
        "ev_sales": "enterprise_value / revenue",
        "price_to_book": "market_cap / total_equity",
        "fcf_yield": "(operating_cash_flow - |capex|) / market_cap",
        "peg": "price_to_earnings / (revenue_growth x 100)",
    }[key]


def _absent_reason(key: str) -> str:
    return {
        "pe": "Earnings are negative or zero, so the multiple is not meaningful",
        "ev_ebitda": "EBITDA is not positive, so the multiple is not meaningful",
        "ev_sales": "Enterprise value or revenue is unavailable",
        "price_to_book": "Book value of equity is zero or negative",
        "fcf_yield": "Free cash flow or market capitalisation is unavailable",
        "peg": "Requires a positive price/earnings ratio and positive revenue growth",
    }[key]
