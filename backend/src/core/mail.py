"""Outgoing email.

The standard library's smtplib, run in a thread: one message per password reset does
not justify a dependency. With no SMTP_HOST configured the message is logged instead of
sent, so every flow that sends mail still works end to end in development.
"""

from __future__ import annotations

import asyncio
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr
import logging
import smtplib
import ssl

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
            # Strip spaces commonly present in Google App Passwords (e.g. "abcd efgh ijkl mnop")
            clean_password = (settings.smtp_password or "").replace(" ", "")
            server.login(settings.smtp_user, clean_password)
        server.send_message(msg)


async def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Send one message. Returns False, and logs why, rather than raising: a mail
    outage must not turn into a 500 on the page that asked for the email."""
    if not settings.smtp_host:
        log.warning("SMTP_HOST is not set; email to %s not sent. Body:\n%s", to, text)
        return False

    display_name, from_email = parseaddr(settings.smtp_from)
    effective_from = settings.smtp_from

    # Anti-Spam / SPF & DKIM Alignment check:
    # When sending through smtp.gmail.com with a personal Gmail account (e.g. user@gmail.com),
    # Gmail signs messages with DKIM domain d=gmail.com. If the From header domain is custom
    # (e.g. no-reply@sahell.in), SPF and DKIM alignment fail on recipient servers (Gmail,
    # Outlook, Yahoo, etc.), immediately routing the message to SPAM.
    # To ensure deliverability, align the From address with the authenticated Gmail account
    # while preserving the brand display name, and route replies to the original address.
    if (
        "smtp.gmail.com" in settings.smtp_host.lower()
        and settings.smtp_user
        and settings.smtp_user.lower().endswith(("@gmail.com", "@googlemail.com"))
    ):
        if not from_email.lower().endswith(("@gmail.com", "@googlemail.com")):
            log.warning(
                "SMTP_FROM address '%s' does not match Gmail user '%s'. Rewriting From header to '%s' "
                "with display name '%s' to satisfy SPF/DKIM/DMARC alignment.",
                from_email,
                settings.smtp_user,
                settings.smtp_user,
                display_name or "Assay",
            )
            effective_from = formataddr((display_name or "Assay", settings.smtp_user))

    msg = EmailMessage()
    msg["From"] = effective_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)

    # Message-ID: Required for RFC 5322 compliance and to avoid spam penalty (MISSING_MID)
    _, sender_addr = parseaddr(effective_from)
    domain = sender_addr.split("@")[-1] if "@" in sender_addr else "localhost"
    msg["Message-ID"] = make_msgid(domain=domain)

    # Transactional & automated suppression headers: Tells mail systems this is an automated OTP/transaction
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Auto-Response-Suppress"] = "All"

    # Reply-To header: ensure replies reach the intended destination
    reply_to = getattr(settings, "smtp_reply_to", "").strip()
    if reply_to:
        msg["Reply-To"] = reply_to
    elif from_email and from_email != sender_addr:
        msg["Reply-To"] = settings.smtp_from

    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        await asyncio.to_thread(_send_sync, msg)
        return True
    except Exception as exc:
        log.error("could not send email to %s: %s", to, exc)
        return False
