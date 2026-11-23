-- ============================================================
-- FACTORY AI - SEED DATA
-- PostgreSQL
--
-- Chạy SAU schema.sql. Tài khoản đăng nhập (app_users) tạo bằng
-- scripts/manage_users.py, không nằm trong file này.
-- ============================================================
 
-- ============================================================
-- 1. FACTORY
-- ============================================================
 
INSERT INTO factories (
    factory_code,
    factory_name,
    location
)
VALUES (
    'FAC001',
    'Nhà máy Điện tử Bắc Ninh',
    'Bắc Ninh, Việt Nam'
);
 
 
-- ============================================================
-- 2. WORKSHOP
-- ============================================================
 
INSERT INTO workshops (
    factory_id,
    workshop_code,
    workshop_name,
    workshop_type
)
SELECT
    id,
    'LINE01',
    'Xưởng Lắp ráp - Bắc Ninh',
    'Electronics Assembly'
FROM factories
WHERE factory_code = 'FAC001';
 
-- ============================================================
-- BỔ SUNG 4 XƯỞNG CHO 4 PO MỚI
-- ============================================================
 
INSERT INTO workshops (
    factory_id,
    workshop_code,
    workshop_name,
    workshop_type
)
SELECT
    id,
    'LINE02',
    'Xưởng SMT - Bắc Ninh',
    'SMT Production'
FROM factories
WHERE factory_code = 'FAC001';
 
INSERT INTO workshops (
    factory_id,
    workshop_code,
    workshop_name,
    workshop_type
)
SELECT
    id,
    'LINE03',
    'Xưởng Gia công - Bắc Ninh',
    'Machining'
FROM factories
WHERE factory_code = 'FAC001';
 
INSERT INTO workshops (
    factory_id,
    workshop_code,
    workshop_name,
    workshop_type
)
SELECT
    id,
    'LINE04',
    'Xưởng Lắp ráp linh kiện - Bắc Ninh',
    'Electronics Assembly'
FROM factories
WHERE factory_code = 'FAC001';
 
INSERT INTO workshops (
    factory_id,
    workshop_code,
    workshop_name,
    workshop_type
)
SELECT
    id,
    'LINE05',
    'Xưởng Kiểm tra - Bắc Ninh',
    'Quality Control'
FROM factories
WHERE factory_code = 'FAC001';
 
 
 
-- ============================================================
-- 3. PRODUCT
-- ============================================================
 
INSERT INTO products (
    product_code,
    product_name,
    product_type,
    unit,
    standard_cycle_time_minutes
)
VALUES (
    'PCB-A01',
    'Bo mạch PCB loại A',
    'PCB',
    'piece',
    10
);
 
-- ============================================================
-- BỔ SUNG 4 SẢN PHẨM CHO 4 PO MỚI
-- ============================================================
 
INSERT INTO products (
    product_code,
    product_name,
    product_type,
    unit,
    standard_cycle_time_minutes
)
VALUES
(
    'PCB-B01',
    'Bo mạch PCB loại B',
    'PCB',
    'piece',
    12
),
(
    'PCB-C01',
    'Bo mạch PCB đa lớp loại C',
    'PCB',
    'piece',
    15
),
(
    'MCU-001',
    'Vi điều khiển 8-bit MCU',
    'Chip',
    'piece',
    3
),
(
    'SENS-TEMP',
    'Cảm biến nhiệt độ',
    'Sensor',
    'piece',
    4
);
 
 
 
-- ============================================================
-- 4. PRODUCTION PROCESSES
-- ============================================================
--
-- THỨ TỰ DÂY CHUYỀN:
--
-- 1. Cắt
-- 2. CNC
-- 3. Mài
-- 4. Lắp ráp
-- 5. Kiểm tra
-- 6. Đóng gói
--
-- ============================================================
 
