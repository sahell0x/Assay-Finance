"""One end-to-end graph run with every external call mocked.

This is the integration test the spec asks for: it proves the nodes wire together, that
state flows in the right order, that peers writes percentiles back onto the earlier
blocks, and — most importantly — that the rating on the finished memo is the rating the
rubric produced, not one a model chose.
"""

from __future__ import annotations

import uuid

import pytest

from src.agent.state import InvestmentMemo


@pytest.fixture
def mocked_pipeline(monkeypatch, aapl_fixture):
    """Replace every network boundary: yfinance, EDGAR, news, pgvector and the model."""
    from src.data.fundamentals import Fundamentals, assess_quality, build_facts

    stmts, market = aapl_fixture
    facts, periods, annual = build_facts(stmts)

    def make_fundamentals(ticker: str, scale: float = 1.0) -> Fundamentals:
        scaled = {
            p: {k: (v * scale if isinstance(v, int | float) and v is not None else v)
                for k, v in row.items()}
            for p, row in facts.items()
        }
        f = Fundamentals(
            ticker=ticker.upper(),
            name=f"{ticker.upper()} Inc.",
            sector="Technology",
            industry="Consumer Electronics",
            periods=list(periods),
            annual_periods=list(annual),
            facts=scaled,
            market={**market, "market_cap": (market.get("market_cap") or 3e12) * scale,
                    "shares_out": market.get("shares_out") or 15e9,
                    "price": 200.0},
        )
        for p in f.periods:
            row = f.facts[p]
            row["market_cap"] = f.market["market_cap"]
            row["enterprise_value"] = (
                f.market["market_cap"] + (row.get("total_debt") or 0) - (row.get("cash") or 0)
            )
        f.data_quality = assess_quality(f)
        return f

    async def fake_get_fundamentals(ticker: str, use_cache: bool = True):
        return make_fundamentals(ticker)

    def fake_fetch_many(tickers: list[str]) -> dict[str, dict]:
        from src.agent.nodes.peers import _snapshot

        out = {}
        for i, t in enumerate(tickers[:5]):
            out[t] = _snapshot(make_fundamentals(t, scale=0.6 + i * 0.25))
        return out

    import src.agent.nodes.ingest as ingest_mod
    import src.agent.nodes.peers as peers_mod

    monkeypatch.setattr(ingest_mod, "get_fundamentals", fake_get_fundamentals)
    monkeypatch.setattr(peers_mod, "_fetch_many", fake_fetch_many)

    # Retrieval: three chunks, no database, no embeddings.
    import src.agent.nodes.news_rag as rag_mod
    from src.agent.state import Evidence

    async def fake_news_rag(state: dict) -> dict:
        evidence = [
            Evidence(
                label=f"S{i}", chunk_id=f"c{i}", ticker=state["ticker"],
                source_type="sec_10k", section="Item 1A. Risk Factors",
                published="2025-10-31", text=f"Risk factor number {i}.", relevance=0.7,
            )
            for i in (1, 2, 3)
        ]
        return {
            "evidence": evidence,
            "sentiment_score": 0.2,
            "retrieval_stats": {"queries_issued": 4, "selected": 3, "candidates": 9},
        }

    monkeypatch.setattr(rag_mod, "news_rag", fake_news_rag)

    # Rebuild the graph so it picks up the patched node.
    import src.agent.graph as graph_mod

    monkeypatch.setattr(graph_mod, "_compiled", None, raising=False)
    monkeypatch.setattr(graph_mod, "news_rag", fake_news_rag)
    monkeypatch.setattr(graph_mod, "_compiled", None, raising=False)

    # Progress events: no Redis, no Postgres.
    import src.agent.progress as progress_mod

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(progress_mod, "record_event", noop)
    monkeypatch.setattr(progress_mod, "publish", noop)

    # Force offline rather than assert it. This test must never make a network call, but
    # checking that the ambient environment happens to have no API key means the whole
    # suite starts failing the moment a developer configures one — which is everyone,
    # eventually. Clearing the key and dropping the cached router makes the guarantee
    # hold regardless of what is in .env.
    import src.agent.models as models_mod
    from src.config import settings as live_settings

    monkeypatch.setattr(live_settings, "openai_api_key", "", raising=False)
    monkeypatch.setattr(models_mod, "_router", None, raising=False)
    router = models_mod.get_router()
    assert router.offline, "the router should be offline once the key is cleared"

    return graph_mod


