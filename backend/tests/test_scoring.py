"""The rubric decides the rating. These tests pin that behaviour down.

If a change here starts letting the language model influence the recommendation, or lets
a missing dimension quietly drag a score toward SELL, one of these fails.
"""

from __future__ import annotations

import pytest

from src.analytics import scoring as sc


class TestInterpolation:
    ANCHORS = [(0.0, 0.0), (10.0, 5.0), (20.0, 10.0)]

    def test_exact_anchor(self):
        assert sc.interpolate(10.0, self.ANCHORS) == 5.0

    def test_midpoint_is_linear(self):
        assert sc.interpolate(5.0, self.ANCHORS) == 2.5
        assert sc.interpolate(15.0, self.ANCHORS) == 7.5

    def test_clamps_at_both_ends(self):
        assert sc.interpolate(-100.0, self.ANCHORS) == 0.0
        assert sc.interpolate(1e9, self.ANCHORS) == 10.0

    def test_is_monotonic_over_an_ascending_table(self):
        prev = -1.0
        for x in range(0, 21):
            cur = sc.interpolate(float(x), self.ANCHORS)
            assert cur >= prev
            prev = cur


class TestMetricScoring:
    def test_none_in_none_out(self):
        assert sc.score_metric("roic", None) is None

    def test_unknown_metric_scores_nothing(self):
        assert sc.score_metric("not_a_metric", 1.0) is None

    def test_higher_is_better_metrics_slope_up(self):
        assert sc.score_metric("roic", 0.30) > sc.score_metric("roic", 0.05)
        assert sc.score_metric("rev_yoy", 0.25) > sc.score_metric("rev_yoy", 0.02)
        assert sc.score_metric("fcf_yield", 0.10) > sc.score_metric("fcf_yield", 0.01)

    def test_lower_is_better_multiples_slope_down(self):
        assert sc.score_metric("pe", 10.0) > sc.score_metric("pe", 40.0)
        assert sc.score_metric("ev_ebitda", 6.0) > sc.score_metric("ev_ebitda", 25.0)
        assert sc.score_metric("peg", 0.8) > sc.score_metric("peg", 3.0)

    def test_net_cash_scores_above_moderate_leverage(self):
        assert sc.score_metric("net_debt_ebitda", -1.0) > sc.score_metric("net_debt_ebitda", 2.0)

    def test_leverage_score_falls_as_debt_rises(self):
        chain = [sc.score_metric("net_debt_ebitda", x) for x in (0.0, 1.0, 2.0, 4.0, 6.0)]
        assert chain == sorted(chain, reverse=True)

    def test_every_scoreable_metric_stays_inside_the_scale(self):
        for name in sc.ANCHORS:
            for probe in (-1e6, -1.0, 0.0, 0.5, 5.0, 1e6):
                s = sc.score_metric(name, probe)
                assert s is None or 0.0 <= s <= 10.0, (name, probe, s)


class TestDimensionScoring:
    def test_weighted_mean_of_available_metrics(self):
        # Only two of the profitability metrics are present; weights 1.4 and 1.2.
        score, detail = sc.score_dimension("profitability", {"roic": 0.20, "operating_margin": 0.28})
        expected = (8.0 * 1.4 + 8.0 * 1.2) / (1.4 + 1.2)
        assert score == pytest.approx(expected, abs=1e-3)
        assert detail["roic"]["score"] == pytest.approx(8.0)

    def test_absent_metrics_do_not_count_as_zero(self):
        with_gaps, _ = sc.score_dimension("profitability", {"roic": 0.20})
        assert with_gaps == pytest.approx(8.0, abs=1e-3)

    def test_dimension_with_no_data_scores_none(self):
        score, detail = sc.score_dimension("profitability", {})
        assert score is None
        assert all(v["score"] is None for v in detail.values())

    def test_detail_records_the_raw_value_for_provenance(self):
        _, detail = sc.score_dimension("growth", {"rev_yoy": 0.123})
        assert detail["rev_yoy"]["value"] == 0.123