INSERT INTO production_processes (
    process_code,
    process_name,
    process_order,
    description
)
VALUES
(
    'CUT',
    'Cắt',
    1,
    'Cắt PCB theo kích thước yêu cầu'
),
(
    'CNC',
    'CNC',
    2,
    'Gia công PCB bằng máy CNC'
),
(
    'GRIND',
    'Mài',
    3,
    'Mài và xử lý bề mặt PCB'
),
(
    'ASSY',
    'Lắp ráp',
    4,
    'Lắp ráp linh kiện PCB'
),
(
    'QC',
    'Kiểm tra',
    5,
    'Kiểm tra chất lượng PCB'
),
(
    'PACK',
    'Đóng gói',
    6,
    'Đóng gói sản phẩm hoàn thành'
);
 
 
-- ============================================================
-- 4B. PRODUCT_PROCESSES
-- ============================================================
--
-- Công đoạn của từng sản phẩm (dữ liệu mẫu):
-- PCB đi đủ 6 công đoạn; MCU và cảm biến đi ít công đoạn hơn.
--
-- ============================================================
 
INSERT INTO product_processes (
    product_id,
    process_id,
    process_order
)
SELECT
    p.id,
    pr.id,
    v.step
FROM (VALUES
    ('PCB-A01',   'CUT',   1),
    ('PCB-A01',   'CNC',   2),
    ('PCB-A01',   'GRIND', 3),
    ('PCB-A01',   'ASSY',  4),
    ('PCB-A01',   'QC',    5),
    ('PCB-A01',   'PACK',  6),
    ('PCB-B01',   'CUT',   1),
    ('PCB-B01',   'CNC',   2),
    ('PCB-B01',   'GRIND', 3),
    ('PCB-B01',   'ASSY',  4),
    ('PCB-B01',   'QC',    5),
    ('PCB-B01',   'PACK',  6),
    ('PCB-C01',   'CUT',   1),
    ('PCB-C01',   'CNC',   2),
    ('PCB-C01',   'GRIND', 3),
    ('PCB-C01',   'ASSY',  4),
    ('PCB-C01',   'QC',    5),
    ('PCB-C01',   'PACK',  6),
    ('MCU-001',   'CNC',   1),
    ('MCU-001',   'ASSY',  2),
    ('MCU-001',   'QC',    3),
    ('MCU-001',   'PACK',  4),
    ('SENS-TEMP', 'ASSY',  1),
    ('SENS-TEMP', 'QC',    2),
    ('SENS-TEMP', 'PACK',  3)
) AS v(product_code, process_code, step)
JOIN products p
    ON p.product_code = v.product_code
JOIN production_processes pr
    ON pr.process_code = v.process_code;
 
 
-- ============================================================
-- 5. MACHINES
-- ============================================================
 
INSERT INTO machines (
    machine_code,
    machine_name,
    workshop_id,
    process_id,
    machine_type,
    manufacturer,
    status,
    installation_date
)
SELECT
    'MC001',
    'Máy cắt PCB #1',
    w.id,
    p.id,
    'PCB Cutter',
    'Factory Equipment',
    'Running',
    '2024-01-10'
FROM workshops w
CROSS JOIN production_processes p
WHERE w.workshop_code = 'LINE01'
  AND p.process_code = 'CUT';
 
 
INSERT INTO machines (
    machine_code,
    machine_name,
    workshop_id,
    process_id,
    machine_type,
    manufacturer,
    status,
    installation_date
)
SELECT
    'MC003',
    'Máy CNC #1',
    w.id,
    p.id,
    'CNC Machine',
    'Factory Equipment',
    'Running',
    '2024-01-15'
FROM workshops w
CROSS JOIN production_processes p
WHERE w.workshop_code = 'LINE01'
  AND p.process_code = 'CNC';
 
 
INSERT INTO machines (
    machine_code,
    machine_name,
    workshop_id,
    process_id,
    machine_type,
    manufacturer,
    status,
    installation_date
)
SELECT
    'MC005',
    'Máy mài #1',
    w.id,
    p.id,
    'Grinding Machine',
    'Factory Equipment',
    'Running',
    '2024-01-20'
FROM workshops w
CROSS JOIN production_processes p
WHERE w.workshop_code = 'LINE01'
  AND p.process_code = 'GRIND';
 
 
INSERT INTO machines (
    machine_code,
    machine_name,
    workshop_id,
    process_id,
    machine_type,
    manufacturer,
    status,
    installation_date
)
SELECT
    'MC007',
    'Trạm lắp ráp #2',
    w.id,
    p.id,
    'Assembly Station',
    'Factory Equipment',
    'Running',
    '2024-02-01'