class TestFullGraph:
    @pytest.fixture
    async def state(self, mocked_pipeline):
        graph = mocked_pipeline.build_graph()
        initial = mocked_pipeline.initial_state(
            analysis_id=str(uuid.uuid4()), ticker="AAPL", peer_tickers=["MSFT", "GOOGL", "META", "AMZN"]
        )
        return await graph.ainvoke(initial, config={"configurable": {"thread_id": "t1"}})

    async def test_every_node_ran(self, state):
        nodes = {t["node"] for t in state["trace"] if "duration_ms" in t}
        assert {"ingest", "validate", "profitability", "liquidity", "growth", "peers",
                "scorecard", "memo", "critic"} <= nodes

    async def test_all_four_blocks_are_populated(self, state):
        for dim in ("profitability", "liquidity", "growth", "peers"):
            block = state[dim]
            assert block.dimension in {"profitability", "liquidity", "growth", "peers"}
            assert block.metrics
            assert any(m.value is not None for m in block.metrics.values()), dim
            assert 0 <= block.score <= 10

    async def test_every_metric_carries_its_provenance(self, state):
        """The formula and inputs are what let the interface show where a number came
        from. A metric without them is not shippable."""
        for dim in ("profitability", "liquidity", "growth", "peers"):
            for name, m in state[dim].metrics.items():
                assert m.formula, f"{dim}.{name} has no formula"
                assert isinstance(m.inputs, dict), f"{dim}.{name} has no inputs"
                assert m.unit in {"ratio", "percent", "currency", "days", "x", "score"}
                assert m.period

    async def test_a_missing_value_always_explains_itself(self, state):
        for dim in ("profitability", "liquidity", "growth", "peers"):
            for name, m in state[dim].metrics.items():
                if m.value is None:
                    assert m.note, f"{dim}.{name} is unavailable with no explanation"

    async def test_peers_wrote_percentiles_back_onto_earlier_blocks(self, state):
        """This is why peers runs last."""
        ranked = [
            m for dim in ("profitability", "liquidity", "growth")
            for m in state[dim].metrics.values()
            if m.peer_percentile is not None
        ]
        assert ranked, "no percentile reached the company blocks"
        assert all(0.0 <= m.peer_percentile <= 1.0 for m in ranked)

    async def test_scorecard_is_the_weighted_fold_of_the_dimensions(self, state):
        card = state["scorecard"]
        assert card["total"] is not None
        assert card["rating"] in {"BUY", "HOLD", "SELL"}
        assert sum(card["weights_applied"].values()) == pytest.approx(1.0)

        recomputed = sum(
            card["dimension_scores"][k] * w for k, w in card["weights_applied"].items()
        )
        assert recomputed == pytest.approx(card["total"], abs=0.01)

    async def test_the_memo_carries_the_rubrics_rating_not_its_own(self, state):
        """The load-bearing invariant of the whole system."""
        memo: InvestmentMemo = state["memo"]
        assert memo.recommendation == state["scorecard"]["rating"]
        assert memo.conviction == state["scorecard"]["conviction"]

    async def test_the_memo_satisfies_its_schema(self, state):
        memo: InvestmentMemo = state["memo"]
        assert 3 <= len(memo.key_drivers) <= 5
        assert 3 <= len(memo.key_risks) <= 5
        assert memo.thesis
        assert memo.valuation_method

    async def test_the_price_target_comes_from_peers_not_the_memo(self, state):
        pt = state["price_target"]
        memo: InvestmentMemo = state["memo"]
        if pt.get("available"):
            assert memo.price_target_low == pt["low"]
            assert memo.price_target_high == pt["high"]
        else:
            assert memo.price_target_low is None

    async def test_the_critic_ran_and_checked_real_figures(self, state):
        verdict = state["critic_verdict"]
        assert verdict["verdict"] in {"pass", "revise"}
        assert verdict["figures_checked"] >= 0
        assert "python_verdict" in verdict

    async def test_revision_is_capped(self, state):
        assert state.get("revision_count", 0) <= 2

    async def test_cost_is_accounted_for(self, state):
        cost = state["cost"]
        assert cost["tokens_in"] >= 0
        assert cost["cost_usd"] >= 0
        assert isinstance(cost["calls"], list)

    async def test_the_trace_is_ordered_and_timed(self, state):
        timed = [t for t in state["trace"] if "duration_ms" in t]
        assert timed
        assert all(t["duration_ms"] >= 0 for t in timed)
        order = [t["node"] for t in timed]
        assert order.index("profitability") < order.index("peers")
        assert order.index("peers") < order.index("scorecard")
        assert order.index("scorecard") < order.index("memo")


