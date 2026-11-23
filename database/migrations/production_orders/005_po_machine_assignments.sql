-- Chạy một lần trong pgAdmin, trên database testmes. Không xóa hoặc sửa dữ liệu cũ.
BEGIN;
CREATE TABLE IF NOT EXISTS public.po_machine_assignments (
  production_order_id integer NOT NULL REFERENCES public.production_orders(id) ON DELETE CASCADE,
  machine_id integer NOT NULL REFERENCES public.machines(id),
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (production_order_id,machine_id)
);
CREATE INDEX IF NOT EXISTS idx_po_machine_assignments_machine ON public.po_machine_assignments(machine_id);
-- Đồng bộ danh sách máy cho PO đã có lịch sử sản xuất.
INSERT INTO public.po_machine_assignments(production_order_id,machine_id)
SELECT DISTINCT production_order_id,machine_id FROM public.production_records
WHERE production_order_id IS NOT NULL AND machine_id IS NOT NULL
ON CONFLICT DO NOTHING;
COMMIT;
