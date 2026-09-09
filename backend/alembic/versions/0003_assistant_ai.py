"""Assistant profiles, task costs, tasks, internal AI usage.

Revision ID: 0003_assistant_ai
Revises: 0002_billing_credits
Create Date: 2026-09-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_assistant_ai"
down_revision: Union[str, Sequence[str], None] = "0002_billing_credits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rls_user_id(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_tenant ON {table}
        FOR ALL
        USING (user_id::text = current_setting('app.user_id', true))
        WITH CHECK (user_id::text = current_setting('app.user_id', true))
        """
    )


def upgrade() -> None:
    op.create_table(
        "assistant_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_name", sa.String(length=80), nullable=False, server_default="Assistant"),
        sa.Column("personality", sa.String(length=255), nullable=False, server_default="Helpful and concise"),
        sa.Column("response_style", sa.String(length=64), nullable=False, server_default="clear"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("language", sa.String(length=32), nullable=False, server_default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_assistant_profiles_user_id", "assistant_profiles", ["user_id"])

    op.create_table(
        "task_costs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("base_credit_cost", sa.Integer(), nullable=False),
        sa.Column("minimum_cost", sa.Integer(), nullable=False),
        sa.Column("maximum_cost", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_costs_task_type", "task_costs", ["task_type"], unique=True)

    op.create_table(
        "assistant_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False, server_default="assistant_ask"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("input_data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("credits_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_tasks_user_id", "assistant_tasks", ["user_id"])

    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["assistant_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_user_id", "ai_usage", ["user_id"])

    for table in ("assistant_profiles", "assistant_tasks", "ai_usage"):
        _rls_user_id(table)

    op.execute(
        """
        INSERT INTO task_costs (id, task_type, base_credit_cost, minimum_cost, maximum_cost, enabled)
        VALUES (gen_random_uuid(), 'assistant_ask', 5, 1, 20, true)
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'pa_app') THEN
            GRANT SELECT ON TABLE task_costs TO pa_app;
            GRANT SELECT, INSERT, UPDATE ON TABLE assistant_profiles, assistant_tasks, ai_usage TO pa_app;
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    for table in ("ai_usage", "assistant_tasks", "assistant_profiles"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
    op.drop_table("ai_usage")
    op.drop_table("assistant_tasks")
    op.drop_table("task_costs")
    op.drop_table("assistant_profiles")
