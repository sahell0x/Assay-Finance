"""Citation enforcement and numeric verification.

Both of these run in Python on purpose. A model asked to check its own citations will
confirm the tag it just invented, and a model asked to check its own arithmetic is the
wrong instrument for catching the transposed digit it just produced.
"""

from __future__ import annotations

import pytest

from src.agent.nodes.critic import verify_numbers
from src.agent.nodes.memo import (
    QUALITATIVE_MARKERS,
    cited_labels,
    enforce_citations,
    split_sentences,
)
from src.agent.state import InvestmentMemo

LABELS = {"S1", "S2", "S3", "S4"}


class TestQualitativeMarkers:
    @pytest.mark.parametrize(
        "text",
        [
            "The company faces intense competition.",
            "Its competitors are better funded.",
            "Regulators have opened an inquiry.",
            "Regulatory scrutiny is increasing.",
            "Litigation risk is rising.",
            "Recent acquisitions have not integrated well.",
            "Management guided to slower growth.",
            "Market share has eroded.",
            "The firm has pricing power.",
            "Demand softened in the quarter.",
            "An analyst downgraded the shares.",
            "The FDA declined the application.",
        ],
    )
    def test_claims_about_the_world_are_detected(self, text):
        assert QUALITATIVE_MARKERS.search(text), text

    @pytest.mark.parametrize(
        "text",
        [
            "Revenue grew 12.4% year over year.",
            "Operating margin was 31.5% on a trailing basis.",
            "The composite score is 7.2 out of 10.",
            "Net debt to EBITDA stands at 1.8x.",
            "Free cash flow reached $108.8B.",
        ],
    )
    def test_pure_figure_reporting_needs_no_citation(self, text):
        assert not QUALITATIVE_MARKERS.search(text), text

    def test_prefix_markers_match_inside_words(self):
        """The bug this guards: a trailing \\b after a stem like "compet" never matches,
        because there is no word boundary inside "competition"."""
        for word in ("competition", "competitor", "competitive", "regulators", "regulatory"):
            assert QUALITATIVE_MARKERS.search(word), word


class TestEnforceCitations:
    def test_uncited_qualitative_claim_is_stripped(self):
        text = "Revenue grew. The company faces intense competition in its core market."
        out, stats = enforce_citations(text, LABELS)
        assert "competition" not in out
        assert stats["stripped"] == 1

    def test_properly_cited_claim_survives(self):
        text = "The company faces intense competition in its core market [S2]."
        out, stats = enforce_citations(text, LABELS)
        assert out == text
        assert stats["cited"] == 1

    def test_out_of_range_tag_is_treated_as_no_citation(self):
        """An invented tag is worse than a missing one: it looks like evidence."""
        text = "Regulators opened an inquiry into the company [S99]."
        out, stats = enforce_citations(text, LABELS)
        assert out == ""
        assert stats["stripped"] == 1

    def test_mixed_valid_and_invalid_tags_keep_only_the_valid_ones(self):
        text = "Management guided to slower growth [S1][S42]."
        out, _ = enforce_citations(text, LABELS)
        assert "[S1]" in out
        assert "[S42]" not in out

    def test_numeric_sentence_keeps_no_tag_without_being_stripped(self):
        text = "Operating margin was 31.5%."
        out, stats = enforce_citations(text, LABELS)
        assert out == text
        assert stats["stripped"] == 0

    def test_numeric_sentence_with_a_bogus_tag_keeps_the_sentence(self):
        text = "Operating margin was 31.5% [S77]."
        out, _ = enforce_citations(text, LABELS)
        assert "31.5%" in out
        assert "S77" not in out

    def test_citation_rate_counts_only_claims_that_needed_one(self):
        text = (
            "Revenue grew 12%. "
            "Competition intensified [S1]. "
            "Regulators are investigating."
        )
        _, stats = enforce_citations(text, LABELS)
        assert stats["needing_citation"] == 2
        assert stats["cited"] == 1
        assert stats["citation_rate"] == pytest.approx(0.5)

    def test_empty_input(self):
        out, stats = enforce_citations("", LABELS)
        assert out == ""
        assert stats["sentences"] == 0
        assert stats["citation_rate"] == 1.0

    def test_no_evidence_means_every_claim_is_stripped(self):
        text = "Competition is fierce [S1]. Regulators are watching [S2]."
        out, stats = enforce_citations(text, set())
        assert out == ""
        assert stats["stripped"] == 2

    def test_sentence_splitting_handles_abbreviations_and_quotes(self):
        text = 'Revenue rose. "Growth was strong," management said [S1]. It fell later.'
        assert len(split_sentences(text)) == 3


