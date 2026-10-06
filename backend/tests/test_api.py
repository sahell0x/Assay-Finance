"""HTTP contract tests.

What these assert, in order of how much it would hurt to get wrong: that a run is never
executed inside a request handler, that quota and budget are enforced before anything is
enqueued, that a cache hit does not consume someone's allowance, that anonymous
visitors get the full feature set, and that authenticated endpoints actually require
authentication.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def known_tickers(monkeypatch):
    """Every symbol counts as listed unless a test says otherwise. The real check
    downloads the SEC ticker file, and a test suite must not depend on the network."""
    import src.api.tickers as tickers_mod

    async def listed(symbol: str):
        return True, []

    monkeypatch.setattr(tickers_mod, "check_ticker", listed)


async def _seed_complete(session_factory, sample_result, *, ticker="AAPL", anon_id=None,
                         user_id=None, cache_key="k1", slug=None):
    from src.db import repo

    async with session_factory() as db:
        row = await repo.create_analysis(
            db, ticker=ticker, peer_tickers=None, weights=None,
            user_id=user_id, anon_id=anon_id, cache_key=cache_key,
        )
        await repo.add_event(db, row.id, node="ingest", status="start")
        await repo.add_event(db, row.id, node="ingest", status="ok", duration_ms=1200)
        await repo.add_event(db, row.id, node="memo", status="ok", duration_ms=3400)
        await repo.replace_evidence(db, row.id, [{
            "label": "S1", "source_type": "sec_10k", "url": "http://sec.gov/x",
            "published": "2025-10-31", "text": "A risk factor.", "relevance": 0.8,
            "title": "10-K", "section": "Item 1A",
        }])
        await repo.save_result(
            db, row.id,
            scorecard=sample_result["scorecard"], memo=sample_result["memo"],
            blocks=sample_result["blocks"], data_quality=sample_result["data_quality"],
            cost_usd=0.031,
        )
        if slug:
            fresh = await repo.get_analysis(db, row.id)
            await repo.ensure_public_slug(db, fresh)
        return row.id


class TestHealth:
    async def test_healthz_reports_both_datastores(self, client, fake_redis):
        r = await client.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["checks"]["database"] == "ok"
        assert "redis" in body["checks"]

    async def test_pipeline_metadata_is_public(self, client, fake_redis):
        r = await client.get("/meta/pipeline")
        assert r.status_code == 200
        body = r.json()
        assert len(body["pipeline"]) == 10
        assert body["thresholds"] == {"buy": 7.5, "hold": 5.0}


class TestCreateAnalysis:
    async def test_returns_202_and_does_not_run_inline(self, client, fake_redis):
        r = await client.post("/analyses", json={"ticker": "aapl"})
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "queued"
        assert body["ticker"] == "AAPL"
        assert body["stream_url"].endswith("/stream")
        # The work was handed to the queue, not done here.
        assert client.enqueued == [body["id"]]

    async def test_issues_an_anonymous_cookie(self, client, fake_redis):
        r = await client.post("/analyses", json={"ticker": "AAPL"})
        assert r.status_code == 202
        assert "anon_id" in r.cookies or "anon_id" in client.cookies

    @pytest.mark.parametrize("bad", ["", "   ", "A" * 20, "AA PL", "<script>"])
    async def test_rejects_malformed_tickers(self, client, fake_redis, bad):
        r = await client.post("/analyses", json={"ticker": bad})
        assert r.status_code == 422

    async def test_normalises_peers_and_weights(self, client, fake_redis, session_factory):
        r = await client.post(
            "/analyses",
            json={
                "ticker": "AAPL",
                "peer_tickers": ["msft", "MSFT", " googl ", ""],
                "weights": {"growth": 0.6, "nonsense": 5, "valuation": "x"},
            },
        )
        assert r.status_code == 202

        from src.db import repo

        async with session_factory() as db:
            row = await repo.get_analysis(db, uuid.UUID(r.json()["id"]))
        assert row.peer_tickers == ["MSFT", "GOOGL"]
        assert row.weights == {"growth": 0.6}


class TestCaching:
    async def test_identical_request_is_served_from_cache(
        self, client, fake_redis, session_factory, sample_result
    ):
        from src.core.cache import analysis_cache_key

        key = analysis_cache_key("AAPL", [], None)
        await _seed_complete(session_factory, sample_result, cache_key=key)

        r = await client.post("/analyses", json={"ticker": "AAPL"})
        assert r.status_code == 202
        body = r.json()
        assert body["cached"] is True
        assert body["status"] == "complete"
        assert client.enqueued == []  # nothing was computed

    async def test_a_cache_hit_does_not_consume_quota(
        self, client, fake_redis, session_factory, sample_result
    ):
        from src.core.cache import analysis_cache_key

        await _seed_complete(
            session_factory, sample_result, cache_key=analysis_cache_key("AAPL", [], None)
        )
        await client.post("/analyses", json={"ticker": "AAPL"})
        usage = (await client.get("/usage")).json()
        assert usage["used"] == 0
        assert usage["remaining"] == usage["limit"]

    async def test_the_clone_belongs_to_the_requester_and_carries_everything(
        self, client, fake_redis, session_factory, sample_result
    ):
        from src.core.cache import analysis_cache_key

        await _seed_complete(
            session_factory, sample_result,
            cache_key=analysis_cache_key("AAPL", [], None), anon_id="somebody-else",
        )
        created = (await client.post("/analyses", json={"ticker": "AAPL"})).json()

        detail = (await client.get(f"/analyses/{created['id']}")).json()
        assert detail["cached"] is True
        assert detail["owned"] is True
        assert detail["scorecard"]["rating"] == "BUY"
        # Events are cloned too: without them a cached run could not replay its pipeline.
        assert len(detail["events"]) == 3
        assert len(detail["evidence"]) == 1

    async def test_force_refresh_bypasses_the_cache(
        self, client, fake_redis, session_factory, sample_result
    ):
        from src.core.cache import analysis_cache_key

        await _seed_complete(
            session_factory, sample_result, cache_key=analysis_cache_key("AAPL", [], None)
        )
        r = await client.post("/analyses", json={"ticker": "AAPL", "force_refresh": True})
        assert r.json()["cached"] is False
        assert client.enqueued

    async def test_different_weights_are_a_different_cache_key(
        self, client, fake_redis, session_factory, sample_result
    ):
        from src.core.cache import analysis_cache_key

        await _seed_complete(
            session_factory, sample_result, cache_key=analysis_cache_key("AAPL", [], None)
        )
        r = await client.post("/analyses", json={"ticker": "AAPL", "weights": {"growth": 0.5}})
        assert r.json()["cached"] is False


class TestQuota:
    async def test_anonymous_visitors_get_three_runs(self, client, fake_redis):
        for i in range(3):
            r = await client.post("/analyses", json={"ticker": f"TCK{i}"})
            assert r.status_code == 202, i

        r = await client.post("/analyses", json={"ticker": "TCK9"})
        assert r.status_code == 429
        detail = r.json()["detail"]
        assert detail["code"] == "quota_exhausted"
        assert "account" in detail["message"].lower()

    async def test_the_gate_names_what_an_account_adds(self, client, fake_redis):
        usage = (await client.get("/usage")).json()
        assert usage["scope"] == "anon"
        assert len(usage["signup_benefits"]) >= 3
        assert any("history" in b.lower() for b in usage["signup_benefits"])

    async def test_a_failed_enqueue_refunds_the_run(self, client, fake_redis, monkeypatch):
        import src.worker as worker_module

        async def boom(analysis_id):
            raise RuntimeError("queue down")

        monkeypatch.setattr(worker_module, "enqueue_analysis", boom, raising=False)

        r = await client.post("/analyses", json={"ticker": "AAPL"})
        assert r.status_code == 503
        usage = (await client.get("/usage")).json()
        assert usage["used"] == 0, "a crash must not eat someone's allowance"

    async def test_the_ip_ceiling_stops_cookie_clearing(self, client, fake_redis):
        from src.config import settings

        # Simulate a network that has already hit today's ceiling.
        from src.core.ratelimit import hash_ip

        # ASGITransport reports 127.0.0.1; derive the key the same way the app does.
        key = f"quota:ip:{datetime.now(UTC).date().isoformat()}:{hash_ip('127.0.0.1')}"
        fake_redis.store[key] = str(settings.anon_ip_daily_cap)

        r = await client.post("/analyses", json={"ticker": "AAPL"})
        assert r.status_code == 429
        assert r.json()["detail"]["quota"]["scope"] == "ip"


class TestBudgetGuard:
    async def test_new_runs_stop_when_the_daily_cap_is_spent(self, client, fake_redis):
        from src.config import settings

        # The app keys spend by the UTC date; a local date breaks this test for the
        # hours between local midnight and UTC midnight.
        fake_redis.store[f"spend:{datetime.now(UTC).date().isoformat()}"] = str(
            settings.daily_cap_usd + 1
        )

        r = await client.post("/analyses", json={"ticker": "AAPL"})
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["code"] == "budget_exhausted"
        assert detail["budget"] == {"exhausted": True}, "no spend figures to the browser"

    async def test_cached_results_still_serve_with_the_budget_spent(
        self, client, fake_redis, session_factory, sample_result
    ):
        """Degrading gracefully means the cache keeps working, not that everything 503s."""
        from src.config import settings
        from src.core.cache import analysis_cache_key

        await _seed_complete(
            session_factory, sample_result, cache_key=analysis_cache_key("AAPL", [], None)
        )
        fake_redis.store[f"spend:{datetime.now(UTC).date().isoformat()}"] = str(
            settings.daily_cap_usd + 1
        )

        r = await client.post("/analyses", json={"ticker": "AAPL"})
        assert r.status_code == 202
        assert r.json()["cached"] is True


class TestReadEndpoints:
    async def test_detail_shape(self, client, fake_redis, session_factory, sample_result):
        aid = await _seed_complete(session_factory, sample_result)
        body = (await client.get(f"/analyses/{aid}")).json()

        assert body["status"] == "complete"
        assert body["memo"]["recommendation"] == "BUY"
        assert body["evidence"][0]["label"] == "S1"
        assert len(body["pipeline"]) == 10

    async def test_run_instrumentation_never_reaches_the_browser(
        self, client, fake_redis, session_factory, sample_result
    ):
        """Cost, tokens, model names and timings are the operator's, not the reader's."""
        aid = await _seed_complete(session_factory, sample_result)
        body = (await client.get(f"/analyses/{aid}")).json()

        assert "cost_usd" not in body
        assert "trace" not in body
        assert "cost" not in (body["blocks"] or {})
        assert "trace" not in (body["blocks"] or {})
        assert "tokens" not in str(body)

    async def test_unknown_id_is_404(self, client, fake_redis):
        assert (await client.get(f"/analyses/{uuid.uuid4()}")).status_code == 404

    async def test_anonymous_history_is_scoped_to_the_cookie(
        self, client, fake_redis, session_factory, sample_result
    ):
        await client.post("/analyses", json={"ticker": "AAPL"})
        anon = client.cookies.get("anon_id")
        assert anon

        await _seed_complete(session_factory, sample_result, ticker="ZZZZ", anon_id="someone-else")

        rows = (await client.get("/analyses")).json()
        assert [r["ticker"] for r in rows] == ["AAPL"]

    async def test_listing_filters_by_ticker(self, client, fake_redis):
        await client.post("/analyses", json={"ticker": "AAPL"})
        await client.post("/analyses", json={"ticker": "MSFT"})
        rows = (await client.get("/analyses", params={"ticker": "MSFT"})).json()
        assert [r["ticker"] for r in rows] == ["MSFT"]


class TestSSE:
    async def test_stream_replays_current_progress_on_connect(
        self, client, fake_redis, session_factory, sample_result
    ):
        """A mid-run refresh must never show an empty checklist."""
        aid = await _seed_complete(session_factory, sample_result)

        async with client.stream("GET", f"/analyses/{aid}/stream") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            assert resp.headers["x-accel-buffering"] == "no"
            first = ""
            async for chunk in resp.aiter_text():
                first += chunk
                if "\n\n" in first:
                    break

        assert '"type": "snapshot"' in first
        assert '"node": "ingest"' in first
        assert '"status": "pending"' in first  # nodes that never ran are shown as pending

    async def test_a_completed_run_replays_its_pipeline(
        self, client, fake_redis, session_factory, sample_result
    ):
        aid = await _seed_complete(session_factory, sample_result)
        body = (await client.get(f"/analyses/{aid}/stream")).text
        assert '"type": "replay"' in body
        assert '"replayed": true' in body
        assert '"type": "done"' in body

    async def test_stream_404s_for_an_unknown_analysis(self, client, fake_redis):
        assert (await client.get(f"/analyses/{uuid.uuid4()}/stream")).status_code == 404


class TestSharing:
    async def test_public_memo_needs_no_auth(
        self, client, fake_redis, session_factory, sample_result
    ):
        aid = await _seed_complete(session_factory, sample_result, slug=True)
        from src.db import repo

        async with session_factory() as db:
            row = await repo.get_analysis(db, aid)
        r = await client.get(f"/public/{row.public_slug}")
        assert r.status_code == 200
        assert r.json()["memo"]["recommendation"] == "BUY"
        assert r.json()["owned"] is False

    async def test_an_unknown_slug_is_404(self, client, fake_redis):
        assert (await client.get("/public/nope-nothing")).status_code == 404

    async def test_sharing_someone_elses_analysis_is_forbidden(
        self, client, fake_redis, session_factory, sample_result
    ):
        aid = await _seed_complete(session_factory, sample_result, anon_id="not-you")
        r = await client.post(f"/analyses/{aid}/share")
        assert r.status_code == 403


class TestPdf:
    async def test_completed_analysis_renders(
        self, client, fake_redis, session_factory, sample_result
    ):
        aid = await _seed_complete(session_factory, sample_result, anon_id=None, slug=True)
        r = await client.get(f"/analyses/{aid}/pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
        assert "attachment" in r.headers["content-disposition"]

    async def test_an_unfinished_analysis_cannot_be_exported(self, client, fake_redis):
        created = (await client.post("/analyses", json={"ticker": "AAPL"})).json()
        assert (await client.get(f"/analyses/{created['id']}/pdf")).status_code == 409


class TestAuthenticationRequired:
    async def test_a_visitor_keeps_a_watchlist_without_an_account(self, client, fake_redis):
        assert (await client.post("/watchlist/AAPL")).status_code == 201
        rows = (await client.get("/watchlist")).json()
        assert [r["ticker"] for r in rows] == ["AAPL"]
        assert (await client.delete("/watchlist/AAPL")).status_code == 204

    @pytest.mark.parametrize(
        "method,path",
        # The watchlist and compare are scoped to the anonymous cookie rather than an
        # account (see src/api/watchlist.py), so they are not in this list.
        [
            ("GET", "/tickers/AAPL/history"),
        ],
    )
    async def test_signed_out_requests_are_refused(self, client, fake_redis, method, path):
        r = await client.request(method, path)
        assert r.status_code == 401

    async def test_deleting_an_analysis_requires_an_account(
        self, client, fake_redis, session_factory, sample_result
    ):
        aid = await _seed_complete(session_factory, sample_result)
        assert (await client.delete(f"/analyses/{aid}")).status_code == 401

    @pytest.mark.parametrize("path", ["/analyses", "/usage", "/meta/pipeline", "/tickers/search"])
    async def test_the_core_product_is_open_to_anonymous_visitors(
        self, client, fake_redis, path
    ):
        assert (await client.get(path)).status_code == 200


class TestAuthenticatedFlow:
    async def _register_and_login(self, client, email="a@example.com"):
        await client.post(
            "/auth/register",
            json={"email": email, "password": "correct-horse-battery"},
        )
        r = await client.post(
            "/auth/login",
            data={"username": email, "password": "correct-horse-battery"},
        )
        assert r.status_code in (200, 204)

    async def test_registration_migrates_anonymous_analyses(self, client, fake_redis):
        """Someone who ran analyses before signing up must find them afterwards."""
        await client.post("/analyses", json={"ticker": "AAPL"})
        await client.post("/analyses", json={"ticker": "MSFT"})
        before = (await client.get("/analyses")).json()
        assert len(before) == 2

        await self._register_and_login(client)

        after = (await client.get("/analyses")).json()
        assert sorted(r["ticker"] for r in after) == ["AAPL", "MSFT"]

        usage = (await client.get("/usage")).json()
        assert usage["scope"] == "free"
        assert usage["authenticated"] is True

        from src.config import settings

        assert usage["limit"] == settings.free_account_credits

    async def test_watchlist_round_trip(self, client, fake_redis):
        await self._register_and_login(client, "w@example.com")

        assert (await client.post("/watchlist/nvda")).status_code == 201
        rows = (await client.get("/watchlist")).json()
        assert [r["ticker"] for r in rows] == ["NVDA"]

        assert (await client.post("/watchlist/NVDA")).status_code == 201  # idempotent
        assert len((await client.get("/watchlist")).json()) == 1

        assert (await client.delete("/watchlist/NVDA")).status_code == 204
        assert (await client.get("/watchlist")).json() == []

    async def test_compare_reports_what_is_missing(self, client, fake_redis):
        await self._register_and_login(client, "c@example.com")
        body = (await client.get("/compare", params={"tickers": "AAPL,MSFT"})).json()
        assert body["missing"] == ["AAPL", "MSFT"]
        assert all(col["available"] is False for col in body["columns"])

    async def test_delete_removes_only_your_own(self, client, fake_redis, session_factory, sample_result):
        await self._register_and_login(client, "d@example.com")
        mine = (await client.post("/analyses", json={"ticker": "AAPL"})).json()["id"]
        theirs = await _seed_complete(session_factory, sample_result, anon_id="other")

        assert (await client.delete(f"/analyses/{mine}")).status_code == 204
        assert (await client.delete(f"/analyses/{theirs}")).status_code == 404


class TestTickerSearch:
    async def test_empty_query_returns_suggestions(self, client, fake_redis):
        rows = (await client.get("/tickers/search")).json()
        assert rows
        assert all({"ticker", "name"} <= set(r) for r in rows)

    async def test_ranking_puts_an_exact_symbol_first(self, client, fake_redis, monkeypatch):
        import src.api.tickers as tickers_module

        index = [
            {"ticker": "AAP", "name": "Advance Auto Parts", "exchange": "NYSE"},
            {"ticker": "AAPL", "name": "Apple Inc.", "exchange": "Nasdaq"},
            {"ticker": "APLE", "name": "Apple Hospitality REIT", "exchange": "NYSE"},
        ]

        async def fake_index():
            return index

        monkeypatch.setattr(tickers_module, "_load_index", fake_index)

        rows = (await client.get("/tickers/search", params={"q": "AAPL"})).json()
        assert rows[0]["ticker"] == "AAPL"

        rows = (await client.get("/tickers/search", params={"q": "apple"})).json()
        assert {r["ticker"] for r in rows} == {"AAPL", "APLE"}



class TestUnknownTicker:
    async def test_a_company_name_is_refused_before_any_credit_is_used(
        self, client, fake_redis, monkeypatch
    ):
        import src.api.tickers as tickers_mod

        async def not_listed(symbol: str):
            return False, [{"ticker": "AAPL", "name": "Apple Inc."}]

        monkeypatch.setattr(tickers_mod, "check_ticker", not_listed)

        r = await client.post("/analyses", json={"ticker": "APPLE"})
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["code"] == "unknown_ticker"
        assert detail["suggestions"][0]["ticker"] == "AAPL"
        assert "AAPL" in detail["message"]
        assert (await client.get("/usage")).json()["used"] == 0


class TestSession:
    async def test_a_visitor_gets_null_not_401(self, client, fake_redis):
        r = await client.get("/auth/session")
        assert r.status_code == 200
        assert r.json() is None


class TestPasswordRules:
    async def test_a_short_password_is_refused_by_the_api_itself(self, client, fake_redis):
        r = await client.post(
            "/auth/register", json={"email": "short-pw@example.com", "password": "1"}
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "REGISTER_INVALID_PASSWORD"

    async def test_forgot_password_answers_the_same_for_unknown_addresses(
        self, client, fake_redis
    ):
        r = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
        assert r.status_code == 202


class TestClientErrors:
    async def test_a_browser_crash_report_is_accepted(self, client, fake_redis):
        r = await client.post(
            "/client-errors", json={"message": "boom", "path": "/dashboard", "digest": "abc"}
        )
        assert r.status_code == 204

    async def test_an_oversized_report_is_refused(self, client, fake_redis):
        r = await client.post("/client-errors", json={"message": "x" * 5000})
        assert r.status_code == 422
