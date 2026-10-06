"""The scenario engine: re-running the rubric under changed assumptions.

Two things are being pinned down here.

**Recomputation is the same rubric, not a copy of it.** A scenario with no overrides
must reproduce the stored scorecard exactly. If someone adds a dimension, changes an
anchor table or alters the weighting fold and the scenario path drifts from the real
one, the first test in ``TestRecompute`` fails. That invariant is the whole reason the
recompute runs in Python against ``scoring.py`` rather than as a second implementation
in the browser.

**A solved path has to survive being applied.** ``solve_paths`` says "ROIC of 14% makes
this a BUY"; ``TestSolveSelfConsistency`` takes that answer, feeds it back through
``recompute``, and asserts the rating really is BUY. A solver that reports a threshold
its own engine disagrees with is worse than no solver.
"""

from __future__ import annotations

import pytest

from src.analytics import scenario as sn
from src.analytics import scoring as sc

# --------------------------------------------------------------------------- fixtures

# A deliberately mid-table company: every dimension scores and the composite lands in
# the middle of HOLD, well away from either boundary. Values are plausible for a
# large-cap industrial. Used for the recompute and lever tests, where what matters is
# that every dimension is populated.
BASE_METRICS: dict[str, dict[str, float | None]] = {
    "profitability": {
        "gross_margin": 0.42,
        "operating_margin": 0.17,
        "net_margin": 0.12,
        "fcf_margin": 0.11,
        "roe": 0.19,
        "roic": 0.11,
        "roa": 0.08,
    },
    "financial_health": {
        "current_ratio": 1.35,
        "quick_ratio": 0.95,
        "net_debt_ebitda": 1.8,
        "interest_coverage": 9.0,
        "debt_to_equity": 0.72,
        "altman_z": 3.4,
        "fcf_to_debt": 0.31,
    },
    "growth": {
        "rev_yoy": 0.08,
        "rev_cagr_3y": 0.09,
        "rev_cagr_5y": 0.07,
        "eps_growth": 0.11,
        "fcf_cagr_3y": 0.10,
        "growth_acceleration": 0.01,
        "incremental_operating_margin": 0.19,
    },
    "valuation": {
        "pe": 22.0,
        "ev_ebitda": 14.0,
        "ev_sales": 3.1,
        "price_to_book": 4.2,
        "fcf_yield": 0.042,
        "peg": 1.7,
    },
}

# Two companies parked either side of a rating boundary. The solver only has anything
# to say near an edge: no single metric carries more than about a quarter of one
# dimension, so the most a lever can move a composite is a few tenths of a point. A
# company in the middle of HOLD is genuinely two points from BUY and the honest answer
# is that nothing gets there alone — ``test_a_mid_band_company_has_no_single_lever_route``
# pins that down using BASE_METRICS above.
NEAR_BUY_METRICS: dict[str, dict[str, float | None]] = {
    "profitability": {
        "gross_margin": 0.5826,
        "operating_margin": 0.296,
        "net_margin": 0.2292,
        "fcf_margin": 0.2483,
        "roe": 0.2865,
        "roic": 0.2101,
        "roa": 0.1337,
    },
    "financial_health": {
        "current_ratio": 1.7668,
        "quick_ratio": 1.3847,
        "net_debt_ebitda": 0.573,
        "interest_coverage": 18.145,
        "debt_to_equity": 0.3629,
        "altman_z": 5.348,
        "fcf_to_debt": 0.8117,
    },
    "growth": {
        "rev_yoy": 0.1815,
        "rev_cagr_3y": 0.1719,
        "rev_cagr_5y": 0.1528,
        "eps_growth": 0.2006,
        "fcf_cagr_3y": 0.1815,
        "growth_acceleration": 0.0286,
        "incremental_operating_margin": 0.3247,
    },
    "valuation": {
        "pe": 21.945,
        "ev_ebitda": 13.585,
        "ev_sales": 3.762,
        "price_to_book": 4.598,
        "fcf_yield": 0.047,
        "peg": 1.463,
    },
}

