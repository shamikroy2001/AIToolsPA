"""Align credit/subscription timestamps with aware ORM binds.

POST /api/tasks 503'd in CreditService.reserve: asyncpg DataError
because the ORM bound utc_now() (aware) as TIMESTAMP WITHOUT TIME ZONE
on credit_transactions.created_at. Alembic 0002 created timestamptz;
this repair converts any leftover naive timestamp columns.

Revision ID: 0007_credit_timestamptz
Revises: 0006_assistant_profile_rls
Create Date: 2026-09-14
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007_credit_timestamptz"
down_revision: Union[str, Sequence[str], None] = "0006_assistant_profile_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN
            SELECT c.table_name, c.column_name
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.table_name IN (
                'credit_accounts', 'credit_lots', 'credit_transactions',
                'subscriptions', 'stripe_events',
                'assistant_tasks', 'ai_usage', 'assistant_profiles'
              )
              AND c.column_name IN (
                'created_at', 'updated_at', 'completed_at',
                'current_period_start', 'current_period_end', 'expires_at'
              )
              AND c.data_type = 'timestamp without time zone'
          LOOP
            EXECUTE format(
              'ALTER TABLE %I ALTER COLUMN %I TYPE timestamptz '
              'USING %I AT TIME ZONE %L',
              r.table_name, r.column_name, r.column_name, 'UTC'
            );
          END LOOP;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Repair only converted leftover naive columns. Do not widen-narrow
    # columns that 0002/0003 already created as timestamptz.
    return
