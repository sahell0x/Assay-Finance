"""Node 3: margins, returns on capital, and the DuPont decomposition.

Every metric is computed for TTM (or the latest fiscal year when no TTM could be built)
and carries a five-period history for the trend chart. The DuPont identity is included
because it turns a single ROE number into an argument: high returns from margin are a
different business than high returns from leverage, and the memo should be able to say
which.
"""

from __future__ import annotations

from ...analytics import ratios as r
from ...analytics import scoring as sc
from ...data.fundamentals import Fundamentals
from ..progress import node
from ..state import MetricBlock, flag_from_score, metric
from ._shared import narrate, usage_from


def _prior_of(f: Fundamentals, period: str) -> dict:
    """The period before ``period``, for average-balance ratios.

    For TTM the comparison is the most recent completed fiscal year, which is the
    closest thing to a year-ago balance sheet the annual statements offer.
    """
    if period == "TTM":
        return f.facts.get(f.annual_periods[0], {}) if f.annual_periods else {}
    if period in f.annual_periods:
        i = f.annual_periods.index(period)
        if i + 1 < len(f.annual_periods):
            return f.facts.get(f.annual_periods[i + 1], {})
    return {}


def _history(f: Fundamentals, fn, *, needs_prior: bool = False) -> list[dict]:
    out = []
    for p in f.annual_periods[:5]:
        row = f.facts.get(p, {})
        value = fn(row, _prior_of(f, p)) if needs_prior else fn(row)
        out.append({"period": p, "value": value})
    return out


