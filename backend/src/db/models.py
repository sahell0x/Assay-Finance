"""SQLAlchemy 2.0 models.

Notes that are load-bearing:

* ``news_chunks.embedding`` is ``halfvec(512)``, not ``vector(1536)``. Half precision at
  512 dimensions is ~6x cheaper in storage than fp32 at 1536 with negligible retrieval
  loss, which is what keeps the index inside Neon's 0.5 GB free tier.
* ``analyses.user_id`` is nullable and ``anon_id`` exists alongside it because anonymous
  visitors get real runs (see ``core/quota.py``). Exactly one of the two is set.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

# Imported from ``fastapi_users.db`` rather than ``fastapi_users_db_sqlalchemy``:
# the two are circular, and importing the latter first leaves ``fastapi_users.db``
# half-initialised, so auth.py then fails with a confusing ImportError depending only
# on which module the process happened to touch first.
from fastapi_users.db import SQLAlchemyBaseOAuthAccountTableUUID
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
    relationship,
)

from ..config import settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(1024), nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(String(32), default="free", server_default="free")
    # Bought credits, spent only once the free monthly allowance is used up. They never
    # expire. Every change is mirrored by a ``credit_transactions`` row in the same
    # transaction, so this is a cached sum of that ledger, never edited on its own.
    paid_credits: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # fastapi-users contract
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        "OAuthAccount", lazy="joined", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("paid_credits >= 0", name="ck_users_paid_credits_nonneg"),
    )


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    """Google (and any future provider) links. Columns come from fastapi-users.

    The base class points its foreign key at a table called ``user``; ours is ``users``,
    so ``user_id`` is redeclared here to target the right table.
    """

    __tablename__ = "accounts"

    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        )

    __table_args__ = (
        UniqueConstraint("oauth_name", "account_id", name="uq_accounts_provider_account"),
    )


class Session(Base):
    __tablename__ = "sessions"

    session_token: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignupOTP(Base):
    """Pending email verification for signup.

    OTPs are salted with ``settings.auth_secret`` before being stored, so a database
    dump does not leak usable codes. Rows are cleaned up upon successful registration
    or upon expiry.
    """

    __tablename__ = "signup_otps"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PasswordResetOTP(Base):
    """Pending email verification for password reset.

    OTPs are salted with ``settings.auth_secret`` before being stored, so a database
    dump does not leak usable codes. Rows are cleaned up upon successful reset
    or upon expiry.
    """

    __tablename__ = "password_reset_otps"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )



class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    anon_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    peer_tickers: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    weights: Mapped[dict | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    current_node: Mapped[str | None] = mapped_column(Text)
    thread_id: Mapped[str | None] = mapped_column(Text)

    scorecard: Mapped[dict | None] = mapped_column(JSONB)
    memo: Mapped[dict | None] = mapped_column(JSONB)
    blocks: Mapped[dict | None] = mapped_column(JSONB)
    data_quality: Mapped[dict | None] = mapped_column(JSONB)

    error: Mapped[str | None] = mapped_column(Text)
    token_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    cache_key: Mapped[str | None] = mapped_column(Text)
    cached_from: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    # Which allowance paid for this run: "free" (the account's one-time free credits),
    # "paid" (a bought credit, refunded if the run fails), "anon" (the visitor allowance)
    # or NULL (cached clones, and rows from before the credit ledger).
    credit_source: Mapped[str | None] = mapped_column(String(8), nullable=True)
    public_slug: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list[AnalysisEvent]] = relationship(
        "AnalysisEvent", cascade="all, delete-orphan", back_populates="analysis"
    )
    evidence: Mapped[list[Evidence]] = relationship(
        "Evidence", cascade="all, delete-orphan", back_populates="analysis"
    )

    __table_args__ = (
        Index("ix_analyses_user_created", "user_id", "created_at"),
        Index("ix_analyses_anon", "anon_id"),
        # Partial index: the cache lookup only ever asks for completed runs.
        Index(
            "ix_analyses_cache_key_complete",
            "cache_key",
            postgresql_where=(status == "complete"),
        ),
    )


class AnalysisEvent(Base):
    """One row per node transition. Replayed to animate cached results."""

    __tablename__ = "analysis_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    node: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # start|ok|error|skipped
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    analysis: Mapped[Analysis] = relationship("Analysis", back_populates="events")


class Evidence(Base):
    """A retrieved chunk that made it into the memo prompt, with its S-label."""

    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(8), nullable=False)  # S1..S20
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    published: Mapped[date | None] = mapped_column(Date)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    relevance: Mapped[float | None] = mapped_column(Float)
    title: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(Text)

    analysis: Mapped[Analysis] = relationship("Analysis", back_populates="evidence")


class Watchlist(Base):
    """Owned by a user *or* by an anonymous cookie, the same way ``Analysis`` is.

    An anonymous visitor gets the full feature set, so the watchlist cannot be the one
    thing that requires an account. On signup the rows are re-pointed at the new user by
    ``migrate_anon_to_user``.
    """

    __tablename__ = "watchlists"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    anon_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    name: Mapped[str] = mapped_column(Text, default="Default")

    items: Mapped[list[WatchlistItem]] = relationship(
        "WatchlistItem", cascade="all, delete-orphan", back_populates="watchlist"
    )

    __table_args__ = (
        CheckConstraint(
            "user_id IS NOT NULL OR anon_id IS NOT NULL",
            name="ck_watchlists_has_owner",
        ),
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("watchlists.id", ondelete="CASCADE"), primary_key=True
    )
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    watchlist: Mapped[Watchlist] = relationship("Watchlist", back_populates="items")


class UsageLedger(Base):
    __tablename__ = "usage_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    anon_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class CreditPurchase(Base):
    """One attempt to buy a credit pack, from Razorpay order to captured payment.

    The Razorpay order id is unique, and it is the key both confirmation paths (the
    browser's callback and the webhook) look the purchase up by. Whichever arrives first
    moves it to ``paid`` under a row lock, so the credits are granted exactly once.
    """

    __tablename__ = "credit_purchases"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    pack_id: Mapped[str] = mapped_column(String(32), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="created", server_default="created"
    )  # created | paid | over_limit | refunded (over_limit, then given back)
    razorpay_order_id: Mapped[str | None] = mapped_column(Text, unique=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreditTransaction(Base):
    """The credit ledger: every change to ``users.paid_credits``, with its reason.

    ``delta`` is signed (+150 for a purchase, -1 for a run, +1 for a refund) and
    ``balance_after`` records the balance it left, so a user's history reads on its own
    and can be reconciled against Razorpay. The partial unique indexes make a purchase
    grant, a spend and a refund each impossible to record twice.
    """

    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # purchase|spend|refund
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("credit_purchases.id", ondelete="SET NULL")
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analyses.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_credit_transactions_user_created", "user_id", "created_at"),
        Index(
            "uq_credit_transactions_purchase",
            "purchase_id",
            unique=True,
            postgresql_where=(kind == "purchase"),
        ),
        Index(
            "uq_credit_transactions_analysis_kind",
            "analysis_id",
            "kind",
            unique=True,
            postgresql_where=(analysis_id.isnot(None)),
        ),
        CheckConstraint("balance_after >= 0", name="ck_credit_transactions_nonneg"),
    )


class NewsChunk(Base):
    """Corpus for retrieval: SEC sections, yfinance news, Yahoo RSS."""

    __tablename__ = "news_chunks"

    chunk_id: Mapped[str] = mapped_column(Text, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    section: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    published: Mapped[date | None] = mapped_column(Date)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(HALFVEC(settings.embedding_dims))
    model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_news_chunks_ticker_published", "ticker", "published"),
        Index(
            "ix_news_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "halfvec_cosine_ops"},
        ),
    )
