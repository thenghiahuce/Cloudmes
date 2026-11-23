-- Phase 2: Task workflow. Does not alter production_orders or existing production records.
CREATE TABLE IF NOT EXISTS tasks (
 id BIGSERIAL PRIMARY KEY,
 machine_id INTEGER NOT NULL REFERENCES machines(id) ON DELETE RESTRICT,
 assigned_by INTEGER NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 assigned_to INTEGER NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 title VARCHAR(200) NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 due_at TIMESTAMPTZ NOT NULL,
 status VARCHAR(24) NOT NULL DEFAULT 'assigned' CHECK (status IN ('assigned','in_progress','submitted','approved','returned')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 started_at TIMESTAMPTZ,
 completed_at TIMESTAMPTZ,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tasks_machine ON tasks(machine_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assigned_to,created_at DESC);
CREATE TABLE IF NOT EXISTS task_reports (
 id BIGSERIAL PRIMARY KEY,
 task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
 submitted_by INTEGER NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 work_done TEXT NOT NULL,
 errors_found TEXT NOT NULL DEFAULT '',
 submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reports_task ON task_reports(task_id,submitted_at DESC);
CREATE TABLE IF NOT EXISTS task_reviews (
 id BIGSERIAL PRIMARY KEY,
 task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
 report_id BIGINT NOT NULL REFERENCES task_reports(id) ON DELETE RESTRICT,
 reviewer_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 decision VARCHAR(16) NOT NULL CHECK (decision IN ('approved','returned')),
 comment TEXT NOT NULL DEFAULT '',
 reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reviews_task ON task_reviews(task_id,reviewed_at DESC);
