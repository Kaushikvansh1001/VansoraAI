"""Keep workflow history when a canvas is saved again.

Adds a snapshot of the node name on each step and keeps the step when its
node is replaced. Existing rows are not deleted.

Revision ID: 0003_workflow_step_snapshot
Revises: 0002_ai_usage_detail
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_workflow_step_snapshot"
down_revision = "0002_ai_usage_detail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("workflow_execution_steps")}
    if "node_type" not in columns:
        op.add_column("workflow_execution_steps", sa.Column("node_type", sa.String(length=64), nullable=True))
    if "node_label" not in columns:
        op.add_column("workflow_execution_steps", sa.Column("node_label", sa.String(length=160), nullable=True))

    op.execute(
        """
        UPDATE workflow_execution_steps AS step
        SET node_type = node.node_type,
            node_label = node.label
        FROM workflow_nodes AS node
        WHERE step.node_id = node.id
          AND step.node_type IS NULL
        """
    )

    inspector = sa.inspect(bind)
    node_id = next(column for column in inspector.get_columns("workflow_execution_steps") if column["name"] == "node_id")
    if node_id.get("nullable") is False:
        op.alter_column(
            "workflow_execution_steps",
            "node_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=True,
        )

    foreign_key = _node_foreign_key(sa.inspect(bind))
    ondelete = ""
    if foreign_key is not None:
        ondelete = str((foreign_key.get("options") or {}).get("ondelete") or foreign_key.get("ondelete") or "")
    if foreign_key is not None and ondelete.upper() != "SET NULL":
        op.drop_constraint(foreign_key["name"], "workflow_execution_steps", type_="foreignkey")
        op.create_foreign_key(
            foreign_key["name"],
            "workflow_execution_steps",
            "workflow_nodes",
            ["node_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if os.getenv("ALLOW_SCHEMA_DESTRUCT") != "yes":
        raise RuntimeError(
            "Refusing to drop workflow history columns on the shared Supabase database. "
            "Set ALLOW_SCHEMA_DESTRUCT=yes only against a disposable database."
        )
    bind = op.get_bind()
    foreign_key = _node_foreign_key(sa.inspect(bind))
    if foreign_key is not None:
        op.drop_constraint(foreign_key["name"], "workflow_execution_steps", type_="foreignkey")
        op.create_foreign_key(
            foreign_key["name"],
            "workflow_execution_steps",
            "workflow_nodes",
            ["node_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.drop_column("workflow_execution_steps", "node_label")
    op.drop_column("workflow_execution_steps", "node_type")


def _node_foreign_key(inspector):
    for foreign_key in inspector.get_foreign_keys("workflow_execution_steps"):
        if foreign_key.get("constrained_columns") == ["node_id"]:
            return foreign_key
    return None
