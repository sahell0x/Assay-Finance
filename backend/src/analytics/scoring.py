"""The rubric. This file, not the language model, decides BUY / HOLD / SELL.

Scoring is a two-stage fold:

1. every metric is mapped onto 0-10 by piecewise-linear interpolation between named
   anchor points, so a score is a continuous function of the underlying number rather
   than a cliff at an arbitrary threshold;
2. dimension scores are averaged and combined with weights that renormalise whenever a
   dimension could not be computed.

The model is handed the resulting rating and writes the argument for it. If it disagrees
it is instructed to say so in ``data_caveats`` — it cannot change the rating.
"""

from __future__ import annotations

from .ratios import Num

WEIGHTS: dict[str, float] = {
    "profitability": 0.25,
    "financial_health": 0.20,
    "growth": 0.25,
    "valuation": 0.20,
    "sentiment": 0.10,
}

BUY_THRESHOLD = 7.5
HOLD_THRESHOLD = 5.0

# Anchor tables: (metric_value, score_out_of_10), ascending by value.
# Reading one of these top to bottom is the whole editorial position of the rubric,
# which is why they are data rather than nested ifs.
ANCHORS: dict[str, list[tuple[float, float]]] = {
    # --- profitability
    "gross_margin": [(0.05, 1), (0.20, 3), (0.35, 5), (0.50, 7), (0.65, 9), (0.80, 10)],
    "operating_margin": [(-0.05, 0), (0.03, 2), (0.10, 4), (0.18, 6), (0.28, 8), (0.40, 10)],
    "net_margin": [(-0.05, 0), (0.02, 2), (0.08, 4), (0.15, 6), (0.22, 8), (0.32, 10)],
    "ebitda_margin": [(0.0, 0), (0.08, 2), (0.16, 4), (0.25, 6), (0.35, 8), (0.50, 10)],
    "fcf_margin": [(-0.05, 0), (0.02, 2), (0.08, 4), (0.15, 6), (0.24, 8), (0.35, 10)],
    "roe": [(0.0, 0), (0.05, 2), (0.10, 4), (0.16, 6), (0.24, 8), (0.40, 10)],
    "roa": [(0.0, 0), (0.02, 2), (0.05, 4), (0.09, 6), (0.15, 8), (0.22, 10)],
    "roic": [(0.0, 0), (0.04, 2), (0.08, 4), (0.13, 6), (0.20, 8), (0.32, 10)],
    # --- financial health
    "current_ratio": [(0.4, 0), (0.8, 2), (1.0, 4), (1.5, 7), (2.0, 9), (3.5, 9.5)],
    "quick_ratio": [(0.2, 0), (0.6, 2), (0.9, 4), (1.2, 7), (1.8, 9), (3.0, 9.5)],
    "interest_coverage": [(0.5, 0), (1.5, 2), (3.0, 4), (6.0, 6), (12.0, 8), (25.0, 10)],
    "altman_z": [(0.5, 0), (1.81, 3), (2.99, 6), (4.5, 8), (7.0, 10)],
    "fcf_to_debt": [(0.0, 1), (0.08, 3), (0.20, 5), (0.40, 7), (0.80, 9), (1.50, 10)],
    # --- growth
    "rev_yoy": [(-0.15, 0), (-0.02, 2), (0.04, 4), (0.10, 6), (0.20, 8), (0.35, 10)],
    "rev_cagr_3y": [(-0.10, 0), (0.0, 2), (0.05, 4), (0.11, 6), (0.20, 8), (0.32, 10)],
    "rev_cagr_5y": [(-0.10, 0), (0.0, 2), (0.05, 4), (0.11, 6), (0.20, 8), (0.32, 10)],
    "eps_growth": [(-0.20, 0), (-0.02, 2), (0.05, 4), (0.12, 6), (0.22, 8), (0.40, 10)],
    "fcf_cagr_3y": [(-0.15, 0), (0.0, 2), (0.06, 4), (0.13, 6), (0.22, 8), (0.35, 10)],
    "growth_acceleration": [(-0.12, 1), (-0.03, 3), (0.0, 5), (0.04, 7), (0.12, 9)],
    "incremental_operating_margin": [(-0.10, 1), (0.05, 3), (0.15, 5), (0.30, 7), (0.50, 9)],
    # --- valuation (lower multiple is a better score)
    "pe": [(6.0, 10), (12.0, 8), (20.0, 6), (30.0, 4), (45.0, 2), (70.0, 0)],
    "ev_ebitda": [(4.0, 10), (8.0, 8), (13.0, 6), (20.0, 4), (30.0, 2), (45.0, 0)],
    "ev_sales": [(0.8, 10), (2.0, 8), (4.0, 6), (7.0, 4), (12.0, 2), (20.0, 0)],
    "price_to_book": [(0.8, 10), (1.8, 8), (3.5, 6), (6.0, 4), (10.0, 2), (18.0, 0)],
    "fcf_yield": [(0.0, 1), (0.02, 3), (0.04, 5), (0.06, 7), (0.09, 9), (0.13, 10)],
    "peg": [(0.5, 10), (1.0, 7.5), (1.5, 5.5), (2.5, 3), (4.0, 1)],
}

