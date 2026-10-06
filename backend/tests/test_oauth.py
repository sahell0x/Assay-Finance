"""The Google sign-in handshake.

fastapi-users' callback trusts nothing it did not issue itself: it requires a signed
``state`` token in the query string, and that token's ``csrftoken`` claim has to match a
cookie set at the same moment the authorization URL was built. A login entry point that
skips either half fails *after* the user has already consented at Google — the callback
answers ``{"detail": "ACCESS_TOKEN_DECODE_ERROR"}`` and there is no way forward from
there. These tests pin both halves to the entry point the sign-in button actually uses.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


@pytest.fixture
def google_app(monkeypatch):
    """The app with Google configured, which is what mounts the OAuth routes at all."""
    from fastapi import FastAPI

    from src.config import settings

    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret")

    from src.api.auth import mount_auth

    app = FastAPI()
    mount_auth(app)
    return app


async def _login(app) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost",
        follow_redirects=False,
    ) as c:
        return await c.get("/auth/google/login")


def _state_token(response: httpx.Response) -> str:
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert "state" in query, (
        "no state in the authorization URL: Google echoes none back, and the callback "
        "rejects the login with ACCESS_TOKEN_DECODE_ERROR"
    )
    return query["state"][0]


class TestGoogleLogin:
    async def test_is_a_redirect_a_link_can_use(self, google_app):
        # The point of this route over fastapi-users' /authorize, which answers JSON.
        r = await _login(google_app)
        assert r.status_code == 302
        assert r.headers["location"].startswith("https://accounts.google.com/")

    async def test_asks_for_the_scopes_the_callback_needs(self, google_app):
        r = await _login(google_app)
        query = parse_qs(urlparse(r.headers["location"]).query)
        assert set(query["scope"][0].split()) == {"openid", "email", "profile"}

    async def test_carries_a_state_token_the_callback_can_decode(self, google_app):
        from fastapi_users.jwt import decode_jwt
        from fastapi_users.router.oauth import STATE_TOKEN_AUDIENCE

        from src.config import settings

        r = await _login(google_app)
        # Exactly the call the callback makes; a DecodeError here is the 400 the user saw.
        decode_jwt(_state_token(r), settings.auth_secret, [STATE_TOKEN_AUDIENCE])

    async def test_sets_the_csrf_cookie_the_state_is_checked_against(self, google_app):
        from fastapi_users.jwt import decode_jwt
        from fastapi_users.router.oauth import (
            CSRF_TOKEN_COOKIE_NAME,
            CSRF_TOKEN_KEY,
            STATE_TOKEN_AUDIENCE,
        )

        from src.config import settings

        r = await _login(google_app)
        claims = decode_jwt(_state_token(r), settings.auth_secret, [STATE_TOKEN_AUDIENCE])
        assert CSRF_TOKEN_KEY in claims
        assert r.cookies.get(CSRF_TOKEN_COOKIE_NAME) == claims[CSRF_TOKEN_KEY]

    async def test_csrf_cookie_survives_plain_http_in_development(self, google_app):
        # Secure=True would drop the cookie on any http:// host that is not localhost,
        # and the failure looks identical to a CSRF mismatch.
        from fastapi_users.router.oauth import CSRF_TOKEN_COOKIE_NAME

        from src.config import settings

        r = await _login(google_app)
        cookies = [
            v for k, v in r.headers.multi_items()
            if k.lower() == "set-cookie" and v.startswith(CSRF_TOKEN_COOKIE_NAME)
        ]
        assert cookies, "no CSRF cookie was set at all"
        cookie = cookies[0]
        assert settings.cookie_secure is False
        assert "secure" not in cookie.lower()
        assert "httponly" in cookie.lower()


@pytest_asyncio.fixture
async def browser(google_app, session_factory, clean_db):
    """A client that keeps cookies between requests, the way a browser does.

    The CSRF cookie is the whole point: it is set on the redirect out to Google and read
    back on the callback, so a client that forgets it cannot exercise the handshake.
    """
    from src.db.session import get_session

    async def override_get_session():
        async with session_factory() as s:
            yield s

    google_app.dependency_overrides[get_session] = override_get_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=google_app),
        base_url="http://localhost",
        follow_redirects=False,
    ) as c:
        yield c
    google_app.dependency_overrides.clear()


@pytest.fixture
def google_says_yes(monkeypatch):
    """Stand in for Google's token and userinfo endpoints, nothing else."""
    from httpx_oauth.oauth2 import OAuth2Token

    from src.api.auth import OpenIDGoogleOAuth2

    async def get_access_token(self, code, redirect_uri, code_verifier=None):
        return OAuth2Token({"access_token": "google-access-token", "expires_in": 3600})

    async def get_id_email(self, token):
        return "google-subject-1", "newcomer@example.com"

    monkeypatch.setattr(OpenIDGoogleOAuth2, "get_access_token", get_access_token)
    monkeypatch.setattr(OpenIDGoogleOAuth2, "get_id_email", get_id_email)


