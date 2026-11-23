-- Giữ nguyên dữ liệu lịch sử và chỉ ẩn công đơn đã xóa ở giao diện.
ALTER TABLE public.customer_orders
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_customer_orders_active
  ON public.customer_orders (created_by, created_at DESC)
  WHERE deleted_at IS NULL;
