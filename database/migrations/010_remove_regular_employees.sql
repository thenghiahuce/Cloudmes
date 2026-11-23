-- Run ONCE after backing up PostgreSQL. Delete ONLY exact position "Nhân viên".
-- Technicians, team leads and Admins are excluded.
BEGIN;
CREATE TABLE IF NOT EXISTS deleted_regular_employees_backup_20261031 AS
 SELECT e.*, now() AS backed_up_at FROM employees e WHERE false;
INSERT INTO deleted_regular_employees_backup_20261031
 SELECT e.*, now() FROM employees e WHERE lower(btrim(coalesce(e.position,'')))=lower('Nhân viên')
 AND NOT EXISTS (SELECT 1 FROM deleted_regular_employees_backup_20261031 b WHERE b.id=e.id);
-- Preserve linked task/review history, disable only affected application accounts.
UPDATE app_users u SET is_active=FALSE, employee_id=NULL
 WHERE employee_id IN (SELECT id FROM employees WHERE lower(btrim(coalesce(position,'')))=lower('Nhân viên'));
-- Backup and remove attendance rows referencing employees due for deletion.
CREATE TABLE IF NOT EXISTS deleted_regular_attendance_backup_20261031 AS
 SELECT a.*, now() AS backed_up_at FROM attendance a WHERE false;
INSERT INTO deleted_regular_attendance_backup_20261031
 SELECT a.*, now() FROM attendance a JOIN employees e ON e.id=a.employee_id
 WHERE lower(btrim(coalesce(e.position,'')))=lower('Nhân viên')
 AND NOT EXISTS (SELECT 1 FROM deleted_regular_attendance_backup_20261031 b WHERE b.id=a.id);
DELETE FROM attendance WHERE employee_id IN
 (SELECT id FROM employees WHERE lower(btrim(coalesce(position,'')))=lower('Nhân viên'));
-- machine_assignments has ON DELETE CASCADE; other unknown references intentionally trigger rollback.
DELETE FROM employees WHERE lower(btrim(coalesce(position,'')))=lower('Nhân viên');
COMMIT;
SELECT position,count(*) FROM employees GROUP BY position ORDER BY position;
