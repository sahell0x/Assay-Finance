"""Degenerate inputs.

Financial data is full of cases where the arithmetic still "works" but the answer is
nonsense: a company with a shareholders' deficit shows a beautiful ROE, a loss-making
company shows a negative leverage multiple that reads as conservative. Every one of
these must produce ``None`` and a warning, never a number.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.analytics import ratios as r
from src.analytics import scoring as sc
from src.analytics import trends as t
from src.data.fundamentals import Statements, build_facts, derive


class TestNegativeEquity:
    """A shareholders' deficit makes every equity-denominated ratio meaningless."""

    ROW = {
        "net_income": 500.0,
        "revenue": 5_000.0,
        "total_equity": -2_000.0,
        "total_assets": 10_000.0,
        "total_debt": 8_000.0,
        "cash": 500.0,
        "nopat": 400.0,
        "market_cap": 6_000.0,
    }

    def test_roe_is_none_not_a_flattering_negative(self):
        # -0.25 would read as a modest loss; the truth is the ratio does not apply.
        assert r.roe(self.ROW) is None

    def test_equity_multiplier_is_none(self):
        assert r.equity_multiplier(self.ROW) is None

    def test_debt_to_equity_is_none(self):
        assert r.debt_to_equity(self.ROW) is None

    def test_price_to_book_is_none(self):
        assert r.price_to_book(self.ROW) is None

    def test_roic_survives_if_invested_capital_is_still_positive(self):
        # 8,000 - 2,000 - 500 = 5,500 of invested capital remains.
        assert r.invested_capital(self.ROW) == 5_500.0
        assert r.roic(self.ROW) == pytest.approx(400.0 / 5_500.0)

    def test_roic_is_none_when_invested_capital_goes_negative(self):
        row = dict(self.ROW, total_debt=100.0, cash=500.0)  # 100 - 2,000 - 500 < 0
        assert r.roic(row) is None

    def test_dupont_does_not_fabricate_a_product(self):
        d = r.dupont(self.ROW)
        assert d["equity_multiplier"] is None
        assert d["product"] is None
        assert d["reconciles"] is None

    def test_averaging_across_the_sign_flip_is_still_rejected(self):
        """Equity going from +1,000 to -2,000 averages to -500, still meaningless."""
        assert r.roe(self.ROW, {"total_equity": 1_000.0}) is None


class TestZeroOrNegativeEbitda:
    def test_net_debt_to_ebitda_is_none_not_infinity(self):
        row = {"total_debt": 1_000.0, "cash": 100.0, "ebitda": 0.0}
        assert r.net_debt_to_ebitda(row) is None

    def test_negative_ebitda_does_not_produce_a_reassuring_negative_ratio(self):
        # 900 / -300 = -3.0 would score as net cash. It is the opposite.
        row = {"total_debt": 1_000.0, "cash": 100.0, "ebitda": -300.0}
        assert r.net_debt_to_ebitda(row) is None

    def test_ev_ebitda_is_none(self):
        assert r.ev_ebitda({"enterprise_value": 5_000.0, "ebitda": -300.0}) is None

    def test_pe_is_none_for_a_loss(self):
        assert r.pe_ratio({"market_cap": 5_000.0, "net_income": -300.0}) is None
        assert r.pe_ratio({"market_cap": 5_000.0, "net_income": 0.0}) is None


class TestZeroDebt:
    def test_interest_coverage_is_none_when_there_is_no_interest_expense(self):
        """A debt-free company has infinite coverage; the node flags it "strong" rather
        than printing inf."""
        assert r.interest_coverage({"operating_income": 1_000.0, "interest_expense": 0.0}) is None
        assert r.interest_coverage({"operating_income": 1_000.0, "interest_expense": None}) is None

    def test_sub_dollar_interest_expense_is_treated_as_none(self):
        assert r.interest_coverage({"operating_income": 1_000.0, "interest_expense": 0.4}) is None

    def test_fcf_to_debt_is_none_with_no_debt(self):
        assert r.fcf_to_debt({"fcf": 500.0, "total_debt": 0.0}) is None


class TestBankShapedData:
    """Banks have no inventory, no cost of revenue and no current/non-current split."""

    ROW = {
        "revenue": 100_000.0,
        "net_income": 20_000.0,
        "total_assets": 3_000_000.0,
        "total_equity": 300_000.0,
        "current_assets": None,
        "current_liab": None,
        "inventory": None,
        "cogs": None,
        "payables": None,
        "receivables": 50_000.0,
    }

    def test_working_capital_ratios_are_none(self):
        assert r.current_ratio(self.ROW) is None
        assert r.quick_ratio(self.ROW) is None
        assert r.cash_ratio(self.ROW) is None

    def test_cycle_metrics_are_none(self):
        assert r.dio(self.ROW) is None
        assert r.dpo(self.ROW) is None
        assert r.cash_conversion_cycle(self.ROW) is None

    def test_dso_still_computes(self):
        assert r.dso(self.ROW) == pytest.approx(50_000.0 / 100_000.0 * 365)

    def test_gross_margin_is_none_without_cost_of_revenue(self):
        assert r.gross_margin(derive(dict(self.ROW))) is None

    def test_altman_z_is_none_without_working_capital(self):
        row = derive(dict(self.ROW, market_cap=200_000.0, retained_earnings=150_000.0,
                          operating_income=25_000.0))
        assert r.altman_z(row) is None

    def test_roe_and_roa_still_work(self):
        assert r.roe(self.ROW) == pytest.approx(20_000.0 / 300_000.0)
        assert r.roa(self.ROW) == pytest.approx(20_000.0 / 3_000_000.0)


