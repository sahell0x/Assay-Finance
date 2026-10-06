"""What-if analysis over a finished scorecard.

Two questions, both answered by arithmetic rather than by a model:

- **"What if?"** — re-run the rubric with one or more metrics moved, and report the
  composite, the rating, the conviction and the price target that fall out.
- **"What would have to be true?"** — for a rating the company does not currently hold,
  find for each metric the smallest move that would reach it, and say plainly which
  metrics cannot get there on their own.

Both run against a stored scorecard alone. Everything they need — each metric's value,
its weight inside its dimension, the dimension weights, the data coverage, and the
price target's own inputs — is already in the JSONB the pipeline writes, so a scenario
costs no data fetch, no model call and no queue slot.

**This module scores nothing itself.** It rearranges inputs and hands them to
``scoring.py``, which is the only place a metric becomes a number out of ten. That is
deliberate and it is load-bearing: a scenario that scored metrics its own way — or, more
tempting, a copy of the anchor tables in the browser for instant sliders — would be a
second rubric free to drift from the real one, and the drift would show up as a memo
arguing a rating the scenario panel disagrees with. A scenario with no overrides
reproduces the stored card exactly, and there is a test that fails if it ever stops
doing so.
"""

from __future__ import annotations

import math

from . import scoring as sc
from .ratios import Num

# The one lever that is not a metric. Moving the share price moves six valuation
# metrics at once, each by a different law — see ``_rescale_for_price``.
PRICE_LEVER = "share_price"

_RANK = {"SELL": 0, "HOLD": 1, "BUY": 2}

# Display metadata. ``unit`` tells the interface how to format the handle: "pct" is a
# fraction rendered as a percentage, "x" a multiple, "ratio" a bare number, "score" a
# points scale, "currency" a share price.
METRIC_META: dict[str, tuple[str, str]] = {
    # profitability
    "gross_margin": ("Gross margin", "pct"),
    "operating_margin": ("Operating margin", "pct"),
    "net_margin": ("Net margin", "pct"),
    "fcf_margin": ("FCF margin", "pct"),
    "roe": ("Return on equity", "pct"),
    "roic": ("Return on invested capital", "pct"),
    "roa": ("Return on assets", "pct"),
    # financial health
    "current_ratio": ("Current ratio", "ratio"),
    "quick_ratio": ("Quick ratio", "ratio"),
    "net_debt_ebitda": ("Net debt / EBITDA", "x"),
    "interest_coverage": ("Interest coverage", "x"),
    "debt_to_equity": ("Debt / equity", "ratio"),
    "altman_z": ("Altman Z-score", "score"),
    "fcf_to_debt": ("FCF / total debt", "pct"),
    # growth
    "rev_yoy": ("Revenue growth, YoY", "pct"),
    "rev_cagr_3y": ("Revenue CAGR, 3y", "pct"),
    "rev_cagr_5y": ("Revenue CAGR, 5y", "pct"),
    "eps_growth": ("EPS growth", "pct"),
    "fcf_cagr_3y": ("FCF CAGR, 3y", "pct"),
    "growth_acceleration": ("Growth acceleration", "pct"),
    "incremental_operating_margin": ("Incremental operating margin", "pct"),
    # valuation
    "pe": ("P / E", "x"),
    "ev_ebitda": ("EV / EBITDA", "x"),
    "ev_sales": ("EV / sales", "x"),
    "price_to_book": ("Price / book", "x"),
    "fcf_yield": ("FCF yield", "pct"),
    "peg": ("PEG", "x"),
}

# Overrides arrive as a flat ``{metric: value}`` map, which is only unambiguous while no
# two dimensions share a metric name. ``TestMetricNamespace`` guards that.
_DIMENSION_OF: dict[str, str] = {
    name: dim for dim, spec in sc.DIMENSION_METRICS.items() for name in spec
}

# How each valuation metric responds to a change in the share price.
_SCALES_WITH_PRICE = ("pe", "price_to_book", "peg")
_SCALES_WITH_EV = ("ev_ebitda", "ev_sales")
_SCALES_INVERSELY = ("fcf_yield",)
_PRICE_SENSITIVE = _SCALES_WITH_PRICE + _SCALES_WITH_EV + _SCALES_INVERSELY

_STEP_MANTISSAS = (1.0, 2.0, 2.5, 5.0, 10.0)
_TARGET_STEPS = 200


# ------------------------------------------------------------------------------ levers


