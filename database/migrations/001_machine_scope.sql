-- ============================================================
-- MIGRATION 001 - PHÂN QUYỀN THEO MÁY (Giai đoạn 1)
--
-- An toàn khi chạy nhiều lần, KHÔNG xóa dữ liệu hiện có.
-- Chạy bằng:  py scripts/apply_migration.py
-- (script tự chạy auth.sql -> file này -> seed_team_leads.sql
--  trong MỘT transaction, bằng tài khoản trong .env)
--
-- Nếu chạy tay bằng psql: chạy database/auth.sql trước, rồi file này,
-- và dùng cùng user với user của ứng dụng (user đó phải là chủ của các bảng).
-- ============================================================


-- ------------------------------------------------------------
-- 1. Liên kết tài khoản đăng nhập <-> nhân viên
-- ------------------------------------------------------------
ALTER TABLE app_users
    ADD COLUMN IF NOT EXISTS employee_id INTEGER
        REFERENCES employees(id) ON DELETE SET NULL;

-- Tài khoản tạo bằng sync-staff có username = mã nhân viên.
UPDATE app_users u
SET employee_id = e.id
FROM employees e
WHERE e.employee_code = u.username
  AND u.employee_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_app_users_employee ON app_users(employee_id);


-- ------------------------------------------------------------
-- 2. MACHINE_ASSIGNMENTS - ai được quản lý / làm việc trên máy nào
--    team_lead : tổ trưởng quản lý máy
--    member    : kỹ sư / kỹ thuật viên làm việc trên máy
--    (admin không cần dòng nào: admin thấy tất cả máy)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS machine_assignments (
    id SERIAL PRIMARY KEY,
    machine_id INTEGER NOT NULL
        REFERENCES machines(id) ON DELETE CASCADE,
    employee_id INTEGER NOT NULL
        REFERENCES employees(id) ON DELETE CASCADE,
    assignment_role VARCHAR(20) NOT NULL DEFAULT 'team_lead'
        CHECK (assignment_role IN ('team_lead', 'member')),
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(50),
    CONSTRAINT uq_machine_assignment UNIQUE (machine_id, employee_id)
);

CREATE INDEX IF NOT EXISTS idx_machine_assignments_employee
    ON machine_assignments(employee_id);
CREATE INDEX IF NOT EXISTS idx_machine_assignments_machine
    ON machine_assignments(machine_id);


-- ------------------------------------------------------------
-- 3. APP_SCOPE_SESSIONS - phạm vi dữ liệu của MỘT truy vấn
--
-- Backend (không phải AI) INSERT một dòng với token ngẫu nhiên trong
-- transaction của truy vấn, gán token đó vào biến phiên app.scope_token,
-- chạy truy vấn rồi ROLLBACK (dòng này biến mất, không cần dọn dẹp).
-- Các policy bên dưới tra phạm vi theo token. SQL do AI sinh ra không
-- thể tự nâng quyền vì không đoán được token của phiên khác.
-- Role ai_scoped / ai_admin KHÔNG có quyền đọc bảng này.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_scope_sessions (
    token TEXT PRIMARY KEY,
    all_machines BOOLEAN NOT NULL DEFAULT FALSE,
    machine_ids INTEGER[] NOT NULL DEFAULT '{}'
);


-- ------------------------------------------------------------
-- 4. ROLE CHỈ-ĐỌC CHO AI VÀ DASHBOARD
--    ai_scoped : tổ trưởng / kỹ thuật viên - không đọc được employees,
--                attendance, machine_assignments
--    ai_admin  : admin - đọc thêm các bảng nhân sự
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_scoped') THEN
        CREATE ROLE ai_scoped NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_admin') THEN
        CREATE ROLE ai_admin NOLOGIN;
    END IF;
END
$$;

-- Để user của ứng dụng chuyển được sang 2 role này bằng SET LOCAL ROLE.
GRANT ai_scoped TO CURRENT_USER;
GRANT ai_admin  TO CURRENT_USER;