NEAR_SELL_METRICS: dict[str, dict[str, float | None]] = {
    "profitability": {
        "gross_margin": 0.459,
        "operating_margin": 0.1283,
        "net_margin": 0.0837,
        "fcf_margin": 0.0783,
        "roe": 0.1418,
        "roic": 0.0972,
        "roa": 0.0607,
    },
    "financial_health": {
        "current_ratio": 1.5525,
        "quick_ratio": 1.053,
        "net_debt_ebitda": 2.0,
        "interest_coverage": 6.21,
        "debt_to_equity": 0.8889,
        "altman_z": 3.51,
        "fcf_to_debt": 0.243,
    },
    "growth": {
        "rev_yoy": 0.0473,
        "rev_cagr_3y": 0.054,
        "rev_cagr_5y": 0.0607,
        "eps_growth": 0.0405,
        "fcf_cagr_3y": 0.0473,
        "growth_acceleration": -0.0068,
        "incremental_operating_margin": 0.1215,
    },
    "valuation": {
        "pe": 15.0,
        "ev_ebitda": 9.0,
        "ev_sales": 1.7,
        "price_to_book": 2.0,
        "fcf_yield": 0.062,
        "peg": 1.6,
    },
}

PRICE_TARGET_INPUTS = {
    "peer_median_ev_ebitda": 15.5,
    "company_ebitda": 28_000_000_000.0,
    "total_debt": 40_000_000_000.0,
    "cash": 22_000_000_000.0,
    "shares": 1_500_000_000.0,
    "band_pct": 0.15,
    "current_price": 240.0,
}


def build_card(
    metrics: dict[str, dict] | None = None,
    *,
    sentiment: float | None = 0.2,
    coverage: float = 0.9,
    user_weights: dict[str, float] | None = None,
    with_price_target: bool = True,
) -> dict:
    """Build a scorecard the way ``nodes/scorecard.py`` does.

    Constructed through the real scoring functions rather than hand-written JSON, so the
    fixture cannot drift from the shape the pipeline actually stores.
    """
    metrics = metrics if metrics is not None else BASE_METRICS
    dimension_scores: dict[str, float | None] = {}
    detail: dict[str, dict] = {}
    for dim in ("profitability", "financial_health", "growth", "valuation"):
        score, dim_detail = sc.score_dimension(dim, metrics.get(dim, {}))
        dimension_scores[dim] = score
        detail[dim] = dim_detail
    dimension_scores["sentiment"] = sc.score_sentiment(sentiment)
    detail["sentiment"] = {"raw_sentiment": sentiment, "evidence_count": 12}

    card = sc.build_scorecard(
        dimension_scores=dimension_scores,
        dimension_detail=detail,
        user_weights=user_weights,
        coverage=coverage,
    )
    if with_price_target:
        card["price_target"] = sc.price_target(
            peer_median_ev_ebitda=PRICE_TARGET_INPUTS["peer_median_ev_ebitda"],
            company_ebitda=PRICE_TARGET_INPUTS["company_ebitda"],
            total_debt=PRICE_TARGET_INPUTS["total_debt"],
            cash=PRICE_TARGET_INPUTS["cash"],
            shares=PRICE_TARGET_INPUTS["shares"],
            current_price=PRICE_TARGET_INPUTS["current_price"],
        )
    else:
        card["price_target"] = {"available": False}
    return card


@pytest.fixture
def card() -> dict:
    """Mid-band HOLD, far from either boundary."""
    return build_card()


@pytest.fixture
def near_buy() -> dict:
    """HOLD at 7.42, a fraction under the 7.5 BUY line."""
    return build_card(NEAR_BUY_METRICS, sentiment=0.45)


@pytest.fixture
def near_sell() -> dict:
    """HOLD at 5.25, a fraction over the 5.0 SELL line."""
    return build_card(NEAR_SELL_METRICS, sentiment=-0.30)


# ------------------------------------------------------------------- namespace safety


