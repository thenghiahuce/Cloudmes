-- Giai đoạn 2: giao việc, báo cáo và duyệt. Không thay đổi PO.
CREATE TABLE IF NOT EXISTS tasks (
 id BIGSERIAL PRIMARY KEY,
 machine_id INTEGER NOT NULL REFERENCES machines(id),
 assigned_by INTEGER NOT NULL REFERENCES app_users(id),
 assigned_to INTEGER NOT NULL REFERENCES app_users(id),
 title VARCHAR(255) NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 due_at TIMESTAMPTZ NOT NULL,
 status VARCHAR(30) NOT NULL DEFAULT 'assigned' CHECK (status IN ('assigned','in_progress','submitted','approved','returned')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tasks_machine ON tasks(machine_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assigned_to, status);
CREATE TABLE IF NOT EXISTS task_reports (
 id BIGSERIAL PRIMARY KEY,
 task_id BIGINT NOT NULL REFERENCES tasks(id),
 author_id INTEGER NOT NULL REFERENCES app_users(id),
 summary TEXT NOT NULL,
 errors TEXT NOT NULL DEFAULT '',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reports_task ON task_reports(task_id);
CREATE TABLE IF NOT EXISTS task_reviews (
 id BIGSERIAL PRIMARY KEY,
 task_id BIGINT NOT NULL REFERENCES tasks(id),
 report_id BIGINT NOT NULL REFERENCES task_reports(id),
 reviewer_id INTEGER NOT NULL REFERENCES app_users(id),
 decision VARCHAR(20) NOT NULL CHECK (decision IN ('approved','returned')),
 comment TEXT NOT NULL DEFAULT '',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reviews_task ON task_reviews(task_id);
-- Các bảng mới chỉ được truy cập qua API có xác thực, không cấp SELECT cho ai_scoped.
REVOKE ALL ON tasks, task_reports, task_reviews FROM PUBLIC;
