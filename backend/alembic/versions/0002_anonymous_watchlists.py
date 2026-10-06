"""anonymous watchlists

Watchlists were owned by a user row, so a visitor without an account could not keep one.
That contradicted the identity model in ``deps.py``, which says anonymous visitors get
the full feature set limited only by a run count: history was already cookie-scoped and
the watchlist was the one feature arbitrarily behind the account wall.

``user_id`` becomes nullable and ``anon_id`` joins it, exactly as on ``analyses``. A row
carries one or the other, never neither, which the check constraint enforces — a
watchlist owned by nobody is unreachable and would leak.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("watchlists", "user_id", existing_type=sa.dialects.postgresql.UUID(), nullable=True)
    op.add_column("watchlists", sa.Column("anon_id", sa.Text(), nullable=True))
    op.create_index("ix_watchlists_anon_id", "watchlists", ["anon_id"])
    op.create_check_constraint(
        "ck_watchlists_has_owner",
        "watchlists",
        "user_id IS NOT NULL OR anon_id IS NOT NULL",
    )


def downgrade() -> None:
    # Anonymous watchlists have no user to belong to, so they cannot survive the
    # column becoming NOT NULL. Dropping them is the only honest downgrade.
    op.execute("DELETE FROM watchlists WHERE user_id IS NULL")
    op.drop_constraint("ck_watchlists_has_owner", "watchlists", type_="check")
    op.drop_index("ix_watchlists_anon_id", table_name="watchlists")
    op.drop_column("watchlists", "anon_id")
    op.alter_column("watchlists", "user_id", existing_type=sa.dialects.postgresql.UUID(), nullable=False)
