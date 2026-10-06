"""Credit packs and the credit ledger.

In order of how much it would hurt to get wrong: that a payment grants its credits
exactly once however many times it is confirmed, that nothing is granted without a
valid Razorpay signature, that two runs cannot both spend the last credit, that a
failed run gives its credit back once, and that free credits are used before bought ones.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid

import httpx
import pytest
import respx

from src.config import settings

pytestmark = pytest.mark.asyncio

KEY_SECRET = "test_key_secret"
WEBHOOK_SECRET = "test_webhook_secret"


@pytest.fixture(autouse=True)
def known_tickers(monkeypatch):
    import src.api.tickers as tickers_mod

    async def listed(symbol: str):
        return True, []

    monkeypatch.setattr(tickers_mod, "check_ticker", listed)


@pytest.fixture
def payments(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_abc")
    monkeypatch.setattr(settings, "razorpay_key_secret", KEY_SECRET)
    monkeypatch.setattr(settings, "razorpay_webhook_secret", WEBHOOK_SECRET)


@pytest.fixture
def one_free_credit(monkeypatch):
    monkeypatch.setattr(settings, "free_account_credits", 1)


@pytest.fixture
def two_free_credits(monkeypatch):
    monkeypatch.setattr(settings, "free_account_credits", 2)


async def _login(client, email="buyer@example.com"):
    await client.post("/auth/register", json={"email": email, "password": "correct-horse-battery"})
    r = await client.post(
        "/auth/login", data={"username": email, "password": "correct-horse-battery"}
    )
    assert r.status_code in (200, 204)


async def _user_id(session_factory, email="buyer@example.com") -> uuid.UUID:
    from sqlalchemy import select

    from src.db.models import User

    async with session_factory() as db:
        return (await db.execute(select(User.id).where(User.email == email))).scalar_one()


async def _set_balance(session_factory, user_id, credits):
    from sqlalchemy import update

    from src.db.models import User

    async with session_factory() as db:
        await db.execute(update(User).where(User.id == user_id).values(paid_credits=credits))
        await db.commit()


def _sign(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


async def _order(client, pack_id="pro", order_id="order_TEST1"):
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{settings.razorpay_api_base}/orders").mock(
            return_value=httpx.Response(200, json={"id": order_id, "status": "created"})
        )
        r = await client.post("/billing/orders", json={"pack_id": pack_id})
    assert r.status_code == 200, r.text
    sent = json.loads(route.calls[0].request.content)
    return r.json(), sent


def _webhook_body(order_id, payment_id, amount, event="payment.captured", currency="INR"):
    return json.dumps({
        "event": event,
        "payload": {"payment": {"entity": {
            "id": payment_id, "order_id": order_id, "amount": amount,
            "currency": currency, "status": "captured",
        }}},
    }).encode()


# ----------------------------------------------------------------------- the shop


class TestPacks:
    async def test_packs_are_public_and_priced_server_side(self, client, fake_redis):
        body = (await client.get("/billing/packs")).json()
        ids = [p["id"] for p in body["packs"]]
        assert ids == ["starter", "pro", "power"]
        pro = next(p for p in body["packs"] if p["id"] == "pro")
        assert (pro["credits"], pro["price_paise"], pro["popular"]) == (5, 5900, True)

    async def test_the_shop_says_when_payments_are_not_set_up(self, client, fake_redis):
        assert (await client.get("/billing/packs")).json()["enabled"] is False
        await _login(client)
        r = await client.post("/billing/orders", json={"pack_id": "pro"})
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "payments_disabled"

    async def test_buying_needs_an_account(self, client, fake_redis, payments):
        r = await client.post("/billing/orders", json={"pack_id": "pro"})
        assert r.status_code == 401


class TestOrders:
    async def test_the_order_amount_comes_from_the_pack_not_the_browser(
        self, client, fake_redis, payments
    ):
        await _login(client)
        body, sent = await _order(client, "starter")
        assert body["order_id"] == "order_TEST1"
        assert body["key_id"] == "rzp_test_abc"
        assert sent["amount"] == 2900
        assert sent["currency"] == "INR"
        assert body["prefill"]["email"] == "buyer@example.com"

    async def test_an_unknown_pack_is_refused(self, client, fake_redis, payments):
        await _login(client)
        r = await client.post("/billing/orders", json={"pack_id": "free-money"})
        assert r.status_code == 404

    async def test_a_razorpay_outage_is_a_clear_error(self, client, fake_redis, payments):
        await _login(client)
        with respx.mock() as mock:
            mock.post(f"{settings.razorpay_api_base}/orders").mock(
                return_value=httpx.Response(401, json={"error": {"description": "bad key"}})
            )
            r = await client.post("/billing/orders", json={"pack_id": "pro"})
        assert r.status_code == 502
        assert "Nothing was charged" in r.json()["detail"]["message"]


# ------------------------------------------------------------------ confirmation


class TestVerify:
    async def test_a_valid_signature_grants_the_pack_once(
        self, client, fake_redis, payments
    ):
        await _login(client)
        await _order(client, "pro")
        payload = {
            "razorpay_order_id": "order_TEST1",
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": _sign(KEY_SECRET, b"order_TEST1|pay_1"),
        }
        first = await client.post("/billing/verify", json=payload)
        assert first.status_code == 200
        assert first.json()["paid_credits"] == 5
        assert first.json()["newly_granted"] is True

        again = await client.post("/billing/verify", json=payload)
        assert again.json()["paid_credits"] == 5, "a retry must not grant twice"
        assert again.json()["newly_granted"] is False

        usage = (await client.get("/usage")).json()
        assert usage["paid_credits"] == 5
        assert usage["remaining"] == settings.free_account_credits + 5

        items = (await client.get("/billing/activity")).json()["items"]
        assert [(t["kind"], t["delta"], t["pack_name"], t["amount_paise"]) for t in items] == [
            ("purchase", 5, "Pro", 5900)
        ]

    async def test_a_forged_signature_grants_nothing(self, client, fake_redis, payments):
        await _login(client)
        await _order(client)
        r = await client.post("/billing/verify", json={
            "razorpay_order_id": "order_TEST1",
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": _sign("wrong-secret", b"order_TEST1|pay_1"),
        })
        assert r.status_code == 400
        assert (await client.get("/usage")).json()["paid_credits"] == 0

    async def test_someone_elses_order_cannot_be_claimed(
        self, client, fake_redis, payments
    ):
        await _login(client, "owner@example.com")
        await _order(client)
        await client.post("/auth/logout")
        client.cookies.clear()
        await _login(client, "thief@example.com")

        r = await client.post("/billing/verify", json={
            "razorpay_order_id": "order_TEST1",
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": _sign(KEY_SECRET, b"order_TEST1|pay_1"),
        })
        assert r.status_code == 404
        assert (await client.get("/usage")).json()["paid_credits"] == 0


class TestWebhook:
    async def test_a_captured_payment_grants_credits_without_the_browser(
        self, client, fake_redis, payments, session_factory
    ):
        await _login(client)
        await _order(client, "power")
        body = _webhook_body("order_TEST1", "pay_9", 9900)
        r = await client.post(
            "/billing/webhook", content=body,
            headers={"X-Razorpay-Signature": _sign(WEBHOOK_SECRET, body)},
        )
        assert r.json()["granted"] is True
        assert (await client.get("/usage")).json()["paid_credits"] == 10

    async def test_webhook_and_browser_together_grant_once(
        self, client, fake_redis, payments
    ):
        await _login(client)
        await _order(client, "pro")
        await client.post("/billing/verify", json={
            "razorpay_order_id": "order_TEST1",
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": _sign(KEY_SECRET, b"order_TEST1|pay_1"),
        })
        for event in ("payment.captured", "order.paid"):
            body = _webhook_body("order_TEST1", "pay_1", 5900, event=event)
            r = await client.post(
                "/billing/webhook", content=body,
                headers={"X-Razorpay-Signature": _sign(WEBHOOK_SECRET, body)},
            )
            assert r.json()["granted"] is False
        assert (await client.get("/usage")).json()["paid_credits"] == 5

    async def test_an_unsigned_webhook_is_refused(self, client, fake_redis, payments):
        await _login(client)
        await _order(client)
        body = _webhook_body("order_TEST1", "pay_1", 5900)
        r = await client.post(
            "/billing/webhook", content=body, headers={"X-Razorpay-Signature": "nope"}
        )
        assert r.status_code == 400
        assert (await client.get("/usage")).json()["paid_credits"] == 0

    async def test_a_payment_for_the_wrong_amount_grants_nothing(
        self, client, fake_redis, payments
    ):
        await _login(client)
        await _order(client, "power")
        body = _webhook_body("order_TEST1", "pay_1", 100)
        r = await client.post(
            "/billing/webhook", content=body,
            headers={"X-Razorpay-Signature": _sign(WEBHOOK_SECRET, body)},
        )
        assert r.status_code == 200  # acknowledged, so Razorpay stops retrying
        assert (await client.get("/usage")).json()["paid_credits"] == 0

    async def test_other_events_are_acknowledged_and_ignored(
        self, client, fake_redis, payments
    ):
        body = json.dumps({"event": "refund.created", "payload": {}}).encode()
        r = await client.post(
            "/billing/webhook", content=body,
            headers={"X-Razorpay-Signature": _sign(WEBHOOK_SECRET, body)},
        )
        assert r.status_code == 200


# -------------------------------------------------------------------- spending


class TestSpending:
    async def test_free_credits_are_used_before_bought_ones(
        self, client, fake_redis, session_factory, one_free_credit
    ):
        await _login(client)
        uid = await _user_id(session_factory)
        await _set_balance(session_factory, uid, 2)

        await client.post("/analyses", json={"ticker": "AAPL"})
        usage = (await client.get("/usage")).json()
        assert (usage["free_remaining"], usage["paid_credits"]) == (0, 2)

        await client.post("/analyses", json={"ticker": "MSFT"})
        usage = (await client.get("/usage")).json()
        assert (usage["free_remaining"], usage["paid_credits"]) == (0, 1)
        assert usage["remaining"] == 1

        items = (await client.get("/billing/activity")).json()["items"]
        assert [(t["kind"], t["source"], t["delta"], t["ticker"]) for t in items] == [
            ("spend", "bought", -1, "MSFT"),
            ("free_spend", "free", -1, "AAPL"),
        ]

    async def test_out_of_everything_points_at_the_shop(
        self, client, fake_redis, one_free_credit, payments
    ):
        await _login(client)
        await client.post("/analyses", json={"ticker": "AAPL"})
        r = await client.post("/analyses", json={"ticker": "MSFT"})
        assert r.status_code == 429
        detail = r.json()["detail"]
        assert detail["code"] == "quota_exhausted"
        assert "credit pack" in detail["message"]
        assert detail["usage"]["exhausted"] is True

    async def test_deleting_a_run_does_not_give_the_free_credit_back(
        self, client, fake_redis, one_free_credit
    ):
        await _login(client)
        created = (await client.post("/analyses", json={"ticker": "AAPL"})).json()
        await client.delete(f"/analyses/{created['id']}")
        assert (await client.get("/usage")).json()["free_remaining"] == 0
        assert (await client.post("/analyses", json={"ticker": "AAPL"})).status_code == 429

    async def test_a_failed_paid_run_refunds_its_credit_once(
        self, client, fake_redis, session_factory, one_free_credit
    ):
        from src.db import credits, repo

        await _login(client)
        uid = await _user_id(session_factory)
        await _set_balance(session_factory, uid, 1)
        await client.post("/analyses", json={"ticker": "AAPL"})  # free
        paid = (await client.post("/analyses", json={"ticker": "MSFT"})).json()
        assert (await client.get("/usage")).json()["paid_credits"] == 0

        aid = uuid.UUID(paid["id"])
        async with session_factory() as db:
            await repo.set_status(db, aid, status="failed", error="x")
            assert await credits.refund_run(db, aid) is True
            assert await credits.refund_run(db, aid) is False  # the sweep, again
        assert (await client.get("/usage")).json()["paid_credits"] == 1

        items = (await client.get("/billing/activity?kind=usage")).json()["items"]
        assert [t["kind"] for t in items] == ["refund", "spend", "free_spend"]

    async def test_a_failed_free_run_gives_the_free_credit_back(
        self, client, fake_redis, session_factory, one_free_credit
    ):
        from src.db import credits, repo

        await _login(client)
        created = (await client.post("/analyses", json={"ticker": "AAPL"})).json()
        async with session_factory() as db:
            await repo.set_status(db, uuid.UUID(created["id"]), status="failed", error="x")
            await credits.refund_run(db, uuid.UUID(created["id"]))
        assert (await client.get("/usage")).json()["free_remaining"] == 1

    async def test_a_failed_enqueue_refunds_a_bought_credit(
        self, client, fake_redis, session_factory, one_free_credit, monkeypatch
    ):
        import src.worker as worker_module

        await _login(client)
        uid = await _user_id(session_factory)
        await _set_balance(session_factory, uid, 1)
        await client.post("/analyses", json={"ticker": "AAPL"})  # free

        async def boom(analysis_id):
            raise RuntimeError("queue down")

        monkeypatch.setattr(worker_module, "enqueue_analysis", boom, raising=False)
        r = await client.post("/analyses", json={"ticker": "MSFT"})
        assert r.status_code == 503
        assert (await client.get("/usage")).json()["paid_credits"] == 1

    async def test_two_runs_cannot_both_spend_the_last_credit(
        self, client, fake_redis, session_factory, one_free_credit
    ):
        from src.db import credits

        await _login(client)
        uid = await _user_id(session_factory)
        await _set_balance(session_factory, uid, 1)
        await client.post("/analyses", json={"ticker": "AAPL"})  # uses the free credit

        async def attempt(ticker):
            async with session_factory() as db:
                return await credits.create_charged_run(
                    db, user_id=uid, ticker=ticker, peer_tickers=None, weights=None,
                    cache_key=f"k-{ticker}",
                )

        results = await asyncio.gather(*(attempt(t) for t in ("MSFT", "NVDA", "GOOG")))
        assert sum(r is not None for r in results) == 1
        assert (await client.get("/usage")).json()["paid_credits"] == 0


# ------------------------------------------------------------------- test mode


async def _buy(client, pack_id, n):
    """Order and pay one pack through the browser path. Returns the verify response."""
    order_id, payment_id = f"order_T{n}", f"pay_T{n}"
    await _order(client, pack_id, order_id)
    return await client.post("/billing/verify", json={
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": _sign(KEY_SECRET, f"{order_id}|{payment_id}".encode()),
    })


class TestTestMode:
    async def test_a_live_key_is_refused_in_test_mode(self, client, fake_redis, payments,
                                                      monkeypatch):
        monkeypatch.setattr(settings, "razorpay_key_id", "rzp_live_real")
        assert (await client.get("/billing/packs")).json()["enabled"] is False
        await _login(client)
        r = await client.post("/billing/orders", json={"pack_id": "starter"})
        assert r.status_code == 503

    async def test_the_shop_reports_the_limit(self, client, fake_redis, payments):
        await _login(client)
        await _buy(client, "pro", 1)
        limits = (await client.get("/billing/packs")).json()["limits"]
        assert limits == {
            "max_purchases": 3, "max_credits": 10, "purchases_used": 1,
            "credits_bought": 5, "purchases_left": 2, "credits_left": 5,
        }

    async def test_an_order_past_the_credit_limit_is_refused_before_checkout(
        self, client, fake_redis, payments
    ):
        await _login(client)
        await _buy(client, "pro", 1)  # 5 of 10
        with respx.mock(assert_all_called=False) as mock:
            route = mock.post(f"{settings.razorpay_api_base}/orders")
            r = await client.post("/billing/orders", json={"pack_id": "power"})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "test_limit_reached"
        assert "up to 5 more" in r.json()["detail"]["message"]
        assert not route.called, "no Razorpay order for a purchase we would refuse"

        assert (await _buy(client, "pro", 2)).status_code == 200  # exactly 10 is fine

    async def test_no_more_than_three_purchases(self, client, fake_redis, payments):
        await _login(client)
        for n in range(3):
            assert (await _buy(client, "starter", n)).status_code == 200
        r = await client.post("/billing/orders", json={"pack_id": "starter"})
        assert r.status_code == 409
        assert "3 test purchases" in r.json()["detail"]["message"]
        assert (await client.get("/usage")).json()["paid_credits"] == 6

    async def test_paying_several_open_orders_cannot_beat_the_limit(
        self, client, fake_redis, payments
    ):
        """Open two Power orders while under the limit, then pay both. The second
        payment must add nothing and be refunded."""
        await _login(client)
        await _order(client, "power", "order_A")
        await _order(client, "power", "order_B")

        ok = await client.post("/billing/verify", json={
            "razorpay_order_id": "order_A", "razorpay_payment_id": "pay_A",
            "razorpay_signature": _sign(KEY_SECRET, b"order_A|pay_A"),
        })
        assert ok.status_code == 200

        with respx.mock() as mock:
            refund = mock.post(f"{settings.razorpay_api_base}/payments/pay_B/refund").mock(
                return_value=httpx.Response(200, json={"id": "rfnd_1"})
            )
            r = await client.post("/billing/verify", json={
                "razorpay_order_id": "order_B", "razorpay_payment_id": "pay_B",
                "razorpay_signature": _sign(KEY_SECRET, b"order_B|pay_B"),
            })
        assert r.status_code == 409
        assert "refunded" in r.json()["detail"]["message"]
        assert refund.called
        assert json.loads(refund.calls[0].request.content) == {"amount": 9900}
        assert (await client.get("/usage")).json()["paid_credits"] == 10

        # The webhook for the same payment arriving later changes nothing either.
        body = _webhook_body("order_B", "pay_B", 9900)
        with respx.mock(assert_all_called=False) as mock:
            again = mock.post(f"{settings.razorpay_api_base}/payments/pay_B/refund")
            w = await client.post(
                "/billing/webhook", content=body,
                headers={"X-Razorpay-Signature": _sign(WEBHOOK_SECRET, body)},
            )
        assert w.json()["outcome"] == "already"
        assert not again.called, "refunded once, not once per confirmation"

    async def test_live_mode_has_no_limit(self, client, fake_redis, payments, monkeypatch):
        monkeypatch.setattr(settings, "payments_test_mode", False)
        await _login(client)
        for n in range(4):
            assert (await _buy(client, "power", n)).status_code == 200
        assert (await client.get("/usage")).json()["paid_credits"] == 40
        assert (await client.get("/billing/packs")).json()["limits"] is None


# ------------------------------------------------------------ one-time free credits


class TestFreeCredits:
    async def test_free_credits_are_one_time_not_monthly(
        self, client, fake_redis, session_factory, two_free_credits
    ):
        """A run from months ago still counts: the free credits never reset."""
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import update

        from src.db.models import Analysis

        await _login(client)
        created = (await client.post("/analyses", json={"ticker": "AAPL"})).json()
        async with session_factory() as db:
            await db.execute(
                update(Analysis)
                .where(Analysis.id == uuid.UUID(created["id"]))
                .values(created_at=datetime.now(UTC) - timedelta(days=90))
            )
            await db.commit()
        usage = (await client.get("/usage")).json()
        assert (usage["used"], usage["free_remaining"]) == (1, 1)

    async def test_runs_from_before_the_ledger_count_whenever_they_were(
        self, client, fake_redis, session_factory, two_free_credits
    ):
        from src.db import repo

        await _login(client)
        uid = await _user_id(session_factory)
        async with session_factory() as db:
            await repo.create_analysis(
                db, ticker="OLD", peer_tickers=None, weights=None, user_id=uid,
                anon_id=None, cache_key="old",
            )  # credit_source NULL, as every row was before the ledger
        assert (await client.get("/usage")).json()["free_remaining"] == 1

    async def test_anonymous_runs_do_not_eat_the_account_credits(
        self, client, fake_redis, two_free_credits
    ):
        await client.post("/analyses", json={"ticker": "AAPL"})
        await client.post("/analyses", json={"ticker": "MSFT"})
        await _login(client)
        usage = (await client.get("/usage")).json()
        assert (usage["used"], usage["free_remaining"]) == (0, 2)
        assert len((await client.get("/analyses")).json()) == 2  # still theirs

    async def test_with_no_way_to_buy_the_message_does_not_offer_the_shop(
        self, client, fake_redis, one_free_credit
    ):
        await _login(client)
        await client.post("/analyses", json={"ticker": "AAPL"})
        r = await client.post("/analyses", json={"ticker": "MSFT"})
        assert r.status_code == 429
        message = r.json()["detail"]["message"]
        assert "credit pack" not in message
        assert "does not sell any more" in message
        assert (await client.get("/usage")).json()["can_buy"] is False

    async def test_can_buy_follows_the_test_limit(self, client, fake_redis, payments):
        await _login(client)
        assert (await client.get("/usage")).json()["can_buy"] is True
        await _buy(client, "power", 1)  # all 10 test credits
        assert (await client.get("/usage")).json()["can_buy"] is False


# ------------------------------------------------------------------ spend tracking


class TestTracking:
    async def test_summary_adds_up(
        self, client, fake_redis, payments, session_factory, one_free_credit
    ):
        from src.db import credits, repo

        await _login(client)
        await _buy(client, "pro", 1)                          # +5 bought, Rs 59
        await client.post("/analyses", json={"ticker": "AAPL"})  # free
        await client.post("/analyses", json={"ticker": "MSFT"})  # bought
        failed = (await client.post("/analyses", json={"ticker": "NVDA"})).json()
        async with session_factory() as db:                   # fails, refunded
            await repo.set_status(db, uuid.UUID(failed["id"]), status="failed", error="x")
            await credits.refund_run(db, uuid.UUID(failed["id"]))

        body = (await client.get("/billing/summary")).json()
        assert body["credits_used"] == 2
        assert (body["free_used"], body["free_total"], body["bought_used"]) == (1, 1, 1)
        assert (body["credits_bought"], body["paid_balance"]) == (5, 4)
        assert (body["purchases"], body["amount_spent_paise"]) == (1, 5900)
        assert body["refunds"] == 1
        assert len(body["daily"]) == 30
        assert body["daily"][-1] == {
            "date": body["daily"][-1]["date"], "free": 1, "bought": 1,
        }

    async def test_activity_pages_and_filters(
        self, client, fake_redis, session_factory, payments
    ):
        await _login(client)
        uid = await _user_id(session_factory)
        await _set_balance(session_factory, uid, 50)
        for i in range(7):
            await client.post("/analyses", json={"ticker": f"T{i}"})
        await _buy(client, "starter", 1)

        first = (await client.get("/billing/activity?limit=5")).json()
        assert len(first["items"]) == 5 and first["next"] is not None
        assert first["items"][0]["kind"] == "purchase"
        rest = (await client.get(f"/billing/activity?limit=5&before={first['next']}")).json()
        assert len(rest["items"]) == 3 and rest["next"] is None
        ids = [r["id"] for r in first["items"] + rest["items"]]
        assert ids == sorted(ids, reverse=True) and len(set(ids)) == 8

        purchases = (await client.get("/billing/activity?kind=purchases")).json()["items"]
        assert [p["kind"] for p in purchases] == ["purchase"]
        usage = (await client.get("/billing/activity?kind=usage")).json()["items"]
        assert len(usage) == 7 and all(u["delta"] == -1 for u in usage)

    async def test_activity_exports_as_csv(self, client, fake_redis, payments):
        await _login(client)
        await _buy(client, "pro", 1)
        await client.post("/analyses", json={"ticker": "AAPL"})
        r = await client.get("/billing/activity.csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("date_utc,activity,credit_type,credits")
        assert any(",purchase,bought,5,,Pro,59.00,INR," in line for line in lines)
        assert any(",free_spend,free,-1,AAPL," in line for line in lines)

    async def test_payments_list_every_checkout_with_its_outcome(
        self, client, fake_redis, payments
    ):
        await _login(client)
        await _buy(client, "starter", 1)
        await _order(client, "pro", "order_OPEN")  # never paid
        items = (await client.get("/billing/payments")).json()["items"]
        assert [(p["pack_name"], p["status"]) for p in items] == [
            ("Pro", "pending"), ("Starter", "paid"),
        ]
        paid = items[1]
        assert (paid["amount_paise"], paid["payment_id"]) == (2900, "pay_T1")

    async def test_tracking_needs_an_account(self, client, fake_redis):
        for path in ("/billing/summary", "/billing/activity", "/billing/payments",
                     "/billing/activity.csv"):
            assert (await client.get(path)).status_code == 401, path