def _nice_step(span: float) -> float:
    """A step of roughly ``span / 200``, rounded to a number a human reads easily."""
    raw = abs(span) / _TARGET_STEPS
    if raw <= 0 or not math.isfinite(raw):
        return 1.0
    magnitude = 10.0 ** math.floor(math.log10(raw))
    for mantissa in _STEP_MANTISSAS:
        step = mantissa * magnitude
        if step >= raw:
            return step
    return 10.0 * magnitude


def _range_for(anchors: list[tuple[float, float]], value: float) -> tuple[float, float, float]:
    """A draggable domain for a metric.

    The anchor table already states where a metric stops being interesting in either
    direction, so it defines the range; a margin either side keeps the ends reachable.
    A metric that is not floored at zero in its own table keeps its negative side.
    """
    low, high = float(anchors[0][0]), float(anchors[-1][0])
    pad = 0.15 * (high - low) or 1.0

    lo, hi = low - pad, high + pad
    if low >= 0:
        lo = max(0.0, lo)
    # A company outside its own anchor table still needs a handle it can be dragged from.
    if value < lo:
        lo = value - pad
    if value > hi:
        hi = value + pad
    return lo, hi, _nice_step(hi - lo)


def _price_lever(card: dict) -> dict | None:
    inputs = ((card.get("price_target") or {}).get("inputs")) or {}
    price = inputs.get("current_price")
    shares = inputs.get("shares")
    if not price or price <= 0 or not shares or shares <= 0:
        return None
    lo, hi = 0.2 * price, 2.0 * price
    return {
        "name": PRICE_LEVER,
        "label": "Share price",
        "dimension": "valuation",
        "unit": "currency",
        "value": float(price),
        "min": round(lo, 2),
        "max": round(hi, 2),
        "step": _nice_step(hi - lo),
        "higher_is_better": False,
    }


def levers_for(card: dict) -> list[dict]:
    """Every metric on this card that can be moved, plus the share price.

    A metric that could not be computed is not a lever: there is no baseline to move
    from, and inventing one would put a number on the screen the analysis never had.
    """
    detail = card.get("detail") or {}
    levers: list[dict] = []

    for dim, spec in sc.DIMENSION_METRICS.items():
        dim_detail = detail.get(dim) or {}
        for name in spec:
            value = (dim_detail.get(name) or {}).get("value")
            anchors = sc.anchors_for(name)
            if value is None or anchors is None:
                continue
            label, unit = METRIC_META.get(name, (name.replace("_", " ").capitalize(), "ratio"))
            lo, hi, step = _range_for(anchors, float(value))
            levers.append(
                {
                    "name": name,
                    "label": label,
                    "dimension": dim,
                    "unit": unit,
                    "value": float(value),
                    "min": lo,
                    "max": hi,
                    "step": step,
                    "higher_is_better": name not in sc.LOWER_IS_BETTER,
                }
            )

    price = _price_lever(card)
    if price is not None:
        levers.append(price)
    return levers


# --------------------------------------------------------------------------- recompute


def _metrics_from(card: dict) -> dict[str, dict[str, Num]]:
    """The metric values that produced this card, by dimension."""
    detail = card.get("detail") or {}
    out: dict[str, dict[str, Num]] = {}
    for dim, spec in sc.DIMENSION_METRICS.items():
        dim_detail = detail.get(dim) or {}
        out[dim] = {name: (dim_detail.get(name) or {}).get("value") for name in spec}
    return out


def _price_scenario(card: dict, new_price: float) -> dict | None:
    """What a move to ``new_price`` does to the equity and to the enterprise value."""
    inputs = ((card.get("price_target") or {}).get("inputs")) or {}
    base = inputs.get("current_price")
    shares = inputs.get("shares")
    if not base or base <= 0 or not shares or shares <= 0 or new_price <= 0:
        return None

    factor = new_price / base
    market_cap = shares * base
    net_debt = (inputs.get("total_debt") or 0.0) - (inputs.get("cash") or 0.0)
    enterprise_value = market_cap + net_debt

    return {
        "price": new_price,
        "baseline_price": float(base),
        "move": round(factor - 1.0, 6),
        "factor": factor,
        # Only the equity half of enterprise value moves with the share price.
        "ev_factor": ((market_cap * factor + net_debt) / enterprise_value)
        if enterprise_value
        else factor,
    }


def _rescale_for_price(metrics: dict[str, dict[str, Num]], scenario: dict) -> None:
    """Move every price-sensitive valuation metric, each by its own law.

    P/E, price/book and PEG are equity multiples and scale with the price. EV/EBITDA and
    EV/sales scale with enterprise value, which moves less because net debt does not
    move at all. FCF yield is a reciprocal and moves the other way.
    """
    valuation = metrics.get("valuation") or {}
    factor, ev_factor = scenario["factor"], scenario["ev_factor"]

    for name in _SCALES_WITH_PRICE:
        if valuation.get(name) is not None:
            valuation[name] = valuation[name] * factor
    for name in _SCALES_WITH_EV:
        if valuation.get(name) is not None:
            valuation[name] = valuation[name] * ev_factor
    for name in _SCALES_INVERSELY:
        if valuation.get(name) is not None and factor:
            valuation[name] = valuation[name] / factor


