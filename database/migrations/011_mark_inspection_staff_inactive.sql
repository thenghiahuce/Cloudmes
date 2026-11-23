-- Chỉ áp dụng cho nhân sự có chức vụ Nhân viên kiểm tra.
-- Không xóa bản ghi hoặc động chạm các tài khoản Admin/Tổ trưởng.
-- Chạy SQL này trên đúng database đang dùng trong .env; sao lưu trước khi chạy.
BEGIN;
UPDATE employees
SET position = 'Đã nghỉ', employment_status = 'Đã nghỉ'
WHERE LOWER(TRIM(COALESCE(position, ''))) = LOWER('Nhân viên kiểm tra');
COMMIT;