# Two metrics are scored against tables that do not live in ANCHORS, because their
# shape is not "more is better along one slope": net cash is a strictly good thing
# rather than the bottom of the debt scale, and leverage is scored generously up to the
# point where it stops being ordinary. They are named data rather than literals inside
# ``score_metric`` so that anything needing a metric's domain — the scenario engine's
# slider ranges, for one — reads the same table the score is computed from.
SPECIAL_ANCHORS: dict[str, list[tuple[float, float]]] = {
    "net_debt_ebitda": [(-2.0, 10), (0.0, 9), (1.0, 7.5), (2.0, 6), (3.5, 4), (5.0, 2), (7.0, 0)],
    "debt_to_equity": [(0.0, 10), (0.25, 8.5), (0.6, 7), (1.0, 5.5), (2.0, 3.5), (4.0, 1.5), (8.0, 0)],
}


def anchors_for(name: str) -> list[tuple[float, float]] | None:
    """The anchor table a metric is scored against, wherever it is defined."""
    return ANCHORS.get(name) or SPECIAL_ANCHORS.get(name)


# Ratios where a lower reading is the better one. Used for percentile direction and to
# validate that anchor tables slope the way their metric should.
LOWER_IS_BETTER = frozenset(
    {
        "pe",
        "ev_ebitda",
        "ev_sales",
        "price_to_book",
        "peg",
        "net_debt_ebitda",
        "debt_to_equity",
        "dso",
        "dio",
        "ccc",
    }
)

# Metrics that feed each dimension's score, with the relative pull of each.
DIMENSION_METRICS: dict[str, dict[str, float]] = {
    "profitability": {
        "gross_margin": 0.8,
        "operating_margin": 1.2,
        "net_margin": 1.0,
        "fcf_margin": 1.2,
        "roe": 1.0,
        "roic": 1.4,
        "roa": 0.6,
    },
    "financial_health": {
        "current_ratio": 0.9,
        "quick_ratio": 0.6,
        "net_debt_ebitda": 1.3,
        "interest_coverage": 1.2,
        "debt_to_equity": 0.9,
        "altman_z": 1.0,
        "fcf_to_debt": 1.0,
    },
    "growth": {
        "rev_yoy": 1.3,
        "rev_cagr_3y": 1.2,
        "rev_cagr_5y": 0.7,
        "eps_growth": 1.0,
        "fcf_cagr_3y": 0.9,
        "growth_acceleration": 0.7,
        "incremental_operating_margin": 0.6,
    },
    "valuation": {
        "pe": 1.0,
        "ev_ebitda": 1.2,
        "ev_sales": 0.8,
        "price_to_book": 0.5,
        "fcf_yield": 1.1,
        "peg": 0.8,
    },
}