@node("profitability")
async def profitability(state: dict) -> dict:
    f = Fundamentals.from_dict(state["facts"])
    flags = (state.get("data_quality") or {}).get("sector_flags", {})
    period = f.periods[0] if f.periods else ""
    row = f.facts.get(period, {})
    prior = _prior_of(f, period)

    warnings: list[str] = []
    metrics = {}

    # --- margins -----------------------------------------------------------
    if flags.get("suppress_gross_margin"):
        metrics["gross_margin"] = metric(
            "gross_margin", None, unit="percent", period=period,
            formula="gross_profit / revenue", label="Gross margin",
            inputs={"gross_profit": row.get("gross_profit"), "revenue": row.get("revenue")},
            note="Not meaningful for a financial-sector issuer, which reports no cost of revenue",
        )
    else:
        metrics["gross_margin"] = metric(
            "gross_margin", r.gross_margin(row), unit="percent", period=period,
            formula="gross_profit / revenue", label="Gross margin",
            inputs={"gross_profit": row.get("gross_profit"), "revenue": row.get("revenue")},
            history=_history(f, r.gross_margin),
        )

    metrics["operating_margin"] = metric(
        "operating_margin", r.operating_margin(row), unit="percent", period=period,
        formula="operating_income / revenue", label="Operating margin",
        inputs={"operating_income": row.get("operating_income"), "revenue": row.get("revenue")},
        history=_history(f, r.operating_margin),
    )
    metrics["net_margin"] = metric(
        "net_margin", r.net_margin(row), unit="percent", period=period,
        formula="net_income / revenue", label="Net margin",
        inputs={"net_income": row.get("net_income"), "revenue": row.get("revenue")},
        history=_history(f, r.net_margin),
    )
    metrics["ebitda_margin"] = metric(
        "ebitda_margin", r.ebitda_margin(row), unit="percent", period=period,
        formula="ebitda / revenue", label="EBITDA margin",
        inputs={"ebitda": row.get("ebitda"), "revenue": row.get("revenue")},
        history=_history(f, r.ebitda_margin),
    )
    metrics["fcf_margin"] = metric(
        "fcf_margin", r.fcf_margin(row), unit="percent", period=period,
        formula="(operating_cash_flow - |capex|) / revenue", label="Free cash flow margin",
        inputs={"ocf": row.get("ocf"), "capex": row.get("capex"), "revenue": row.get("revenue")},
        history=_history(f, r.fcf_margin),
    )

    # --- returns on capital ------------------------------------------------
    avg_equity = r.average(row.get("total_equity"), prior.get("total_equity"))
    roe_value = r.roe(row, prior)
    roe_flag = None
    roe_note = None
    if roe_value is None and avg_equity is not None and avg_equity <= 0:
        # A shareholders' deficit produces a flattering positive ROE from a loss.
        roe_flag = "unreliable"
        roe_note = "Average shareholders' equity is negative, which makes return on equity meaningless"
        warnings.append(
            "Shareholders' equity is negative on average across the period, so return on "
            "equity and the equity multiplier are not reported. This usually reflects "
            "sustained buybacks or accumulated losses rather than insolvency, and the "
            "DuPont decomposition below is incomplete as a result."
        )

    metrics["roe"] = metric(
        "roe", roe_value, unit="percent", period=period,
        formula="net_income / average(total_equity, prior_total_equity)",
        label="Return on equity", flag=roe_flag, note=roe_note,
        inputs={
            "net_income": row.get("net_income"),
            "total_equity": row.get("total_equity"),
            "prior_total_equity": prior.get("total_equity"),
            "avg_total_equity": avg_equity,
        },
        history=_history(f, r.roe, needs_prior=True),
    )
    metrics["roa"] = metric(
        "roa", r.roa(row, prior), unit="percent", period=period,
        formula="net_income / average(total_assets, prior_total_assets)",
        label="Return on assets",
        inputs={
            "net_income": row.get("net_income"),
            "total_assets": row.get("total_assets"),
            "prior_total_assets": prior.get("total_assets"),
        },
        history=_history(f, r.roa, needs_prior=True),
    )
    ic_now, ic_prior = r.invested_capital(row), r.invested_capital(prior)
    metrics["roic"] = metric(
        "roic", r.roic(row, prior), unit="percent", period=period,
        formula="nopat / average(invested_capital), where invested_capital = total_debt + total_equity - cash",
        label="Return on invested capital",
        inputs={
            "nopat": row.get("nopat"),
            "operating_income": row.get("operating_income"),
            "effective_tax_rate": row.get("effective_tax_rate"),
            "invested_capital": ic_now,
            "prior_invested_capital": ic_prior,
        },
        history=_history(f, r.roic, needs_prior=True),
    )
    metrics["asset_turnover"] = metric(
        "asset_turnover", r.asset_turnover(row, prior), unit="x", period=period,
        formula="revenue / average(total_assets, prior_total_assets)",
        label="Asset turnover",
        inputs={
            "revenue": row.get("revenue"),
            "total_assets": row.get("total_assets"),
            "prior_total_assets": prior.get("total_assets"),
        },
        history=_history(f, r.asset_turnover, needs_prior=True),
    )
    metrics["equity_multiplier"] = metric(
        "equity_multiplier", r.equity_multiplier(row, prior), unit="x", period=period,
        formula="average(total_assets) / average(total_equity)",
        label="Equity multiplier",
        flag="unreliable" if roe_flag == "unreliable" else None,
        inputs={
            "total_assets": row.get("total_assets"),
            "prior_total_assets": prior.get("total_assets"),
            "total_equity": row.get("total_equity"),
            "prior_total_equity": prior.get("total_equity"),
        },
        history=_history(f, r.equity_multiplier, needs_prior=True),
    )

    # --- DuPont ------------------------------------------------------------
    du = r.dupont(row, prior)
    if du["reconciles"] is False:
        warnings.append(
            "The DuPont components do not multiply back to the directly computed return "
            "on equity, which points to an inconsistency between the periods used for "
            "the income statement and the balance sheet. Both figures are shown."
        )

    # --- score -------------------------------------------------------------
    score, detail = sc.score_dimension(
        "profitability", {k: m.value for k, m in metrics.items()}
    )
    for name, m in metrics.items():
        m.flag = m.flag or flag_from_score(detail.get(name, {}).get("score"))

    usage = usage_from(state)
    narrative = await narrate(
        company=f.name or f.ticker,
        section="Profitability and returns on capital",
        metrics=metrics,
        extra_context=_dupont_context(du),
        warnings=warnings,
        usage=usage,
    )

    block = MetricBlock(
        dimension="profitability",
        metrics=metrics,
        narrative=narrative,
        score=score if score is not None else 0.0,
        warnings=warnings,
        extras={
            "dupont": du,
            "period": period,
            "score_detail": detail,
            "margin_trend": _margin_trend(f),
        },
    )
    return {"profitability": block, "cost": usage.as_dict(), "warnings": warnings}


def _dupont_context(du: dict) -> str:
    if du["product"] is None:
        return "DuPont decomposition: incomplete, because at least one component is unavailable."
    return (
        "DuPont decomposition of return on equity — "
        f"net margin {du['net_margin'] * 100:.1f}% x "
        f"asset turnover {du['asset_turnover']:.2f}x x "
        f"equity multiplier {du['equity_multiplier']:.2f}x = "
        f"{du['product'] * 100:.1f}%. Say which of the three is doing the work."
    )


def _margin_trend(f: Fundamentals) -> list[dict]:
    """Five periods of the four margins, oldest-first, for the trend chart."""
    out = []
    for p in reversed(f.annual_periods[:5]):
        row = f.facts.get(p, {})
        out.append(
            {
                "period": p,
                "gross_margin": r.gross_margin(row),
                "operating_margin": r.operating_margin(row),
                "net_margin": r.net_margin(row),
                "fcf_margin": r.fcf_margin(row),
            }
        )
    return out
