"""Node 7: retrieve qualitative context, interrogating what the numbers exposed.

The design choice that matters here is that retrieval is *not* one generic query about
the company. It is a set of themed queries, several of which exist only because the
quantitative nodes found something. If revenue fell, the pipeline goes looking for
demand weakness. If leverage is above three turns, it goes looking for refinancing and
covenants. If margins compressed, it asks about cost inflation.

That coupling is the point of running the quantitative work first: the retrieval
interrogates exactly the weaknesses the ratios exposed, instead of returning whatever
the company's investor-relations copy happens to rank highly for its own name.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from ...config import settings
from ...data.fundamentals import Fundamentals
from ...data.news.embed import embed_query
from ...data.news.ingest import index_ticker
from ...data.news.store import count_for, search
from ...db.session import SessionLocal
from ..models import UNTRUSTED_NOTICE, get_router, wrap_untrusted
from ..progress import node
from ..state import Evidence
from ._shared import usage_from

log = logging.getLogger(__name__)

K_PER_QUERY = 6
HALF_LIFE_DAYS = 180

SENTIMENT_SYSTEM = f"""You read source documents about a company and judge the tone of \
what they say about its prospects.

{UNTRUSTED_NOTICE}

Return JSON: {{"sentiment": <number between -1 and 1>, "rationale": "<one sentence>", \
"themes": ["<short phrase>", ...]}}