class TestMetricNamespace:
    def test_metric_names_are_unique_across_dimensions(self):
        """Overrides are a flat ``{metric: value}`` map, which only works while no two
        dimensions share a metric name. Adding a clashing metric must fail here rather
        than silently apply an override to the wrong dimension."""
        seen: dict[str, str] = {}
        for dim, spec in sc.DIMENSION_METRICS.items():
            for name in spec:
                assert name not in seen, f"{name} is in both {seen.get(name)} and {dim}"
                seen[name] = dim

    def test_every_scored_metric_has_an_anchor_table(self):
        """A metric with no anchors scores None forever and would render a dead slider."""
        for spec in sc.DIMENSION_METRICS.values():
            for name in spec:
                assert sc.anchors_for(name) is not None, f"{name} has no anchor table"


# -------------------------------------------------------------------------- recompute


class TestRecompute:
    def test_no_overrides_reproduces_the_stored_card(self, card):
        """The invariant the whole feature rests on."""
        out = sn.recompute(card)
        assert out["total"] == card["total"]
        assert out["rating"] == card["rating"]
        assert out["conviction"] == card["conviction"]
        assert out["dimension_scores"] == card["dimension_scores"]
        assert out["weights_applied"] == card["weights_applied"]

    def test_improving_a_metric_raises_its_dimension_and_the_total(self, card):
        out = sn.recompute(card, overrides={"roic": 0.30})
        assert out["dimension_scores"]["profitability"] > card["dimension_scores"]["profitability"]
        assert out["total"] > card["total"]

    def test_worsening_a_metric_lowers_the_total(self, card):
        out = sn.recompute(card, overrides={"rev_yoy": -0.10})
        assert out["total"] < card["total"]

    def test_an_override_only_moves_its_own_dimension(self, card):
        out = sn.recompute(card, overrides={"roic": 0.30})
        for dim in ("financial_health", "growth", "valuation", "sentiment"):
            assert out["dimension_scores"][dim] == card["dimension_scores"][dim]

    def test_unknown_metric_names_are_ignored(self, card):
        """A stale or hand-edited client must not be able to 500 the endpoint."""
        out = sn.recompute(card, overrides={"not_a_metric": 1.0, "roic": 0.11})
        assert out["total"] == card["total"]

    def test_non_numeric_override_values_are_ignored(self, card):
        out = sn.recompute(card, overrides={"roic": "high"})
        assert out["total"] == card["total"]

    def test_detail_carries_the_overridden_value(self, card):
        out = sn.recompute(card, overrides={"roic": 0.30})
        assert out["detail"]["profitability"]["roic"]["value"] == 0.30

    def test_overridden_metrics_are_reported(self, card):
        out = sn.recompute(card, overrides={"roic": 0.30, "pe": 15.0})
        assert set(out["overridden"]) == {"roic", "pe"}

    def test_weights_can_be_changed_without_touching_metrics(self, card):
        out = sn.recompute(card, weights={"valuation": 0.6, "profitability": 0.1})
        assert out["total"] != card["total"]
        assert out["dimension_scores"] == card["dimension_scores"]

    def test_a_missing_dimension_stays_missing(self):
        """Overriding one dimension must not resurrect another that had no data."""
        metrics = {k: v for k, v in BASE_METRICS.items() if k != "valuation"}
        thin = build_card(metrics, with_price_target=False)
        assert thin["dimension_scores"]["valuation"] is None

        out = sn.recompute(thin, overrides={"roic": 0.30})
        assert out["dimension_scores"]["valuation"] is None
        assert "valuation" in out["dimensions_unavailable"]

    def test_conviction_is_recomputed_not_copied(self, card):
        """Pushing the composite deep into BUY territory should firm the conviction up."""
        strong = {dim: dict(m) for dim, m in BASE_METRICS.items()}
        strong["profitability"].update({"roic": 0.35, "operating_margin": 0.40, "roe": 0.40})
        strong["growth"].update({"rev_yoy": 0.35, "rev_cagr_3y": 0.32})
        out = sn.recompute(card, overrides={
            "roic": 0.35, "operating_margin": 0.40, "roe": 0.40,
            "rev_yoy": 0.35, "rev_cagr_3y": 0.32,
        })
        assert out["total"] > card["total"]
        assert sc.rating_for(out["total"]) == out["rating"]


# ------------------------------------------------------------------------ price lever


