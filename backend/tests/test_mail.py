"""Tests for outgoing email delivery, headers, and anti-spam templates."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.config import settings
from src.core.email_templates import (
    render_otp_email,
    render_password_reset_email,
    render_password_reset_otp_email,
)
from src.core.mail import send_email


def test_password_reset_otp_email_template():
    code = "581920"
    email = "investor@example.com"
    text, html = render_password_reset_otp_email(code, email)

    assert code in text
    assert email in text
    assert "https://assay.sahell.in" in text
    assert code in html
    assert email in html
    assert "Reset your password" in html
    assert "#22c55e" in html
    assert "#0a0a0a" in html
    assert "10 minutes" in html
    assert "font-size: 1px" not in html
    assert "opacity: 0" not in html


def test_otp_email_template_anti_spam_compliance():
    code = "729481"
    email = "trader@example.com"
    text, html = render_otp_email(code, email)

    # Core content present
    assert code in text
    assert email in text
    assert "https://assay.sahell.in" in text
    assert code in html
    assert email in html
    assert "https://assay.sahell.in" in html

    # Brand style preserved
    assert "#22c55e" in html
    assert "#0a0a0a" in html
    assert "10 minutes" in html

    # Anti-spam checks: NO low-contrast or invisible text hacks
    assert "font-size: 1px" not in html
    assert "; color: #fafafa" not in html
    assert "opacity: 0" not in html


def test_password_reset_email_template():
    link = "https://assay.sahell.in/reset-password?token=secret123"
    email = "trader@example.com"
    text, html = render_password_reset_email(link, email)

    assert link in text
    assert email in text
    assert link in html
    assert email in html
    assert "Reset Password" in html
    assert "font-size: 1px" not in html
    assert "opacity: 0" not in html


@pytest.mark.asyncio
async def test_send_email_adds_anti_spam_and_rfc_headers(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.testserver.com")
    monkeypatch.setattr(settings, "smtp_from", "Assay <no-reply@sahell.in>")
    monkeypatch.setattr(settings, "smtp_reply_to", "support@sahell.in")
    monkeypatch.setattr(settings, "smtp_user", "sahell")

    captured_msg = None

    def fake_send_sync(msg):
        nonlocal captured_msg
        captured_msg = msg

    with patch("src.core.mail._send_sync", side_effect=fake_send_sync):
        ok = await send_email(
            to="recipient@example.com",
            subject="123456 is your Assay verification code",
            text="Your code is 123456",
            html="<p>Your code is 123456</p>",
        )

    assert ok is True
    assert captured_msg is not None

    # Required RFC 5322 and anti-spam headers
    assert captured_msg["To"] == "recipient@example.com"
    assert captured_msg["From"] == "Assay <no-reply@sahell.in>"
    assert captured_msg["Subject"] == "123456 is your Assay verification code"
    assert captured_msg["Date"] is not None
    assert captured_msg["Message-ID"] is not None
    assert captured_msg["Message-ID"].startswith("<")
    assert captured_msg["Message-ID"].endswith("@sahell.in>")
    assert captured_msg["Auto-Submitted"] == "auto-generated"
    assert captured_msg["X-Auto-Response-Suppress"] == "All"
    assert captured_msg["Reply-To"] == "support@sahell.in"


@pytest.mark.asyncio
async def test_send_email_aligns_gmail_sender_to_prevent_spam(monkeypatch):
    """When using Gmail SMTP with a @gmail.com user, From must match the Gmail address
    to prevent SPF/DKIM alignment failure."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "s.sahil9752@gmail.com")
    monkeypatch.setattr(settings, "smtp_from", "Assay <no-reply@sahell.in>")
    monkeypatch.setattr(settings, "smtp_reply_to", "")

    captured_msg = None

    def fake_send_sync(msg):
        nonlocal captured_msg
        captured_msg = msg

    with patch("src.core.mail._send_sync", side_effect=fake_send_sync):
        ok = await send_email(
            to="recipient@example.com",
            subject="123456 is your Assay verification code",
            text="Your code is 123456",
        )

    assert ok is True
    assert captured_msg is not None
    # From rewritten to align with Gmail SPF/DKIM
    assert captured_msg["From"] == "Assay <s.sahil9752@gmail.com>"
    # Reply-To preserves original configured address
    assert captured_msg["Reply-To"] == "Assay <no-reply@sahell.in>"
    assert captured_msg["Message-ID"].endswith("@gmail.com>")