-1 is uniformly negative (deteriorating demand, litigation, guidance cuts), 0 is neutral \
or mixed, +1 is uniformly positive. Judge the substance of what the documents report, \
not how enthusiastically they are written. Routine risk-factor boilerplate present in \
every filing is neutral, not negative."""


def build_queries(state: dict, f: Fundamentals) -> list[dict]:
    """Themed queries. The conditional ones are the interesting half."""
    name = f.name or f.ticker
    queries: list[dict] = [
        {"q": f"{name} competitive threats market share", "theme": "competition"},
        {"q": f"{name} management guidance outlook", "theme": "guidance"},
        {"q": f"{name} regulatory legal proceedings", "theme": "regulatory"},
        {"q": f"{name} margin pressure cost inflation", "theme": "costs"},
    ]

    growth = state.get("growth")
    liquidity = state.get("liquidity")
    profitability = state.get("profitability")

    rev_yoy = growth.value("rev_yoy") if growth else None
    if rev_yoy is not None and rev_yoy < 0:
        queries.append(
            {"q": f"{name} revenue decline demand weakness", "theme": "demand", "because": "revenue fell year over year"}
        )

    nd_ebitda = liquidity.value("net_debt_ebitda") if liquidity else None
    if nd_ebitda is not None and nd_ebitda > 3:
        queries.append(
            {"q": f"{name} debt refinancing covenants leverage", "theme": "leverage",
             "because": f"net debt is {nd_ebitda:.1f}x EBITDA"}
        )

    coverage = liquidity.value("interest_coverage") if liquidity else None
    if coverage is not None and coverage < 3:
        queries.append(
            {"q": f"{name} interest expense debt service liquidity", "theme": "solvency",
             "because": f"interest coverage is {coverage:.1f}x"}
        )

    if profitability is not None:
        op_margin = profitability.metrics.get("operating_margin")
        if op_margin and op_margin.history and len(op_margin.history) >= 2:
            latest, prior = op_margin.history[0]["value"], op_margin.history[1]["value"]
            if latest is not None and prior is not None and latest < prior - 0.02:
                queries.append(
                    {"q": f"{name} gross margin decline pricing competition input costs",
                     "theme": "margin", "because": "operating margin compressed year over year"}
                )

    accel = growth.value("growth_acceleration") if growth else None
    if accel is not None and accel < -0.05:
        queries.append(
            {"q": f"{name} slowing growth saturation customer churn", "theme": "deceleration",
             "because": "growth decelerated materially"}
        )

    peers_block = state.get("peers")
    if peers_block is not None:
        pe = peers_block.metrics.get("pe")
        if pe and pe.peer_percentile is not None and pe.peer_percentile > 0.8:
            queries.append(
                {"q": f"{name} valuation premium growth expectations investor", "theme": "valuation",
                 "because": "the shares trade at a premium to peers"}
            )

    return queries


def recency_weight(published: date | None, today: date | None = None) -> float:
    """Halve relevance every 180 days. Undated items sit at the half-life."""
    if published is None:
        return 0.5
    today = today or date.today()
    age = max((today - published).days, 0)
    return 0.5 ** (age / HALF_LIFE_DAYS)


@node("news_rag", optional=True)
async def news_rag(state: dict) -> dict:
    f = Fundamentals.from_dict(state["facts"])
    ticker = f.ticker
    usage = usage_from(state)
    router = get_router()
    warnings: list[str] = []

    queries = build_queries(state, f)
    hits: dict[str, dict] = {}
    queries_issued = 0
    indexed_now = False

    async with SessionLocal() as db:
        available = await count_for(db, ticker)
        if available == 0:
            # Nothing indexed yet: build the corpus on demand so a ticker nobody has
            # looked at before still gets evidence on its first run.
            try:
                report = await index_ticker(db, ticker, usage=usage)
                indexed_now = True
                available = report.get("chunks", 0)
                log.info("indexed %s on demand: %s", ticker, report)
            except Exception as exc:
                log.warning("on-demand indexing failed for %s: %s", ticker, exc)
                warnings.append(
                    "Source documents for this company could not be retrieved, so the "
                    "memo is written from the computed figures alone and carries no "
                    "qualitative citations."
                )

        if available:
            since = date.today() - timedelta(days=730)
            for spec in queries:
                try:
                    vec = await embed_query(spec["q"], usage)
                    rows = await search(db, ticker=ticker, embedding=vec, k=K_PER_QUERY, since=since)
                except Exception as exc:
                    log.warning("retrieval failed for %r: %s", spec["q"], exc)
                    continue
                queries_issued += 1
                for row in rows:
                    cid = row["chunk_id"]
                    weighted = float(row["score"]) * recency_weight(row.get("published"))
                    existing = hits.get(cid)
                    if existing is None or weighted > existing["weighted"]:
                        hits[cid] = {
                            **row,
                            "weighted": weighted,
                            "cosine": float(row["score"]),
                            "query": spec["q"],
                            "theme": spec["theme"],
                            "because": spec.get("because"),
                        }
        elif not warnings:
            warnings.append(
                "No source documents are indexed for this company, so the memo is "
                "written from the computed figures alone."
            )

    ranked = sorted(hits.values(), key=lambda h: h["weighted"], reverse=True)[
        : settings.max_evidence_chunks
    ]

    evidence = [
        Evidence(
            label=f"S{i}",
            chunk_id=h["chunk_id"],
            ticker=ticker,
            source_type=h["source_type"],
            section=h.get("section"),
            title=h.get("title"),
            url=h.get("url"),
            published=h["published"].isoformat() if isinstance(h.get("published"), date) else h.get("published"),
            text=h["text"],
            relevance=round(h["weighted"], 4),
            query=h.get("query"),
        )
        for i, h in enumerate(ranked, start=1)
    ]

    sentiment, rationale, themes = await _judge_sentiment(evidence, f, usage, router)

    stats = {
        "queries_issued": queries_issued,
        "queries": [{"q": q["q"], "theme": q["theme"], "conditional": "because" in q} for q in queries],
        "conditional_queries": [q for q in queries if "because" in q],
        "candidates": len(hits),
        "selected": len(evidence),
        "indexed_on_demand": indexed_now,
        "corpus_size": available,
        "sentiment_rationale": rationale,
        "themes": themes,
        "by_source": _count_sources(evidence),
    }

    return {
        "evidence": evidence,
        "sentiment_score": sentiment,
        "retrieval_stats": stats,
        "cost": usage.as_dict(),
        "warnings": warnings,
    }


def _count_sources(evidence: list[Evidence]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in evidence:
        out[e.source_type] = out.get(e.source_type, 0) + 1
    return out


async def _judge_sentiment(
    evidence: list[Evidence], f: Fundamentals, usage, router
) -> tuple[float, str, list[str]]:
    if not evidence:
        return 0.0, "No source documents were available to judge.", []

    body = "\n\n".join(
        wrap_untrusted(e.label, f"{e.section or e.source_type}: {e.text[:900]}")
        for e in evidence[:12]
    )
    result = await router.json_call(
        "rag",
        system=SENTIMENT_SYSTEM,
        user=f"Company: {f.name} ({f.ticker})\n\nDocuments:\n{body}",
        usage=usage,
        label="sentiment",
        fallback={"sentiment": 0.0, "rationale": "Sentiment scoring was unavailable.", "themes": []},
        max_tokens=1000,
    )

    try:
        value = float(result.get("sentiment", 0.0))
    except (TypeError, ValueError):
        value = 0.0
    value = max(-1.0, min(1.0, value))
    themes = [t for t in (result.get("themes") or []) if isinstance(t, str)][:6]
    return value, str(result.get("rationale", ""))[:400], themes
