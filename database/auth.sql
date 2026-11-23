-- Bảng tài khoản đăng nhập. An toàn khi chạy nhiều lần, KHÔNG xóa dữ liệu hiện có.
CREATE TABLE IF NOT EXISTS app_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL
        CHECK (role IN ('admin', 'team_lead', 'technician', 'customer')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Liên kết tài khoản với nhân viên (dùng để biết tổ trưởng/kỹ thuật viên quản lý máy nào).
ALTER TABLE app_users
    ADD COLUMN IF NOT EXISTS employee_id INTEGER
        REFERENCES employees(id) ON DELETE SET NULL;