FROM workshops w
CROSS JOIN production_processes p
WHERE w.workshop_code = 'LINE01'
  AND p.process_code = 'ASSY';
 
 
INSERT INTO machines (
    machine_code,
    machine_name,
    workshop_id,
    process_id,
    machine_type,
    manufacturer,
    status,
    installation_date
)
SELECT
    'MC008',
    'Máy kiểm tra QC #1',
    w.id,
    p.id,
    'QC Machine',
    'Factory Equipment',
    'Running',
    '2024-02-05'
FROM workshops w
CROSS JOIN production_processes p
WHERE w.workshop_code = 'LINE01'
  AND p.process_code = 'QC';
 
 
INSERT INTO machines (
    machine_code,
    machine_name,
    workshop_id,
    process_id,
    machine_type,
    manufacturer,
    status,
    installation_date
)
SELECT
    'MC009',
    'Máy đóng gói #1',
    w.id,
    p.id,
    'Packaging Machine',
    'Factory Equipment',
    'Running',
    '2024-02-10'
FROM workshops w
CROSS JOIN production_processes p
WHERE w.workshop_code = 'LINE01'
  AND p.process_code = 'PACK';
 
-- ============================================================
-- BỔ SUNG MÁY CHO 4 PO MỚI
-- ============================================================
 
INSERT INTO machines (
    machine_code,
    machine_name,
    workshop_id,
    process_id,
    machine_type,
    manufacturer,
    status,
    installation_date
)
SELECT
    'MC010',
    'Máy SMT #1',
    w.id,
    p.id,
    'SMT Machine',
    'Factory Equipment',
    'Running',
    '2024-03-01'
FROM workshops w
CROSS JOIN production_processes p
WHERE w.workshop_code = 'LINE02'
  AND p.process_code = 'CUT';
 
INSERT INTO machines (
    machine_code,
    machine_name,
    workshop_id,
    process_id,
    machine_type,
    manufacturer,
    status,
    installation_date
)
SELECT
    'MC011',
    'Máy gia công #1',
    w.id,
    p.id,
    'Machining Machine',
    'Factory Equipment',
    'Running',
    '2024-03-05'
FROM workshops w
CROSS JOIN production_processes p
WHERE w.workshop_code = 'LINE03'
  AND p.process_code = 'CNC';
 
INSERT INTO machines (
    machine_code,
    machine_name,
    workshop_id,
    process_id,
    machine_type,
    manufacturer,
    status,
    installation_date
)
SELECT
    'MC012',
    'Trạm lắp ráp #3',
    w.id,
    p.id,
    'Assembly Station',
    'Factory Equipment',
    'Running',
    '2024-03-10'
FROM workshops w
CROSS JOIN production_processes p
WHERE w.workshop_code = 'LINE04'
  AND p.process_code = 'ASSY';
 
INSERT INTO machines (
    machine_code,
    machine_name,
    workshop_id,
    process_id,
    machine_type,
    manufacturer,
    status,
    installation_date
)
SELECT
    'MC013',
    'Máy kiểm tra nhiệt #1',
    w.id,
    p.id,
    'Inspection Machine',
    'Factory Equipment',
    'Running',
    '2024-03-15'
FROM workshops w
CROSS JOIN production_processes p
WHERE w.workshop_code = 'LINE05'
  AND p.process_code = 'QC';
 
 
 
-- ============================================================
-- 6. PRODUCTION ORDER
-- ============================================================
 
INSERT INTO production_orders (
    order_code,
    workshop_id,
    product_id,
    planned_quantity,
    planned_start,
    planned_end,
    actual_start,
    actual_end,
    status
)
SELECT
    'PO-LINE01-001',
    w.id,
    p.id,
    1000,
    '2026-08-27 08:00:00',
    '2026-08-27 18:00:00',
    '2026-08-27 08:10:00',
    NULL,
    'In Progress'
FROM workshops w
CROSS JOIN products p
WHERE w.workshop_code = 'LINE01'
  AND p.product_code = 'PCB-A01';
 
-- ============================================================
-- BỔ SUNG PO 002 → 005
-- Mỗi PO dùng một xưởng và một sản phẩm khác nhau.
-- ============================================================
 
