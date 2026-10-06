"""Application settings.

Everything is read from the environment (see ``.env.example``). Nothing here has a
secret as its default; the only values with defaults are ones that are safe to run
with in development.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_AUTH_SECRET = "dev-secret-do-not-use-in-production"
# Copied unchanged from .env.example, this is long enough to pass a length check.
_PLACEHOLDER_SECRETS = {DEV_AUTH_SECRET, "change-me-in-production-use-openssl-rand-hex-32"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # ---- runtime ---------------------------------------------------------
    app_name: str = "Assay"
    env: str = Field(default="dev")  # dev | prod
    log_level: str = "INFO"

    # ---- datastores ------------------------------------------------------
    database_url: str = "postgresql+asyncpg://equity:equity@localhost:5432/equity"
    redis_url: str = "redis://localhost:6379/0"

    # ---- models ----------------------------------------------------------
    # Any OpenAI-compatible endpoint will do: official OpenAI, Azure OpenAI, or a
    # gateway such as aicredits.in, OpenRouter, LiteLLM or a self-hosted vLLM. Only the
    # provider, the base URL and the key change; `.env.example` has a worked block for
    # each of the three.
    llm_provider: str = "openai"  # openai | azure | compatible
    openai_api_key: str = ""
    openai_base_url: str = ""  # blank means the official https://api.openai.com/v1
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-10-21"
    model_narrative: str = "gpt-5.6-luna"
    model_rag: str = "gpt-5.6-terra"
    model_memo: str = "gpt-5.6-terra"
    model_critic: str = "gpt-5.6-luna"
    # Ordered, best first. Consulted only when a configured ID is missing from the
    # provider's model list. NoDecode for the same reason as cors_origins.
    model_fallbacks: Annotated[list[str], NoDecode] = [
        "gpt-4.1-mini",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4o",
        "gpt-4o-2024-08-06",
    ]

    # ---- embeddings ------------------------------------------------------
    # Separate from the chat settings because a gateway that proxies chat completions
    # very often does not proxy embeddings. Each blank value falls back to its chat
    # equivalent, so a single-provider setup needs none of these.
    embedding_provider: str = ""
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 512

    # ---- external data ---------------------------------------------------
    sec_user_agent: str = "Equity Research Agent you@example.com"

    # ---- auth ------------------------------------------------------------
    auth_secret: str = DEV_AUTH_SECRET
    google_client_id: str = ""
    google_client_secret: str = ""

    # Outgoing email (password reset). Any SMTP provider works: Postmark, SES, Resend,
    # Mailgun, Gmail. Leave SMTP_HOST blank and the reset link is written to the log
    # instead, which is enough for development.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Assay <no-reply@localhost>"
    smtp_starttls: bool = True  # port 587. For port 465 set SMTP_SSL=true instead.
    smtp_ssl: bool = False

    # Error monitoring. Set SENTRY_DSN to report crashes to Sentry; blank disables it.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0
    cookie_domain: str = "localhost"
    # NoDecode: pydantic-settings would otherwise JSON-decode this before our
    # validator runs, so a plain comma-separated .env value would blow up.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    frontend_url: str = "http://localhost:3000"
    cookie_secure: bool = False
    # The API's PUBLIC base, as a browser sees it. Blank derives "{frontend_url}/api",
    # which is correct in single-origin mode. It exists because the OAuth redirect URI
    # has to be the address Google can reach, and inside the container the app is
    # mounted at "/" with no idea it is served under a "/api" prefix.
    api_public_url: str = ""

    # ---- limits ----------------------------------------------------------
    daily_cap_usd: float = 3.00
    anon_run_limit: int = 3
    free_account_credits: int = 10
    anon_ip_daily_cap: int = 12
    ip_hash_salt: str = "dev-salt"
    anon_cookie_days: int = 30

    # ---- payments (Razorpay) ----------------------------------------------
    # Signed-in users can buy credit packs on top of the free monthly allowance. Leave
    # the keys blank and the shop says payments are not set up yet; nothing else changes.
    # The webhook secret is the one you type when adding the webhook in the Razorpay
    # dashboard, not the API secret.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_api_base: str = "https://api.razorpay.com/v1"

    # Test mode: the whole flow is real (orders, Checkout, signatures, webhooks, refunds)
    # but runs on Razorpay's test keys, so no real money moves. It is the default because
    # this deployment is a demonstration. In test mode a live key (rzp_live_) is refused
    # outright, and each account can only buy a little, because every bought credit is a
    # real analysis on the model bill even when the payment is pretend.
    payments_test_mode: bool = True
    test_max_purchases: int = 3
    test_max_credits: int = 10

    # Prices are in paise (1/100 of a rupee), which is what Razorpay expects.
    # Override with a JSON list in CREDIT_PACKS to change them without a deploy.
    credit_packs: list[dict] = [
        {"id": "starter", "name": "Starter", "credits": 2, "price_paise": 2900},
        {"id": "pro", "name": "Pro", "credits": 5, "price_paise": 5900, "popular": True},
        {"id": "power", "name": "Power", "credits": 10, "price_paise": 9900},
    ]
    currency: str = "INR"

    # The ticker whose completed analysis the landing page renders. Any completed run
    # is used as a fallback, so an empty database degrades to the input alone rather
    # than to an error.
    sample_ticker: str = "MSFT"

    # ---- tuning ----------------------------------------------------------
    fundamentals_cache_ttl: int = 12 * 3600
    max_evidence_chunks: int = 20
    max_peers: int = 8
    edgar_max_bytes: int = 8 * 1024 * 1024

    @field_validator("cors_origins", "model_fallbacks", mode="before")
    @classmethod
    def _split_list(cls, v: object) -> object:
        """Accept ``a,b`` as well as a real JSON list, so the .env stays readable."""
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                return v
            return [o.strip() for o in s.split(",") if o.strip()]
        return v

    @field_validator("llm_provider", "embedding_provider", mode="before")
    @classmethod
    def _normalise_provider(cls, v: object) -> object:
        """``Azure`` and ``azure`` name the same provider."""
        return v.strip().lower() if isinstance(v, str) else v

    @property
    def effective_embedding_provider(self) -> str:
        """Embeddings run on the chat provider unless ``EMBEDDING_PROVIDER`` says otherwise."""
        return self.embedding_provider or self.llm_provider

    @property
    def effective_embedding_api_key(self) -> str:
        return self.embedding_api_key or self.openai_api_key

    @property
    def effective_embedding_base_url(self) -> str:
        """The chat base URL is inherited only when both halves are on the same provider.

        Pointing ``EMBEDDING_PROVIDER`` at official OpenAI is exactly what you do when a
        gateway serves chat but not embeddings — sending the embedding request to the
        gateway's URL anyway would defeat it.
        """
        if self.embedding_base_url:
            return self.embedding_base_url
        return self.openai_base_url if self.effective_embedding_provider == self.llm_provider else ""

    @property
    def payments_enabled(self) -> bool:
        if not (self.razorpay_key_id and self.razorpay_key_secret):
            return False
        # In test mode anything but a test key is refused, so a live key pasted into the
        # wrong .env cannot take real money from someone who was told it is a demo.
        return not self.payments_test_mode or self.razorpay_key_id.startswith("rzp_test_")

    def credit_pack(self, pack_id: str) -> dict | None:
        return next((p for p in self.credit_packs if p.get("id") == pack_id), None)

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in {"prod", "production"}

    def check_production(self) -> None:
        """Refuse to start a production server that would be unsafe to run.

        Sessions are JWTs signed with ``auth_secret``. With the public development default
        anyone could sign a cookie for any account, so a missing or weak secret is a
        startup error in production, not a warning.
        """
        if not self.is_prod:
            return
        secret = self.auth_secret or ""
        if secret in _PLACEHOLDER_SECRETS or "change-me" in secret or len(secret) < 32:
            raise RuntimeError(
                "AUTH_SECRET must be set to a random value of at least 32 characters in "
                "production. Generate one with: python -c 'import secrets; "
                "print(secrets.token_urlsafe(48))'"
            )

    @property
    def public_api_base(self) -> str:
        """Public base URL of the API, without a trailing slash."""
        if self.api_public_url.strip():
            return self.api_public_url.strip().rstrip("/")
        return f"{self.frontend_url.rstrip('/')}/api"

    @property
    def oauth_redirect_url(self) -> str:
        """The one value that must also be registered in the Google console."""
        return f"{self.public_api_base}/auth/google/callback"

    @property
    def cookie_domain_attr(self) -> str | None:
        """The value to put in a cookie's ``Domain`` attribute, or None to omit it.

        A single-label host such as ``localhost`` must not carry a Domain attribute:
        RFC 6265 domain-matching needs an embedded dot, browsers treat it as host-only
        anyway, and strict cookie jars (Python's included) drop the cookie outright.
        Omitting the attribute gives the host-only behaviour that is wanted in
        development. In production ``COOKIE_DOMAIN`` is a real parent domain such as
        ``.example.com``, which is exactly where the attribute earns its keep — it lets
        ``app.`` and ``api.`` share the session.
        """
        domain = (self.cookie_domain or "").strip()
        if not domain or domain == "localhost" or "." not in domain.strip("."):
            return None
        return domain

    @property
    def sync_database_url(self) -> str:
        """Alembic runs synchronously; strip the asyncpg driver marker."""
        return self.database_url.replace("+asyncpg", "").replace("+psycopg", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
