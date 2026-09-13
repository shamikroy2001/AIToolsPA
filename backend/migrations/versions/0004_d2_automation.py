"""D2 automation tables: integrations, monitors, schedules, notifications.

Revision ID: 0004_d2_automation
Revises: 0003_assistant_ai
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_d2_automation"
down_revision: Union[str, Sequence[str], None] = "0003_assistant_ai"
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
        "integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="disconnected"),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_integrations_user_id", "integrations", ["user_id"])

    op.create_table(
        "monitored_websites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitored_websites_user_id", "monitored_websites", ["user_id"])

    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("cadence", sa.String(length=64), nullable=False, server_default="daily"),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_tasks_user_id", "scheduled_tasks", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="in_app"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    for table in (
        "integrations",
        "monitored_websites",
        "scheduled_tasks",
        "notifications",
    ):
        _rls_user_id(table)

    op.execute(
        """
        INSERT INTO task_costs (id, task_type, base_credit_cost, minimum_cost, maximum_cost, enabled)
        VALUES
          (gen_random_uuid(), 'gmail_analyze', 8, 2, 40, true),
          (gen_random_uuid(), 'website_monitor', 3, 1, 15, true),
          (gen_random_uuid(), 'telegram_notify', 1, 1, 5, true)
        ON CONFLICT (task_type) DO NOTHING
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'pa_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
              integrations, monitored_websites, scheduled_tasks, notifications
            TO pa_app;
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    for table in (
        "notifications",
        "scheduled_tasks",
        "monitored_websites",
        "integrations",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
        op.drop_table(table)
    op.execute("DELETE FROM task_costs WHERE task_type IN ('gmail_analyze', 'website_monitor', 'telegram_notify')")
