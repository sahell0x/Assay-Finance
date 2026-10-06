"""Multi-period maths: growth, CAGR, acceleration, incremental margins.

Series arrive newest-first as ``[(period_label, value), ...]`` exactly as
``Fundamentals.series`` produces them, and every function tolerates holes.
"""

from __future__ import annotations

from .ratios import Num, cagr, pct_change, safe_div

Series = list[tuple[str, Num]]


def values(series: Series) -> list[Num]:
    return [v for _, v in series]


def first_valid(series: Series, start: int = 0) -> tuple[int, Num]:
    """Index and value of the first non-None entry at or after ``start``."""
    for i in range(start, len(series)):
        if series[i][1] is not None:
            return i, series[i][1]
    return -1, None


def yoy(series: Series, offset: int = 0) -> Num:
    """Year-over-year change between consecutive annual entries.

    ``offset=0`` is the most recent year, ``offset=1`` the year before it — that pairing
    is what makes growth *acceleration* computable.
    """
    if len(series) < offset + 2:
        return None
    return pct_change(series[offset][1], series[offset + 1][1])


def growth_acceleration(series: Series) -> Num:
    """Change in the growth rate itself: yoy(t) - yoy(t-1).

    Positive means growth is speeding up. This is often more informative than the level
    of growth, and it is the kind of second-order fact an LLM will happily invent.
    """
    a, b = yoy(series, 0), yoy(series, 1)
    if a is None or b is None:
        return None
    return a - b


def cagr_over(series: Series, years: int) -> Num:
    """CAGR across ``years`` of compounding, i.e. between index 0 and index ``years``."""
    if len(series) < years + 1:
        return None
    latest = series[0][1]
    earliest = series[years][1]
    return cagr(latest, earliest, float(years))


def incremental_margin(rev: Series, profit: Series) -> Num:
    """Delta operating income over delta revenue.

    The marginal economics of the last year of growth: how much of each incremental
    dollar of revenue reached the operating line. Undefined when revenue was flat or
    fell, because dividing by a tiny or negative delta produces a garbage number.
    """
    if len(rev) < 2 or len(profit) < 2:
        return None
    r0, r1 = rev[0][1], rev[1][1]
    p0, p1 = profit[0][1], profit[1][1]
    if None in (r0, r1, p0, p1):
        return None
    d_rev = r0 - r1
    if d_rev <= 0 or (r1 > 0 and d_rev / r1 < 0.005):
        return None
    return (p0 - p1) / d_rev


def reinvestment_rate(row: dict) -> Num:
    """Capex as a share of operating cash flow. Capex sign is not trustworthy, so abs."""
    ocf, capex = row.get("ocf"), row.get("capex")
    if ocf is None or capex is None or ocf <= 0:
        return None
    return abs(capex) / ocf


def rule_of_40(rev_growth: Num, margin: Num) -> Num:
    """Revenue growth % + FCF margin %, the software-sector health heuristic."""
    if rev_growth is None or margin is None:
        return None
    return (rev_growth + margin) * 100.0


def eps_growth(series: Series) -> Num:
    """Diluted EPS growth. Undefined off a loss-making base."""
    return yoy(series, 0)


def derive_eps(row: dict) -> Num:
    """EPS from net income and diluted shares when the statement does not report it."""
    reported = row.get("eps_diluted")
    if reported is not None:
        return reported
    return safe_div(row.get("net_income"), row.get("shares_diluted"), allow_negative_denom=False)


def percentile_rank(value: Num, peers: list[Num], *, higher_is_better: bool = True) -> Num:
    """Where ``value`` sits within its peer set, 0-1.

    Requires at least three valid peer observations; below that a "percentile" is a
    decoration, not a statistic, so the caller gets ``None``.
    """
    if value is None:
        return None
    clean = [p for p in peers if p is not None]
    if len(clean) < 3:
        return None
    below = sum(1 for p in clean if (p < value if higher_is_better else p > value))
    ties = sum(1 for p in clean if p == value)
    # Midpoint handling for ties keeps an exactly-median company at 0.5.
    return (below + 0.5 * ties) / len(clean)


def median(vals: list[Num]) -> Num:
    clean = sorted(v for v in vals if v is not None)
    if not clean:
        return None
    n = len(clean)
    mid = n // 2
    return clean[mid] if n % 2 else (clean[mid - 1] + clean[mid]) / 2.0


def quantile(vals: list[float], q: float) -> Num:
    """Linear-interpolated quantile over an already-cleaned, sorted-able list."""
    clean = sorted(v for v in vals if v is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    pos = q * (len(clean) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(clean) - 1)
    frac = pos - lo
    return clean[lo] + (clean[hi] - clean[lo]) * frac


# Above these readings a multiple stops describing how the market values a business and
# starts describing how small its denominator is. Research notes mark them "NM" — not
# meaningful — and exclude them from a cohort median. These thresholds do the same.
NOT_MEANINGFUL_ABOVE: dict[str, float] = {
    "ev_ebitda": 50.0,
    "pe": 100.0,
    "ev_sales": 40.0,
    "price_to_book": 40.0,
    "peg": 10.0,
}


def trimmed_median(
    vals: list[Num], *, cap: float | None = None, k: float = 1.5
) -> tuple[Num, list[float]]:
    """Median of the meaningful readings, with the excluded ones returned alongside.

    Two filters, in order:

    1. an absolute "not meaningful" cap — a peer whose EBITDA is barely positive prints
       a multiple in the hundreds or thousands of turns, and one such name drags a
       six-company median into three figures;
    2. Tukey fences on what survives, to catch skew the cap did not.

    The cap runs first because the IQR of a set containing a 2,900x reading is itself so
    wide that the fence keeps a 480x reading inside it — outlier rejection cannot save a
    distribution that broken.

    Returns ``(median, excluded)``, never a silently cleaned number.
    """
    clean = [v for v in vals if v is not None]
    if not clean:
        return None, []

    excluded: list[float] = []
    if cap is not None:
        kept = [v for v in clean if v <= cap]
        excluded = [v for v in clean if v > cap]
        # If the cap would leave nothing, the whole cohort is non-meaningful and saying
        # so is better than reporting a median of two survivors.
        if not kept:
            return None, excluded
        clean = kept

    if len(clean) >= 4:
        q1, q3 = quantile(clean, 0.25), quantile(clean, 0.75)
        if q1 is not None and q3 is not None:
            iqr = q3 - q1
            lo, hi = q1 - k * iqr, q3 + k * iqr
            fenced = [v for v in clean if lo <= v <= hi]
            if len(fenced) >= 3:
                excluded += [v for v in clean if not (lo <= v <= hi)]
                clean = fenced

    return median(clean), excluded
