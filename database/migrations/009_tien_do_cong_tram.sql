-- Lưu sản lượng từng công đoạn và vị trí hiện tại của lô hàng. Không xóa dữ liệu cũ.
BEGIN;
CREATE TABLE IF NOT EXISTS public.customer_order_stage_progress (
    customer_order_id BIGINT NOT NULL REFERENCES public.customer_orders(id) ON DELETE CASCADE,
    machine_id INTEGER NOT NULL REFERENCES public.machines(id),
    process_order INTEGER NOT NULL CHECK(process_order > 0),
    quantity_completed INTEGER NOT NULL DEFAULT 0 CHECK(quantity_completed >= 0),
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by INTEGER REFERENCES public.app_users(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(customer_order_id,machine_id),
    UNIQUE(customer_order_id,process_order)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_order_one_current_stage
 ON public.customer_order_stage_progress(customer_order_id) WHERE is_current;
COMMIT;