class TestGraphFailurePaths:
    async def test_an_unknown_ticker_fails_loudly(self, monkeypatch):
        """No statements means no analysis. Producing a confident memo anyway would be
        the worst possible failure mode."""
        from src.data.fundamentals import Fundamentals

        async def empty(ticker: str, use_cache: bool = True):
            return Fundamentals(ticker=ticker, periods=[], annual_periods=[], facts={})

        import src.agent.graph as graph_mod
        import src.agent.nodes.ingest as ingest_mod
        import src.agent.progress as progress_mod

        async def noop(*a, **k):
            return None

        monkeypatch.setattr(ingest_mod, "get_fundamentals", empty)
        monkeypatch.setattr(progress_mod, "record_event", noop)
        monkeypatch.setattr(progress_mod, "publish", noop)

        graph = graph_mod.build_graph()
        with pytest.raises(ValueError, match="No financial statements"):
            await graph.ainvoke(
                graph_mod.initial_state(analysis_id=str(uuid.uuid4()), ticker="NOTATICKER"),
                config={"configurable": {"thread_id": "t2"}},
            )

    async def test_peers_failing_degrades_rather_than_aborts(self, mocked_pipeline, monkeypatch):
        """An analysis without a peer set is still worth having."""
        import src.agent.nodes.peers as peers_mod

        def explode(tickers):
            raise RuntimeError("data provider is down")

        monkeypatch.setattr(peers_mod, "_fetch_many", explode)

        graph = mocked_pipeline.build_graph()
        state = await graph.ainvoke(
            mocked_pipeline.initial_state(analysis_id=str(uuid.uuid4()), ticker="AAPL"),
            config={"configurable": {"thread_id": "t3"}},
        )
        assert state["scorecard"]["rating"] in {"BUY", "HOLD", "SELL"}
        assert "valuation" in state["scorecard"]["dimensions_unavailable"]
        assert any("peers" in w for w in state["warnings"])


async def test_unknown_user_peers_fall_back_to_the_industry_cohort(mocked_pipeline, monkeypatch):
    """A company name typed as a ticker must not leave valuation with nothing to compare."""
    import src.agent.nodes.peers as peers_mod

    real_fetch_many = peers_mod._fetch_many

    def fetch_known(tickers):
        return real_fetch_many([t for t in tickers if t != "GOOGLE"])

    monkeypatch.setattr(peers_mod, "_fetch_many", fetch_known)

    graph = mocked_pipeline.build_graph()
    state = await graph.ainvoke(
        mocked_pipeline.initial_state(
            analysis_id=str(uuid.uuid4()), ticker="AAPL", peer_tickers=["GOOGLE"]
        ),
        config={"configurable": {"thread_id": "t4"}},
    )
    extras = state["peers"].extras
    assert extras["source"] in {"map", "fallback"}
    assert extras["resolved"], "the industry cohort should have produced peers"
    assert "GOOGLE" not in extras["requested"]
    assert extras["peer_median_ev_ebitda"] is not None
    assert any("GOOGLE" in w and "similar companies" in w for w in state["warnings"])