class TestSentiment:
    def test_maps_the_full_range(self):
        assert sc.score_sentiment(-1.0) == 0.0
        assert sc.score_sentiment(0.0) == 5.0
        assert sc.score_sentiment(1.0) == 10.0

    def test_clamps_out_of_range_input(self):
        assert sc.score_sentiment(-5.0) == 0.0
        assert sc.score_sentiment(5.0) == 10.0

    def test_none_passes_through(self):
        assert sc.score_sentiment(None) is None


class TestWeightNormalisation:
    ALL = set(sc.WEIGHTS)

    def test_defaults_sum_to_one(self):
        w = sc.normalise_weights(None, self.ALL)
        assert sum(w.values()) == pytest.approx(1.0)
        assert w["profitability"] == pytest.approx(0.25)

    def test_dropping_a_dimension_renormalises_the_rest(self):
        w = sc.normalise_weights(None, self.ALL - {"sentiment"})
        assert "sentiment" not in w
        assert sum(w.values()) == pytest.approx(1.0)
        # 0.25 / 0.90
        assert w["profitability"] == pytest.approx(0.277778, abs=1e-5)

    def test_dropping_two_dimensions(self):
        w = sc.normalise_weights(None, {"profitability", "growth", "financial_health"})
        assert sum(w.values()) == pytest.approx(1.0)
        assert set(w) == {"profitability", "growth", "financial_health"}

    def test_user_weights_are_honoured_and_renormalised(self):
        w = sc.normalise_weights({"growth": 0.6, "profitability": 0.4}, self.ALL)
        assert sum(w.values()) == pytest.approx(1.0)
        # growth 0.6 against a total of 0.6+0.4+0.20+0.20+0.10 = 1.5
        assert w["growth"] == pytest.approx(0.4, abs=1e-5)

    def test_a_zero_weight_removes_a_dimension(self):
        w = sc.normalise_weights({"sentiment": 0.0}, self.ALL)
        assert "sentiment" not in w
        assert sum(w.values()) == pytest.approx(1.0)

    def test_unknown_and_malformed_weights_are_ignored(self):
        w = sc.normalise_weights({"vibes": 5.0, "growth": "lots", "profitability": -2.0}, self.ALL)
        assert "vibes" not in w
        assert w["growth"] == pytest.approx(0.25)
        assert sum(w.values()) == pytest.approx(1.0)

    def test_no_available_dimensions_yields_no_weights(self):
        assert sc.normalise_weights(None, set()) == {}


class TestRatingBands:
    @pytest.mark.parametrize(
        "total,expected",
        [
            (10.0, "BUY"),
            (7.51, "BUY"),
            (7.5, "BUY"),      # inclusive lower edge
            (7.49, "HOLD"),
            (6.0, "HOLD"),
            (5.0, "HOLD"),     # inclusive lower edge
            (4.99, "SELL"),
            (0.0, "SELL"),
        ],
    )
    def test_boundaries_are_exact(self, total, expected):
        assert sc.rating_for(total) == expected

    def test_no_score_defaults_to_hold(self):
        assert sc.rating_for(None) == "HOLD"

    def test_distance_to_edge(self):
        assert sc.distance_to_band_edge(7.5) == 0.0
        assert sc.distance_to_band_edge(5.0) == 0.0
        assert sc.distance_to_band_edge(6.25) == pytest.approx(1.25)
        assert sc.distance_to_band_edge(9.0) == pytest.approx(1.5)


class TestConviction:
    def test_high_needs_clear_separation_and_full_data(self):
        assert sc.conviction_for(9.0, coverage=0.95, dimensions_used=5) == "high"

    def test_sitting_on_a_boundary_lowers_conviction(self):
        assert sc.conviction_for(7.5, coverage=0.95, dimensions_used=5) == "medium"

    def test_perfect_data_cannot_buy_conviction_near_a_band_edge(self):
        """A rating 0.46 from flipping is not one to hold high conviction in, however
        complete the data behind it is."""
        assert sc.conviction_for(7.04, coverage=1.0, dimensions_used=5) == "medium"
        assert sc.conviction_for(7.5 - 0.8, coverage=1.0, dimensions_used=5) == "high"

    def test_thin_data_lowers_conviction(self):
        assert sc.conviction_for(9.0, coverage=0.4, dimensions_used=3) == "low"

    def test_no_total_is_low(self):
        assert sc.conviction_for(None, coverage=1.0, dimensions_used=5) == "low"


