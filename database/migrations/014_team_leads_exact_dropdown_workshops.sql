-- 014: Tổ trưởng theo đúng 5 XƯỞNG HIỂN THỊ TRONG DROPDOWN, KHÔNG THEO PO.
-- Chạy MỘT LẦN trên database đang sử dụng, sau khi sao lưu.
-- Không xóa đơn/PO và không đổi mã công đơn. Có thể chạy lại (idempotent).
BEGIN;
DO $do$
DECLARE
    wanted_count integer;
    mapped_count integer;
BEGIN
    CREATE TEMP TABLE _mes_lead_workshop_map (
        employee_code text PRIMARY KEY, workshop_name text NOT NULL
    ) ON COMMIT DROP;
    INSERT INTO _mes_lead_workshop_map VALUES
      ('NV-011','Xưởng Lắp ráp - Bắc Ninh'),
      ('NV-012','Xưởng SMT - Bắc Ninh'),
      ('NV-013','Xưởng Chip - Bắc Ninh'),
      ('NV-014','Xưởng Sensor - Bắc Ninh'),
      ('NV-015','Xưởng PCB - Bắc Ninh');

    -- Kiểm tra tên xưởng không trùng và tất cả nhân sự/tài khoản hợp lệ.
    SELECT count(*) INTO wanted_count FROM _mes_lead_workshop_map;
    SELECT count(*) INTO mapped_count
    FROM _mes_lead_workshop_map map
    JOIN workshops w ON btrim(w.workshop_name)=map.workshop_name
    JOIN employees e ON e.employee_code=map.employee_code
    WHERE EXISTS(SELECT 1 FROM app_users u WHERE u.employee_id=e.id AND u.role='team_lead' AND u.is_active);
    IF wanted_count <> 5 OR mapped_count <> 5 THEN
       RAISE EXCEPTION 'Không đủ 5 cặp Tổ trưởng / xưởng / tài khoản role team_lead. Kiểm tra workshops và app_users trước khi chạy.';
    END IF;
    IF EXISTS (SELECT 1 FROM _mes_lead_workshop_map map JOIN workshops w
               ON btrim(w.workshop_name)=map.workshop_name
               GROUP BY map.employee_code HAVING count(*)<>1) THEN
       RAISE EXCEPTION 'Tên xưởng bị trùng';
    END IF;

    UPDATE employees e SET workshop_id=w.id, position='Tổ trưởng'
    FROM _mes_lead_workshop_map map JOIN workshops w ON btrim(w.workshop_name)=map.workshop_name
    WHERE e.employee_code=map.employee_code;

    -- Xóa quyền máy cũ của CHỈ 5 Tổ trưởng, sau đó gán toàn bộ máy trong đúng xưởng.
    DELETE FROM machine_assignments ma USING employees e
    WHERE ma.employee_id=e.id AND e.employee_code IN (SELECT employee_code FROM _mes_lead_workshop_map);
    INSERT INTO machine_assignments(machine_id,employee_id,assignment_role,assigned_by)
    SELECT m.id,e.id,'team_lead','workshop-role-migration-014'
    FROM employees e JOIN machines m ON m.workshop_id=e.workshop_id
    WHERE e.employee_code IN (SELECT employee_code FROM _mes_lead_workshop_map)
    ON CONFLICT (machine_id,employee_id) DO UPDATE
       SET assignment_role='team_lead',assigned_by='workshop-role-migration-014';
END $do$;
COMMIT;

-- Kiểm tra kết quả:
SELECT e.employee_code,e.employee_name,w.workshop_name,u.username,u.role,
       (SELECT count(*) FROM machine_assignments ma WHERE ma.employee_id=e.id) AS so_may
FROM employees e JOIN workshops w ON w.id=e.workshop_id
LEFT JOIN app_users u ON u.employee_id=e.id AND u.role='team_lead'
WHERE e.employee_code IN ('NV-011','NV-012','NV-013','NV-014','NV-015')
ORDER BY e.employee_code;
