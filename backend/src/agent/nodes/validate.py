"""Node 2: decide whether the data is good enough, and say so plainly.

Nothing here is cosmetic. The coverage figure computed in this node feeds the conviction
calculation, and the sector flags it sets suppress metrics that would be actively
misleading — a bank's current ratio, a software company's Altman Z-score.
"""

from __future__ import annotations

from ...data.fundamentals import Fundamentals
from ..progress import node
from ._shared import is_financial, is_software


@node("validate")
async def validate(state: dict) -> dict:
    f = Fundamentals.from_dict(state["facts"])
    dq = dict(state.get("data_quality") or {})
    warnings: list[str] = []

    if not dq.get("usable"):
        missing = ", ".join(dq.get("missing_critical", []))
        raise ValueError(
            f"{f.ticker} is missing core statement lines ({missing}); the analysis would "
            f"be built on gaps rather than facts."
        )

    financial = is_financial(f.sector)
    software = is_software(f.sector, f.industry)

    if financial:
        warnings.append(
            "Financial-sector reporting: gross margin, working-capital ratios and the "
            "cash conversion cycle are not meaningful for a bank or insurer and are "
            "suppressed rather than shown as zero."
        )
    if software:
        warnings.append(
            "Asset-light business: the Altman Z-score is calibrated on manufacturers "
            "and reads high for software companies with small balance sheets. It is "
            "reported with that caveat rather than treated as a solvency verdict."
        )

    if f.market.get("market_cap") is None:
        warnings.append(
            "Market capitalisation is unavailable, so valuation multiples and the "
            "Altman Z-score cannot be computed."
        )

    # Growth carries less weight when there is too little history to support it.
    weights = dict(state.get("weights") or {})
    if dq.get("annual_periods", 0) < 3:
        from ...analytics.scoring import WEIGHTS

        weights.setdefault("growth", WEIGHTS["growth"] * 0.5)
        warnings.append(
            "Fewer than three annual periods are available; growth is weighted at half "
            "its usual influence on the composite score."
        )

    dq["sector_flags"] = {
        "financial": financial,
        "software": software,
        "suppress_gross_margin": financial,
        "suppress_working_capital": financial,
        "altman_unreliable": financial or software,
    }

    return {"data_quality": dq, "weights": weights, "warnings": warnings}
