-- Optional: paste in the Supabase SQL editor if POST /api/tasks 500s
-- while GET /api/me and GET /api/credits work. Safe to re-run.
-- Alembic 0005_catalog_rls and bootstrap.sql apply the same policies.

ALTER TABLE task_costs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS task_costs_read ON task_costs;
CREATE POLICY task_costs_read ON task_costs FOR SELECT USING (true);
GRANT SELECT ON TABLE task_costs TO pa_app;

ALTER TABLE plans ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS plans_read ON plans;
CREATE POLICY plans_read ON plans FOR SELECT USING (true);
GRANT SELECT ON TABLE plans TO pa_app;

INSERT INTO task_costs (id, task_type, base_credit_cost, minimum_cost, maximum_cost, enabled)
VALUES (gen_random_uuid(), 'assistant_ask', 5, 1, 20, true)
ON CONFLICT (task_type) DO UPDATE
  SET enabled = true,
      base_credit_cost = 5,
      minimum_cost = 1,
      maximum_cost = 20;
