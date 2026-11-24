-- Thực hiện một lần sau khi sao lưu DB. Không chuyển nhân viên vật lý thành công ty.
ALTER TABLE app_users DROP CONSTRAINT IF EXISTS app_users_role_check;
ALTER TABLE app_users ADD CONSTRAINT app_users_role_check CHECK (role IN ('admin','team_lead','technician','customer'));
CREATE TABLE IF NOT EXISTS customer_companies (
 id BIGSERIAL PRIMARY KEY, company_name VARCHAR(200) NOT NULL UNIQUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS customer_company_id BIGINT REFERENCES customer_companies(id);
CREATE TABLE IF NOT EXISTS customer_orders (
 id BIGSERIAL PRIMARY KEY,
 company_id BIGINT NOT NULL REFERENCES customer_companies(id),
 created_by INTEGER NOT NULL REFERENCES app_users(id),
 workshop_id INTEGER NOT NULL REFERENCES workshops(id),
 product_id INTEGER NOT NULL REFERENCES products(id),
 quantity INTEGER NOT NULL CHECK (quantity > 0),
 expected_date DATE NOT NULL,
 note TEXT NOT NULL DEFAULT '',
 status VARCHAR(40) NOT NULL DEFAULT 'pending_lead' CHECK(status IN ('pending_lead','pending_admin','in_production','rejected')),
 lead_reviewer INTEGER REFERENCES app_users(id), lead_reviewed_at TIMESTAMPTZ,
 admin_reviewer INTEGER REFERENCES app_users(id), admin_reviewed_at TIMESTAMPTZ,
 rejection_reason TEXT, production_order_id INTEGER UNIQUE REFERENCES production_orders(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_customer_orders_company ON customer_orders(company_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_orders_review ON customer_orders(status,workshop_id);
-- Gán khách hàng mẫu bằng scripts/setup_customers.py; không tự đổi hàng loạt tài khoản tổ trưởng.