class TestScorecard:
    FULL = {
        "profitability": 8.0,
        "financial_health": 7.0,
        "growth": 8.0,
        "valuation": 5.0,
        "sentiment": 6.0,
    }

    def test_composite_is_the_weighted_sum(self):
        card = sc.build_scorecard(dimension_scores=self.FULL, coverage=1.0)
        # .25(8) + .20(7) + .25(8) + .20(5) + .10(6) = 2+1.4+2+1+0.6 = 7.0
        assert card["total"] == pytest.approx(7.0)
        assert card["rating"] == "HOLD"

    def test_missing_dimension_is_reported_and_reweighted(self):
        scores = dict(self.FULL, sentiment=None)
        card = sc.build_scorecard(dimension_scores=scores, coverage=0.9)
        assert card["dimensions_unavailable"] == ["sentiment"]
        assert sum(card["weights_applied"].values()) == pytest.approx(1.0)
        # (2 + 1.4 + 2 + 1) / 0.9 = 7.111
        assert card["total"] == pytest.approx(7.111, abs=1e-3)

    def test_a_missing_dimension_does_not_drag_the_score_down(self):
        """The bug this guards against: treating an unavailable dimension as a zero."""
        with_all = sc.build_scorecard(dimension_scores=self.FULL)["total"]
        naive_zero = sum(
            v * sc.WEIGHTS[k] for k, v in dict(self.FULL, sentiment=0.0).items()
        )
        renormalised = sc.build_scorecard(
            dimension_scores=dict(self.FULL, sentiment=None)
        )["total"]
        assert renormalised > naive_zero
        assert renormalised >= with_all - 0.2

    def test_all_dimensions_missing(self):
        card = sc.build_scorecard(dimension_scores=dict.fromkeys(sc.WEIGHTS))
        assert card["total"] is None
        assert card["rating"] == "HOLD"
        assert card["conviction"] == "low"
        assert card["weights_applied"] == {}

    def test_user_weights_shift_the_rating(self):
        scores = dict(self.FULL, growth=10.0, valuation=1.0)
        balanced = sc.build_scorecard(dimension_scores=scores)["total"]
        growth_tilted = sc.build_scorecard(
            dimension_scores=scores, user_weights={"growth": 0.7, "valuation": 0.05}
        )["total"]
        assert growth_tilted > balanced

    def test_scorecard_carries_its_own_thresholds_for_the_ui(self):
        card = sc.build_scorecard(dimension_scores=self.FULL)
        assert card["thresholds"] == {"buy": 7.5, "hold": 5.0}
        assert card["distance_to_edge"] is not None

    def test_rating_is_consistent_with_the_total_at_every_probe(self):
        for probe in [x / 4 for x in range(0, 41)]:
            card = sc.build_scorecard(dimension_scores=dict.fromkeys(sc.WEIGHTS, probe))
            assert card["total"] == pytest.approx(probe, abs=1e-6)
            assert card["rating"] == sc.rating_for(probe)


class TestPriceTarget:
    def test_band_is_symmetric_around_the_midpoint(self):
        pt = sc.price_target(
            peer_median_ev_ebitda=10.0, company_ebitda=500.0,
            total_debt=1_000.0, cash=200.0, shares=100.0,
        )
        # EV 5,000 ; equity 5,000 - 1,000 + 200 = 4,200 ; /100 = 42.00
        assert pt["mid"] == pytest.approx(42.0)
        assert pt["high"] - pt["mid"] == pytest.approx(pt["mid"] - pt["low"], abs=0.01)

    def test_method_is_always_labelled(self):
        pt = sc.price_target(
            peer_median_ev_ebitda=None, company_ebitda=None,
            total_debt=None, cash=None, shares=None,
        )
        assert "EV/EBITDA" in pt["method"]

    def test_inputs_are_recorded_for_audit(self):
        pt = sc.price_target(
            peer_median_ev_ebitda=10.0, company_ebitda=500.0,
            total_debt=1_000.0, cash=200.0, shares=100.0,
        )
        assert pt["inputs"]["company_ebitda"] == 500.0
        assert pt["inputs"]["band_pct"] == 0.15
