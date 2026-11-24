-- Chạy SAU migration 005_phan_may_va_tao_ma_cong_don.sql.
-- Thêm thứ tự thực hiện, không thay đổi/xóa các máy hiện có.
BEGIN;
ALTER TABLE public.customer_order_machines
 ADD COLUMN IF NOT EXISTS process_order integer;
ALTER TABLE public.po_machine_assignments
 ADD COLUMN IF NOT EXISTS process_order integer;
-- Dữ liệu cũ không có thứ tự; đặt thứ tự ổn định theo ID máy.
WITH ranked AS (
 SELECT customer_order_id, machine_id,
 ROW_NUMBER() OVER (PARTITION BY customer_order_id ORDER BY machine_id)::integer AS pos
 FROM public.customer_order_machines
)
UPDATE public.customer_order_machines t SET process_order=ranked.pos
 FROM ranked WHERE t.customer_order_id=ranked.customer_order_id AND t.machine_id=ranked.machine_id AND t.process_order IS NULL;
WITH ranked AS (
 SELECT production_order_id, machine_id,
 ROW_NUMBER() OVER (PARTITION BY production_order_id ORDER BY machine_id)::integer AS pos
 FROM public.po_machine_assignments
)
UPDATE public.po_machine_assignments t SET process_order=ranked.pos
 FROM ranked WHERE t.production_order_id=ranked.production_order_id AND t.machine_id=ranked.machine_id AND t.process_order IS NULL;
COMMIT;
