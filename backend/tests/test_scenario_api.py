"""The HTTP contract of the scenario endpoints.

These run without a database, unlike the rest of the API tests, and the reason is worth
stating. The other API tests need a real Postgres because they exercise repository
queries against JSONB, arrays, partial indexes and pgvector — a stand-in there would be
a test of the stand-in. The scenario routes touch the database exactly once, to fetch
one row by primary key, and everything after that is arithmetic over the JSON that row
holds. So the fetch is stubbed and the rest is real: real routing, real validation, real
status codes, real response bodies.

What is being pinned down is that the endpoint cannot do anything the analysis did not
already pay for — no queue, no quota, no model call — and that a client sending nonsense
gets the baseline rather than a 500 or a 422.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
import pytest_asyncio
from test_scenario import NEAR_BUY_METRICS, build_card

from src.analytics import scenario as sn

ANALYSIS_ID = "11111111-1111-1111-1111-111111111111"
NO_CARD_ID = "22222222-2222-2222-2222-222222222222"
MISSING_ID = "33333333-3333-3333-3333-333333333333"


@pytest.fixture
def card() -> dict:
    return build_card(NEAR_BUY_METRICS, sentiment=0.45)


@pytest_asyncio.fixture
async def client(card, monkeypatch) -> AsyncIterator:
    """The real app, with the single row fetch stubbed out."""
    import httpx

    from src.db import repo
    from src.db.session import get_session
    from src.main import app

    rows = {
        ANALYSIS_ID: SimpleNamespace(id=ANALYSIS_ID, ticker="TEST", scorecard=card),
        NO_CARD_ID: SimpleNamespace(id=NO_CARD_ID, ticker="TEST", scorecard=None),
    }

    async def fake_get_analysis(db, analysis_id):
        return rows.get(str(analysis_id))

    async def override_get_session() -> AsyncIterator[None]:
        yield None

    monkeypatch.setattr(repo, "get_analysis", fake_get_analysis)
    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c

    app.dependency_overrides.clear()


# ------------------------------------------------------------------------------- GET


@pytest.mark.asyncio
class TestScenarioSetup:
    async def test_it_returns_levers_for_every_scored_metric(self, client, card):
        r = await client.get(f"/analyses/{ANALYSIS_ID}/scenario")
        assert r.status_code == 200
        assert len(r.json()["levers"]) == len(sn.levers_for(card))

    async def test_it_reports_the_stored_rating_as_the_baseline(self, client, card):
        r = await client.get(f"/analyses/{ANALYSIS_ID}/scenario")
        baseline = r.json()["baseline"]
        assert baseline["rating"] == card["rating"]
        assert baseline["total"] == card["total"]

    async def test_it_aims_at_the_next_band_up_by_default(self, client):
        r = await client.get(f"/analyses/{ANALYSIS_ID}/scenario")
        assert r.json()["target_rating"] == "BUY"

    async def test_it_returns_paths_with_at_least_one_route(self, client):
        paths = (await client.get(f"/analyses/{ANALYSIS_ID}/scenario")).json()["paths"]
        assert any(p["reachable"] for p in paths)

    async def test_an_explicit_target_is_honoured(self, client):
        r = await client.get(f"/analyses/{ANALYSIS_ID}/scenario?target=SELL")
        assert r.json()["target_rating"] == "SELL"

    async def test_a_target_that_is_not_a_rating_is_rejected(self, client):
        r = await client.get(f"/analyses/{ANALYSIS_ID}/scenario?target=MOON")
        assert r.status_code == 422

    async def test_an_unknown_analysis_is_a_404(self, client):
        r = await client.get(f"/analyses/{MISSING_ID}/scenario")
        assert r.status_code == 404

    async def test_an_analysis_without_a_scorecard_is_a_409(self, client):
        r = await client.get(f"/analyses/{NO_CARD_ID}/scenario")
        assert r.status_code == 409
        assert "nothing to vary" in r.json()["detail"]

    async def test_a_malformed_id_is_a_422_not_a_500(self, client):
        r = await client.get("/analyses/not-a-uuid/scenario")
        assert r.status_code == 422


# ------------------------------------------------------------------------------ POST


@pytest.mark.asyncio
class TestRunScenario:
    async def test_an_empty_scenario_returns_the_stored_result(self, client, card):
        r = await client.post(f"/analyses/{ANALYSIS_ID}/scenario", json={})
        assert r.status_code == 200
        assert r.json()["total"] == card["total"]
        assert r.json()["rating"] == card["rating"]

    async def test_an_override_moves_the_composite(self, client, card):
        r = await client.post(
            f"/analyses/{ANALYSIS_ID}/scenario", json={"overrides": {"roic": 0.35}}
        )
        assert r.json()["total"] > card["total"]

    async def test_an_override_can_flip_the_rating(self, client, card):
        assert card["rating"] == "HOLD"
        path = next(
            p
            for p in sn.solve_paths(card, target_rating="BUY")
            if p["reachable"]
        )
        r = await client.post(
            f"/analyses/{ANALYSIS_ID}/scenario",
            json={"overrides": {path["lever"]: path["to"]}},
        )
        assert r.json()["rating"] == "BUY"

    async def test_the_response_carries_what_the_panel_renders(self, client):
        body = (await client.post(f"/analyses/{ANALYSIS_ID}/scenario", json={})).json()
        for key in ("total", "rating", "conviction", "dimension_scores",
                    "weights_applied", "distance_to_edge", "price_target", "overridden"):
            assert key in body, f"{key} missing from the scenario response"

    async def test_unknown_override_keys_fall_back_to_the_baseline(self, client, card):
        """A stale tab must get the stored answer, not a 422 and not a 500."""
        r = await client.post(
            f"/analyses/{ANALYSIS_ID}/scenario",
            json={"overrides": {"gross_margin_v2": 0.9, "nonsense": "x"}},
        )
        assert r.status_code == 200
        assert r.json()["total"] == card["total"]

    async def test_weights_can_be_reweighted_without_overrides(self, client, card):
        r = await client.post(
            f"/analyses/{ANALYSIS_ID}/scenario",
            json={"weights": {"valuation": 0.6, "profitability": 0.1}},
        )
        assert r.status_code == 200
        assert r.json()["total"] != card["total"]

    async def test_a_weight_for_an_unknown_dimension_is_dropped(self, client, card):
        r = await client.post(
            f"/analyses/{ANALYSIS_ID}/scenario", json={"weights": {"vibes": 0.9}}
        )
        assert r.json()["weights_applied"] == card["weights_applied"]

    async def test_the_price_lever_is_accepted_over_http(self, client, card):
        r = await client.post(
            f"/analyses/{ANALYSIS_ID}/scenario",
            json={"overrides": {sn.PRICE_LEVER: 120.0}},
        )
        body = r.json()
        assert body["price_scenario"]["move"] == pytest.approx(-0.5)
        assert body["dimension_scores"]["valuation"] > card["dimension_scores"]["valuation"]

    async def test_an_oversized_payload_is_refused(self, client):
        r = await client.post(
            f"/analyses/{ANALYSIS_ID}/scenario",
            json={"overrides": {f"m{i}": 1.0 for i in range(200)}},
        )
        assert r.status_code == 422

    async def test_an_analysis_without_a_scorecard_is_a_409(self, client):
        r = await client.post(f"/analyses/{NO_CARD_ID}/scenario", json={})
        assert r.status_code == 409

    async def test_an_unknown_analysis_is_a_404(self, client):
        r = await client.post(f"/analyses/{MISSING_ID}/scenario", json={})
        assert r.status_code == 404

    async def test_it_never_enqueues_anything(self, client, monkeypatch):
        """A scenario is arithmetic over a stored row. If it ever reaches the queue,
        it has stopped being free and started competing for the single worker slot."""
        import src.worker as worker_module

        called: list[str] = []

        async def boom(analysis_id: str) -> None:
            called.append(analysis_id)

        monkeypatch.setattr(worker_module, "enqueue_analysis", boom, raising=False)
        await client.post(
            f"/analyses/{ANALYSIS_ID}/scenario", json={"overrides": {"roic": 0.3}}
        )
        assert called == []
