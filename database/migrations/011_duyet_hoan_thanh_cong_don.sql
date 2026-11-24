-- Quy trình hoàn thành: Tổ trưởng nộp duyệt, chỉ Admin xác nhận hoàn thành.
-- Chạy một lần (an toàn khi chạy lại) trong pgAdmin; sao lưu DB trước khi migration.
BEGIN;
ALTER TABLE customer_orders
    ADD COLUMN IF NOT EXISTS completion_requested_at TIMESTAMPTZ;
ALTER TABLE customer_orders
    ADD COLUMN IF NOT EXISTS completion_requested_by INTEGER REFERENCES app_users(id);
ALTER TABLE customer_orders
    ADD COLUMN IF NOT EXISTS completion_return_reason TEXT;
ALTER TABLE customer_orders
    ADD COLUMN IF NOT EXISTS completion_returned_at TIMESTAMPTZ;
ALTER TABLE customer_orders
    ADD COLUMN IF NOT EXISTS completion_returned_by INTEGER REFERENCES app_users(id);
CREATE INDEX IF NOT EXISTS idx_customer_orders_completion_request
    ON customer_orders(completion_requested_at)
    WHERE status = 'in_production' AND completion_requested_at IS NOT NULL;
COMMIT;
