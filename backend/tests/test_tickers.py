"""Ticker search ranking: brands, punctuation, and real symbols winning ties."""

from __future__ import annotations


class TestTickerRanking:
    """Pure ranking, no HTTP: people search by brand and ignore punctuation."""

    ROWS = [
        {"ticker": "GOOGL", "name": "Alphabet Inc.", "exchange": "Nasdaq"},
        {"ticker": "GOOG", "name": "Alphabet Inc.", "exchange": "Nasdaq"},
        {"ticker": "MCD", "name": "McDONALD'S CORP", "exchange": "NYSE"},
        {"ticker": "KO", "name": "COCA-COLA CO", "exchange": "NYSE"},
        {"ticker": "COKE", "name": "Coca-Cola Consolidated, Inc.", "exchange": "Nasdaq"},
    ]

    def test_a_brand_finds_its_listed_parent(self):
        from src.api.tickers import _rank

        assert [r["ticker"] for r in _rank(self.ROWS, "google", 3)][:2] == ["GOOGL", "GOOG"]

    def test_punctuation_in_names_does_not_matter(self):
        from src.api.tickers import _rank

        assert _rank(self.ROWS, "mcdonalds", 3)[0]["ticker"] == "MCD"
        assert _rank(self.ROWS, "coca cola", 3)[0]["ticker"] == "KO"

    def test_a_real_ticker_is_never_overridden_by_an_alias(self):
        from src.api.tickers import _rank

        assert _rank(self.ROWS, "COKE", 3)[0]["ticker"] == "COKE"


class TestPrivateCompanies:
    """A private company is named as such instead of being answered with look-alikes."""

    ROWS = [
        {"ticker": "MRSH", "name": "Marsh & Mclennan Companies, Inc.", "exchange": "NYSE"},
        {"ticker": "AAPL", "name": "Apple Inc.", "exchange": "Nasdaq"},
    ]

    def test_a_private_name_is_recognised(self):
        from src.api.tickers import private_company

        assert private_company(self.ROWS, "anthropic") == "Anthropic"
        assert private_company(self.ROWS, "Chat GPT") == "OpenAI"
        assert private_company(self.ROWS, "mars") == "Mars"

    def test_listed_companies_are_not_private(self):
        from src.api.tickers import private_company

        assert private_company(self.ROWS, "apple") is None
        assert private_company(self.ROWS, "marsh") is None

    def test_a_company_that_lists_stops_being_private(self):
        from src.api.tickers import private_company

        rows = self.ROWS + [
            {"ticker": "STRP", "name": "Stripe, Inc.", "exchange": "NYSE"},
            {"ticker": "DBX2", "name": "Databricks Holdings Inc.", "exchange": "Nasdaq"},
        ]
        assert private_company(rows, "stripe") is None
        assert private_company(rows, "databricks") is None

    def test_a_real_ticker_wins_over_the_private_list(self):
        from src.api.tickers import private_company

        rows = self.ROWS + [{"ticker": "MARS", "name": "Some Listed Co", "exchange": "NYSE"}]
        assert private_company(rows, "MARS") is None


class TestProductionGuard:
    """A production server must not start with the public development secret."""

    def test_the_dev_secret_is_refused_in_production(self):
        import pytest

        from src.config import DEV_AUTH_SECRET, Settings

        with pytest.raises(RuntimeError, match="AUTH_SECRET"):
            Settings(env="prod", auth_secret=DEV_AUTH_SECRET).check_production()
        with pytest.raises(RuntimeError):
            Settings(env="prod", auth_secret="short").check_production()
        with pytest.raises(RuntimeError):
            Settings(
                env="prod", auth_secret="change-me-in-production-use-openssl-rand-hex-32"
            ).check_production()

    def test_a_strong_secret_and_dev_mode_both_start(self):
        from src.config import Settings

        Settings(env="prod", auth_secret="x" * 48).check_production()
        Settings(env="dev").check_production()


class TestPeerFetchBudget:
    """A hung peer must not hold the analysis hostage."""

    def test_a_slow_peer_is_left_out_within_the_budget(self, monkeypatch):
        import time

        import src.agent.nodes.peers as peers_mod

        def fake_fetch_one(tk):
            if tk == "SLOW":
                time.sleep(5)
            return {"ticker": tk}

        monkeypatch.setattr(peers_mod, "_fetch_one", fake_fetch_one)
        monkeypatch.setattr(peers_mod, "PEER_FETCH_BUDGET_S", 0.5)

        started = time.perf_counter()
        out = peers_mod._fetch_many(["AAA", "SLOW", "BBB"])
        elapsed = time.perf_counter() - started

        assert set(out) == {"AAA", "BBB"}
        assert elapsed < 2, f"waited {elapsed:.1f}s for a peer past the budget"


class TestTagOnlyBullets:
    def test_a_bullet_left_with_only_its_source_tag_is_dropped(self):
        from src.agent.nodes.memo import _clean_list

        kept, _ = _clean_list(["Margins are 30%.", "[S2]", "[S4][S6]"], {"S2", "S4", "S6"})
        assert kept == ["Margins are 30%."]


class TestDisplayNames:
    def test_shouting_names_are_given_normal_case(self):
        from src.api.tickers import display_name

        assert display_name("MORGAN STANLEY") == "Morgan Stanley"
        assert display_name("BANK OF AMERICA CORP /DE/") == "Bank of America Corp."
        assert display_name("THE HERSHEY CO") == "The Hershey Co."

    def test_acronyms_and_mixed_case_are_left_alone(self):
        from src.api.tickers import display_name

        assert display_name("AT&T INC.") == "AT&T Inc."
        assert display_name("HP INC") == "HP Inc."
        assert display_name("Apple Inc.") == "Apple Inc."


def test_monitoring_scrubs_personal_data():
    from src.core.monitoring import _scrub

    event = {
        "request": {"cookies": {"s": "1"}, "data": "pw", "headers": {"Cookie": "s=1"}},
        "user": {"ip_address": "1.2.3.4", "email": "a@b.com"},
        "logentry": {"message": "failed for someone@example.com"},
    }
    out = _scrub(event, {})
    assert "cookies" not in out["request"] and "data" not in out["request"]
    assert out["request"]["headers"]["Cookie"] == "[removed]"
    assert out["user"] == {}
    assert "someone@example.com" not in out["logentry"]["message"]


def test_every_peer_ticker_is_a_string():
    """Bare ON, NO, Y or YES in YAML parse as booleans, which silently put `True` into a
    peer group (semiconductors, via ON Semiconductor) instead of a ticker."""
    from src.data.peers import _load

    data = _load()
    groups = list((data.get("groups") or {}).values()) + [data.get("fallback") or {}]
    for group in groups:
        for t in group.get("tickers", []):
            assert isinstance(t, str) and t, f"non-string ticker {t!r} in peers.yaml"
