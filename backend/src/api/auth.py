"""Authentication.

Cookie-based, httpOnly, ``SameSite=Lax``, with the cookie domain set to the parent
domain so ``app.`` and ``api.`` subdomains share a session. CORS is configured with
explicit origins and credentials enabled — ``allow_origins=["*"]`` is not compatible
with credentialed requests and would silently break login in the browser.

Google OAuth is optional: if ``GOOGLE_CLIENT_ID`` is unset the router is simply not
mounted and the app runs on email and password. That is what makes a clone-and-run
development setup possible without registering an OAuth client.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, Request, Response
from fastapi.responses import RedirectResponse
from fastapi_users import (
    BaseUserManager,
    FastAPIUsers,
    InvalidPasswordException,
    UUIDIDMixin,
    schemas,
)
from fastapi_users.authentication import AuthenticationBackend, CookieTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.router.oauth import (
    CSRF_TOKEN_COOKIE_NAME,
    CSRF_TOKEN_KEY,
    generate_csrf_token,
    generate_state_token,
)
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.exceptions import GetIdEmailError
from pydantic import ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db.models import OAuthAccount, User
from ..db.session import get_session

log = logging.getLogger(__name__)

COOKIE_NAME = "era_session"
ANON_COOKIE = "anon_id"
SESSION_LIFETIME = 60 * 60 * 24 * 30  # 30 days


# ------------------------------------------------------------------------- schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    image_url: str | None = None
    plan: str = "free"


class UserCreate(schemas.BaseUserCreate):
    name: str | None = None


class UserUpdate(schemas.BaseUserUpdate):
    name: str | None = None
    image_url: str | None = None


# -------------------------------------------------------------------- user manager


async def get_user_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.auth_secret
    verification_token_secret = settings.auth_secret

    async def validate_password(self, password: str, user) -> None:
        """Enforced here, not only in the form: the API is reachable without the form,
        and it accepted a one-character password until this existed. Applies to
        sign-up and to password reset alike."""
        if len(password) < 8:
            raise InvalidPasswordException(reason="Use at least eight characters.")
        email = getattr(user, "email", "") or ""
        if email and password.lower() == email.lower():
            raise InvalidPasswordException(reason="Do not use your email address.")

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        """Carry a visitor's anonymous runs into their new account.

        Someone who ran three analyses before signing up should find those three
        analyses in their history, not an empty dashboard. The migration keys off the
        ``anon_id`` cookie that is already on the request.
        """
        log.info("registered %s", user.id)
        await self._migrate_anonymous(user, request)

    async def on_after_login(
        self, user: User, request: Request | None = None, response: Response | None = None
    ) -> None:
        # Also on login: a visitor may have run analyses on a second device before
        # signing in there.
        await self._migrate_anonymous(user, request)

    async def _migrate_anonymous(self, user: User, request: Request | None) -> None:
        if request is None:
            return
        anon_id = request.cookies.get(ANON_COOKIE)
        if not anon_id:
            return
        try:
            from ..db.repo import migrate_anon_to_user

            # Reuse the session fastapi-users is already holding rather than opening a
            # second one: it keeps the migration in the request's transaction and
            # avoids a second connection per signup on a box with a tiny pool.
            db = self.user_db.session
            moved = await migrate_anon_to_user(db, anon_id, user.id)
            if moved:
                log.info("migrated %d anonymous analyses to %s", moved, user.id)
        except Exception as exc:
            # Never block a signup because history migration failed.
            log.warning("anonymous migration failed: %s", exc)

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        from urllib.parse import quote

        from ..core.mail import send_email

        link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={quote(token)}"
        log.info("password reset requested for %s", user.id)
        await send_email(
            user.email,
            "Reset your Assay password",
            (
                "Someone asked to reset the password for this email address on "
                "Assay.\n\n"
                f"To choose a new password, open this link within the next hour:\n{link}\n\n"
                "If this was not you, you can ignore this email. Your password stays "
                "the same until you use the link."
            ),
            html=(
                '<div style="font-family:system-ui,sans-serif;font-size:15px;'
                'line-height:1.6;color:#1c2b26;max-width:480px">'
                "<p>Someone asked to reset the password for this email address on "
                "Assay.</p>"
                f'<p><a href="{link}" style="display:inline-block;background:#123c33;'
                "color:#fff;padding:11px 20px;border-radius:999px;font-weight:700;text-decoration:none\">"
                "Choose a new password</a></p>"
                "<p>The link works for one hour. If this was not you, ignore this email "
                "&mdash; your password stays the same.</p></div>"
            ),
        )


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


# ------------------------------------------------------------------------ backend

cookie_transport = CookieTransport(
    cookie_name=COOKIE_NAME,
    cookie_max_age=SESSION_LIFETIME,
    cookie_domain=settings.cookie_domain_attr,
    cookie_secure=settings.cookie_secure or settings.is_prod,
    cookie_httponly=True,
    cookie_samesite="lax",
)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.auth_secret, lifetime_seconds=SESSION_LIFETIME)


cookie_backend = AuthenticationBackend(
    name="cookie", transport=cookie_transport, get_strategy=get_jwt_strategy
)


class RedirectingCookieTransport(CookieTransport):
    """Sets the same session cookie, then sends the browser back to the app.

    The plain transport answers a successful login with 204 and a Set-Cookie, which is
    exactly right for the email-and-password form — the page is already open and the
    frontend navigates itself. It is wrong for OAuth: there the browser arrives at the
    callback as a full navigation from Google, so a 204 leaves the user staring at a
    blank page with no way forward. This one finishes the journey.

    It is a separate backend rather than a change to the shared one so the form login
    keeps its 204, which the frontend depends on.
    """

    def __init__(self, *args, redirect_to: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.redirect_to = redirect_to

    async def get_login_response(self, token: str) -> Response:
        response = RedirectResponse(self.redirect_to, status_code=302)
        return self._set_login_cookie(response, token)


def oauth_backend() -> AuthenticationBackend:
    """The cookie backend used for OAuth only, landing on the dashboard."""
    return AuthenticationBackend(
        name="cookie-oauth",
        transport=RedirectingCookieTransport(
            cookie_name=COOKIE_NAME,
            cookie_max_age=SESSION_LIFETIME,
            cookie_domain=settings.cookie_domain_attr,
            cookie_secure=settings.cookie_secure or settings.is_prod,
            cookie_httponly=True,
            cookie_samesite="lax",
            redirect_to=f"{settings.frontend_url.rstrip('/')}/dashboard",
        ),
        get_strategy=get_jwt_strategy,
    )

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [cookie_backend])

current_active_user = fastapi_users.current_user(active=True)
current_user_optional = fastapi_users.current_user(active=True, optional=True)


GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"


class OpenIDGoogleOAuth2(GoogleOAuth2):
    """Reads identity from the OpenID userinfo endpoint instead of the People API.

    httpx-oauth's default asks ``people.googleapis.com``, which answers 403 unless the
    People API is separately enabled on the Cloud project — a setup step that is easy
    to miss and fails as a bare 500 on the callback. The userinfo endpoint is covered
    by the ``email`` scope alone.
    """

    async def get_id_email(self, token: str) -> tuple[str, str | None]:
        async with self.get_httpx_client() as client:
            response = await client.get(
                GOOGLE_USERINFO_ENDPOINT,
                headers={**self.request_headers, "Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            raise GetIdEmailError(response=response)
        info = response.json()
        # An unverified address must not sign anyone into the account that owns it.
        email = info.get("email") if info.get("email_verified") else None
        # Same shape as the People API's resourceName, so accounts linked before this
        # change still match.
        return f"people/{info['sub']}", email


def google_client():
    """Returns a configured Google OAuth client, or None when unconfigured."""
    if not (settings.google_client_id and settings.google_client_secret):
        return None
    return OpenIDGoogleOAuth2(settings.google_client_id, settings.google_client_secret)


async def session(user: User | None = Depends(current_user_optional)) -> UserRead | None:
    """Who is signed in, or null.

    /users/me answers 401 to a visitor, which is correct for an API but lands as a red
    console error on every page view by every anonymous visitor. This answers the same
    question with a 200.
    """
    return UserRead.model_validate(user) if user else None


def mount_auth(app) -> None:
    """Attach every auth router the configuration supports."""
    app.add_api_route(
        "/auth/session", session, methods=["GET"], response_model=UserRead | None, tags=["auth"]
    )
    app.include_router(
        fastapi_users.get_auth_router(cookie_backend, requires_verification=False),
        prefix="/auth",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"]
    )
    app.include_router(fastapi_users.get_reset_password_router(), prefix="/auth", tags=["auth"])
    app.include_router(
        fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"]
    )

    client = google_client()
    if client is None:
        log.warning(
            "GOOGLE_CLIENT_ID/SECRET are not set — Google sign-in is disabled. "
            "Email and password authentication is unaffected."
        )
        return

    app.include_router(
        fastapi_users.get_oauth_router(
            client,
            oauth_backend(),
            settings.auth_secret,
            # Must be the address Google can actually send a browser to, and must match
            # the "Authorized redirect URI" registered in the Google console exactly.
            # It cannot be derived from the request: behind the frontend's /api proxy
            # the app is mounted at "/" and has no idea of the prefix it is served under.
            redirect_url=settings.oauth_redirect_url,
            associate_by_email=True,
            is_verified_by_default=True,
        ),
        prefix="/auth/google",
        tags=["auth"],
    )

    @app.get("/auth/google/login", tags=["auth"], include_in_schema=False)
    async def google_login() -> RedirectResponse:
        """Start the Google flow with a plain browser navigation.

        fastapi-users' /authorize answers with JSON containing the authorization URL,
        which is fine for a fetch but not for a link — following it shows the user a
        page of JSON. OAuth has to be a top-level navigation anyway, so this redirects.

        Everything below /authorize's JSON is reproduced here, and has to be: the
        callback above verifies the handshake this route opens. It decodes ``state`` as
        a JWT signed with the same secret, then compares the ``csrftoken`` claim inside
        it against the cookie set here. Omitting either half does not disable a check —
        it fails one, and it fails it after the user has already consented at Google,
        where the only thing left to show them is ACCESS_TOKEN_DECODE_ERROR.
        """
        csrf_token = generate_csrf_token()
        state = generate_state_token({CSRF_TOKEN_KEY: csrf_token}, settings.auth_secret)
        url = await client.get_authorization_url(
            settings.oauth_redirect_url,
            state,
            scope=["openid", "email", "profile"],
        )
        response = RedirectResponse(url, status_code=302)
        # Same attributes as the session cookie, for the same reasons: no Domain on a
        # single-label host, and Secure only where the site is actually served over TLS
        # — a Secure cookie on plain http is dropped, and the callback then reports a
        # CSRF mismatch that looks nothing like the misconfiguration behind it.
        # SameSite=Lax is what lets it survive the top-level redirect back from Google.
        response.set_cookie(
            CSRF_TOKEN_COOKIE_NAME,
            csrf_token,
            max_age=3600,
            path="/",
            domain=settings.cookie_domain_attr,
            secure=settings.cookie_secure or settings.is_prod,
            httponly=True,
            samesite="lax",
        )
        return response
    app.include_router(
        fastapi_users.get_oauth_associate_router(client, UserRead, settings.auth_secret),
        prefix="/auth/associate/google",
        tags=["auth"],
    )
    log.info("Google OAuth enabled")
