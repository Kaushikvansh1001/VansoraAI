"""Add estimate flags to AI usage logs.

Existing rows stay in place. The new columns are filled with defaults.

Revision ID: 0002_ai_usage_detail
Revises: 0001_initial
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0002_ai_usage_detail"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_usage_logs",
        sa.Column("tokens_source", sa.String(length=16), server_default="provider", nullable=False),
    )
    op.add_column(
        "ai_usage_logs",
        sa.Column("cost_is_estimate", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    if os.getenv("ALLOW_SCHEMA_DESTRUCT") != "yes":
        raise RuntimeError(
            "Refusing to drop columns on the shared Supabase database. "
            "Set ALLOW_SCHEMA_DESTRUCT=yes only against a disposable database."
        )
    op.drop_column("ai_usage_logs", "cost_is_estimate")
    op.drop_column("ai_usage_logs", "tokens_source")