INSERT INTO production_orders (
    order_code,
    workshop_id,
    product_id,
    planned_quantity,
    planned_start,
    planned_end,
    actual_start,
    actual_end,
    status
)
SELECT
    'PO-LINE01-002',
    w.id,
    p.id,
    1200,
    '2026-08-28 08:00:00',
    '2026-08-28 18:00:00',
    '2026-08-28 08:05:00',
    NULL,
    'In Progress'
FROM workshops w
CROSS JOIN products p
WHERE w.workshop_code = 'LINE02'
  AND p.product_code = 'PCB-B01';
 
INSERT INTO production_orders (
    order_code,
    workshop_id,
    product_id,
    planned_quantity,
    planned_start,
    planned_end,
    actual_start,
    actual_end,
    status
)
SELECT
    'PO-LINE01-003',
    w.id,
    p.id,
    800,
    '2026-08-29 08:00:00',
    '2026-08-29 17:00:00',
    '2026-08-29 08:15:00',
    '2026-08-29 16:45:00',
    'Completed'
FROM workshops w
CROSS JOIN products p
WHERE w.workshop_code = 'LINE03'
  AND p.product_code = 'PCB-C01';
 
INSERT INTO production_orders (
    order_code,
    workshop_id,
    product_id,
    planned_quantity,
    planned_start,
    planned_end,
    actual_start,
    actual_end,
    status
)
SELECT
    'PO-LINE01-004',
    w.id,
    p.id,
    1500,
    '2026-08-30 08:00:00',
    '2026-08-30 18:00:00',
    '2026-08-30 08:20:00',
    NULL,
    'In Progress'
FROM workshops w
CROSS JOIN products p
WHERE w.workshop_code = 'LINE04'
  AND p.product_code = 'MCU-001';
 
INSERT INTO production_orders (
    order_code,
    workshop_id,
    product_id,
    planned_quantity,
    planned_start,
    planned_end,
    actual_start,
    actual_end,
    status
)
SELECT
    'PO-LINE01-005',
    w.id,
    p.id,
    900,
    '2026-08-31 08:00:00',
    '2026-08-31 17:00:00',
    NULL,
    NULL,
    'Planned'
FROM workshops w
CROSS JOIN products p
WHERE w.workshop_code = 'LINE05'
  AND p.product_code = 'SENS-TEMP';
 
 
 
-- ============================================================
-- 7. PRODUCTION RECORD - CUT
-- ============================================================
 
INSERT INTO production_records (
    production_order_id,
    production_date,
    shift,
    quantity_produced,
    quantity_defective,
    production_minutes,
    machine_id
)
SELECT
    po.id,
    '2026-08-27',
    'Shift 1',
    1000,
    0,
    120,
    m.id
FROM production_orders po
JOIN machines m
    ON m.machine_code = 'MC001'
WHERE po.order_code = 'PO-LINE01-001';
 
 
-- ============================================================
-- 8. PRODUCTION RECORD - CNC
-- ============================================================
 
INSERT INTO production_records (
    production_order_id,
    production_date,
    shift,
    quantity_produced,
    quantity_defective,
    production_minutes,
    machine_id
)
SELECT
    po.id,
    '2026-08-27',
    'Shift 1',
    980,
    20,
    180,
    m.id
FROM production_orders po
JOIN machines m
    ON m.machine_code = 'MC003'
WHERE po.order_code = 'PO-LINE01-001';
 
 
-- ============================================================
-- 9. PRODUCTION RECORD - GRIND
-- ============================================================
 
INSERT INTO production_records (
    production_order_id,
    production_date,
    shift,
    quantity_produced,
    quantity_defective,
    production_minutes,
    machine_id
)
SELECT
    po.id,
    '2026-08-27',
    'Shift 1',
    970,
    10,
    150,
    m.id
FROM production_orders po
JOIN machines m
    ON m.machine_code = 'MC005'
WHERE po.order_code = 'PO-LINE01-001';
 
 
-- ============================================================
-- 10. PRODUCTION RECORD - ASSY
-- ============================================================
 
INSERT INTO production_records (
    production_order_id,
    production_date,
    shift,
    quantity_produced,
    quantity_defective,
    production_minutes,
    machine_id
)
SELECT
    po.id,
    '2026-08-27',
    'Shift 1',
    955,
    15,
    210,
    m.id
FROM production_orders po
JOIN machines m
    ON m.machine_code = 'MC007'
