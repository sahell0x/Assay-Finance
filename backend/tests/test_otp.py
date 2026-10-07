"""Tests for the email OTP signup flow."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.config import settings
from src.core.email_templates import render_otp_email
from src.db.models import SignupOTP


def test_render_otp_email_template():
    code = "492815"
    email = "test@example.com"
    text, html = render_otp_email(code, email)

    assert code in text
    assert email in text
    assert "Assay" in text

    assert code in html
    assert email in html
    assert "Assay" in html
    assert "#22c55e" in html  # Brand green accent
    assert "#0a0a0a" in html  # Brand ink color
    assert "10 minutes" in html


@pytest.mark.asyncio
class TestSignupOTPFlow:
    async def test_otp_send_success(self, client, session_factory):
        email = "newuser@example.com"
        r = await client.post("/auth/otp/send", json={"email": email})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        # Check DB row exists
        async with session_factory() as session:
            row = await session.scalar(
                select(SignupOTP).where(SignupOTP.email == email)
            )
            assert row is not None
            assert row.attempts == 0
            assert row.expires_at > datetime.now(UTC)

    async def test_otp_send_rejects_existing_user(self, client):
        # Register a user first
        email = "existing@example.com"
        await client.post(
            "/auth/register",
            json={"email": email, "password": "password1234"},
        )

        r = await client.post("/auth/otp/send", json={"email": email})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "EMAIL_ALREADY_EXISTS"

    async def test_otp_send_rate_limiting(self, client):
        email = "ratelimit@example.com"
        r1 = await client.post("/auth/otp/send", json={"email": email})
        assert r1.status_code == 200

        # Immediate second request should be rate limited
        r2 = await client.post("/auth/otp/send", json={"email": email})
        assert r2.status_code == 429
        assert r2.json()["detail"]["code"] == "RATE_LIMITED"

    async def test_otp_verify_invalid_code(self, client, session_factory):
        email = "tester@example.com"
        await client.post("/auth/otp/send", json={"email": email})

        # Submit wrong OTP
        r = await client.post(
            "/auth/otp/verify",
            json={"email": email, "password": "secure-password-123", "otp": "000000"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "OTP_INVALID"

        async with session_factory() as session:
            row = await session.scalar(
                select(SignupOTP).where(SignupOTP.email == email)
            )
            assert row is not None
            assert row.attempts == 1

    async def test_otp_verify_success_and_login(self, client, session_factory):
        email = "verified@example.com"
        # Seed an OTP directly to know the code
        code = "789123"
        otp_hash = hashlib.sha256(f"{settings.auth_secret}:{email}:{code}".encode()).hexdigest()
        async with session_factory() as session:
            session.add(
                SignupOTP(
                    email=email,
                    otp_hash=otp_hash,
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                    attempts=0,
                )
            )
            await session.commit()

        # Verify and create account
        r = await client.post(
            "/auth/otp/verify",
            json={
                "email": email,
                "password": "valid-password-123",
                "otp": code,
                "name": "Verified User",
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["email"] == email
        assert data["is_verified"] is True
        assert data["name"] == "Verified User"

        # Session cookie should be set
        cookies = client.cookies
        assert "era_session" in cookies

        # OTP row should be deleted
        async with session_factory() as session:
            row = await session.scalar(
                select(SignupOTP).where(SignupOTP.email == email)
            )
            assert row is None

        # /auth/session should now return the logged in user
        session_res = await client.get("/auth/session")
        assert session_res.status_code == 200
        assert session_res.json()["email"] == email

    async def test_otp_verify_expired(self, client, session_factory):
        email = "expired@example.com"
        code = "123456"
        otp_hash = hashlib.sha256(f"{settings.auth_secret}:{email}:{code}".encode()).hexdigest()
        async with session_factory() as session:
            session.add(
                SignupOTP(
                    email=email,
                    otp_hash=otp_hash,
                    expires_at=datetime.now(UTC) - timedelta(minutes=1),
                    attempts=0,
                )
            )
            await session.commit()

        r = await client.post(
            "/auth/otp/verify",
            json={"email": email, "password": "valid-password-123", "otp": code},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "OTP_EXPIRED"

    async def test_direct_registration_blocked_when_verification_required(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(settings, "require_email_verification", True)

        r = await client.post(
            "/auth/register",
            json={"email": "direct@example.com", "password": "valid-password-123"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "OTP_REQUIRED"
