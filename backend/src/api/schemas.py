"""Request and response shapes for the HTTP layer."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TICKER_MAX = 12

DIMENSIONS = {"profitability", "financial_health", "growth", "valuation", "sentiment"}


def clean_weights(v: dict | None) -> dict | None:
    """Keep the dimension weights a client sent that name a real dimension and parse.

    Shared by the analysis request and the scenario request so the two cannot disagree
    about what a weight override is allowed to be.
    """
    if not v:
        return None
    out = {}
    for k, val in v.items():
        if k not in DIMENSIONS:
            continue
        try:
            f = float(val)
        except (TypeError, ValueError):
            continue
        out[k] = max(0.0, min(1.0, f))
    return out or None


class AnalysisRequest(BaseModel):
    ticker: str
    peer_tickers: list[str] = Field(default_factory=list, max_length=8)
    # Typed loosely and cleaned in a "before" validator: a stray key or a
    # non-numeric value from a client should be dropped, not turned into a 422 that
    # fails an otherwise valid request.
    weights: dict[str, Any] | None = None
    force_refresh: bool = False

    @field_validator("ticker")
    @classmethod
    def _clean_ticker(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not v or len(v) > TICKER_MAX or not all(c.isalnum() or c in ".-^" for c in v):
            raise ValueError("Enter a valid ticker symbol, for example AAPL or BRK.B.")
        return v

    @field_validator("peer_tickers")
    @classmethod
    def _clean_peers(cls, v: list[str]) -> list[str]:
        out = []
        for p in v or []:
            p = (p or "").strip().upper()
            if p and len(p) <= TICKER_MAX and p not in out:
                out.append(p)
        return out

    @field_validator("weights", mode="before")
    @classmethod
    def _clean_weights(cls, v: dict | None) -> dict | None:
        return clean_weights(v)


class AnalysisAccepted(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "running", "complete", "failed"]
    ticker: str
    cached: bool = False
    cached_at: datetime | None = None
    stream_url: str
    poll_url: str
    budget: dict | None = None
    quota: dict | None = None


class AnalysisSummary(BaseModel):
    id: uuid.UUID
    ticker: str
    status: str
    rating: str | None = None
    conviction: str | None = None
    total_score: float | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    cached: bool = False
    error: str | None = None


class ShowcaseCard(BaseModel):
    """One pre-computed company on the landing page.

    A summary is not enough for a card a visitor decides to click: it needs the company's
    name, what it costs, and the five dimension scores that draw the sparkline. Every
    field comes from an analysis that really ran — the page has no mock data path.
    """

    id: uuid.UUID
    ticker: str
    name: str | None = None
    sector: str | None = None
    rating: str | None = None
    conviction: str | None = None
    total_score: float | None = None
    dimension_scores: dict[str, float | None] = Field(default_factory=dict)
    price: float | None = None
    currency: str | None = None
    market_cap: float | None = None
    thesis: str | None = None
    completed_at: datetime | None = None


class EvidenceOut(BaseModel):
    label: str
    source_type: str
    section: str | None = None
    title: str | None = None
    url: str | None = None
    published: str | None = None
    text: str
    relevance: float | None = None


class AnalysisDetail(BaseModel):
    id: uuid.UUID
    ticker: str
    status: str
    current_node: str | None = None
    peer_tickers: list[str] | None = None
    weights: dict | None = None
    scorecard: dict | None = None
    memo: dict | None = None
    blocks: dict | None = None
    data_quality: dict | None = None
    evidence: list[EvidenceOut] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    pipeline: list[dict] = Field(default_factory=list)
    cached: bool = False
    cached_at: datetime | None = None
    public_slug: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    owned: bool = False


class ScenarioRequest(BaseModel):
    """A what-if over a finished analysis.

    Both fields are typed loosely and cleaned before use, for the same reason
    ``AnalysisRequest.weights`` is: a slider a release renamed, or a stale tab posting a
    metric that no longer exists, should fall back to the stored value rather than 422
    an otherwise sensible request. ``analytics.scenario`` drops anything it does not
    recognise, so the validator here only has to bound the size of the payload.
    """

    overrides: dict[str, Any] = Field(default_factory=dict, max_length=64)
    weights: dict[str, Any] | None = None

    @field_validator("weights", mode="before")
    @classmethod
    def _clean_weights(cls, v: dict | None) -> dict | None:
        return clean_weights(v)


class TickerSuggestion(BaseModel):
    ticker: str
    name: str
    exchange: str | None = None
    sector: str | None = None


class TickerResolution(BaseModel):
    matches: list[TickerSuggestion] = []
    # Set when the query names a well-known company that is not publicly traded.
    private_company: str | None = None


class WatchlistEntry(BaseModel):
    ticker: str
    added_at: datetime | None = None
    name: str | None = None
    rating: str | None = None
    total_score: float | None = None
    analysis_id: uuid.UUID | None = None
    last_run: datetime | None = None


class HistoryPoint(BaseModel):
    analysis_id: uuid.UUID
    date: datetime
    total: float | None
    rating: str | None
    dimension_scores: dict[str, Any] | None = None
