"""Chunking, peer resolution, recency decay, and the retrieval query builder."""

from __future__ import annotations

from datetime import date

import pytest

from src.agent.nodes.news_rag import build_queries, recency_weight
from src.agent.state import MetricBlock, metric
from src.analytics.trends import NOT_MEANINGFUL_ABOVE, trimmed_median
from src.data.fundamentals import Fundamentals
from src.data.news.chunk import (
    CHUNK_SIZE,
    chunk_risk_factors,
    chunk_text,
    make_chunk_id,
    split_risk_factors,
)
from src.data.peers import groups, resolve_peers


class TestChunking:
    def test_chunks_respect_the_size_budget(self):
        text = "\n\n".join(f"Sentence number {i}. " * 12 for i in range(40))
        chunks = chunk_text(text, ticker="AAPL", source_type="sec_10k")
        assert chunks
        assert all(len(c.text) <= CHUNK_SIZE * 1.7 for c in chunks)

    def test_chunks_overlap_so_a_claim_split_across_a_boundary_survives(self):
        text = " ".join(f"word{i}" for i in range(600))
        chunks = chunk_text(text, ticker="AAPL", source_type="sec_10k")
        assert len(chunks) >= 2
        tail = chunks[0].text[-100:].split()
        head = chunks[1].text[:200].split()
        assert set(tail) & set(head), "consecutive chunks share no text"

    def test_ids_are_content_addressed_and_therefore_idempotent(self):
        a = make_chunk_id("AAPL", "sec_10k", "Item 1A", "http://x", "body")
        b = make_chunk_id("AAPL", "sec_10k", "Item 1A", "http://x", "body")
        c = make_chunk_id("AAPL", "sec_10k", "Item 1A", "http://x", "different")
        assert a == b
        assert a != c

    def test_reindexing_the_same_document_produces_the_same_ids(self):
        text = "Paragraph one is here.\n\nParagraph two follows on.\n\n" + "Filler. " * 200
        first = chunk_text(text, ticker="AAPL", source_type="sec_10k")
        second = chunk_text(text, ticker="AAPL", source_type="sec_10k")
        assert [c.chunk_id for c in first] == [c.chunk_id for c in second]

    def test_empty_and_tiny_input(self):
        assert chunk_text("", ticker="AAPL", source_type="rss") == []
        assert chunk_text("Too short.", ticker="AAPL", source_type="rss") == []

    def test_metadata_is_carried_onto_every_chunk(self):
        chunks = chunk_text(
            "Body text. " * 200, ticker="AAPL", source_type="sec_10k",
            section="Item 7", title="AAPL 10-K", url="http://sec.gov/x", published="2025-10-31",
        )
        assert chunks
        for c in chunks:
            assert c.ticker == "AAPL"
            assert c.section == "Item 7"
            assert c.published == "2025-10-31"
            assert c.url == "http://sec.gov/x"


class TestRiskFactorSplitting:
    HEADED = (
        "Our business depends on a limited number of suppliers\n\n"
        + "We rely on a small group of suppliers. " * 12
        + "\n\nChanges in regulation could materially affect our operations\n\n"
        + "New rules may impose significant costs. " * 12
        + "\n\nWe face intense competition across all of our markets\n\n"
        + "Competitors are numerous and well funded. " * 12
    )

    def test_each_named_risk_becomes_its_own_unit(self):
        risks = split_risk_factors(self.HEADED)
        assert len(risks) == 3
        assert all(header for header, _ in risks)

    def test_headers_reach_the_chunk_section_label(self):
        chunks = chunk_risk_factors(self.HEADED, ticker="AAPL", source_type="sec_10k")
        assert len(chunks) == 3
        assert all(c.section.startswith("Item 1A. Risk Factors — ") for c in chunks)

    def test_header_with_no_blank_line_before_the_body(self):
        text = self.HEADED.replace("suppliers\n\nWe rely", "suppliers\nWe rely")
        assert len(split_risk_factors(text)) == 3

    def test_continuous_prose_falls_back_to_one_unit(self):
        prose = "Risk prose that never uses a header. " * 60
        risks = split_risk_factors(prose)
        assert len(risks) == 1
        assert risks[0][0] == ""

    def test_a_long_single_risk_is_sub_chunked(self):
        text = (
            "A single very long risk factor about supply concentration\n\n"
            + "Detail sentence here. " * 400
        )
        chunks = chunk_risk_factors(text, ticker="AAPL", source_type="sec_10k")
        assert len(chunks) > 1


class TestRecencyDecay:
    TODAY = date(2026, 9, 11)

    def test_half_life_is_180_days(self):
        assert recency_weight(date(2026, 3, 15), self.TODAY) == pytest.approx(0.5, abs=0.02)

    def test_today_is_undiscounted(self):
        assert recency_weight(self.TODAY, self.TODAY) == 1.0

    def test_decay_is_monotonic(self):
        weights = [
            recency_weight(date(2026, 9, 11) - __import__("datetime").timedelta(days=d), self.TODAY)
            for d in (0, 90, 180, 365, 730)
        ]
        assert weights == sorted(weights, reverse=True)

    def test_undated_items_sit_at_the_half_life(self):
        assert recency_weight(None, self.TODAY) == 0.5

    def test_a_future_date_is_not_amplified(self):
        assert recency_weight(date(2027, 1, 1), self.TODAY) == 1.0


