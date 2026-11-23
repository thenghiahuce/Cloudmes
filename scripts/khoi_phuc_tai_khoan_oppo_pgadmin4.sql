-- KHÔI PHỤC tài khoản khách hàng Oppo đã bị vô hiệu hóa.
-- Chạy trong pgAdmin 4 -> database testmes -> Query Tool.
-- KHÔNG tạo tài khoản mới, KHÔNG xóa hoặc thay đổi công đơn.
-- Sao lưu PostgreSQL trước khi chạy. Đọc kết quả kiểm tra trước.

-- BƯỚC 1: xem tài khoản Oppo và công đơn tương ứng (không thay đổi dữ liệu).
SELECT u.id AS account_id, u.username, u.full_name, u.role, u.is_active,
       u.customer_company_id, c.company_name,
       (SELECT COUNT(*) FROM customer_orders o
         WHERE o.created_by = u.id OR o.company_id = c.id) AS order_count
FROM app_users u
JOIN customer_companies c ON c.id = u.customer_company_id
WHERE u.role = 'customer' AND lower(btrim(c.company_name)) = 'oppo'
ORDER BY u.id;

-- BƯỚC 2: Chỉ kích hoạt lại khi tìm đúng DUY NHẤT 1 tài khoản Oppo đã xóa
-- có công đơn liên kết. Nếu không đúng, dừng bằng lỗi, KHÔNG sửa dữ liệu.
BEGIN;
DO $restore$
DECLARE
  account_id bigint;
  candidate_count integer;
BEGIN
  SELECT count(*), min(u.id)
    INTO candidate_count, account_id
  FROM app_users u
  JOIN customer_companies c ON c.id = u.customer_company_id
  WHERE u.role = 'customer' AND u.is_active IS FALSE
    AND lower(btrim(c.company_name)) = 'oppo'
    AND EXISTS (
      SELECT 1 FROM customer_orders o
      WHERE o.created_by = u.id OR o.company_id = c.id
    );

  IF candidate_count <> 1 THEN
    RAISE EXCEPTION 'Không tự khôi phục: tìm thấy % tài khoản Oppo đã xóa có công đơn. Xem bảng ở bước 1 và chọn đúng ID.', candidate_count;
  END IF;

  UPDATE app_users SET is_active = TRUE
  WHERE id = account_id AND role = 'customer' AND is_active IS FALSE;
  RAISE NOTICE 'Đã khôi phục tài khoản Oppo có ID = %. Công đơn giữ nguyên.', account_id;
END
$restore$;
COMMIT;

-- BƯỚC 3: xác minh Oppo xuất hiện lại, công đơn giữ nguyên.
SELECT u.id, u.username, u.is_active, c.company_name,
       (SELECT COUNT(*) FROM customer_orders o
          WHERE o.company_id = c.id OR o.created_by = u.id) AS order_count
FROM app_users u JOIN customer_companies c ON c.id=u.customer_company_id
WHERE u.role='customer' AND lower(btrim(c.company_name)) = 'oppo';
