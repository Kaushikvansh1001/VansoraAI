"""Add support assistants and draft review fields.

Existing tickets and messages stay. Escalation is a flag, so the ticket
status values are unchanged. Downgrade is refused on the shared database.

Revision ID: 0004_support_assistant
Revises: 0003_workflow_step_snapshot
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_support_assistant"
down_revision = "0003_workflow_step_snapshot"
branch_labels = None
depends_on = None

ASSISTANT_POLICY = "support_assistants_tenant_isolation"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "support_assistants" not in inspector.get_table_names():
        op.create_table(
            "support_assistants",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("welcome_message", sa.Text(), nullable=False),
            sa.Column("instructions", sa.Text(), nullable=False),
            sa.Column("tone", sa.String(length=32), nullable=False),
            sa.Column("language", sa.String(length=40), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["profiles.id"]),
        )
        op.create_index("ix_support_assistants_organization_id", "support_assistants", ["organization_id"])

    _ensure_tenant_policy(bind, "support_assistants", ASSISTANT_POLICY)

    inspector = sa.inspect(bind)
    ticket_columns = {column["name"] for column in inspector.get_columns("support_tickets")}
    if "assistant_id" not in ticket_columns:
        op.add_column("support_tickets", sa.Column("assistant_id", postgresql.UUID(as_uuid=True), nullable=True))
    if "escalated" not in ticket_columns:
        op.add_column(
            "support_tickets",
            sa.Column("escalated", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if not _foreign_key(sa.inspect(bind), "support_tickets", "assistant_id"):
        op.create_foreign_key(
            "fk_support_tickets_assistant_id_support_assistants",
            "support_tickets",
            "support_assistants",
            ["assistant_id"],
            ["id"],
            ondelete="SET NULL",
        )

    message_columns = {column["name"] for column in sa.inspect(bind).get_columns("support_messages")}
    additions = (
        ("draft_status", sa.Column("draft_status", sa.String(length=16), nullable=True)),
        ("internal", sa.Column("internal", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("provider", sa.Column("provider", sa.String(length=40), nullable=True)),
        ("model", sa.Column("model", sa.String(length=120), nullable=True)),
        ("suggest_escalation", sa.Column("suggest_escalation", sa.Boolean(), nullable=True)),
    )
    for name, column in additions:
        if name not in message_columns:
            op.add_column("support_messages", column)


def downgrade() -> None:
    if os.getenv("ALLOW_SCHEMA_DESTRUCT") != "yes":
        raise RuntimeError(
            "Refusing to drop support assistant columns on the shared Supabase database. "
            "Set ALLOW_SCHEMA_DESTRUCT=yes only against a disposable database."
        )
    bind = op.get_bind()
    foreign_key = _foreign_key(sa.inspect(bind), "support_tickets", "assistant_id")
    if foreign_key is not None and foreign_key.get("name"):
        op.drop_constraint(foreign_key["name"], "support_tickets", type_="foreignkey")
    inspector = sa.inspect(bind)
    ticket_columns = {column["name"] for column in inspector.get_columns("support_tickets")}
    if "assistant_id" in ticket_columns:
        op.drop_column("support_tickets", "assistant_id")
    if "escalated" in ticket_columns:
        op.drop_column("support_tickets", "escalated")
    message_columns = {column["name"] for column in inspector.get_columns("support_messages")}
    for name in ("suggest_escalation", "model", "provider", "internal", "draft_status"):
        if name in message_columns:
            op.drop_column("support_messages", name)
    if "support_assistants" in inspector.get_table_names():
        op.execute(f"DROP POLICY IF EXISTS {ASSISTANT_POLICY} ON support_assistants")
        op.drop_index("ix_support_assistants_organization_id", table_name="support_assistants")
        op.drop_table("support_assistants")


def _ensure_tenant_policy(bind, table: str, policy: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    exists = bind.execute(sa.text("SELECT 1 FROM pg_policies WHERE policyname = :name"), {"name": policy}).first()
    if exists:
        return
    op.execute(
        f"""
        CREATE POLICY {policy} ON {table}
        USING (organization_id::text = current_setting('app.current_org_id', true))
        WITH CHECK (organization_id::text = current_setting('app.current_org_id', true))
        """
    )


def _foreign_key(inspector, table: str, column: str):
    for foreign_key in inspector.get_foreign_keys(table):
        if foreign_key.get("constrained_columns") == [column]:
            return foreign_key
    return None
