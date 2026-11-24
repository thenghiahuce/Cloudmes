-- Chạy MỘT LẦN trên PostgreSQL sau khi sao lưu DB; không tự chạy khi app khởi động.
BEGIN;
ALTER TABLE customer_orders ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE customer_orders ADD COLUMN IF NOT EXISTS completed_by INTEGER REFERENCES app_users(id);
ALTER TABLE customer_orders DROP CONSTRAINT IF EXISTS customer_orders_status_check;
ALTER TABLE customer_orders ADD CONSTRAINT customer_orders_status_check
  CHECK(status IN ('pending_lead','pending_admin','in_production','completed','rejected'));
CREATE INDEX IF NOT EXISTS idx_customer_orders_completed_at ON customer_orders(completed_at)
  WHERE status='completed';
COMMIT;
