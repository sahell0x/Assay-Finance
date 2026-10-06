"""The shape of everything that flows through the graph.

Two ideas carry most of the weight here:

``MetricValue.formula`` and ``MetricValue.inputs`` are not documentation. They are the
audit trail that lets the interface show, for any number on screen, the expression that
produced it and the statement lines that went in. Every metric the system reports
carries them.

``InvestmentMemo`` is a structured-output target, not free text. The model fills fields;
it does not decide the rating, which arrives already decided in the scorecard.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

Unit = Literal["ratio", "percent", "currency", "days", "x", "score"]
Flag = Literal["strong", "neutral", "weak", "unreliable"]
Dimension = Literal["profitability", "liquidity", "growth", "peers"]


class MetricValue(BaseModel):
    """One computed number, with everything needed to justify it."""

    name: str
    value: float | None
    unit: Unit
    period: str                       # "FY2024" | "TTM"
    formula: str                      # "net_income / avg_total_equity"
    inputs: dict[str, float | None]   # the statement lines that fed the formula
    peer_percentile: float | None = None
    yoy_change: float | None = None
    flag: Flag | None = None
    note: str | None = None           # why a value is missing, when it is
    label: str | None = None          # display name for the interface
    history: list[dict] | None = None  # [{period, value}] newest-first, for charts

    @property
    def available(self) -> bool:
        return self.value is not None


class MetricBlock(BaseModel):
    """One analysis dimension's full output."""

    dimension: Dimension
    metrics: dict[str, MetricValue]
    narrative: str = ""
    score: float = 0.0                # 0-10, computed by the rubric, never by a model
    warnings: list[str] = Field(default_factory=list)
    extras: dict = Field(default_factory=dict)  # charts and decompositions

    # Postgres stores JSONB with its keys reordered by length and bytes, so a dict's
    # insertion order does not survive a round trip through the database. Without an
    # explicit ordering the metric table comes back shuffled — margins interleaved with
    # returns — which reads as carelessness. This list is the display order.
    order: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: object) -> None:
        if not self.order:
            self.order = list(self.metrics.keys())

    def value(self, name: str) -> float | None:
        m = self.metrics.get(name)
        return m.value if m else None

    def ordered(self) -> list[tuple[str, MetricValue]]:
        seen = set(self.order)
        pairs = [(k, self.metrics[k]) for k in self.order if k in self.metrics]
        pairs += [(k, v) for k, v in self.metrics.items() if k not in seen]
        return pairs


class Evidence(BaseModel):
    """A retrieved chunk, labelled so the memo can cite it."""

    label: str                        # "S1"
    chunk_id: str
    ticker: str
    source_type: str                  # sec_10k | sec_10q | yf_news | rss
    section: str | None = None
    title: str | None = None
    url: str | None = None
    published: str | None = None      # ISO date
    text: str
    relevance: float | None = None
    query: str | None = None          # which themed query surfaced it


class InvestmentMemo(BaseModel):
    """The deliverable. Produced by structured output against this exact schema."""

    ticker: str
    as_of: str
    recommendation: Literal["BUY", "HOLD", "SELL"]
    conviction: Literal["low", "medium", "high"]
    thesis: str
    price_target_low: float | None = None
    price_target_high: float | None = None
    valuation_method: str
    key_drivers: list[str] = Field(min_length=3, max_length=5)
    key_risks: list[str] = Field(min_length=3, max_length=5)
    what_would_change_our_mind: list[str] = Field(default_factory=list)
    data_caveats: list[str] = Field(default_factory=list)
    cited_sources: list[str] = Field(default_factory=list)


class FinState(TypedDict, total=False):
    """LangGraph state.

    ``warnings`` and ``trace`` are reducer-annotated so concurrent nodes append rather
    than clobber; everything else is written by exactly one node.
    """

    analysis_id: str
    ticker: str
    peer_tickers: list[str]
    weights: dict

    facts: dict            # Fundamentals.to_dict()
    market: dict
    data_quality: dict

    profitability: MetricBlock
    liquidity: MetricBlock
    growth: MetricBlock
    peers: MetricBlock

    evidence: list[Evidence]
    sentiment_score: float
    retrieval_stats: dict

    scorecard: dict
    memo: InvestmentMemo
    critic_verdict: dict
    revision_count: int

    price_target: dict
    budget_flag: dict
    cost: dict

    warnings: Annotated[list[str], operator.add]
    trace: Annotated[list[dict], operator.add]


def metric(
    name: str,
    value: float | None,
    *,
    unit: Unit,
    period: str,
    formula: str,
    inputs: dict[str, float | None],
    label: str | None = None,
    flag: Flag | None = None,
    note: str | None = None,
    history: list[dict] | None = None,
    yoy_change: float | None = None,
) -> MetricValue:
    """Constructor that makes the provenance fields impossible to forget."""
    return MetricValue(
        name=name,
        value=value,
        unit=unit,
        period=period,
        formula=formula,
        inputs=inputs,
        label=label or name.replace("_", " ").title(),
        flag=flag,
        note=note,
        history=history,
        yoy_change=yoy_change,
    )


def flag_from_score(score: float | None) -> Flag | None:
    """Translate a 0-10 rubric score into the four-way display flag."""
    if score is None:
        return None
    if score >= 7.0:
        return "strong"
    if score >= 4.0:
        return "neutral"
    return "weak"


def block_to_dict(block: MetricBlock | None) -> dict | None:
    return block.model_dump(mode="json") if block else None