class TestPeerResolution:
    def test_user_supplied_peers_win(self):
        peers, source = resolve_peers("AAPL", sector="Technology", supplied=["msft", "googl"])
        assert source == "user"
        assert peers == ["MSFT", "GOOGL"]

    def test_the_target_is_never_its_own_peer(self):
        peers, _ = resolve_peers("AAPL", supplied=["AAPL", "MSFT"])
        assert "AAPL" not in peers

    def test_industry_match_beats_sector(self):
        peers, source = resolve_peers("JPM", sector="Financial Services", industry="Banks - Diversified")
        assert source == "map"
        assert "BAC" in peers

    def test_unknown_industry_falls_back_and_says_so(self):
        peers, source = resolve_peers("XYZ", sector="Nonsense", industry="Nothing")
        assert source == "fallback"
        assert peers

    def test_cohort_is_capped(self):
        peers, _ = resolve_peers("NVDA", industry="Semiconductors", limit=4)
        assert len(peers) == 4

    def test_duplicates_are_removed(self):
        peers, _ = resolve_peers("AAPL", supplied=["MSFT", "msft", "GOOGL"])
        assert peers == ["MSFT", "GOOGL"]

    def test_every_group_is_well_formed(self):
        for name, group in groups().items():
            assert group.get("match"), f"{name} has no match terms"
            assert len(group.get("tickers", [])) >= 8, f"{name} has too few tickers"


class TestNotMeaningfulMultiples:
    def test_a_near_zero_ebitda_peer_does_not_set_the_median(self):
        # Two sane multiples and four artefacts; the plain median would be 138x.
        vals = [16.9, 40.8, 138.2, 285.6, 479.9, 2913.1]
        med, excluded = trimmed_median(vals, cap=NOT_MEANINGFUL_ABOVE["ev_ebitda"])
        assert med == pytest.approx(28.85, abs=0.1)
        assert len(excluded) == 4

    def test_a_sane_cohort_is_left_alone(self):
        vals = [8.2, 9.5, 11.0, 12.4, 13.1, 15.9]
        med, excluded = trimmed_median(vals, cap=NOT_MEANINGFUL_ABOVE["ev_ebitda"])
        assert excluded == []
        assert med == pytest.approx(11.7)

    def test_an_entirely_non_meaningful_cohort_yields_no_median(self):
        med, excluded = trimmed_median([120.0, 300.0, 900.0], cap=50.0)
        assert med is None
        assert len(excluded) == 3

    def test_small_samples_are_not_trimmed(self):
        med, excluded = trimmed_median([11.0, 13.0], cap=50.0)
        assert med == 12.0
        assert excluded == []

    def test_empty_input(self):
        assert trimmed_median([], cap=50.0) == (None, [])


class TestConditionalQueries:
    """Retrieval that is conditioned on what the numbers found is the core feature."""

    def _state(self, **blocks) -> dict:
        return {"facts": {}, **blocks}

    def _block(self, dimension, values: dict) -> MetricBlock:
        return MetricBlock(
            dimension=dimension,
            metrics={
                k: metric(k, v, unit="x", period="TTM", formula="f", inputs={})
                for k, v in values.items()
            },
        )

    @property
    def fundamentals(self) -> Fundamentals:
        return Fundamentals(ticker="XYZ", name="XYZ Corp")

    def test_baseline_queries_are_always_issued(self):
        qs = build_queries(self._state(), self.fundamentals)
        themes = {q["theme"] for q in qs}
        assert {"competition", "guidance", "regulatory", "costs"} <= themes
        assert all("because" not in q for q in qs)

    def test_falling_revenue_triggers_a_demand_query(self):
        state = self._state(growth=self._block("growth", {"rev_yoy": -0.08}))
        qs = build_queries(state, self.fundamentals)
        demand = [q for q in qs if q["theme"] == "demand"]
        assert demand and demand[0]["because"]

    def test_growing_revenue_does_not(self):
        state = self._state(growth=self._block("growth", {"rev_yoy": 0.15}))
        assert not [q for q in build_queries(state, self.fundamentals) if q["theme"] == "demand"]

    def test_high_leverage_triggers_a_refinancing_query(self):
        state = self._state(liquidity=self._block("liquidity", {"net_debt_ebitda": 4.2}))
        qs = build_queries(state, self.fundamentals)
        assert [q for q in qs if q["theme"] == "leverage"]

    def test_leverage_below_the_threshold_does_not(self):
        state = self._state(liquidity=self._block("liquidity", {"net_debt_ebitda": 1.1}))
        assert not [q for q in build_queries(state, self.fundamentals) if q["theme"] == "leverage"]

    def test_thin_interest_coverage_triggers_a_solvency_query(self):
        state = self._state(liquidity=self._block("liquidity", {"interest_coverage": 1.4}))
        assert [q for q in build_queries(state, self.fundamentals) if q["theme"] == "solvency"]

    def test_margin_compression_triggers_a_cost_query(self):
        block = self._block("profitability", {"operating_margin": 0.18})
        block.metrics["operating_margin"].history = [
            {"period": "FY2025", "value": 0.18},
            {"period": "FY2024", "value": 0.25},
        ]
        qs = build_queries(self._state(profitability=block), self.fundamentals)
        assert [q for q in qs if q["theme"] == "margin"]

    def test_a_premium_valuation_triggers_a_valuation_query(self):
        block = self._block("peers", {"pe": 60.0})
        block.metrics["pe"].peer_percentile = 0.95
        qs = build_queries(self._state(peers=block), self.fundamentals)
        assert [q for q in qs if q["theme"] == "valuation"]

    def test_missing_values_never_raise(self):
        state = self._state(
            growth=self._block("growth", {"rev_yoy": None}),
            liquidity=self._block("liquidity", {"net_debt_ebitda": None, "interest_coverage": None}),
        )
        assert len(build_queries(state, self.fundamentals)) == 4
