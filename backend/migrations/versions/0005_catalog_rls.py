"""Allow pa_app to read catalog tables even when RLS is enabled.

plans and task_costs have no user_id. Enabling RLS without a SELECT policy
hides every row from pa_app. The tenant ask path then used to INSERT
task_costs (GRANT is SELECT-only) and 500.

Revision ID: 0005_catalog_rls
Revises: 0004_d2_automation
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005_catalog_rls"
down_revision: Union[str, Sequence[str], None] = "0004_d2_automation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.task_costs') IS NOT NULL THEN
            ALTER TABLE task_costs ENABLE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS task_costs_read ON task_costs;
            CREATE POLICY task_costs_read ON task_costs
              FOR SELECT
              USING (true);
          END IF;
          IF to_regclass('public.plans') IS NOT NULL THEN
            ALTER TABLE plans ENABLE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS plans_read ON plans;
            CREATE POLICY plans_read ON plans
              FOR SELECT
              USING (true);
          END IF;
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'pa_app') THEN
            IF to_regclass('public.task_costs') IS NOT NULL THEN
              GRANT SELECT ON TABLE task_costs TO pa_app;
            END IF;
            IF to_regclass('public.plans') IS NOT NULL THEN
              GRANT SELECT ON TABLE plans TO pa_app;
            END IF;
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS task_costs_read ON task_costs")
    op.execute("DROP POLICY IF EXISTS plans_read ON plans")
