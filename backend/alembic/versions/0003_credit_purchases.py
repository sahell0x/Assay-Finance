"""credit purchases

Signed-in users can now buy credit packs through Razorpay on top of the free monthly
allowance. Three pieces:

* ``users.paid_credits`` holds the bought balance. It is only ever changed alongside a
  ``credit_transactions`` row, so it is a cached sum of that ledger.
* ``credit_purchases`` tracks each Razorpay order until it is paid. The unique order id
  is what makes granting the credits idempotent across the browser callback and the
  webhook.
* ``analyses.credit_source`` records which allowance a run used, so a failed run can
  refund a bought credit and the free monthly count can leave bought runs out.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("paid_credits", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint("ck_users_paid_credits_nonneg", "users", "paid_credits >= 0")
    op.add_column("analyses", sa.Column("credit_source", sa.String(8), nullable=True))

    op.create_table(
        "credit_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pack_id", sa.String(32), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), server_default="created", nullable=False),
        sa.Column("razorpay_order_id", sa.Text(), unique=True),
        sa.Column("razorpay_payment_id", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_credit_purchases_user_id", "credit_purchases", ["user_id"])

    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column(
            "purchase_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_purchases.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("balance_after >= 0", name="ck_credit_transactions_nonneg"),
    )
    op.create_index(
        "ix_credit_transactions_user_created",
        "credit_transactions",
        ["user_id", "created_at"],
    )
    op.create_index(
        "uq_credit_transactions_purchase",
        "credit_transactions",
        ["purchase_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'purchase'"),
    )
    op.create_index(
        "uq_credit_transactions_analysis_kind",
        "credit_transactions",
        ["analysis_id", "kind"],
        unique=True,
        postgresql_where=sa.text("analysis_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Bought balances cannot be represented without these tables. Downgrading after
    # real purchases loses them, so export credit_transactions first if that matters.
    op.drop_table("credit_transactions")
    op.drop_index("ix_credit_purchases_user_id", table_name="credit_purchases")
    op.drop_table("credit_purchases")
    op.drop_column("analyses", "credit_source")
    op.drop_constraint("ck_users_paid_credits_nonneg", "users", type_="check")
    op.drop_column("users", "paid_credits")