class TestInsufficientHistory:
    def test_cagr_needs_the_full_window(self):
        two_years = [("FY2024", 120.0), ("FY2023", 100.0)]
        assert t.cagr_over(two_years, 3) is None
        assert t.cagr_over(two_years, 5) is None
        assert t.yoy(two_years) == pytest.approx(0.20)

    def test_acceleration_needs_three_periods(self):
        assert t.growth_acceleration([("FY2024", 120.0), ("FY2023", 100.0)]) is None

    def test_two_annual_periods_still_build_facts_with_a_warning(self):
        cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31")]
        inc = pd.DataFrame(
            [[100.0, 90.0], [10.0, 9.0]], index=["Total Revenue", "Net Income"], columns=cols
        )
        bs = pd.DataFrame(
            [[500.0, 450.0], [200.0, 180.0]],
            index=["Total Assets", "Stockholders Equity"],
            columns=cols,
        )
        facts, periods, annual = build_facts(Statements(income=inc, balance=bs))
        assert len(annual) == 2
        assert facts["FY2024"]["revenue"] == 100.0

        from src.data.fundamentals import Fundamentals, assess_quality

        q = assess_quality(
            Fundamentals(ticker="X", periods=periods, annual_periods=annual, facts=facts)
        )
        assert any("annual period" in w for w in q["warnings"])

    def test_growth_dimension_scores_on_what_exists(self):
        """Missing multi-year CAGRs must not zero the growth score."""
        score, detail = sc.score_dimension("growth", {"rev_yoy": 0.20, "rev_cagr_3y": None,
                                                      "rev_cagr_5y": None, "eps_growth": 0.22})
        assert score is not None and score > 7
        assert detail["rev_cagr_3y"]["score"] is None


class TestMissingPeers:
    def test_percentile_needs_three_observations(self):
        assert t.percentile_rank(10.0, []) is None
        assert t.percentile_rank(10.0, [5.0, 15.0]) is None

    def test_median_of_nothing_is_none(self):
        assert t.median([]) is None
        assert t.median([None]) is None

    def test_price_target_unavailable_without_a_peer_multiple(self):
        pt = sc.price_target(
            peer_median_ev_ebitda=None, company_ebitda=1_000.0,
            total_debt=200.0, cash=100.0, shares=50.0,
        )
        assert pt["available"] is False
        assert pt["low"] is None and pt["high"] is None
        assert "peer median" in pt["reason"]

    def test_price_target_unavailable_on_negative_ebitda(self):
        pt = sc.price_target(
            peer_median_ev_ebitda=12.0, company_ebitda=-500.0,
            total_debt=200.0, cash=100.0, shares=50.0,
        )
        assert pt["available"] is False

    def test_price_target_refuses_a_negative_implied_value(self):
        # 10x EBITDA of 100 = 1,000 EV, against 5,000 of debt.
        pt = sc.price_target(
            peer_median_ev_ebitda=10.0, company_ebitda=100.0,
            total_debt=5_000.0, cash=0.0, shares=50.0,
        )
        assert pt["available"] is False
        assert "negative" in pt["reason"]

    def test_price_target_computes_when_inputs_are_present(self):
        # EV = 12 x 1,000 = 12,000 ; equity = 12,000 - 200 + 100 = 11,900 ; /50 = 238.00
        pt = sc.price_target(
            peer_median_ev_ebitda=12.0, company_ebitda=1_000.0,
            total_debt=200.0, cash=100.0, shares=50.0,
        )
        assert pt["available"] is True
        assert pt["mid"] == pytest.approx(238.00)
        assert pt["low"] == pytest.approx(202.30)    # -15%
        assert pt["high"] == pytest.approx(273.70)   # +15%


class TestNoNaNOrInfEverEscapes:
    """Whatever goes in, a ratio function returns a finite float or None."""

    NASTY = [
        {},
        {"revenue": 0.0, "net_income": 5.0},
        {"revenue": float("nan"), "net_income": 5.0},
        {"revenue": -100.0, "net_income": 5.0, "total_equity": 0.0, "total_assets": 0.0},
        {"total_assets": 0.0, "total_liabilities": 0.0, "market_cap": 0.0},
    ]

    @pytest.mark.parametrize("row", NASTY)
    def test_all_ratio_functions(self, row):
        import math

        fns = [
            r.gross_margin, r.operating_margin, r.net_margin, r.ebitda_margin,
            r.fcf_margin, r.roe, r.roa, r.roic, r.asset_turnover, r.equity_multiplier,
            r.current_ratio, r.quick_ratio, r.cash_ratio, r.debt_to_equity,
            r.net_debt_to_ebitda, r.interest_coverage, r.fcf_to_debt, r.dso, r.dio,
            r.dpo, r.cash_conversion_cycle, r.altman_z, r.pe_ratio, r.ev_ebitda,
            r.ev_sales, r.price_to_book, r.fcf_yield,
        ]
        for fn in fns:
            out = fn(row)
            assert out is None or (
                isinstance(out, float) and math.isfinite(out)
            ), f"{fn.__name__} returned {out!r}"