def _retarget(price_target: dict, new_price: float) -> dict:
    """Re-state the target against the scenario price.

    The band itself does not move — it is a peer multiple applied to the company's own
    EBITDA and knows nothing about the share price — but the *implied move* is a
    statement about the price and would be a lie if it were left stale.
    """
    mid = price_target.get("mid")
    if not price_target.get("available") or mid is None or new_price <= 0:
        return price_target

    out = dict(price_target)
    out["implied_move"] = round(mid / new_price - 1.0, 6)
    out["stretched"] = mid > new_price * 2.5 or mid < new_price * 0.4
    out["inputs"] = {**(price_target.get("inputs") or {}), "current_price": new_price}
    return out


def _clean_overrides(card: dict, overrides: dict | None) -> tuple[dict[str, float], dict | None]:
    """Keep the overrides that name a real metric and carry a real number.

    A stale client, a hand-edited request or a renamed metric must produce the baseline
    scorecard, not a 500 and not a silently wrong one.
    """
    clean: dict[str, float] = {}
    price_scenario: dict | None = None

    for name, raw in (overrides or {}).items():
        if isinstance(raw, bool):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        if name == PRICE_LEVER:
            price_scenario = _price_scenario(card, value)
        elif name in _DIMENSION_OF:
            clean[name] = value

    return clean, price_scenario


def recompute(
    card: dict,
    *,
    overrides: dict | None = None,
    weights: dict | None = None,
) -> dict:
    """Re-run the rubric over one scorecard with some inputs changed.

    Returns a card of the same shape ``build_scorecard`` produces, so every component
    that renders a real scorecard renders a scenario unchanged.
    """
    metrics = _metrics_from(card)
    clean, price_scenario = _clean_overrides(card, overrides)
    price_target = card.get("price_target") or {"available": False}

    if price_scenario is not None:
        _rescale_for_price(metrics, price_scenario)
        price_target = _retarget(price_target, price_scenario["price"])

    # Applied after the price rescale, so a metric the user set by hand wins over the
    # value the price lever would have implied for it.
    for name, value in clean.items():
        metrics[_DIMENSION_OF[name]][name] = value

    dimension_scores: dict[str, Num] = {}
    detail: dict[str, dict] = {}
    for dim in sc.DIMENSION_METRICS:
        score, dim_detail = sc.score_dimension(dim, metrics[dim])
        dimension_scores[dim] = score
        detail[dim] = dim_detail

    stored_sentiment = ((card.get("detail") or {}).get("sentiment")) or {}
    dimension_scores["sentiment"] = sc.score_sentiment(stored_sentiment.get("raw_sentiment"))
    detail["sentiment"] = stored_sentiment

    out = sc.build_scorecard(
        dimension_scores=dimension_scores,
        dimension_detail=detail,
        user_weights=weights if weights is not None else card.get("weights_requested"),
        coverage=float(card.get("coverage") or 1.0),
    )
    out["price_target"] = price_target
    out["price_scenario"] = price_scenario
    out["overridden"] = sorted(clean) + ([PRICE_LEVER] if price_scenario else [])
    out["baseline"] = {
        "total": card.get("total"),
        "rating": card.get("rating"),
        "conviction": card.get("conviction"),
    }
    return out


# ------------------------------------------------------------------------------ solver


def default_target(rating: str | None) -> str:
    """The interesting question for a company already at this rating.

    For anything below BUY it is "what would raise it". For a BUY it is the opposite —
    what would take it away — because that is the question a holder actually has.
    """
    return {"SELL": "HOLD", "HOLD": "BUY", "BUY": "HOLD"}.get(rating or "HOLD", "BUY")


def _dimension_denominator(card: dict, dimension: str) -> float:
    """The weight ``score_dimension`` divides by: the metrics that actually scored."""
    detail = (card.get("detail") or {}).get(dimension) or {}
    total = 0.0
    for name, weight in sc.DIMENSION_METRICS.get(dimension, {}).items():
        if sc.score_metric(name, (detail.get(name) or {}).get("value")) is not None:
            total += weight
    return total