class TestPriceLever:
    def test_halving_the_price_halves_the_pe(self, card):
        out = sn.recompute(card, overrides={sn.PRICE_LEVER: 120.0})
        assert out["detail"]["valuation"]["pe"]["value"] == pytest.approx(11.0)

    def test_halving_the_price_halves_price_to_book(self, card):
        out = sn.recompute(card, overrides={sn.PRICE_LEVER: 120.0})
        assert out["detail"]["valuation"]["price_to_book"]["value"] == pytest.approx(2.1)

    def test_halving_the_price_doubles_the_fcf_yield(self, card):
        """FCF yield is a reciprocal of price, not a multiple of it."""
        out = sn.recompute(card, overrides={sn.PRICE_LEVER: 120.0})
        assert out["detail"]["valuation"]["fcf_yield"]["value"] == pytest.approx(0.084)

    def test_ev_multiples_do_not_scale_linearly_with_price(self, card):
        """EV is market cap plus net debt. Only the equity half moves with the price, so
        a halved share price cuts EV/EBITDA by less than half."""
        out = sn.recompute(card, overrides={sn.PRICE_LEVER: 120.0})
        new_ev_ebitda = out["detail"]["valuation"]["ev_ebitda"]["value"]
        assert new_ev_ebitda > 7.0
        assert new_ev_ebitda < 14.0

    def test_ev_multiple_rescaling_is_exact(self, card):
        """mktcap 360bn, net debt 18bn -> EV 378bn. At half price: 180 + 18 = 198bn.
        14.0 * 198/378 = 7.333..."""
        out = sn.recompute(card, overrides={sn.PRICE_LEVER: 120.0})
        assert out["detail"]["valuation"]["ev_ebitda"]["value"] == pytest.approx(
            14.0 * 198.0 / 378.0, rel=1e-6
        )

    def test_a_lower_price_improves_the_valuation_score(self, card):
        out = sn.recompute(card, overrides={sn.PRICE_LEVER: 150.0})
        assert out["dimension_scores"]["valuation"] > card["dimension_scores"]["valuation"]

    def test_the_price_lever_reports_the_implied_move(self, card):
        out = sn.recompute(card, overrides={sn.PRICE_LEVER: 180.0})
        assert out["price_scenario"]["price"] == 180.0
        assert out["price_scenario"]["move"] == pytest.approx(-0.25)

    def test_no_price_lever_means_no_price_scenario(self, card):
        assert sn.recompute(card, overrides={"roic": 0.2}).get("price_scenario") is None

    def test_the_price_target_implied_move_follows_the_new_price(self, card):
        """A target band next to a stale implied move is a lie about the same screen."""
        out = sn.recompute(card, overrides={sn.PRICE_LEVER: 120.0})
        mid = out["price_target"]["mid"]
        assert out["price_target"]["implied_move"] == pytest.approx(mid / 120.0 - 1, rel=1e-3)

    def test_the_price_target_band_itself_does_not_move_with_the_price(self, card):
        """The target is a peer multiple applied to EBITDA. It does not know the price."""
        out = sn.recompute(card, overrides={sn.PRICE_LEVER: 120.0})
        assert out["price_target"]["mid"] == card["price_target"]["mid"]

    def test_the_price_target_is_untouched_without_a_price_override(self, card):
        out = sn.recompute(card, overrides={"roic": 0.30})
        assert out["price_target"] == card["price_target"]

    def test_price_lever_is_absent_when_the_card_has_no_price(self):
        thin = build_card(with_price_target=False)
        names = {lv["name"] for lv in sn.levers_for(thin)}
        assert sn.PRICE_LEVER not in names

    def test_an_explicit_valuation_override_beats_the_price_lever(self, card):
        """A user who drags both should get the number they set, not a rescaled one."""
        out = sn.recompute(card, overrides={sn.PRICE_LEVER: 120.0, "pe": 30.0})
        assert out["detail"]["valuation"]["pe"]["value"] == 30.0


# ----------------------------------------------------------------------------- levers