-- ------------------------------------------------------------
-- 5. HÀM TRA PHẠM VI (SECURITY DEFINER: chạy bằng quyền chủ bảng
--    nên không bị chính policy RLS chặn khi tra cứu)
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION app_scope_all() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT COALESCE(
        (SELECT s.all_machines
           FROM app_scope_sessions s
          WHERE s.token = current_setting('app.scope_token', true)),
        FALSE)
$$;

CREATE OR REPLACE FUNCTION app_scope_machine_ids() RETURNS integer[]
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT COALESCE(
        (SELECT s.machine_ids
           FROM app_scope_sessions s
          WHERE s.token = current_setting('app.scope_token', true)),
        '{}'::integer[])
$$;

-- PO nhìn thấy được khi xưởng của PO có ít nhất một máy trong phạm vi.
CREATE OR REPLACE FUNCTION app_scope_workshop_visible(wid integer) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT app_scope_all()
        OR EXISTS (SELECT 1
                     FROM machines m
                    WHERE m.workshop_id = wid
                      AND m.id = ANY (app_scope_machine_ids()))
$$;

-- Kết quả kiểm tra chất lượng nhìn thấy được khi bản ghi sản xuất của nó
-- thuộc máy trong phạm vi.
CREATE OR REPLACE FUNCTION app_scope_record_visible(rid integer) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT app_scope_all()
        OR EXISTS (SELECT 1
                     FROM production_records pr
                    WHERE pr.id = rid
                      AND pr.machine_id = ANY (app_scope_machine_ids()))
$$;


-- ------------------------------------------------------------
-- 6. ROW LEVEL SECURITY
--    Chủ bảng (user của ứng dụng) không bị RLS chặn nên các chức năng
--    nội bộ như đăng nhập vẫn chạy như cũ. Truy vấn Dashboard/AI luôn
--    chạy dưới role ai_scoped / ai_admin nên luôn bị lọc theo phạm vi.
-- ------------------------------------------------------------
ALTER TABLE machines            ENABLE ROW LEVEL SECURITY;
ALTER TABLE production_orders   ENABLE ROW LEVEL SECURITY;
ALTER TABLE production_records  ENABLE ROW LEVEL SECURITY;
ALTER TABLE machine_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE quality_inspections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS scope_select ON machines;
CREATE POLICY scope_select ON machines FOR SELECT
    USING (app_scope_all() OR id = ANY (app_scope_machine_ids()));

DROP POLICY IF EXISTS scope_select ON production_orders;
CREATE POLICY scope_select ON production_orders FOR SELECT
    USING (app_scope_workshop_visible(workshop_id));

DROP POLICY IF EXISTS scope_select ON production_records;
CREATE POLICY scope_select ON production_records FOR SELECT
    USING (app_scope_all() OR machine_id = ANY (app_scope_machine_ids()));

DROP POLICY IF EXISTS scope_select ON machine_logs;
CREATE POLICY scope_select ON machine_logs FOR SELECT
    USING (app_scope_all() OR machine_id = ANY (app_scope_machine_ids()));

DROP POLICY IF EXISTS scope_select ON quality_inspections;
CREATE POLICY scope_select ON quality_inspections FOR SELECT
    USING (app_scope_record_visible(production_record_id));


-- ------------------------------------------------------------
-- 7. QUYỀN TRUY CẬP BẢNG (chỉ SELECT)
-- ------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ai_scoped, ai_admin;

-- Dữ liệu danh mục + dữ liệu sản xuất (sản xuất đã bị RLS lọc theo máy).
GRANT SELECT ON
    factories, workshops, products, production_processes, product_processes,
    machines, production_orders, production_records, machine_logs,
    quality_inspections
TO ai_scoped, ai_admin;

-- Dữ liệu nhân sự: chỉ admin.
GRANT SELECT ON employees, attendance, machine_assignments TO ai_admin;

-- Không bao giờ cho hai role này đụng vào tài khoản và bảng phạm vi.
REVOKE ALL ON app_users, app_scope_sessions FROM ai_scoped, ai_admin;
