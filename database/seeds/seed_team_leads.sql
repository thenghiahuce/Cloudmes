-- ============================================================
-- SEED GIAI ĐOẠN 1 - TỔ TRƯỞNG MỚI VÀ GÁN MÁY
--
-- An toàn khi chạy nhiều lần (ON CONFLICT DO NOTHING).
-- KHÔNG đụng vào production_orders / production_records: các PO giữ nguyên.
--
-- Mỗi xưởng LINE01..LINE05 có đúng 1 sản phẩm và 1 PO, nên mỗi tổ trưởng
-- mới quản lý trọn một xưởng = một sản phẩm = một PO:
--   NV-011 LINE01 PCB-A01   PO-LINE01-001
--   NV-012 LINE02 PCB-B01   PO-LINE01-002
--   NV-013 LINE03 PCB-C01   PO-LINE01-003
--   NV-014 LINE04 MCU-001   PO-LINE01-004
--   NV-015 LINE05 SENS-TEMP PO-LINE01-005
-- ============================================================

-- 1. Năm tổ trưởng mới
INSERT INTO employees (
    employee_code, employee_name, workshop_id,
    position, gender, hire_date, employment_status
)
SELECT
    v.employee_code, v.employee_name, w.id,
    v.position, v.gender, v.hire_date::date, v.employment_status
FROM (VALUES
    ('NV-011', 'Phan Văn Hải',   'LINE01', 'Tổ trưởng', 'Nam', '2021-04-12', 'Đang làm'),
    ('NV-012', 'Trịnh Thị Mai',  'LINE02', 'Tổ trưởng', 'Nữ',  '2022-01-17', 'Đang làm'),
    ('NV-013', 'Lương Văn Nam',  'LINE03', 'Tổ trưởng', 'Nam', '2020-10-05', 'Đang làm'),
    ('NV-014', 'Đinh Thị Oanh',  'LINE04', 'Tổ trưởng', 'Nữ',  '2023-02-20', 'Đang làm'),
    ('NV-015', 'Mai Văn Phúc',   'LINE05', 'Tổ trưởng', 'Nam', '2021-08-30', 'Đang làm')
) AS v(employee_code, employee_name, workshop_code, position, gender, hire_date, employment_status)
JOIN workshops w ON w.workshop_code = v.workshop_code
ON CONFLICT (employee_code) DO NOTHING;


-- 2. Chấm công 3 ngày mẫu cho các tổ trưởng mới (cùng ngày với dữ liệu cũ)
INSERT INTO attendance (
    employee_id, workshop_id, work_date, shift,
    check_in, check_out, status, overtime_minutes, note
)
SELECT
    e.id, e.workshop_id, d::date, 'Shift 1',
    d::date + TIME '07:55', d::date + TIME '17:05',
    'Có mặt', 0, NULL
FROM employees e
CROSS JOIN generate_series(
    '2026-08-27'::date, '2026-08-29'::date, INTERVAL '1 day'
) AS d
WHERE e.employee_code IN ('NV-011', 'NV-012', 'NV-013', 'NV-014', 'NV-015')
ON CONFLICT (employee_id, work_date, shift) DO NOTHING;


-- 3. Gán máy
--    Tổ trưởng           -> team_lead  trên mọi máy của xưởng mình
--    Kỹ sư / kỹ thuật viên -> member   trên mọi máy của xưởng mình
--    (gồm cả 3 tổ trưởng cũ NV-001, NV-004, NV-008 để tài khoản cũ
--     không mất dữ liệu). Chỉnh lại sau bằng:
--       py scripts/manage_users.py assign / unassign
INSERT INTO machine_assignments (machine_id, employee_id, assignment_role, assigned_by)
SELECT
    m.id,
    e.id,
    CASE WHEN e.position ILIKE '%tổ trưởng%' THEN 'team_lead' ELSE 'member' END,
    'seed'
FROM employees e
JOIN machines m ON m.workshop_id = e.workshop_id
WHERE e.employment_status IN ('Đang làm', 'Đang làm việc', 'Active')
  AND (   e.position ILIKE '%tổ trưởng%'
       OR e.position ILIKE '%kỹ thuật%' OR e.position ILIKE '%kĩ thuật%'
       OR e.position ILIKE '%kỹ sư%'    OR e.position ILIKE '%kĩ sư%')
ON CONFLICT (machine_id, employee_id) DO NOTHING;