def _max_contribution(card: dict, baseline: dict, lever: dict, improving: bool) -> float:
    """The most this lever could move the composite, taken to the end of its scale.

    A metric can score at best 10 and at worst 0, so the ceiling on what moving it does
    to the composite is its remaining headroom times its weight inside its dimension
    times that dimension's weight inside the fold. Levers are only created for metrics
    that already have a value, so neither denominator changes underneath this.

    An over-estimate is the safe direction: it can only ever leave a scan to run that
    would have failed, never skip one that would have succeeded.
    """
    dimension = lever["dimension"]
    dimension_weight = (baseline.get("weights_applied") or {}).get(dimension) or 0.0
    denominator = _dimension_denominator(card, dimension)
    if dimension_weight <= 0 or denominator <= 0:
        return 0.0

    detail = (card.get("detail") or {}).get(dimension) or {}
    # The price lever moves every price-sensitive valuation metric at once, all in the
    # same direction, so its ceiling is the sum of theirs.
    names = _PRICE_SENSITIVE if lever["name"] == PRICE_LEVER else (lever["name"],)

    headroom = 0.0
    for name in names:
        weight = sc.DIMENSION_METRICS.get(dimension, {}).get(name)
        if not weight:
            continue
        score = sc.score_metric(name, (detail.get(name) or {}).get("value"))
        if score is None:
            continue
        headroom += ((10.0 - score) if improving else score) * weight

    return dimension_weight * headroom / denominator


def _unreachable(lever: dict) -> dict:
    return {
        "lever": lever["name"],
        "label": lever["label"],
        "dimension": lever["dimension"],
        "unit": lever["unit"],
        "from": lever["value"],
        "higher_is_better": lever["higher_is_better"],
        "reachable": False,
        "to": None,
        "delta": None,
        "effort": None,
        "resulting_total": None,
    }


def _solve_one(card: dict, lever: dict, target_rating: str, improving: bool) -> dict:
    """The smallest move in one lever that reaches ``target_rating``, if any.

    Solved by walking the lever's own range a step at a time rather than by inverting
    the rubric algebraically. The fold is piecewise-linear through weights that
    renormalise around missing dimensions, and a closed form for it would have to be
    re-derived every time an anchor table changed. A scan cannot fall out of step with
    the scoring code because it calls it.
    """
    # Improving a "lower is better" metric means moving down, and so does worsening a
    # "higher is better" one.
    upward = lever["higher_is_better"] == improving
    start, lo, hi, step = lever["value"], lever["min"], lever["max"], lever["step"]
    span = hi - lo

    steps = int(abs((hi if upward else lo) - start) / step) + 1
    for n in range(1, steps + 1):
        candidate = start + n * step if upward else start - n * step
        if candidate > hi or candidate < lo:
            break
        out = recompute(card, overrides={lever["name"]: candidate})
        if out["rating"] == target_rating:
            return {
                **_unreachable(lever),
                "reachable": True,
                "to": candidate,
                "delta": candidate - start,
                "effort": abs(candidate - start) / span if span else 0.0,
                "resulting_total": out["total"],
            }

    return _unreachable(lever)


def solve_paths(card: dict, *, target_rating: str) -> list[dict]:
    """Every single-lever route to ``target_rating``, easiest first.

    Unreachable levers are returned rather than filtered out. "Nothing this metric can
    do on its own gets there" is the more common answer and the more useful one — it is
    what stops a reader believing a rating is one good quarter away when it is not.
    """
    baseline = recompute(card)
    if baseline["rating"] == target_rating:
        return []

    levers = levers_for(card)
    total = baseline["total"]
    if total is None:
        return [_unreachable(lever) for lever in levers]

    improving = _RANK.get(target_rating, 1) > _RANK.get(baseline["rating"], 1)
    # The band the composite has to land in for the target rating.
    if improving:
        floor = sc.BUY_THRESHOLD if target_rating == "BUY" else sc.HOLD_THRESHOLD
    else:
        ceiling = sc.HOLD_THRESHOLD if target_rating == "SELL" else sc.BUY_THRESHOLD

    paths: list[dict] = []
    for lever in levers:
        # Skip the scan where the arithmetic already rules the lever out. A company in
        # the middle of a band rules out every lever, which is exactly the case that
        # would otherwise scan all of them to their stops.
        reach = _max_contribution(card, baseline, lever, improving)
        if improving and total + reach < floor - 1e-9:
            paths.append(_unreachable(lever))
        elif not improving and total - reach >= ceiling - 1e-9:
            paths.append(_unreachable(lever))
        else:
            paths.append(_solve_one(card, lever, target_rating, improving))
    paths.sort(key=lambda p: (not p["reachable"], p["effort"] if p["effort"] is not None else math.inf))
    return paths
