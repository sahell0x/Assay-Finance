"""Error monitoring.

Off unless SENTRY_DSN is set, and harmless if the package is missing. Personal data is
not sent: no request bodies, no cookies, no IP addresses, and email addresses are
scrubbed from messages, because an error report is not a place to leak a user.
"""

from __future__ import annotations

import logging
import re

from ..config import settings

log = logging.getLogger(__name__)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_enabled = False


def _scrub(event: dict, hint: dict) -> dict:
    request = event.get("request") or {}
    request.pop("cookies", None)
    request.pop("data", None)
    headers = request.get("headers") or {}
    for key in list(headers):
        if key.lower() in {"cookie", "authorization", "x-forwarded-for"}:
            headers[key] = "[removed]"
    user = event.get("user") or {}
    user.pop("ip_address", None)
    user.pop("email", None)
    for entry in (event.get("logentry"), event.get("message")):
        if isinstance(entry, dict) and isinstance(entry.get("message"), str):
            entry["message"] = _EMAIL.sub("[email]", entry["message"])
    return event


def init_monitoring(component: str) -> bool:
    """Start Sentry for this process ("api" or "worker"). Returns whether it is on."""
    global _enabled
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        log.warning("SENTRY_DSN is set but sentry-sdk is not installed; monitoring is off")
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment="production" if settings.is_prod else settings.env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        before_send=_scrub,
        server_name=component,
    )
    _enabled = True
    log.info("error monitoring on (%s)", component)
    return True


def capture_message(message: str, **extra) -> None:
    """Report something that is not an exception (a browser-side crash, say)."""
    if not _enabled:
        return
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        for k, v in extra.items():
            scope.set_extra(k, v)
        sentry_sdk.capture_message(_EMAIL.sub("[email]", message), level="error")
