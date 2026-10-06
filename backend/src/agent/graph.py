"""The pipeline.

Shape, and why:

    ingest -> validate -> profitability -> liquidity -> growth
                                                          |
                                                        peers
                                                          |
                                                       news_rag
                                                          |
                                                      scorecard
                                                          |
                                                        memo  <--+
                                                          |      |
                                                       critic ---+ (at most once)
                                                          |
                                                         END

Two orderings are load-bearing.

``peers`` runs after the three company nodes because it writes back: once peer values
exist, every metric already computed gets a percentile stamped onto it.

``news_rag`` runs after ``peers`` because its queries are conditioned on what the
numbers found. Retrieval that does not know the company's revenue fell cannot go looking
for the reason.

The four analysis nodes are sequential rather than parallel. They are I/O-light once
ingest has run — the expensive fetch already happened — and each makes one small
narrative call. Fanning them out would add concurrent LLM calls and database sessions to
a box sized for one worker, for a saving measured in single-digit seconds.
"""

from __future__ import annotations

import logging
import uuid

from langgraph.graph import END, START, StateGraph

from .nodes.critic import critic, should_revise
from .nodes.growth import growth
from .nodes.ingest import ingest
from .nodes.liquidity import liquidity
from .nodes.memo import memo
from .nodes.news_rag import news_rag
from .nodes.peers import peers
from .nodes.profitability import profitability
from .nodes.scorecard import scorecard
from .nodes.validate import validate
from .state import FinState

log = logging.getLogger(__name__)

_compiled = None


def build_graph():
    g = StateGraph(FinState)

    g.add_node("ingest", ingest)
    g.add_node("validate", validate)
    g.add_node("profitability", profitability)
    g.add_node("liquidity", liquidity)
    g.add_node("growth", growth)
    g.add_node("peers", peers)
    g.add_node("news_rag", news_rag)
    g.add_node("scorecard", scorecard)
    g.add_node("memo", memo)
    g.add_node("critic", critic)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "validate")
    g.add_edge("validate", "profitability")
    g.add_edge("profitability", "liquidity")
    g.add_edge("liquidity", "growth")
    g.add_edge("growth", "peers")
    g.add_edge("peers", "news_rag")
    g.add_edge("news_rag", "scorecard")
    g.add_edge("scorecard", "memo")
    g.add_edge("memo", "critic")

    # One revision, then ship. A memo that still fails verification goes out with the
    # failures recorded in the trace rather than looping.
    g.add_conditional_edges("critic", should_revise, {"memo": "memo", "end": END})

    return g.compile()


def get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def initial_state(
    *,
    analysis_id: str,
    ticker: str,
    peer_tickers: list[str] | None = None,
    weights: dict | None = None,
) -> dict:
    return {
        "analysis_id": str(analysis_id),
        "ticker": ticker.upper().strip(),
        "peer_tickers": [p.upper().strip() for p in (peer_tickers or []) if p.strip()],
        "weights": weights or {},
        "revision_count": 0,
        "warnings": [],
        "trace": [],
    }


async def run_analysis(
    *,
    analysis_id: str,
    ticker: str,
    peer_tickers: list[str] | None = None,
    weights: dict | None = None,
    thread_id: str | None = None,
) -> dict:
    """Execute the whole pipeline and return the final state."""
    graph = get_graph()
    state = initial_state(
        analysis_id=analysis_id, ticker=ticker, peer_tickers=peer_tickers, weights=weights
    )
    config = {
        "configurable": {"thread_id": thread_id or str(uuid.uuid4())},
        "recursion_limit": 40,
    }
    return await graph.ainvoke(state, config=config)
