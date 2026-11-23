-- V12: Xoa lich su cong viec CU trong "Danh sach cong viec & lich su".
-- Anh chup cho thay cac task ngay 27/10/2026, day la bang tasks (KHONG phai action_plan_items).
-- Chay SAU khi da sao luu database va sau migration 019.
-- CHI xoa tasks tao truoc 01/11/2026 00:00 gio Viet Nam; task moi tu ngay do duoc giu nguyen.
-- Backup du lieu vao cac bang legacy_work_*_backup_020 truoc khi xoa; co the kiem tra/hoan tac thu cong.
BEGIN;

CREATE TABLE IF NOT EXISTS legacy_work_tasks_backup_020 (LIKE tasks INCLUDING ALL);
CREATE TABLE IF NOT EXISTS legacy_work_reports_backup_020 (LIKE task_reports INCLUDING ALL);
CREATE TABLE IF NOT EXISTS legacy_work_reviews_backup_020 (LIKE task_reviews INCLUDING ALL);

CREATE TEMP TABLE legacy_work_task_ids_020 ON COMMIT DROP AS
 SELECT id FROM tasks WHERE created_at < TIMESTAMPTZ '2026-11-01 00:00:00+07';

INSERT INTO legacy_work_tasks_backup_020
 SELECT t.* FROM tasks t JOIN legacy_work_task_ids_020 i ON i.id=t.id
 WHERE NOT EXISTS (SELECT 1 FROM legacy_work_tasks_backup_020 b WHERE b.id=t.id);
INSERT INTO legacy_work_reports_backup_020
 SELECT r.* FROM task_reports r JOIN legacy_work_task_ids_020 i ON i.id=r.task_id
 WHERE NOT EXISTS (SELECT 1 FROM legacy_work_reports_backup_020 b WHERE b.id=r.id);
INSERT INTO legacy_work_reviews_backup_020
 SELECT rv.* FROM task_reviews rv JOIN legacy_work_task_ids_020 i ON i.id=rv.task_id
 WHERE NOT EXISTS (SELECT 1 FROM legacy_work_reviews_backup_020 b WHERE b.id=rv.id);

DELETE FROM task_reviews rv USING legacy_work_task_ids_020 i WHERE rv.task_id=i.id;
DELETE FROM task_reports r USING legacy_work_task_ids_020 i WHERE r.task_id=i.id;
DELETE FROM tasks t USING legacy_work_task_ids_020 i WHERE t.id=i.id;
COMMIT;

-- Kiem tra sau khi chay:
-- SELECT count(*) FROM tasks WHERE created_at < TIMESTAMPTZ '2026-11-01 00:00:00+07'; -- mong doi: 0
-- SELECT count(*) FROM legacy_work_tasks_backup_020;