WHERE po.order_code = 'PO-LINE01-001';
 
 
-- ============================================================
-- 11. PRODUCTION RECORD - QC
-- ============================================================
 
INSERT INTO production_records (
    production_order_id,
    production_date,
    shift,
    quantity_produced,
    quantity_defective,
    production_minutes,
    machine_id
)
SELECT
    po.id,
    '2026-08-27',
    'Shift 1',
    955,
    15,
    90,
    m.id
FROM production_orders po
JOIN machines m
    ON m.machine_code = 'MC008'
WHERE po.order_code = 'PO-LINE01-001';
 
 
-- ============================================================
-- 12. PRODUCTION RECORD - PACK
-- ============================================================
 
INSERT INTO production_records (
    production_order_id,
    production_date,
    shift,
    quantity_produced,
    quantity_defective,
    production_minutes,
    machine_id
)
SELECT
    po.id,
    '2026-08-27',
    'Shift 1',
    940,
    0,
    100,
    m.id
FROM production_orders po
JOIN machines m
    ON m.machine_code = 'MC009'
WHERE po.order_code = 'PO-LINE01-001';
 
 
 
 
-- ============================================================
-- PRODUCTION RECORD CHO PO 002 → 005
-- Mỗi PO có 1 máy chính trong danh sách Dashboard.
-- ============================================================
 
INSERT INTO production_records (
    production_order_id,
    production_date,
    shift,
    quantity_produced,
    quantity_defective,
    production_minutes,
    machine_id
)
SELECT
    po.id,
    '2026-08-28',
    'Shift 1',
    1150,
    10,
    240,
    m.id
FROM production_orders po
JOIN machines m
    ON m.machine_code = 'MC010'
WHERE po.order_code = 'PO-LINE01-002';
 
INSERT INTO production_records (
    production_order_id,
    production_date,
    shift,
    quantity_produced,
    quantity_defective,
    production_minutes,
    machine_id
)
SELECT
    po.id,
    '2026-08-29',
    'Shift 1',
    780,
    12,
    260,
    m.id
FROM production_orders po
JOIN machines m
    ON m.machine_code = 'MC011'
WHERE po.order_code = 'PO-LINE01-003';
 
INSERT INTO production_records (
    production_order_id,
    production_date,
    shift,
    quantity_produced,
    quantity_defective,
    production_minutes,
    machine_id
)
SELECT
    po.id,
    '2026-08-30',
    'Shift 1',
    1450,
    20,
    300,
    m.id
FROM production_orders po
JOIN machines m
    ON m.machine_code = 'MC012'
WHERE po.order_code = 'PO-LINE01-004';
 
INSERT INTO production_records (
    production_order_id,
    production_date,
    shift,
    quantity_produced,
    quantity_defective,
    production_minutes,
    machine_id
)
SELECT
    po.id,
    '2026-08-31',
    'Shift 1',
    880,
    8,
    180,
    m.id
FROM production_orders po
JOIN machines m
    ON m.machine_code = 'MC013'
WHERE po.order_code = 'PO-LINE01-005';
 
 
-- ============================================================
-- QUALITY INSPECTION CHO PO 002 → 005
-- ============================================================
 
INSERT INTO quality_inspections (
    production_record_id,
    inspection_time,
    total_checked,
    passed_quantity,
    failed_quantity,
    defect_type,
    inspector_name
)
SELECT
    pr.id,
    '2026-08-28 15:30:00',
    1150,
    1140,
    10,
    'Lỗi hàn',
    'QC Inspector 02'
FROM production_records pr
JOIN production_orders po
    ON po.id = pr.production_order_id
WHERE po.order_code = 'PO-LINE01-002';
 
INSERT INTO quality_inspections (
    production_record_id,
    inspection_time,
    total_checked,
    passed_quantity,
    failed_quantity,
    defect_type,
    inspector_name
)
SELECT
    pr.id,
    '2026-08-29 15:30:00',
    780,
    768,
    12,
    'Sai kích thước',
    'QC Inspector 03'
FROM production_records pr
JOIN production_orders po
    ON po.id = pr.production_order_id
WHERE po.order_code = 'PO-LINE01-003';
 