class TestCitedLabels:
    def test_collects_across_every_field_and_sorts_numerically(self):
        memo = InvestmentMemo(
            ticker="AAPL",
            as_of="2026-09-11",
            recommendation="HOLD",
            conviction="medium",
            thesis="Competition intensified [S10].",
            valuation_method="peer multiple",
            key_drivers=["Margin held [S2]", "Cash generation [S1]", "Scale"],
            key_risks=["Regulatory action [S10]", "Supply concentration [S3]", "Demand"],
            what_would_change_our_mind=["A guidance cut [S4]"],
        )
        # S10 must sort after S4, not between S1 and S2.
        assert cited_labels(memo) == ["S1", "S2", "S3", "S4", "S10"]


class TestNumericVerification:
    KNOWN = {
        "percent": [0.315, 0.2397, 0.1240],
        "x": [25.8, 1.87],
        "currency": [3_400_000_000_000.0, 431.00, 108_807_000_000.0],
        "ratio": [1.5741],
        "score": [7.2],
        "days": [31.2],
    }

    def test_correct_figures_pass(self):
        text = (
            "Operating margin was 31.5% and net margin 23.97%. EV/EBITDA is 25.8x. "
            "Market capitalisation is $3.4T and free cash flow $108.8B. "
            "The composite score is 7.2."
        )
        assert verify_numbers(text, self.KNOWN) == []

    def test_transposed_percentage_is_caught(self):
        """31.5 -> 35.1 is the canonical model arithmetic failure."""
        found = verify_numbers("Operating margin was 35.1%.", self.KNOWN)
        assert [f["stated"] for f in found] == [35.1]

    def test_transposed_multiple_is_caught(self):
        found = verify_numbers("EV/EBITDA is 28.5x.", self.KNOWN)
        assert [f["stated"] for f in found] == [28.5]

    def test_invented_currency_figure_is_caught(self):
        found = verify_numbers("Free cash flow was $205.3B.", self.KNOWN)
        assert found and found[0]["kind"] == "currency"

    def test_rounded_currency_is_tolerated(self):
        # $3.4T against a stored 3,400,000,000,000 and $108.8B against 108,807,000,000.
        assert verify_numbers("Market cap $3.4T, free cash flow $108.8B.", self.KNOWN) == []

    def test_percentage_within_rounding_tolerance_passes(self):
        # 31.5% against a stored 0.315, and 31.4% is within the 0.15pp tolerance.
        assert verify_numbers("Margin of 31.4%.", self.KNOWN) == []

    def test_percentage_outside_tolerance_fails(self):
        assert verify_numbers("Margin of 33.0%.", self.KNOWN)

    def test_years_and_small_integers_are_not_treated_as_claims(self):
        assert verify_numbers("In 2024 the company had 3 segments and 5 plants.", self.KNOWN) == []

    def test_repeated_wrong_figure_reports_once(self):
        text = "Margin was 35.1%. Later the margin of 35.1% persisted."
        assert len(verify_numbers(text, self.KNOWN)) == 1

    def test_empty_known_state_flags_everything_numeric(self):
        found = verify_numbers("Margin was 31.5%.", {})
        assert len(found) == 1

    def test_units_error_is_caught(self):
        """Stating a fraction as if it were a percentage point count."""
        found = verify_numbers("Operating margin was 0.315%.", self.KNOWN)
        assert found and found[0]["stated"] == 0.315
