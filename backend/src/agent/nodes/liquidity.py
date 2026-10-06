"""Node 4: liquidity, leverage, and distress risk.

The guards in this node matter more than the arithmetic. Three cases in particular
produce numbers that look like information and are not:

* zero or negative EBITDA turns net-debt/EBITDA into a sign-flipped artefact that reads
  as *less* leveraged the worse the business gets;
* zero interest expense makes coverage infinite, which prints as ``inf`` if you let it;
* the Altman Z-score is calibrated on 1960s manufacturers and systematically misreads
  banks and asset-light software.

Each is reported as unavailable-with-a-reason rather than as a number.
"""

from __future__ import annotations

from ...analytics import ratios as r
from ...analytics import scoring as sc
from ...data.fundamentals import Fundamentals
from ..progress import node
from ..state import MetricBlock, flag_from_score, metric
from ._shared import narrate, usage_from

BANK_NOTE = "Not meaningful for a financial-sector issuer, which does not present a current/non-current split"


@node("liquidity")
async def liquidity(state: dict) -> dict:
    f = Fundamentals.from_dict(state["facts"])
    flags = (state.get("data_quality") or {}).get("sector_flags", {})
    period = f.periods[0] if f.periods else ""
    row = f.facts.get(period, {})

    suppress_wc = bool(flags.get("suppress_working_capital"))
    warnings: list[str] = []
    metrics = {}

    def wc_metric(name: str, fn, *, label: str, formula: str, inputs: dict, unit="x"):
        if suppress_wc:
            return metric(name, None, unit=unit, period=period, formula=formula,
                          label=label, inputs=inputs, note=BANK_NOTE)
        return metric(name, fn(row), unit=unit, period=period, formula=formula,
                      label=label, inputs=inputs,
                      history=[{"period": p, "value": fn(f.facts.get(p, {}))}
                               for p in f.annual_periods[:5]])

    # --- liquidity ---------------------------------------------------------
    metrics["current_ratio"] = wc_metric(
        "current_ratio", r.current_ratio, label="Current ratio",
        formula="current_assets / current_liabilities",
        inputs={"current_assets": row.get("current_assets"), "current_liab": row.get("current_liab")},
    )
    metrics["quick_ratio"] = wc_metric(
        "quick_ratio", r.quick_ratio, label="Quick ratio",
        formula="(current_assets - inventory) / current_liabilities",
        inputs={
            "current_assets": row.get("current_assets"),
            "inventory": row.get("inventory"),
            "current_liab": row.get("current_liab"),
        },
    )
    metrics["cash_ratio"] = wc_metric(
        "cash_ratio", r.cash_ratio, label="Cash ratio",
        formula="cash / current_liabilities",
        inputs={"cash": row.get("cash"), "current_liab": row.get("current_liab")},
    )

    # --- leverage ----------------------------------------------------------
    metrics["debt_to_equity"] = metric(
        "debt_to_equity", r.debt_to_equity(row), unit="x", period=period,
        formula="total_debt / total_equity", label="Debt to equity",
        inputs={"total_debt": row.get("total_debt"), "total_equity": row.get("total_equity")},
        note=None if r.debt_to_equity(row) is not None
        else "Shareholders' equity is zero or negative, so the ratio has no meaning",
        history=[{"period": p, "value": r.debt_to_equity(f.facts.get(p, {}))}
                 for p in f.annual_periods[:5]],
    )

    ebitda = row.get("ebitda")
    nd_ebitda = r.net_debt_to_ebitda(row)
    nd_note = None
    if nd_ebitda is None:
        if ebitda is None:
            nd_note = "EBITDA could not be computed from the filings"
        elif ebitda <= 0:
            nd_note = (
                "EBITDA is zero or negative; dividing by it would produce a negative "
                "ratio that reads as conservative leverage when the opposite is true"
            )
            warnings.append(
                "EBITDA is not positive, so net debt to EBITDA is not reported. Leverage "
                "for a business that is not generating operating profit is better read "
                "from the absolute debt balance and interest coverage."
            )
    metrics["net_debt_ebitda"] = metric(
        "net_debt_ebitda", nd_ebitda, unit="x", period=period,
        formula="(total_debt - cash) / ebitda", label="Net debt / EBITDA", note=nd_note,
        inputs={
            "total_debt": row.get("total_debt"), "cash": row.get("cash"),
            "net_debt": r.net_debt(row), "ebitda": ebitda,
        },
        history=[{"period": p, "value": r.net_debt_to_ebitda(f.facts.get(p, {}))}
                 for p in f.annual_periods[:5]],
    )

    ie = row.get("interest_expense")
    coverage = r.interest_coverage(row)
    cov_flag = None
    cov_note = None
    if coverage is None and (ie is None or abs(ie or 0) < 1.0) and row.get("operating_income"):
        # No interest expense is the strongest possible coverage position, but printing
        # infinity is not a number and sorting on it breaks.
        cov_flag = "strong"
        cov_note = "No meaningful interest expense is reported — coverage is effectively unlimited"
    metrics["interest_coverage"] = metric(
        "interest_coverage", coverage, unit="x", period=period,
        formula="operating_income / |interest_expense|", label="Interest coverage",
        flag=cov_flag, note=cov_note,
        inputs={"operating_income": row.get("operating_income"), "interest_expense": ie},
        history=[{"period": p, "value": r.interest_coverage(f.facts.get(p, {}))}
                 for p in f.annual_periods[:5]],
    )
    metrics["fcf_to_debt"] = metric(
        "fcf_to_debt", r.fcf_to_debt(row), unit="ratio", period=period,
        formula="(operating_cash_flow - |capex|) / total_debt", label="Free cash flow to debt",
        inputs={"fcf": row.get("fcf"), "total_debt": row.get("total_debt")},
        note=None if r.fcf_to_debt(row) is not None else "No debt outstanding, or free cash flow unavailable",
        history=[{"period": p, "value": r.fcf_to_debt(f.facts.get(p, {}))}
                 for p in f.annual_periods[:5]],
    )

    # --- working capital cycle ---------------------------------------------
    for name, fn, label, formula, inputs in (
        ("dso", r.dso, "Days sales outstanding", "accounts_receivable / revenue x 365",
         {"receivables": row.get("receivables"), "revenue": row.get("revenue")}),
        ("dio", r.dio, "Days inventory outstanding", "inventory / cost_of_revenue x 365",
         {"inventory": row.get("inventory"), "cogs": row.get("cogs")}),
        ("dpo", r.dpo, "Days payables outstanding", "accounts_payable / cost_of_revenue x 365",
         {"payables": row.get("payables"), "cogs": row.get("cogs")}),
    ):
        value = None if suppress_wc and name != "dso" else fn(row)
        metrics[name] = metric(
            name, value, unit="days", period=period, formula=formula, label=label,
            inputs=inputs,
            note=BANK_NOTE if (suppress_wc and name != "dso") else
            (None if value is not None else "Requires inventory and cost-of-revenue detail the filing does not break out"),
        )

    ccc = None if suppress_wc else r.cash_conversion_cycle(row)
    metrics["ccc"] = metric(
        "ccc", ccc, unit="days", period=period,
        formula="days_sales_outstanding + days_inventory_outstanding - days_payables_outstanding",
        label="Cash conversion cycle",
        inputs={"dso": r.dso(row), "dio": r.dio(row), "dpo": r.dpo(row)},
        note=BANK_NOTE if suppress_wc else (None if ccc is not None else "One or more cycle components is unavailable"),
        history=[{"period": p, "value": None if suppress_wc else r.cash_conversion_cycle(f.facts.get(p, {}))}
                 for p in f.annual_periods[:5]],
    )

    # --- distress ----------------------------------------------------------
    z = r.altman_z(row)
    band = r.altman_band(z)
    z_note = None
    if z is None:
        z_note = "Requires working capital, retained earnings, EBIT, market capitalisation and total liabilities"
    elif flags.get("altman_unreliable"):
        z_note = (
            "Calibrated on manufacturers; it reads high for asset-light businesses and "
            "does not apply to financial-sector balance sheets"
        )
        warnings.append(
            "The Altman Z-score shown is outside the model's calibrated universe. It is "
            "reported for completeness and should not be read as a solvency verdict."
        )
    metrics["altman_z"] = metric(
        "altman_z", z, unit="ratio", period=period,
        formula="1.2(WC/TA) + 1.4(RE/TA) + 3.3(EBIT/TA) + 0.6(MCap/TL) + 1.0(Rev/TA)",
        label="Altman Z-score", note=z_note,
        inputs={
            "working_capital": row.get("working_capital"),
            "retained_earnings": row.get("retained_earnings"),
            "operating_income": row.get("operating_income"),
            "market_cap": row.get("market_cap"),
            "total_liabilities": row.get("total_liabilities"),
            "revenue": row.get("revenue"),
            "total_assets": row.get("total_assets"),
        },
        history=[{"period": p, "value": r.altman_z(f.facts.get(p, {}))}
                 for p in f.annual_periods[:5]],
    )

    score, detail = sc.score_dimension(
        "financial_health", {k: m.value for k, m in metrics.items()}
    )
    for name, m in metrics.items():
        m.flag = m.flag or flag_from_score(detail.get(name, {}).get("score"))

    context = []
    if band:
        context.append(
            f"Altman Z-score band: {band} (above 2.99 is safe, 1.81-2.99 is grey, below "
            f"1.81 indicates distress)."
        )
    if ccc is not None and ccc < 0:
        context.append(
            "The cash conversion cycle is negative, meaning suppliers finance the "
            "working capital of the business."
        )

    usage = usage_from(state)
    narrative = await narrate(
        company=f.name or f.ticker,
        section="Liquidity, leverage and solvency",
        metrics=metrics,
        extra_context=" ".join(context),
        warnings=warnings,
        usage=usage,
    )

    block = MetricBlock(
        dimension="liquidity",
        metrics=metrics,
        narrative=narrative,
        score=score if score is not None else 0.0,
        warnings=warnings,
        extras={
            "period": period,
            "altman_band": band,
            "altman_reliable": not flags.get("altman_unreliable", False),
            "score_detail": detail,
            "ccc_components": {
                "dso": metrics["dso"].value,
                "dio": metrics["dio"].value,
                "dpo": metrics["dpo"].value,
                "ccc": ccc,
            },
            "gauges": _gauges(metrics),
        },
    )
    return {"liquidity": block, "cost": usage.as_dict(), "warnings": warnings}