def interpolate(value: float, anchors: list[tuple[float, float]]) -> float:
    """Piecewise-linear lookup, clamped at both ends."""
    if value <= anchors[0][0]:
        return anchors[0][1]
    if value >= anchors[-1][0]:
        return anchors[-1][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:], strict=False):
        if x0 <= value <= x1:
            if x1 == x0:
                return y1
            t = (value - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return anchors[-1][1]


def score_metric(name: str, value: Num) -> Num:
    """0-10 for a single metric, or None if it could not be computed."""
    if value is None:
        return None

    special = SPECIAL_ANCHORS.get(name)
    if special is not None:
        return interpolate(value, special)

    anchors = ANCHORS.get(name)
    if anchors is None:
        return None
    return round(interpolate(value, anchors), 4)


def score_dimension(dimension: str, metrics: dict[str, Num]) -> tuple[Num, dict]:
    """Weighted mean of whichever metric scores exist. Returns (score, detail)."""
    spec = DIMENSION_METRICS.get(dimension, {})
    detail: dict[str, dict] = {}
    num = 0.0
    den = 0.0

    for name, weight in spec.items():
        raw = metrics.get(name)
        s = score_metric(name, raw)
        detail[name] = {"value": raw, "score": s, "weight": weight}
        if s is not None:
            num += s * weight
            den += weight

    if den == 0:
        return None, detail
    return round(num / den, 3), detail


def score_sentiment(sentiment: Num) -> Num:
    """Map a [-1, 1] sentiment reading onto the same 0-10 scale as everything else."""
    if sentiment is None:
        return None
    clamped = max(-1.0, min(1.0, sentiment))
    return round((clamped + 1.0) * 5.0, 3)


def normalise_weights(
    raw: dict[str, float] | None, available: set[str]
) -> dict[str, float]:
    """Drop dimensions that produced no score and renormalise the rest to sum to 1.

    A missing dimension must not silently count as zero — that would punish a company
    for a data gap rather than for its fundamentals.
    """
    base = dict(WEIGHTS)
    if raw:
        for k, v in raw.items():
            if k in base:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if fv >= 0:
                    base[k] = fv

    kept = {k: v for k, v in base.items() if k in available and v > 0}
    total = sum(kept.values())
    if total <= 0:
        return {}
    return {k: round(v / total, 6) for k, v in kept.items()}


def rating_for(total: Num) -> str:
    if total is None:
        return "HOLD"
    if total >= BUY_THRESHOLD:
        return "BUY"
    if total >= HOLD_THRESHOLD:
        return "HOLD"
    return "SELL"


def distance_to_band_edge(total: float) -> float:
    """How far the composite sits from the nearest rating boundary."""
    return min(abs(total - BUY_THRESHOLD), abs(total - HOLD_THRESHOLD))


def conviction_for(total: Num, *, coverage: float, dimensions_used: int) -> str:
    """Conviction reflects how firmly the evidence supports the band, not how good the
    company is. Thin data or a composite sitting on a boundary both reduce it."""
    if total is None:
        return "low"
    edge = distance_to_band_edge(total)

    score = 0
    score += 2 if edge >= 1.0 else (1 if edge >= 0.4 else 0)
    score += 2 if coverage >= 0.85 else (1 if coverage >= 0.6 else 0)
    score += 2 if dimensions_used >= 5 else (1 if dimensions_used >= 4 else 0)

    # Distance from the band edge is a gate, not just a contributor. Perfect data
    # coverage cannot buy high conviction in a rating that a 0.5-point move would flip —
    # the conviction is in the *rating*, and that rating is not stable.
    if score >= 5 and edge >= 0.75:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def build_scorecard(
    *,
    dimension_scores: dict[str, Num],
    dimension_detail: dict[str, dict] | None = None,
    user_weights: dict[str, float] | None = None,
    coverage: float = 1.0,
) -> dict:
    """Fold dimension scores into a composite, a rating, and a conviction.

    The returned dict is the single source of truth for the recommendation; it is stored
    verbatim and handed to the memo writer as a fait accompli.
    """
    available = {k for k, v in dimension_scores.items() if v is not None}
    weights = normalise_weights(user_weights, available)

    total: Num = None
    if weights:
        total = round(sum(dimension_scores[k] * w for k, w in weights.items()), 3)

    dropped = sorted(set(WEIGHTS) - available)
    rating = rating_for(total)

    return {
        "dimension_scores": {k: dimension_scores.get(k) for k in WEIGHTS},
        "weights_applied": weights,
        "weights_requested": user_weights or {k: round(v, 4) for k, v in WEIGHTS.items()},
        "dimensions_unavailable": dropped,
        "total": total,
        "rating": rating,
        "conviction": conviction_for(
            total, coverage=coverage, dimensions_used=len(available)
        ),
        "thresholds": {"buy": BUY_THRESHOLD, "hold": HOLD_THRESHOLD},
        "distance_to_edge": round(distance_to_band_edge(total), 3) if total is not None else None,
        "detail": dimension_detail or {},
        "coverage": round(coverage, 3),
    }


def price_target(
    *,
    peer_median_ev_ebitda: Num,
    company_ebitda: Num,
    total_debt: Num,
    cash: Num,
    shares: Num,
    band: float = 0.15,
    current_price: Num = None,
) -> dict:
    """Multiples-based target: peer median EV/EBITDA applied to the company's own EBITDA.

    Deliberately not a DCF. A DCF's output is dominated by a terminal-growth assumption
    the system has no defensible basis for, and presenting one would imply a precision
    this pipeline does not have. A peer multiple is honest about being relative.
    """
    method = "Peer median EV/EBITDA applied to trailing EBITDA, less net debt, per diluted share"
    if (
        peer_median_ev_ebitda is None
        or company_ebitda is None
        or company_ebitda <= 0
        or shares is None
        or shares <= 0
    ):
        return {
            "low": None,
            "high": None,
            "mid": None,
            "method": method,
            "available": False,
            "reason": "Requires a peer median EV/EBITDA, positive trailing EBITDA, and a share count.",
        }

    ev = peer_median_ev_ebitda * company_ebitda
    equity_value = ev - (total_debt or 0.0) + (cash or 0.0)
    per_share = equity_value / shares

    if per_share <= 0:
        return {
            "low": None,
            "high": None,
            "mid": None,
            "method": method,
            "available": False,
            "reason": "Implied equity value is negative at the peer multiple; no meaningful target.",
        }

    # A target implying a move of several hundred percent is telling you the peer
    # multiple does not apply to this company, not that the shares are mispriced by
    # that much. Report it, but say so.
    implied_move = None
    stretched = False
    if current_price and current_price > 0:
        implied_move = per_share / current_price - 1.0
        stretched = per_share > current_price * 2.5 or per_share < current_price * 0.4

    return {
        "low": round(per_share * (1 - band), 2),
        "mid": round(per_share, 2),
        "high": round(per_share * (1 + band), 2),
        "method": method,
        "available": True,
        "implied_move": round(implied_move, 4) if implied_move is not None else None,
        "stretched": stretched,
        "caveat": (
            "The peer multiple implies a valuation far from the current share price, "
            "which usually means the comparable set is not a true comparable set for "
            "this company. Treat the band as weak evidence."
            if stretched else None
        ),
        "inputs": {
            "peer_median_ev_ebitda": round(peer_median_ev_ebitda, 3),
            "company_ebitda": company_ebitda,
            "total_debt": total_debt,
            "cash": cash,
            "shares": shares,
            "band_pct": band,
            "current_price": current_price,
        },
    }
