"""Tests for the email OTP signup flow."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.config import settings
from src.core.email_templates import render_otp_email, render_password_reset_otp_email
from src.db.models import PasswordResetOTP, SignupOTP


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


def test_render_password_reset_otp_email_template():
    code = "382910"
    email = "reset@example.com"
    text, html = render_password_reset_otp_email(code, email)

    assert code in text
    assert email in text
    assert "Assay" in text
    assert "Reset your password" in html
    assert code in html
    assert email in html
    assert "#22c55e" in html
    assert "#0a0a0a" in html
    assert "10 minutes" in html


@pytest.mark.asyncio
class TestPasswordResetOTPFlow:
    async def test_reset_otp_send_success(self, client, session_factory):
        email = "member@example.com"
        # Register user first so they exist
        await client.post(
            "/auth/register",
            json={"email": email, "password": "initial-password-123"},
        )

        r = await client.post("/auth/password-reset/otp/send", json={"email": email})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        async with session_factory() as session:
            row = await session.scalar(
                select(PasswordResetOTP).where(PasswordResetOTP.email == email)
            )
            assert row is not None
            assert row.attempts == 0
            assert row.expires_at > datetime.now(UTC)

    async def test_reset_otp_send_user_not_found(self, client):
        r = await client.post(
            "/auth/password-reset/otp/send", json={"email": "nonexistent@example.com"}
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "USER_NOT_FOUND"

    async def test_reset_otp_send_rate_limiting(self, client):
        email = "ratelimit-reset@example.com"
        await client.post(
            "/auth/register",
            json={"email": email, "password": "initial-password-123"},
        )

        r1 = await client.post("/auth/password-reset/otp/send", json={"email": email})
        assert r1.status_code == 200

        r2 = await client.post("/auth/password-reset/otp/send", json={"email": email})
        assert r2.status_code == 429
        assert r2.json()["detail"]["code"] == "RATE_LIMITED"

    async def test_reset_otp_verify_invalid_code(self, client, session_factory):
        email = "tryagain@example.com"
        await client.post(
            "/auth/register",
            json={"email": email, "password": "initial-password-123"},
        )
        await client.post("/auth/password-reset/otp/send", json={"email": email})

        r = await client.post(
            "/auth/password-reset/otp/verify",
            json={"email": email, "password": "new-password-456", "otp": "999999"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "OTP_INVALID"

        async with session_factory() as session:
            row = await session.scalar(
                select(PasswordResetOTP).where(PasswordResetOTP.email == email)
            )
            assert row is not None
            assert row.attempts == 1

    async def test_reset_otp_verify_success_and_login(self, client, session_factory):
        email = "success-reset@example.com"
        await client.post(
            "/auth/register",
            json={"email": email, "password": "old-password-123"},
        )

        code = "654321"
        otp_hash = hashlib.sha256(f"{settings.auth_secret}:{email}:{code}".encode()).hexdigest()
        async with session_factory() as session:
            session.add(
                PasswordResetOTP(
                    email=email,
                    otp_hash=otp_hash,
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                    attempts=0,
                )
            )
            await session.commit()

        # Reset password
        new_password = "brand-new-password-789"
        r = await client.post(
            "/auth/password-reset/otp/verify",
            json={"email": email, "password": new_password, "otp": code},
        )
        assert r.status_code == 200
        assert r.json()["email"] == email

        # Session cookie set
        assert "era_session" in client.cookies

        # OTP row cleared
        async with session_factory() as session:
            row = await session.scalar(
                select(PasswordResetOTP).where(PasswordResetOTP.email == email)
            )
            assert row is None

        # Verify new password works by logging in
        login_res = await client.post(
            "/auth/login",
            data={"username": email, "password": new_password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert login_res.status_code == 204

    async def test_reset_otp_verify_expired(self, client, session_factory):
        email = "expired-reset@example.com"
        await client.post(
            "/auth/register",
            json={"email": email, "password": "old-password-123"},
        )

        code = "111222"
        otp_hash = hashlib.sha256(f"{settings.auth_secret}:{email}:{code}".encode()).hexdigest()
        async with session_factory() as session:
            session.add(
                PasswordResetOTP(
                    email=email,
                    otp_hash=otp_hash,
                    expires_at=datetime.now(UTC) - timedelta(minutes=1),
                    attempts=0,
                )
            )
            await session.commit()

        r = await client.post(
            "/auth/password-reset/otp/verify",
            json={"email": email, "password": "valid-password-123", "otp": code},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "OTP_EXPIRED"


@pytest.mark.asyncio
async def test_send_password_reset_otp_user_not_found_direct():
    from unittest.mock import AsyncMock
    from fastapi import HTTPException
    from src.api.auth import send_password_reset_otp
    from src.api.schemas import PasswordResetOTPSendRequest

    mock_session = AsyncMock()
    mock_session.scalar.return_value = None  # user not found

    payload = PasswordResetOTPSendRequest(email="unknown@example.com")
    with pytest.raises(HTTPException) as exc_info:
        await send_password_reset_otp(payload, session=mock_session)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "USER_NOT_FOUND"


@pytest.mark.asyncio
async def test_send_password_reset_otp_success_direct():
    from unittest.mock import AsyncMock, patch
    from src.api.auth import send_password_reset_otp
    from src.api.schemas import PasswordResetOTPSendRequest
    from src.db.models import User

    mock_session = AsyncMock()
    dummy_user = User(email="active@example.com", is_active=True)
    # First call returns user, second call returns None (no recent OTP)
    mock_session.scalar.side_effect = [dummy_user, None]

    payload = PasswordResetOTPSendRequest(email="active@example.com")
    with patch("src.api.auth.send_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        res = await send_password_reset_otp(payload, session=mock_session)

    assert res["status"] == "ok"
    assert "Password reset code sent" in res["message"]
    assert mock_session.add.called
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_verify_password_reset_otp_direct():
    from unittest.mock import AsyncMock, MagicMock
    from src.api.auth import verify_password_reset_otp
    from src.api.schemas import PasswordResetOTPVerifyRequest
    from src.db.models import PasswordResetOTP, User

    email = "resetting@example.com"
    code = "654321"
    otp_hash = hashlib.sha256(f"{settings.auth_secret}:{email}:{code}".encode()).hexdigest()

    dummy_user = User(
        id=uuid.uuid4(),
        email=email,
        is_active=True,
        is_superuser=False,
        is_verified=True,
        plan="free",
        hashed_password="old",
    )
    dummy_otp = PasswordResetOTP(
        email=email,
        otp_hash=otp_hash,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        attempts=0,
    )

    mock_session = AsyncMock()
    # First call returns user, second call returns otp_record
    mock_session.scalar.side_effect = [dummy_user, dummy_otp]

    mock_user_manager = AsyncMock()
    mock_user_manager.validate_password = AsyncMock()
    mock_user_manager._update.return_value = dummy_user
    mock_user_manager.on_after_reset_password = AsyncMock()

    mock_request = MagicMock()
    mock_response = MagicMock()

    payload = PasswordResetOTPVerifyRequest(
        email=email,
        otp=code,
        password="ValidPassword123!",
    )

    user_read = await verify_password_reset_otp(
        payload=payload,
        request=mock_request,
        response=mock_response,
        session=mock_session,
        user_manager=mock_user_manager,
    )

    assert user_read.email == email
    assert mock_user_manager._update.called
    assert mock_user_manager.on_after_reset_password.called
    assert mock_response.set_cookie.called
