"""Outgoing email.

The standard library's smtplib, run in a thread: one message per password reset does
not justify a dependency. With no SMTP_HOST configured the message is logged instead of
sent, so every flow that sends mail still works end to end in development.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from ..config import settings

log = logging.getLogger(__name__)


def _send_sync(msg: EmailMessage) -> None:
    context = ssl.create_default_context()
    if settings.smtp_ssl:
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=20, context=context
        )
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
    with server:
        if settings.smtp_starttls and not settings.smtp_ssl:
            server.starttls(context=context)
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


async def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Send one message. Returns False, and logs why, rather than raising: a mail
    outage must not turn into a 500 on the page that asked for the email."""
    if not settings.smtp_host:
        log.warning("SMTP_HOST is not set; email to %s not sent. Body:\n%s", to, text)
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        await asyncio.to_thread(_send_sync, msg)
        return True
    except Exception as exc:
        log.error("could not send email to %s: %s", to, exc)
        return False