class TestGoogleCallback:
    """The round trip, with only Google's own endpoints replaced."""

    async def test_signs_the_user_in_and_lands_them_on_the_dashboard(
        self, browser, google_says_yes
    ):
        from src.api.auth import COOKIE_NAME
        from src.config import settings

        login = await browser.get("/auth/google/login")
        state = _state_token(login)

        r = await browser.get("/auth/google/callback", params={"code": "x", "state": state})

        assert r.status_code == 302, r.text
        assert r.headers["location"] == f"{settings.frontend_url}/dashboard"
        assert COOKIE_NAME in r.cookies

    async def test_a_callback_without_the_csrf_cookie_is_refused(
        self, browser, google_says_yes
    ):
        # What a stripped or third-party-blocked cookie looks like. It must fail closed,
        # and it must fail as a CSRF problem rather than being waved through.
        from fastapi_users.router.oauth import CSRF_TOKEN_COOKIE_NAME

        login = await browser.get("/auth/google/login")
        state = _state_token(login)
        browser.cookies.delete(CSRF_TOKEN_COOKIE_NAME)

        r = await browser.get("/auth/google/callback", params={"code": "x", "state": state})

        assert r.status_code == 400
        assert r.json()["detail"] == "OAUTH_INVALID_STATE"

    async def test_a_callback_with_someone_elses_state_is_refused(
        self, browser, google_says_yes
    ):
        # The state and the cookie must be halves of the same handshake, not merely
        # both present: two logins in flight must not authenticate each other.
        login = await browser.get("/auth/google/login")
        other = await browser.get("/auth/google/login")  # overwrites the csrf cookie
        assert _state_token(login) != _state_token(other)

        r = await browser.get(
            "/auth/google/callback", params={"code": "x", "state": _state_token(login)}
        )

        assert r.status_code == 400
        assert r.json()["detail"] == "OAUTH_INVALID_STATE"


class TestGoogleIdentity:
    """Identity comes from OpenID userinfo, which needs no extra Cloud API enabled."""

    def _client(self, monkeypatch, status: int, body: dict):
        from src.api.auth import GOOGLE_USERINFO_ENDPOINT, OpenIDGoogleOAuth2

        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == GOOGLE_USERINFO_ENDPOINT
            assert request.headers["Authorization"] == "Bearer tok"
            return httpx.Response(status, json=body)

        client = OpenIDGoogleOAuth2("id", "secret")
        monkeypatch.setattr(
            client,
            "get_httpx_client",
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        return client

    async def test_reads_subject_and_verified_email(self, monkeypatch):
        client = self._client(
            monkeypatch, 200, {"sub": "123", "email": "a@example.com", "email_verified": True}
        )
        assert await client.get_id_email("tok") == ("people/123", "a@example.com")

    async def test_withholds_an_unverified_email(self, monkeypatch):
        client = self._client(
            monkeypatch, 200, {"sub": "123", "email": "a@example.com", "email_verified": False}
        )
        assert await client.get_id_email("tok") == ("people/123", None)

    async def test_an_error_from_google_raises_the_library_error(self, monkeypatch):
        from httpx_oauth.exceptions import GetIdEmailError

        client = self._client(monkeypatch, 401, {"error": "invalid_token"})
        with pytest.raises(GetIdEmailError):
            await client.get_id_email("tok")
