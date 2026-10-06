"""Node 8: the rating.

No model is called here. The composite score is a weighted fold of the four dimension
scores plus sentiment, the weights renormalise around anything unavailable, and the
rating falls out of two fixed thresholds. The memo writer receives the result as
settled fact.
"""

from __future__ import annotations

from ...analytics import scoring as sc
from ..progress import node


@node("scorecard")
async def scorecard(state: dict) -> dict:
    dq = state.get("data_quality") or {}

    dimension_scores: dict[str, float | None] = {
        "profitability": _score_of(state.get("profitability")),
        "financial_health": _score_of(state.get("liquidity")),
        "growth": _score_of(state.get("growth")),
        "valuation": _score_of(state.get("peers")),
        "sentiment": sc.score_sentiment(state.get("sentiment_score")),
    }

    detail = {
        "profitability": _detail_of(state.get("profitability")),
        "financial_health": _detail_of(state.get("liquidity")),
        "growth": _detail_of(state.get("growth")),
        "valuation": _detail_of(state.get("peers")),
        "sentiment": {
            "raw_sentiment": state.get("sentiment_score"),
            "evidence_count": len(state.get("evidence") or []),
        },
    }

    # Coverage blends statement completeness with how much of the pipeline actually ran.
    statement_coverage = float(dq.get("coverage", 0.0) or 0.0)
    dimensions_present = len([v for v in dimension_scores.values() if v is not None])
    coverage = round(
        0.6 * statement_coverage + 0.4 * (dimensions_present / len(sc.WEIGHTS)), 4
    )

    card = sc.build_scorecard(
        dimension_scores=dimension_scores,
        dimension_detail=detail,
        user_weights=state.get("weights"),
        coverage=coverage,
    )
    card["price_target"] = state.get("price_target") or {"available": False}
    card["narrative_by_dimension"] = {
        "profitability": _narrative_of(state.get("profitability")),
        "financial_health": _narrative_of(state.get("liquidity")),
        "growth": _narrative_of(state.get("growth")),
        "valuation": _narrative_of(state.get("peers")),
    }

    warnings = []
    if card["dimensions_unavailable"]:
        warnings.append(
            "Dimensions excluded from the composite score and reweighted: "
            + ", ".join(card["dimensions_unavailable"])
            + "."
        )
    if card["total"] is not None and card["distance_to_edge"] is not None and card["distance_to_edge"] < 0.25:
        warnings.append(
            f"The composite score of {card['total']} sits close to the "
            f"{'BUY' if card['total'] >= sc.BUY_THRESHOLD else 'HOLD'} threshold; small "
            f"changes in the inputs would move the rating."
        )

    return {"scorecard": card, "warnings": warnings}


def _score_of(block) -> float | None:
    if block is None:
        return None
    # A block whose metrics are all unavailable scores 0 by construction; that is a data
    # gap, not a judgement, so it is excluded rather than counted against the company.
    if not any(m.value is not None for m in block.metrics.values()):
        return None
    return block.score


def _detail_of(block) -> dict:
    return (block.extras or {}).get("score_detail", {}) if block else {}


def _narrative_of(block) -> str:
    return block.narrative if block else ""