INSERT INTO quality_inspections (
    production_record_id,
    inspection_time,
    total_checked,
    passed_quantity,
    failed_quantity,
    defect_type,
    inspector_name
)
SELECT
    pr.id,
    '2026-08-30 15:30:00',
    1450,
    1430,
    20,
    'Lỗi linh kiện',
    'QC Inspector 04'
FROM production_records pr
JOIN production_orders po
    ON po.id = pr.production_order_id
WHERE po.order_code = 'PO-LINE01-004';
 
INSERT INTO quality_inspections (
    production_record_id,
    inspection_time,
    total_checked,
    passed_quantity,
    failed_quantity,
    defect_type,
    inspector_name
)
SELECT
    pr.id,
    '2026-08-31 15:30:00',
    880,
    872,
    8,
    'Sai số nhiệt độ',
    'QC Inspector 05'
FROM production_records pr
JOIN production_orders po
    ON po.id = pr.production_order_id
WHERE po.order_code = 'PO-LINE01-005';
 
 
-- ============================================================
-- 13. QUALITY INSPECTION
-- ============================================================
--
-- Lỗi chất lượng:
-- Lỗi hàn = 15
--
-- Gắn với record QC của PO.
--
-- ============================================================
 
INSERT INTO quality_inspections (
    production_record_id,
    inspection_time,
    total_checked,
    passed_quantity,
    failed_quantity,
    defect_type,
    inspector_name
)
SELECT
    pr.id,
    '2026-08-27 16:30:00',
    955,
    940,
    15,
    'Lỗi hàn',
    'QC Inspector 01'
FROM production_records pr
JOIN production_orders po
    ON po.id = pr.production_order_id
JOIN machines m
    ON m.id = pr.machine_id
JOIN production_processes pp
    ON pp.id = m.process_id
WHERE po.order_code = 'PO-LINE01-001'
  AND pp.process_code = 'QC';
 
 
-- ============================================================
-- 14. MACHINE LOGS
-- ============================================================
--
-- LƯU Ý:
--
-- Mỗi log gắn trực tiếp với PO qua production_order_id.
--
-- Tổng downtime của PO-LINE01-001:
-- 30 + 60 + 40 + 35 + 15 + 10 = 190 phút.
--
-- ============================================================
 
INSERT INTO machine_logs (
    machine_id,
    start_time,
    end_time,
    status,
    downtime_minutes,
    reason,
    production_order_id
)
SELECT
    m.id,
    '2026-08-27 10:00:00',
    '2026-08-27 10:30:00',
    'Downtime',
    30,
    'Bảo trì máy',
    po.id
FROM machines m
JOIN production_orders po
    ON po.order_code = 'PO-LINE01-001'
WHERE m.machine_code = 'MC001';
 
 
INSERT INTO machine_logs (
    machine_id,
    start_time,
    end_time,
    status,
    downtime_minutes,
    reason,
    production_order_id
)
SELECT
    m.id,
    '2026-08-27 11:00:00',
    '2026-08-27 12:00:00',
    'Downtime',
    60,
    'Chờ xử lý sự cố máy',
    po.id
FROM machines m
JOIN production_orders po
    ON po.order_code = 'PO-LINE01-001'
WHERE m.machine_code = 'MC003';
 
 
INSERT INTO machine_logs (
    machine_id,
    start_time,
    end_time,
    status,
    downtime_minutes,
    reason,
    production_order_id
)
SELECT
    m.id,
    '2026-08-27 13:00:00',
    '2026-08-27 13:40:00',
    'Downtime',
    40,
    'Vệ sinh và căn chỉnh máy',
    po.id
FROM machines m
JOIN production_orders po
    ON po.order_code = 'PO-LINE01-001'
WHERE m.machine_code = 'MC005';
 
 
INSERT INTO machine_logs (
    machine_id,
    start_time,
    end_time,
    status,
    downtime_minutes,
    reason,
    production_order_id
)
SELECT
    m.id,
    '2026-08-27 14:00:00',
    '2026-08-27 14:35:00',
    'Downtime',
    35,
    'Chờ vật tư',
    po.id
FROM machines m
JOIN production_orders po
    ON po.order_code = 'PO-LINE01-001'
