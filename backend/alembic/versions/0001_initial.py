"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMS = 512


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(1024), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("image_url", sa.Text()),
        sa.Column("plan", sa.String(32), server_default="free", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("oauth_name", sa.String(100), nullable=False),
        sa.Column("access_token", sa.String(1024), nullable=False),
        sa.Column("expires_at", sa.Integer()),
        sa.Column("refresh_token", sa.String(1024)),
        sa.Column("account_id", sa.String(320), nullable=False),
        sa.Column("account_email", sa.String(320), nullable=False),
    )
    op.create_index("ix_accounts_oauth_name", "accounts", ["oauth_name"])
    op.create_index("ix_accounts_account_id", "accounts", ["account_id"])
    op.create_unique_constraint(
        "uq_accounts_provider_account", "accounts", ["oauth_name", "account_id"]
    )

    op.create_table(
        "sessions",
        sa.Column("session_token", sa.Text(), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("anon_id", sa.Text(), nullable=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("peer_tickers", postgresql.ARRAY(sa.Text())),
        sa.Column("weights", postgresql.JSONB()),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("current_node", sa.Text()),
        sa.Column("thread_id", sa.Text()),
        sa.Column("scorecard", postgresql.JSONB()),
        sa.Column("memo", postgresql.JSONB()),
        sa.Column("blocks", postgresql.JSONB()),
        sa.Column("data_quality", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("token_cost_usd", sa.Numeric(10, 4)),
        sa.Column("cache_key", sa.Text()),
        sa.Column("cached_from", postgresql.UUID(as_uuid=True)),
        sa.Column("public_slug", sa.Text(), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_analyses_created_at", "analyses", ["created_at"])
    op.create_index(
        "ix_analyses_user_created", "analyses", ["user_id", "created_at"]
    )
    op.create_index("ix_analyses_anon", "analyses", ["anon_id"])
    # Partial index — the cache lookup only ever asks about completed runs.
    op.create_index(
        "ix_analyses_cache_key_complete",
        "analyses",
        ["cache_key"],
        postgresql_where=sa.text("status = 'complete'"),
    )

    op.create_table(
        "analysis_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("detail", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_analysis_events_analysis_id", "analysis_events", ["analysis_id"])

    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(8), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("url", sa.Text()),
        sa.Column("published", sa.Date()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("relevance", sa.Float()),
        sa.Column("title", sa.Text()),
        sa.Column("section", sa.Text()),
    )
    op.create_index("ix_evidence_analysis_id", "evidence", ["analysis_id"])

    op.create_table(
        "watchlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), server_default="Default", nullable=False),
    )
    op.create_index("ix_watchlists_user_id", "watchlists", ["user_id"])

    op.create_table(
        "watchlist_items",
        sa.Column(
            "watchlist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watchlists.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("ticker", sa.String(16), primary_key=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("anon_id", sa.Text()),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True)),
        sa.Column("tokens_in", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 4), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usage_ledger_created_at", "usage_ledger", ["created_at"])

    op.create_table(
        "news_chunks",
        sa.Column("chunk_id", sa.Text(), primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("section", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("url", sa.Text()),
        sa.Column("published", sa.Date()),
        sa.Column("text", sa.Text(), nullable=False),
        # halfvec(512), not vector(1536): ~6x the rows per gigabyte for a retrieval
        # quality difference that does not show up at this corpus size.
        sa.Column("embedding", HALFVEC(EMBEDDING_DIMS), nullable=False),
        sa.Column("model", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_news_chunks_ticker_published",
        "news_chunks",
        ["ticker", "published"],
    )
    op.create_index(
        "ix_news_chunks_embedding_hnsw",
        "news_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "halfvec_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("news_chunks")
    op.drop_table("usage_ledger")
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")
    op.drop_table("evidence")
    op.drop_table("analysis_events")
    op.drop_table("analyses")
    op.drop_table("sessions")
    op.drop_table("accounts")
    op.drop_table("users")