class TestLevers:
    def test_only_metrics_present_in_the_card_become_levers(self):
        metrics = {k: v for k, v in BASE_METRICS.items() if k != "growth"}
        thin = build_card(metrics, with_price_target=False)
        names = {lv["name"] for lv in sn.levers_for(thin)}
        assert "rev_yoy" not in names
        assert "roic" in names

    def test_a_metric_that_could_not_be_computed_is_not_a_lever(self):
        metrics = {dim: dict(m) for dim, m in BASE_METRICS.items()}
        metrics["profitability"]["roic"] = None
        thin = build_card(metrics, with_price_target=False)
        names = {lv["name"] for lv in sn.levers_for(thin)}
        assert "roic" not in names

    def test_a_lever_range_spans_its_anchor_table(self, card):
        lever = next(lv for lv in sn.levers_for(card) if lv["name"] == "pe")
        anchors = sc.anchors_for("pe")
        assert lever["min"] <= anchors[0][0]
        assert lever["max"] >= anchors[-1][0]

    def test_a_lever_range_contains_the_current_value(self):
        """A company outside its anchor table still needs a draggable handle."""
        metrics = {dim: dict(m) for dim, m in BASE_METRICS.items()}
        metrics["valuation"]["pe"] = 140.0
        wide = build_card(metrics, with_price_target=False)
        lever = next(lv for lv in sn.levers_for(wide) if lv["name"] == "pe")
        assert lever["max"] >= 140.0

    def test_levers_carry_direction_and_dimension(self, card):
        by_name = {lv["name"]: lv for lv in sn.levers_for(card)}
        assert by_name["pe"]["higher_is_better"] is False
        assert by_name["roic"]["higher_is_better"] is True
        assert by_name["roic"]["dimension"] == "profitability"

    def test_levers_carry_a_label_and_a_unit(self, card):
        for lever in sn.levers_for(card):
            assert lever["label"]
            assert lever["unit"] in {"pct", "x", "ratio", "score", "currency"}

    def test_the_step_divides_the_range_finely_enough_to_be_draggable(self, card):
        for lever in sn.levers_for(card):
            steps = (lever["max"] - lever["min"]) / lever["step"]
            assert 20 <= steps <= 2000, f"{lever['name']} has {steps} steps"


# ----------------------------------------------------------------------------- solver


class TestSolvePaths:
    def test_it_finds_at_least_one_way_to_reach_buy(self, near_buy):
        assert near_buy["rating"] == "HOLD"
        paths = sn.solve_paths(near_buy, target_rating="BUY")
        assert any(p["reachable"] for p in paths)

    def test_a_path_names_the_lever_and_both_values(self, near_buy):
        paths = [p for p in sn.solve_paths(near_buy, target_rating="BUY") if p["reachable"]]
        p = paths[0]
        assert p["lever"]
        assert p["from"] is not None
        assert p["to"] is not None

    def test_unreachable_levers_are_reported_not_hidden(self, near_buy):
        """Most single metrics cannot carry a composite across a band on their own, and
        saying so is the honest answer."""
        paths = sn.solve_paths(near_buy, target_rating="BUY")
        assert any(not p["reachable"] for p in paths)

    def test_a_mid_band_company_has_no_single_lever_route(self, card):
        """Two points from the BUY line, nothing gets there alone. The panel must be
        able to say so rather than invent a route."""
        assert card["rating"] == "HOLD"
        assert card["distance_to_edge"] > 0.5
        paths = sn.solve_paths(card, target_rating="BUY")
        assert paths
        assert not any(p["reachable"] for p in paths)

    def test_reachable_paths_come_before_unreachable_ones(self, near_buy):
        paths = sn.solve_paths(near_buy, target_rating="BUY")
        reach = [i for i, p in enumerate(paths) if p["reachable"]]
        unreach = [i for i, p in enumerate(paths) if not p["reachable"]]
        assert reach and unreach
        assert max(reach) < min(unreach)

    def test_paths_are_ordered_by_how_small_the_required_move_is(self, near_buy):
        reachable = [p for p in sn.solve_paths(near_buy, target_rating="BUY") if p["reachable"]]
        efforts = [p["effort"] for p in reachable]
        assert efforts == sorted(efforts)

    def test_a_downgrade_target_is_solved_in_the_other_direction(self, near_sell):
        """From HOLD, reaching SELL means metrics getting worse, not better."""
        paths = [p for p in sn.solve_paths(near_sell, target_rating="SELL") if p["reachable"]]
        assert paths
        for p in paths:
            if p["higher_is_better"]:
                assert p["to"] < p["from"]
            else:
                assert p["to"] > p["from"]

    def test_the_price_lever_is_solved_too(self, near_buy):
        paths = sn.solve_paths(near_buy, target_rating="BUY")
        price = next((p for p in paths if p["lever"] == sn.PRICE_LEVER), None)
        assert price is not None
        assert price["reachable"]

    def test_an_already_met_target_returns_nothing_to_do(self, card):
        paths = sn.solve_paths(card, target_rating="HOLD")
        assert paths == []


