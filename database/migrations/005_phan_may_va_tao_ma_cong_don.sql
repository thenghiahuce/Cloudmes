-- Chạy sau 003_gan_may_lenh_san_xuat.sql và 004_cong_don_khach_hang.sql.
-- Sao lưu PostgreSQL trước khi chạy. Có thể chạy lặp lại.
CREATE TABLE IF NOT EXISTS customer_order_machines (
 customer_order_id BIGINT NOT NULL REFERENCES customer_orders(id) ON DELETE CASCADE,
 machine_id INTEGER NOT NULL REFERENCES machines(id),
 PRIMARY KEY(customer_order_id,machine_id)
);
CREATE SEQUENCE IF NOT EXISTS production_order_code_seq;
-- Chọn số tiếp theo lớn hơn các mã PO-0000001 đã tồn tại.
SELECT setval('production_order_code_seq',
 GREATEST(1,COALESCE((SELECT MAX(SUBSTRING(order_code FROM '^PO-([0-9]+)$')::BIGINT)
 FROM production_orders WHERE order_code ~ '^PO-[0-9]+$'),0)+1), false);
