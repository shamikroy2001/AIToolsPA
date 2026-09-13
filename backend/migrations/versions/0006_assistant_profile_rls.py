"""Repair assistant_profiles / tasks / ai_usage RLS + GRANTs.

Staging GET /api/me/assistant and POST /api/tasks 500'd while D2 SELECTs
worked. Causes: timestamptz vs naive ORM DateTime, and ENABLE/FORCE RLS
without {table}_tenant (INSERT WITH CHECK fails). The API upserts via
admin + app.user_id; this migration restores the tenant policy + GRANTs.

Revision ID: 0006_assistant_profile_rls
Revises: 0005_catalog_rls
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006_assistant_profile_rls"
down_revision: Union[str, Sequence[str], None] = "0005_catalog_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("assistant_profiles", "assistant_tasks", "ai_usage")


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE t text;
        BEGIN
          FOREACH t IN ARRAY ARRAY['assistant_profiles', 'assistant_tasks', 'ai_usage']
          LOOP
            IF to_regclass('public.' || t) IS NULL THEN
              CONTINUE;
            END IF;
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_tenant', t);
            EXECUTE format(
              'CREATE POLICY %I ON %I FOR ALL '
              'USING (user_id::text = current_setting(''app.user_id'', true)) '
              'WITH CHECK (user_id::text = current_setting(''app.user_id'', true))',
              t || '_tenant', t
            );
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'pa_app') THEN
              EXECUTE format(
                'GRANT SELECT, INSERT, UPDATE ON TABLE %I TO pa_app', t
              );
            END IF;
          END LOOP;
        END
        $$;
        """
    )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