class TestSolveSelfConsistency:
    """Every reachable path, fed back through recompute, must produce the target."""

    @pytest.mark.parametrize("fixture,target", [("near_buy", "BUY"), ("near_sell", "SELL")])
    def test_applying_a_solved_path_produces_the_target_rating(self, request, fixture, target):
        card = request.getfixturevalue(fixture)
        paths = [p for p in sn.solve_paths(card, target_rating=target) if p["reachable"]]
        assert paths, f"no reachable path to {target}"
        for p in paths:
            out = sn.recompute(card, overrides={p["lever"]: p["to"]})
            assert out["rating"] == target, (
                f"{p['lever']} -> {p['to']} was reported to reach {target} "
                f"but recompute says {out['rating']} at {out['total']}"
            )

    def test_a_reported_threshold_is_tight(self, near_buy):
        """Stepping a reachable path back one step must fall short, or the solver is
        reporting a bigger move than the rubric actually requires."""
        paths = [p for p in sn.solve_paths(near_buy, target_rating="BUY") if p["reachable"]]
        assert paths
        levers = {lv["name"]: lv for lv in sn.levers_for(near_buy)}
        for p in paths:
            lever = levers[p["lever"]]
            back = p["to"] - lever["step"] if p["to"] > p["from"] else p["to"] + lever["step"]
            out = sn.recompute(near_buy, overrides={p["lever"]: back})
            assert out["rating"] != "BUY", f"{p['lever']} reached BUY before {p['to']}"


class TestSolverPruning:
    """``solve_paths`` skips the scan for levers it can prove cannot reach the target.

    The bound is the most a single lever can contribute: its metric taken to the end of
    the 0-10 scale, scaled by its weight inside its dimension and its dimension's weight
    inside the composite. It exists because the common case — a company in the middle of
    a band — is the one where every lever has to be scanned to its stop before the
    honest "nothing does this alone" can be returned.

    A bound that pruned a lever which could in fact reach the target would turn a real
    route into a silent "unreachable", so it is checked here against the unpruned scan
    for every lever on every fixture.
    """

    @pytest.mark.parametrize("fixture,target", [
        ("near_buy", "BUY"), ("near_sell", "SELL"), ("card", "BUY"), ("card", "SELL"),
    ])
    def test_pruning_never_hides_a_reachable_lever(self, request, fixture, target):
        card = request.getfixturevalue(fixture)
        improving = sn._RANK[target] > sn._RANK[card["rating"]]
        pruned = {p["lever"]: p["reachable"] for p in sn.solve_paths(card, target_rating=target)}

        for lever in sn.levers_for(card):
            brute = sn._solve_one(card, lever, target, improving)
            assert pruned[lever["name"]] == brute["reachable"], (
                f"{lever['name']}: pruning says reachable={pruned[lever['name']]} "
                f"but an unpruned scan says {brute['reachable']}"
            )

    def test_pruning_reports_the_same_threshold_as_an_unpruned_scan(self, near_buy):
        improving = True
        for p in sn.solve_paths(near_buy, target_rating="BUY"):
            if not p["reachable"]:
                continue
            lever = next(lv for lv in sn.levers_for(near_buy) if lv["name"] == p["lever"])
            assert sn._solve_one(near_buy, lever, "BUY", improving)["to"] == p["to"]


class TestDefaultTarget:
    def test_hold_aims_at_buy(self):
        assert sn.default_target("HOLD") == "BUY"

    def test_sell_aims_at_hold(self):
        assert sn.default_target("SELL") == "HOLD"

    def test_buy_asks_what_would_break_it(self):
        assert sn.default_target("BUY") == "HOLD"
