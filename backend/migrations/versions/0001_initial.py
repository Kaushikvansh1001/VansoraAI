"""Initial schema and tenant row-level security policies.

The API user in local development owns these tables, so Postgres skips RLS
for that role. Policies still protect a non-owner role. Service-layer checks
are the enforced boundary until the API connects as a restricted role.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-13
"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "documents",
    "document_chunks",
    "conversations",
    "messages",
    "datasets",
    "dataset_analyses",
    "workflows",
    "workflow_nodes",
    "workflow_edges",
    "workflow_executions",
    "workflow_execution_steps",
    "support_tickets",
    "support_messages",
    "outbox_messages",
    "ai_usage_logs",
    "ai_feedback",
    "audit_logs",
    "jobs",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    from app.models import Base

    Base.metadata.create_all(bind=op.get_bind())

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (organization_id::text = current_setting('app.current_org_id', true))
            WITH CHECK (organization_id::text = current_setting('app.current_org_id', true))
            """
        )

    op.execute("ALTER TABLE profiles ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY profiles_self ON profiles
        USING (id::text = current_setting('app.current_user_id', true))
        WITH CHECK (id::text = current_setting('app.current_user_id', true))
        """
    )
    op.execute("ALTER TABLE local_credentials ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY local_credentials_self ON local_credentials
        USING (user_id::text = current_setting('app.current_user_id', true))
        WITH CHECK (user_id::text = current_setting('app.current_user_id', true))
        """
    )
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY organizations_member_access ON organizations
        USING (
            EXISTS (
                SELECT 1 FROM organization_members AS member
                WHERE member.organization_id = organizations.id
                  AND member.user_id::text = current_setting('app.current_user_id', true)
            )
        )
        WITH CHECK (created_by::text = current_setting('app.current_user_id', true))
        """
    )
    op.execute("ALTER TABLE organization_members ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY organization_members_access ON organization_members
        USING (
            user_id::text = current_setting('app.current_user_id', true)
            OR organization_id::text = current_setting('app.current_org_id', true)
        )
        WITH CHECK (organization_id::text = current_setting('app.current_org_id', true))
        """
    )
    op.execute("ALTER TABLE ai_providers ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    import os

    if os.getenv("ALLOW_SCHEMA_DESTRUCT") != "yes":
        raise RuntimeError(
            "Refusing to drop tables. The shared Supabase database is the source of truth. "
            "Run upgrade only. Set ALLOW_SCHEMA_DESTRUCT=yes only against a disposable database."
        )
    from app.models import Base

    Base.metadata.drop_all(bind=op.get_bind())
    op.execute("DROP EXTENSION IF EXISTS vector")
