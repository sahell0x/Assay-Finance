"""The alias resolver is the seam where yfinance's instability is absorbed.

These tests use captured frames from three companies whose statements genuinely carry
different row labels, which is the failure mode a naive ``df.loc["Total Revenue"]``
implementation hits on its second ticker.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.fundamentals import (
    ALIASES,
    Statements,
    assess_quality,
    build_facts,
    build_ttm,
    derive,
    effective_tax_rate,
    pick,
)


class TestPick:
    def test_resolves_primary_label(self, aapl_fixture):
        stmts, _ = aapl_fixture
        rev = pick(stmts.income, "revenue")
        assert rev is not None
        assert rev.notna().any()

    def test_falls_back_through_alias_list(self):
        """When the primary label is absent the resolver must keep walking."""
        df = pd.DataFrame(
            {pd.Timestamp("2024-12-31"): [500.0]},
            index=["Total Operating Income As Reported"],
        )
        assert pick(df, "operating_income").iloc[0] == 500.0

    def test_is_case_and_whitespace_insensitive(self):
        df = pd.DataFrame({pd.Timestamp("2024-12-31"): [42.0]}, index=["  total revenue  "])
        assert pick(df, "revenue").iloc[0] == 42.0

    def test_missing_label_returns_none_not_keyerror(self, jpm_fixture):
        stmts, _ = jpm_fixture
        # A bank reports no cost of revenue under any alias.
        assert pick(stmts.income, "cogs") is None

    def test_duplicate_labels_prefer_the_populated_row(self):
        """yfinance occasionally emits the same label twice; ``.loc`` then returns a
        DataFrame and naive code raises or silently takes an empty row."""
        cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31")]
        df = pd.DataFrame(
            [[None, None], [100.0, 90.0]], index=["Total Revenue", "Total Revenue"], columns=cols
        )
        picked = pick(df, "revenue")
        assert picked is not None
        assert picked[cols[0]] == 100.0

    def test_all_nan_row_is_treated_as_absent(self):
        df = pd.DataFrame({pd.Timestamp("2024-12-31"): [float("nan")]}, index=["Total Revenue"])
        assert pick(df, "revenue") is None

    def test_empty_and_none_frames(self):
        assert pick(None, "revenue") is None
        assert pick(pd.DataFrame(), "revenue") is None

    def test_every_alias_key_is_resolvable_in_principle(self):
        """Guards against a typo in ALIASES that would silently null a field forever."""
        for key, names in ALIASES.items():
            assert names, f"{key} has no aliases"
            df = pd.DataFrame({pd.Timestamp("2024-12-31"): [1.0]}, index=[names[0]])
            assert pick(df, key) is not None, key


class TestThreeDifferingLabelSets:
    """AAPL, JPM and O must all produce usable facts without special-casing."""

    @pytest.mark.parametrize("ticker", ["AAPL", "JPM", "O"])
    def test_builds_facts(self, statements, ticker):
        stmts, _ = statements(ticker)
        facts, periods, annual = build_facts(stmts)
        assert periods, f"{ticker} produced no periods"
        assert len(annual) >= 3, f"{ticker} produced too few annual periods"
        newest = facts[periods[0]]
        assert newest["revenue"] is not None
        assert newest["net_income"] is not None
        assert newest["total_assets"] is not None

    def test_bank_is_missing_operating_lines_without_crashing(self, jpm_fixture):
        stmts, _ = jpm_fixture
        facts, periods, _ = build_facts(stmts)
        row = facts[periods[0]]
        assert row["cogs"] is None
        assert row["gross_profit"] is None
        assert row["current_assets"] is None
        # ...yet the balance sheet still resolves.
        assert row["total_assets"] is not None
        assert row["total_equity"] is not None

    def test_reit_resolves_a_different_label_set(self, reit_fixture):
        stmts, _ = reit_fixture
        facts, periods, _ = build_facts(stmts)
        row = facts[periods[0]]
        assert row["revenue"] is not None
        assert row["total_debt"] is not None

    @pytest.mark.parametrize("ticker", ["AAPL", "JPM", "O", "MSFT", "NVDA"])
    def test_quality_report_is_honest(self, statements, ticker):
        stmts, _ = statements(ticker)
        from src.data.fundamentals import Fundamentals

        facts, periods, annual = build_facts(stmts)
        f = Fundamentals(ticker=ticker, periods=periods, annual_periods=annual, facts=facts)
        q = assess_quality(f)
        assert 0.0 <= q["coverage"] <= 1.0
        assert isinstance(q["warnings"], list)
        # Anything the report claims is missing must actually be missing.
        row = facts[periods[0]]
        for name in q["missing_critical"] + q["missing_important"]:
            assert row.get(name) is None


class TestDerived:
    def test_fcf_uses_absolute_capex_regardless_of_sign(self):
        """Capex is reported negative by some tickers and positive by others."""
        neg = derive({"ocf": 1000.0, "capex": -300.0})
        pos = derive({"ocf": 1000.0, "capex": 300.0})
        assert neg["fcf"] == 700.0
        assert pos["fcf"] == 700.0

    def test_ebitda_falls_back_to_ebit_plus_da(self):
        row = derive({"operating_income": 800.0, "d_and_a": 200.0})
        assert row["ebitda"] == 1000.0

    def test_reported_ebitda_wins_over_the_fallback(self):
        row = derive({"ebitda": 950.0, "operating_income": 800.0, "d_and_a": 200.0})
        assert row["ebitda"] == 950.0

    def test_gross_profit_derived_when_absent(self):
        assert derive({"revenue": 100.0, "cogs": 60.0})["gross_profit"] == 40.0

    def test_effective_tax_rate_is_clamped(self):
        assert effective_tax_rate(1000.0, 240.0) == pytest.approx(0.24)
        assert effective_tax_rate(1000.0, 900.0) == 0.5      # upper clamp
        assert effective_tax_rate(1000.0, -50.0) == 0.0      # lower clamp
        assert effective_tax_rate(-1000.0, 50.0) is None     # loss year
        assert effective_tax_rate(None, 50.0) is None

    def test_nopat_uses_the_clamped_rate(self):
        row = derive({"operating_income": 1000.0, "pretax_income": 1000.0, "tax_provision": 250.0})
        assert row["nopat"] == pytest.approx(750.0)

    def test_working_capital(self):
        assert derive({"current_assets": 150.0, "current_liab": 176.0})["working_capital"] == -26.0


class TestTTM:
    def test_ttm_sums_four_quarters_of_flows(self):
        cols = [pd.Timestamp(f"2024-{m:02d}-30") for m in (12, 9, 6, 3)]
        q_inc = pd.DataFrame([[10.0, 20.0, 30.0, 40.0]], index=["Total Revenue"], columns=cols)
        q_bs = pd.DataFrame([[500.0, 490.0, 480.0, 470.0]], index=["Total Assets"], columns=cols)
        ttm = build_ttm(Statements(q_income=q_inc, q_balance=q_bs))
        assert ttm["revenue"] == 100.0          # summed
        assert ttm["total_assets"] == 500.0     # newest balance, not summed

    def test_ttm_refuses_a_partial_year(self):
        """Three quarters would understate every flow metric while looking plausible."""
        cols = [pd.Timestamp(f"2024-{m:02d}-30") for m in (12, 9, 6)]
        q_inc = pd.DataFrame([[10.0, 20.0, 30.0]], index=["Total Revenue"], columns=cols)
        assert build_ttm(Statements(q_income=q_inc)) is None

    def test_ttm_flow_with_a_hole_is_none_rather_than_understated(self):
        cols = [pd.Timestamp(f"2024-{m:02d}-30") for m in (12, 9, 6, 3)]
        q_inc = pd.DataFrame(
            [[10.0, 20.0, 30.0, 40.0], [1.0, None, 3.0, 4.0]],
            index=["Total Revenue", "Operating Income"],
            columns=cols,
        )
        ttm = build_ttm(Statements(q_income=q_inc))
        assert ttm["revenue"] == 100.0
        assert ttm["operating_income"] is None

    def test_no_quarterly_data_yields_no_ttm(self):
        assert build_ttm(Statements()) is None

    @pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA"])
    def test_real_tickers_produce_a_ttm(self, statements, ticker):
        stmts, _ = statements(ticker)
        ttm = build_ttm(stmts)
        assert ttm is not None and ttm["revenue"] > 0
