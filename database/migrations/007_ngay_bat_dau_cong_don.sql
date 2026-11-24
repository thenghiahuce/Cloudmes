-- Chạy một lần trên PostgreSQL hiện tại trước khi dùng bản MES này.
-- Giữ NULL cho đơn cũ vì không có ngày bắt đầu gốc để khôi phục chính xác.
ALTER TABLE customer_orders ADD COLUMN IF NOT EXISTS planned_start DATE;