def _gauges(metrics: dict) -> list[dict]:
    """Threshold bands for the gauge charts. Bands are conventional analyst readings,
    not rubric scores, so they are defined here rather than in the scoring module."""
    return [
        {
            "key": "current_ratio",
            "label": "Current ratio",
            "value": metrics["current_ratio"].value,
            "bands": [
                {"to": 1.0, "label": "tight", "tone": "weak"},
                {"to": 1.5, "label": "adequate", "tone": "neutral"},
                {"to": 3.5, "label": "comfortable", "tone": "strong"},
            ],
            "max": 3.5,
        },
        {
            "key": "interest_coverage",
            "label": "Interest coverage",
            "value": metrics["interest_coverage"].value,
            "bands": [
                {"to": 2.0, "label": "strained", "tone": "weak"},
                {"to": 6.0, "label": "adequate", "tone": "neutral"},
                {"to": 25.0, "label": "ample", "tone": "strong"},
            ],
            "max": 25.0,
        },
        {
            "key": "altman_z",
            "label": "Altman Z-score",
            "value": metrics["altman_z"].value,
            "bands": [
                {"to": 1.81, "label": "distress", "tone": "weak"},
                {"to": 2.99, "label": "grey", "tone": "neutral"},
                {"to": 8.0, "label": "safe", "tone": "strong"},
            ],
            "max": 8.0,
        },
    ]
