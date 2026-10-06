"""Node 5: growth, and the second-order facts that make growth legible.

Rate of growth is the least interesting thing in this block. Whether growth is
accelerating, what share of each incremental revenue dollar reaches the operating line,
and how much cash has to be reinvested to sustain it say far more about the business —
and they are exactly the sort of derived quantity a language model will cheerfully
invent, which is why all of it is computed here.
"""

from __future__ import annotations

from ...analytics import ratios as r
from ...analytics import scoring as sc
from ...analytics import trends as t
from ...data.fundamentals import Fundamentals
from ..progress import node
from ..state import MetricBlock, flag_from_score, metric
from ._shared import is_software, narrate, usage_from


@node("growth")
async def growth(state: dict) -> dict:
    f = Fundamentals.from_dict(state["facts"])
    period = f.periods[0] if f.periods else ""
    row = f.facts.get(period, {})
    n_annual = len(f.annual_periods)

    rev = f.series("revenue")
    op_s = f.series("operating_income")
    fcf_s = f.series("fcf")
    eps_s = [(p, t.derive_eps(f.facts.get(p, {}))) for p in f.annual_periods]

    warnings: list[str] = []
    if n_annual < 3:
        warnings.append(
            f"Only {n_annual} annual period(s) of history are available, so three- and "
            f"five-year compound growth rates cannot be computed. The growth dimension "
            f"carries reduced weight in the composite score as a result."
        )

    metrics = {}
    rev_yoy = t.yoy(rev)
    metrics["rev_yoy"] = metric(
        "rev_yoy", rev_yoy, unit="percent", period=period,
        formula="(revenue_t - revenue_t-1) / revenue_t-1", label="Revenue growth, year over year",
        inputs={
            "revenue_latest": rev[0][1] if rev else None,
            "revenue_prior": rev[1][1] if len(rev) > 1 else None,
        },
        note=None if rev_yoy is not None else "Requires two annual periods with a positive base",
        history=[{"period": rev[i][0], "value": t.yoy(rev, i)} for i in range(max(0, len(rev) - 1))],
    )

    for years in (3, 5):
        key = f"rev_cagr_{years}y"
        value = t.cagr_over(rev, years)
        metrics[key] = metric(
            key, value, unit="percent", period=period,
            formula=f"(revenue_t / revenue_t-{years}) ^ (1/{years}) - 1",
            label=f"Revenue CAGR, {years} year",
            inputs={
                "revenue_latest": rev[0][1] if rev else None,
                f"revenue_{years}y_ago": rev[years][1] if len(rev) > years else None,
            },
            note=None if value is not None else (
                f"Requires {years + 1} annual periods with a positive starting base"
            ),
        )

    eps_g = t.eps_growth(eps_s)
    metrics["eps_growth"] = metric(
        "eps_growth", eps_g, unit="percent", period=period,
        formula="(diluted_eps_t - diluted_eps_t-1) / diluted_eps_t-1",
        label="Diluted EPS growth",
        inputs={
            "eps_latest": eps_s[0][1] if eps_s else None,
            "eps_prior": eps_s[1][1] if len(eps_s) > 1 else None,
        },
        note=None if eps_g is not None else "Undefined from a loss-making or zero base",
        history=[{"period": eps_s[i][0], "value": v} for i, (_, v) in enumerate(eps_s[:5])],
    )

    fcf_cagr = t.cagr_over(fcf_s, 3)
    metrics["fcf_cagr_3y"] = metric(
        "fcf_cagr_3y", fcf_cagr, unit="percent", period=period,
        formula="(fcf_t / fcf_t-3) ^ (1/3) - 1", label="Free cash flow CAGR, 3 year",
        inputs={
            "fcf_latest": fcf_s[0][1] if fcf_s else None,
            "fcf_3y_ago": fcf_s[3][1] if len(fcf_s) > 3 else None,
        },
        note=None if fcf_cagr is not None else "Requires four annual periods with positive free cash flow at both ends",
    )

    accel = t.growth_acceleration(rev)
    metrics["growth_acceleration"] = metric(
        "growth_acceleration", accel, unit="percent", period=period,
        formula="revenue_growth_t - revenue_growth_t-1",
        label="Growth acceleration",
        inputs={"yoy_latest": t.yoy(rev, 0), "yoy_prior": t.yoy(rev, 1)},
        note=None if accel is not None else "Requires three annual periods of positive revenue",
    )

    inc_margin = t.incremental_margin(rev, op_s)
    metrics["incremental_operating_margin"] = metric(
        "incremental_operating_margin", inc_margin, unit="percent", period=period,
        formula="(operating_income_t - operating_income_t-1) / (revenue_t - revenue_t-1)",
        label="Incremental operating margin",
        inputs={
            "delta_operating_income": (
                op_s[0][1] - op_s[1][1] if len(op_s) > 1 and None not in (op_s[0][1], op_s[1][1]) else None
            ),
            "delta_revenue": (
                rev[0][1] - rev[1][1] if len(rev) > 1 and None not in (rev[0][1], rev[1][1]) else None
            ),
        },
        note=None if inc_margin is not None else "Undefined when revenue was flat or fell in the period",
    )

    reinvest = t.reinvestment_rate(row)
    metrics["reinvestment_rate"] = metric(
        "reinvestment_rate", reinvest, unit="percent", period=period,
        formula="|capex| / operating_cash_flow", label="Reinvestment rate",
        inputs={"capex": row.get("capex"), "ocf": row.get("ocf")},
        note=None if reinvest is not None else "Requires positive operating cash flow and reported capital expenditure",
    )

    # Rule of 40 only means something for software; showing it elsewhere is decoration.
    software = is_software(f.sector, f.industry)
    ro40 = t.rule_of_40(rev_yoy, r.fcf_margin(row)) if software else None
    metrics["rule_of_40"] = metric(
        "rule_of_40", ro40, unit="score", period=period,
        formula="(revenue_growth + free_cash_flow_margin) x 100", label="Rule of 40",
        inputs={"rev_yoy": rev_yoy, "fcf_margin": r.fcf_margin(row)},
        note=None if ro40 is not None else (
            "Applies to software businesses; not reported for this sector" if not software
            else "Requires both revenue growth and a free cash flow margin"
        ),
    )

    score, detail = sc.score_dimension("growth", {k: m.value for k, m in metrics.items()})
    for name, m in metrics.items():
        m.flag = m.flag or flag_from_score(detail.get(name, {}).get("score"))

    context = []
    if accel is not None:
        context.append(
            "Growth is accelerating." if accel > 0.005
            else "Growth is decelerating." if accel < -0.005
            else "Growth is holding roughly steady."
        )
    if inc_margin is not None:
        context.append(
            "The incremental operating margin describes how much of each additional "
            "dollar of revenue reached the operating line over the last year."
        )

    usage = usage_from(state)
    narrative = await narrate(
        company=f.name or f.ticker,
        section="Revenue, earnings and cash flow growth",
        metrics=metrics,
        extra_context=" ".join(context),
        warnings=warnings,
        usage=usage,
    )

    block = MetricBlock(
        dimension="growth",
        metrics=metrics,
        narrative=narrative,
        score=score if score is not None else 0.0,
        warnings=warnings,
        extras={
            "period": period,
            "score_detail": detail,
            "is_software": software,
            "revenue_trend": _revenue_trend(f, rev),
        },
    )
    return {"growth": block, "cost": usage.as_dict(), "warnings": warnings}


def _revenue_trend(f: Fundamentals, rev: list[tuple[str, float | None]]) -> list[dict]:
    """Revenue bars plus the YoY line, oldest-first."""
    out = []
    for i in range(len(rev) - 1, -1, -1):
        period, value = rev[i]
        out.append({"period": period, "revenue": value, "yoy": t.yoy(rev, i)})
    return out[-5:]
