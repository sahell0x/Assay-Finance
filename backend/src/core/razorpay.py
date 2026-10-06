"""The three things we need from Razorpay, over plain HTTPS.

The official SDK is synchronous (``requests``) and would block the event loop, and the
surface we use is two API calls plus two HMAC checks, so it is written out here instead.

* ``create_order`` — every Checkout starts from a server-created order, which fixes the
  amount so the browser cannot change what it pays.
* ``verify_payment_signature`` — Checkout hands the browser ``order_id``, ``payment_id``
  and a signature over the two; only someone with the key secret can produce it.
* ``verify_webhook_signature`` — the webhook body is signed with the webhook secret.
* ``refund_payment`` — give back a payment we took but will not honour (a purchase that
  landed over the test-mode limit).

Both checks use a constant-time comparison.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

import httpx

from ..config import settings

log = logging.getLogger(__name__)


class RazorpayError(RuntimeError):
    """Razorpay refused the request or could not be reached."""


async def create_order(*, amount_paise: int, currency: str, receipt: str, notes: dict) -> dict:
    """Create an order and return Razorpay's JSON (``id`` is the order id)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                f"{settings.razorpay_api_base.rstrip('/')}/orders",
                auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
                json={
                    "amount": amount_paise,
                    "currency": currency,
                    "receipt": receipt[:40],  # Razorpay's limit
                    "notes": notes,
                },
            )
    except httpx.HTTPError as exc:
        raise RazorpayError(f"could not reach Razorpay: {exc}") from exc
    if res.status_code >= 400:
        # The body names the problem (a bad key, an amount below the minimum) and holds
        # nothing secret, so it goes to the log for whoever is setting this up.
        log.error("razorpay order failed: %s %s", res.status_code, res.text[:500])
        raise RazorpayError(f"Razorpay returned {res.status_code}")
    return res.json()


async def refund_payment(payment_id: str, amount_paise: int) -> bool:
    """Refund a captured payment in full. Best effort: returns False rather than raising.

    A payment that is only authorised (not yet captured) cannot be refunded; Razorpay
    releases those by itself when they are never captured.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                f"{settings.razorpay_api_base.rstrip('/')}/payments/{payment_id}/refund",
                auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
                json={"amount": amount_paise},
            )
    except httpx.HTTPError as exc:
        log.error("razorpay refund of %s could not be sent: %s", payment_id, exc)
        return False
    if res.status_code >= 400:
        log.error("razorpay refund of %s failed: %s %s", payment_id, res.status_code,
                  res.text[:500])
        return False
    return True


def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    if not settings.razorpay_key_secret or not signature:
        return False
    expected = _hmac_hex(settings.razorpay_key_secret, f"{order_id}|{payment_id}".encode())
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    if not settings.razorpay_webhook_secret or not signature:
        return False
    expected = _hmac_hex(settings.razorpay_webhook_secret, body)
    return hmac.compare_digest(expected, signature)