WHERE m.machine_code = 'MC007';
 
 
INSERT INTO machine_logs (
    machine_id,
    start_time,
    end_time,
    status,
    downtime_minutes,
    reason,
    production_order_id
)
SELECT
    m.id,
    '2026-08-27 15:00:00',
    '2026-08-27 15:15:00',
    'Downtime',
    15,
    'Kiểm tra thiết bị',
    po.id
FROM machines m
JOIN production_orders po
    ON po.order_code = 'PO-LINE01-001'
WHERE m.machine_code = 'MC008';
 
 
INSERT INTO machine_logs (
    machine_id,
    start_time,
    end_time,
    status,
    downtime_minutes,
    reason,
    production_order_id
)
SELECT
    m.id,
    '2026-08-27 17:00:00',
    '2026-08-27 17:10:00',
    'Downtime',
    10,
    'Điều chỉnh bao bì',
    po.id
FROM machines m
JOIN production_orders po
    ON po.order_code = 'PO-LINE01-001'
WHERE m.machine_code = 'MC009';
 
 
-- ============================================================
-- 14B. EMPLOYEES (dữ liệu mẫu)
-- ============================================================
--
-- Chức vụ Tổ trưởng / Kỹ thuật viên / Kỹ sư sẽ được
-- manage_users.py sync-staff tự cấp tài khoản.
--
-- ============================================================
 
INSERT INTO employees (
    employee_code,
    employee_name,
    workshop_id,
    position,
    gender,
    hire_date,
    employment_status
)
SELECT
    v.employee_code,
    v.employee_name,
    w.id,
    v.position,
    v.gender,
    v.hire_date::date,
    v.employment_status
FROM (VALUES
    ('NV-001', 'Nguyễn Văn An',  'LINE01', 'Tổ trưởng',     'Nam', '2022-03-01', 'Đang làm'),
    ('NV-002', 'Trần Thị Bình',  'LINE01', 'Kỹ thuật viên', 'Nữ',  '2023-05-15', 'Đang làm'),
    ('NV-003', 'Lê Văn Cường',   'LINE01', 'Công nhân',     'Nam', '2023-08-10', 'Đang làm'),
    ('NV-004', 'Phạm Thị Dung',  'LINE02', 'Tổ trưởng',     'Nữ',  '2021-11-20', 'Đang làm'),
    ('NV-005', 'Hoàng Văn Em',   'LINE02', 'Kỹ sư',         'Nam', '2022-07-05', 'Đang làm'),
    ('NV-006', 'Vũ Thị Hà',      'LINE03', 'Kỹ thuật viên', 'Nữ',  '2024-01-08', 'Đang làm'),
    ('NV-007', 'Đặng Văn Giang', 'LINE03', 'Công nhân',     'Nam', '2024-02-19', 'Đang làm'),
    ('NV-008', 'Bùi Thị Hoa',    'LINE04', 'Tổ trưởng',     'Nữ',  '2020-09-14', 'Đang làm'),
    ('NV-009', 'Đỗ Văn Khánh',   'LINE05', 'Kỹ thuật viên', 'Nam', '2023-12-01', 'Đang làm'),
    ('NV-010', 'Ngô Thị Lan',    'LINE05', 'Công nhân',     'Nữ',  '2022-06-30', 'Nghỉ việc')
) AS v(employee_code, employee_name, workshop_code, position, gender, hire_date, employment_status)
JOIN workshops w
    ON w.workshop_code = v.workshop_code;
 
 
-- ============================================================
-- 14C. ATTENDANCE (3 ngày, nhân viên đang làm)
-- ============================================================
 
INSERT INTO attendance (
    employee_id,
    workshop_id,
    work_date,
    shift,
    check_in,
    check_out,
    status,
    overtime_minutes,
    note
)
SELECT
    e.id,
    e.workshop_id,
    d::date,
    'Shift 1',
    d::date + TIME '07:55',
    d::date + TIME '17:05',
    'Có mặt',
    0,
    NULL
FROM employees e
CROSS JOIN generate_series(
    '2026-08-27'::date,
    '2026-08-29'::date,
    INTERVAL '1 day'
) AS d
WHERE e.employment_status = 'Đang làm';
 
-- Một số trường hợp khác để có đủ trạng thái.
UPDATE attendance a
SET status = 'Đi muộn',
    check_in = a.work_date + TIME '08:25',
    note = 'Kẹt xe'
FROM employees e
WHERE e.id = a.employee_id
  AND e.employee_code = 'NV-003'
  AND a.work_date = '2026-08-28';
 
UPDATE attendance a
SET status = 'Vắng',
    check_in = NULL,
    check_out = NULL,
    note = 'Không báo trước'
FROM employees e
WHERE e.id = a.employee_id
  AND e.employee_code = 'NV-007'
  AND a.work_date = '2026-08-28';
 
UPDATE attendance a
SET status = 'Nghỉ phép',
    check_in = NULL,
    check_out = NULL,
    note = 'Nghỉ phép năm'
FROM employees e
WHERE e.id = a.employee_id
  AND e.employee_code = 'NV-005'
  AND a.work_date = '2026-08-29';
 
UPDATE attendance a
SET overtime_minutes = 90,
    check_out = a.work_date + TIME '18:30',
    note = 'Tăng ca'
FROM employees e
WHERE e.id = a.employee_id
  AND e.employee_code = 'NV-002'
  AND a.work_date = '2026-08-27';
 
 
-- ============================================================
-- 15. KIỂM TRA DỮ LIỆU
-- ============================================================
 
-- Kiểm tra PO
SELECT
    po.order_code,
    p.product_code,
    p.product_name,
    w.workshop_name,
    po.planned_quantity,
    po.actual_start,
    po.actual_end,
    po.status
FROM production_orders po
JOIN products p
    ON p.id = po.product_id
JOIN workshops w
    ON w.id = po.workshop_id
WHERE po.order_code = 'PO-LINE01-001';
 
 
-- Kiểm tra dây chuyền
SELECT
    pp.process_order,
    pp.process_code,
    pp.process_name,
    m.machine_code,
    m.machine_name,
    pr.quantity_produced,
    pr.quantity_defective,
    pr.production_minutes
FROM production_orders po
JOIN production_records pr
    ON pr.production_order_id = po.id
JOIN machines m
    ON m.id = pr.machine_id
JOIN production_processes pp
    ON pp.id = m.process_id
WHERE po.order_code = 'PO-LINE01-001'
ORDER BY pp.process_order;
 
 
-- ============================================================
-- 16. KIỂM TRA % HOÀN THÀNH
-- ============================================================
--
-- Kết quả mong đợi:
--
-- planned_quantity = 1000
-- final_quantity   = 940
-- completion       = 94.00%
--
-- ============================================================
 
WITH process_output AS (
 
    SELECT
        pp.process_order,
        SUM(pr.quantity_produced) AS quantity_produced
 
    FROM production_orders po
 
    JOIN production_records pr
        ON pr.production_order_id = po.id
 
    JOIN machines m
        ON m.id = pr.machine_id
 
    JOIN production_processes pp
        ON pp.id = m.process_id
 
    WHERE po.order_code = 'PO-LINE01-001'
 
    GROUP BY pp.process_order
),
 
final_process AS (
 
    SELECT
        quantity_produced
    FROM process_output
    ORDER BY process_order DESC
    LIMIT 1
 
)
 
SELECT
    po.order_code,
    po.planned_quantity,
    fp.quantity_produced AS final_quantity,
 
    ROUND(
        100.0
        * fp.quantity_produced
        / NULLIF(po.planned_quantity, 0),
        2
    ) AS completion_percent
 
FROM production_orders po
 
CROSS JOIN final_process fp
 
WHERE po.order_code = 'PO-LINE01-001';
 
-- Kiểm tra downtime của PO (kỳ vọng: 190 phút)
SELECT
    po.order_code,
    SUM(ml.downtime_minutes) AS total_downtime_minutes
FROM machine_logs ml
JOIN production_orders po
    ON po.id = ml.production_order_id
WHERE po.order_code = 'PO-LINE01-001'
GROUP BY po.order_code;
 
 
-- Kiểm tra số dòng (kỳ vọng: product_processes 25, employees 10,
-- attendance 27, machine_logs 6)
SELECT 'product_processes' AS table_name, COUNT(*) FROM product_processes
UNION ALL SELECT 'employees',    COUNT(*) FROM employees
UNION ALL SELECT 'attendance',   COUNT(*) FROM attendance
UNION ALL SELECT 'machine_logs', COUNT(*) FROM machine_logs;
 
 
-- ============================================================
-- END SEED
-- ============================================================