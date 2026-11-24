-- ============================================================
-- FACTORY AI - DATABASE SCHEMA
-- PostgreSQL
--
-- 12 bảng nghiệp vụ + 1 bảng tài khoản (app_users) = 13 bảng.
-- Đã khớp với CSDL đang chạy:
--   * thêm bảng product_processes
--   * machine_logs có thêm cột production_order_id
--   * thêm bảng app_users và các INDEX còn thiếu
-- CẢNH BÁO: file này DROP các bảng nghiệp vụ. Hãy sao lưu trước.
-- ============================================================
 
-- ============================================================
-- XÓA BẢNG CŨ
-- ============================================================
 
DROP TABLE IF EXISTS quality_inspections CASCADE;
DROP TABLE IF EXISTS production_records CASCADE;
DROP TABLE IF EXISTS production_orders CASCADE;
DROP TABLE IF EXISTS product_processes CASCADE;
DROP TABLE IF EXISTS attendance CASCADE;
DROP TABLE IF EXISTS machine_logs CASCADE;
DROP TABLE IF EXISTS machines CASCADE;
DROP TABLE IF EXISTS production_processes CASCADE;
DROP TABLE IF EXISTS employees CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS workshops CASCADE;
DROP TABLE IF EXISTS factories CASCADE;
 
 
-- ============================================================
-- 1. FACTORIES - NHÀ MÁY
-- ============================================================
 
CREATE TABLE factories (
    id SERIAL PRIMARY KEY,
 
    factory_code VARCHAR(20)
        UNIQUE
        NOT NULL,
 
    factory_name VARCHAR(255)
        NOT NULL,
 
    location VARCHAR(255),
 
    created_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
);
 
 
-- ============================================================
-- 2. WORKSHOPS - XƯỞNG
-- ============================================================
 
CREATE TABLE workshops (
    id SERIAL PRIMARY KEY,
 
    factory_id INTEGER
        NOT NULL,
 
    workshop_code VARCHAR(20)
        UNIQUE
        NOT NULL,
 
    workshop_name VARCHAR(255)
        NOT NULL,
 
    workshop_type VARCHAR(100),
 
    created_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,
 
    CONSTRAINT fk_workshop_factory
        FOREIGN KEY (factory_id)
        REFERENCES factories(id)
);
 
 
-- ============================================================
-- 3. PRODUCTS - SẢN PHẨM
-- ============================================================
 
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
 
    product_code VARCHAR(50)
        UNIQUE
        NOT NULL,
 
    product_name VARCHAR(255)
        NOT NULL,
 
    product_type VARCHAR(100)
        NOT NULL,
 
    unit VARCHAR(30)
        DEFAULT 'piece',
 
    standard_cycle_time_minutes NUMERIC(10,2),
 
    created_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
);
 
 
-- ============================================================
-- 4. EMPLOYEES - NHÂN VIÊN
-- ============================================================
 
CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
 
    employee_code VARCHAR(50)
        UNIQUE
        NOT NULL,
 
    employee_name VARCHAR(255)
        NOT NULL,
 
    workshop_id INTEGER
        NOT NULL,
 
    position VARCHAR(100),
 
    gender VARCHAR(20),
 
    hire_date DATE,
 
    employment_status VARCHAR(50)
        DEFAULT 'Active',
 
    created_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,
 
    CONSTRAINT fk_employee_workshop
        FOREIGN KEY (workshop_id)
        REFERENCES workshops(id)
);
 
 
-- ============================================================
-- 5. PRODUCTION PROCESSES - CÔNG ĐOẠN SẢN XUẤT
-- ============================================================
--
-- ĐÂY LÀ PHẦN QUAN TRỌNG ĐƯỢC BỔ SUNG.
--
-- process_order xác định thứ tự dây chuyền.
--
-- Ví dụ:
--
-- 1 = CUT
-- 2 = CNC
-- 3 = GRIND
-- 4 = ASSY
-- 5 = QC
-- 6 = PACK
--
-- ============================================================
 
CREATE TABLE production_processes (
    id SERIAL PRIMARY KEY,
 
    process_code VARCHAR(50)
        UNIQUE
        NOT NULL,
 
    process_name VARCHAR(255)
        NOT NULL,
 
    process_order INTEGER
        UNIQUE
        NOT NULL,
 
    description TEXT
);
 
 
-- ============================================================
-- 5B. PRODUCT_PROCESSES - CÔNG ĐOẠN CỦA TỪNG SẢN PHẨM
-- ============================================================
--
-- Bảng liên kết giữa products và production_processes.
-- process_order ở đây là thứ tự công đoạn RIÊNG của sản phẩm.
--
-- ============================================================
 
CREATE TABLE product_processes (
    id SERIAL PRIMARY KEY,
 
    product_id INTEGER
        NOT NULL,
 
    process_id INTEGER
        NOT NULL,
 
    process_order INTEGER
        NOT NULL,
 
    CONSTRAINT fk_pp_product
        FOREIGN KEY (product_id)
        REFERENCES products(id),
 
    CONSTRAINT fk_pp_process
        FOREIGN KEY (process_id)
        REFERENCES production_processes(id),
 
    CONSTRAINT unique_product_process
        UNIQUE (product_id, process_id),
 
    CONSTRAINT unique_product_process_order
        UNIQUE (product_id, process_order),
 
    CONSTRAINT product_process_order_check
        CHECK (process_order > 0)
);
 
 
-- ============================================================
-- 6. MACHINES - MÁY MÓC
-- ============================================================
 
CREATE TABLE machines (
    id SERIAL PRIMARY KEY,
 
    machine_code VARCHAR(50)
        UNIQUE
        NOT NULL,
 
    machine_name VARCHAR(255)
        NOT NULL,
 
    workshop_id INTEGER
        NOT NULL,
 
    -- QUAN TRỌNG:
    -- Xác định máy thuộc công đoạn nào.
    process_id INTEGER,
 
    machine_type VARCHAR(100),
 
    manufacturer VARCHAR(100),
 
    status VARCHAR(50)
        DEFAULT 'Running',
 
    installation_date DATE,
 
    CONSTRAINT fk_machine_workshop
        FOREIGN KEY (workshop_id)
        REFERENCES workshops(id),
 
    CONSTRAINT fk_machine_process
        FOREIGN KEY (process_id)
        REFERENCES production_processes(id)
);
 
 
-- ============================================================
-- 7. ATTENDANCE - CHẤM CÔNG
-- ============================================================
 
CREATE TABLE attendance (
    id SERIAL PRIMARY KEY,
 
    employee_id INTEGER
        NOT NULL,
 
    workshop_id INTEGER
        NOT NULL,
 
    work_date DATE
        NOT NULL,
 
    shift VARCHAR(50)
        NOT NULL,
 
    check_in TIMESTAMP,
 
    check_out TIMESTAMP,
 
    status VARCHAR(50)
        NOT NULL,
 
    overtime_minutes INTEGER
        DEFAULT 0,
 
    note TEXT,
 
    CONSTRAINT fk_attendance_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(id),
 
    CONSTRAINT fk_attendance_workshop
        FOREIGN KEY (workshop_id)
        REFERENCES workshops(id),
 
    CONSTRAINT unique_employee_workday_shift
        UNIQUE (
            employee_id,
            work_date,
            shift
        )
);
 
 
-- ============================================================
-- 8. PRODUCTION ORDERS - LỆNH SẢN XUẤT
-- ============================================================
 
CREATE TABLE production_orders (
    id SERIAL PRIMARY KEY,
 
    order_code VARCHAR(50)
        UNIQUE
        NOT NULL,
 
    workshop_id INTEGER
        NOT NULL,
 
    product_id INTEGER
        NOT NULL,
 
    planned_quantity INTEGER
        NOT NULL,
 
    planned_start TIMESTAMP
        NOT NULL,
 
    planned_end TIMESTAMP
        NOT NULL,
 
    actual_start TIMESTAMP,
 
    actual_end TIMESTAMP,
 
    status VARCHAR(50)
        DEFAULT 'Planned',
 
    created_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,
 
    CONSTRAINT fk_order_workshop
        FOREIGN KEY (workshop_id)
        REFERENCES workshops(id),
 
    CONSTRAINT fk_order_product
        FOREIGN KEY (product_id)
        REFERENCES products(id),
 
    CONSTRAINT planned_quantity_check
        CHECK (planned_quantity >= 0)
);
 
 
-- ============================================================
-- 9. PRODUCTION RECORDS - KẾT QUẢ SẢN XUẤT
-- ============================================================
 
CREATE TABLE production_records (
    id SERIAL PRIMARY KEY,
 
    production_order_id INTEGER
        NOT NULL,
 
    production_date DATE
        NOT NULL,
 
    shift VARCHAR(50)
        NOT NULL,
 
    quantity_produced INTEGER
        NOT NULL
        DEFAULT 0,
 
    quantity_defective INTEGER
        NOT NULL
        DEFAULT 0,
 
    production_minutes INTEGER
        NOT NULL
        DEFAULT 0,
 
    machine_id INTEGER,
 
    recorded_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,
 
    CONSTRAINT fk_production_order
        FOREIGN KEY (production_order_id)
        REFERENCES production_orders(id),
 
    CONSTRAINT fk_production_machine
        FOREIGN KEY (machine_id)
        REFERENCES machines(id),
 
    CONSTRAINT production_quantity_check
        CHECK (quantity_produced >= 0),
 
    CONSTRAINT defective_quantity_check
        CHECK (quantity_defective >= 0),
 
    CONSTRAINT defective_not_greater_than_produced
        CHECK (
            quantity_defective <= quantity_produced
        ),
 
    CONSTRAINT production_minutes_check
        CHECK (production_minutes >= 0)
);
 
 
-- ============================================================
-- 10. MACHINE LOGS - NHẬT KÝ MÁY
-- ============================================================
--
-- LƯU Ý:
--
-- production_order_id cho biết lần dừng máy xảy ra khi máy
-- đang phục vụ PO nào (có thể NULL).
--
-- Khi tính downtime của một PO phải lọc theo cột này,
-- không được cộng toàn bộ log của máy.
--
-- ============================================================
 
CREATE TABLE machine_logs (
    id SERIAL PRIMARY KEY,
 
    machine_id INTEGER
        NOT NULL,
 
    start_time TIMESTAMP
        NOT NULL,
 
    end_time TIMESTAMP,
 
    status VARCHAR(50)
        NOT NULL,
 
    downtime_minutes INTEGER
        DEFAULT 0,
 
    reason TEXT,
 
    production_order_id INTEGER,
 
    CONSTRAINT fk_machine_log_machine
        FOREIGN KEY (machine_id)
        REFERENCES machines(id),
 
    CONSTRAINT fk_machine_log_order
        FOREIGN KEY (production_order_id)
        REFERENCES production_orders(id),
 
    CONSTRAINT downtime_minutes_check
        CHECK (downtime_minutes >= 0),
 
    CONSTRAINT machine_log_time_check
        CHECK (end_time IS NULL OR end_time >= start_time)
);
 
 
-- ============================================================
-- 11. QUALITY INSPECTIONS - KIỂM TRA CHẤT LƯỢNG
-- ============================================================
 
CREATE TABLE quality_inspections (
    id SERIAL PRIMARY KEY,
 
    production_record_id INTEGER
        NOT NULL,
 
    inspection_time TIMESTAMP
        NOT NULL,
 
    total_checked INTEGER
        NOT NULL
        DEFAULT 0,
 
    passed_quantity INTEGER
        NOT NULL
        DEFAULT 0,
 
    failed_quantity INTEGER
        NOT NULL
        DEFAULT 0,
 
    defect_type VARCHAR(255),
 
    inspector_name VARCHAR(255),
 
    CONSTRAINT fk_quality_production
        FOREIGN KEY (production_record_id)
        REFERENCES production_records(id),
 
    CONSTRAINT total_checked_check
        CHECK (total_checked >= 0),
 
    CONSTRAINT passed_quantity_check
        CHECK (passed_quantity >= 0),
 
    CONSTRAINT failed_quantity_check
        CHECK (failed_quantity >= 0),
 
    CONSTRAINT quality_total_check
        CHECK (
            passed_quantity + failed_quantity
            <= total_checked
        )
);
 
 
-- ============================================================
-- 12. APP_USERS - TÀI KHOẢN ĐĂNG NHẬP
-- ============================================================
--
-- Không thuộc dữ liệu sản xuất, không bị DROP ở đầu file.
-- Giống database/auth.sql. Chatbot bị chặn truy vấn bảng này.
-- Tạo tài khoản: py scripts/manage_users.py add ...
--
-- ============================================================
 
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
 
 
-- ============================================================
-- INDEX
-- ============================================================
 
CREATE INDEX idx_workshops_factory
ON workshops(factory_id);
 
 
CREATE INDEX idx_employees_workshop
ON employees(workshop_id);
 
 
CREATE INDEX idx_machines_workshop
ON machines(workshop_id);
 
 
CREATE INDEX idx_machines_process
ON machines(process_id);
 
 
CREATE INDEX idx_attendance_date
ON attendance(work_date);
 
 
CREATE INDEX idx_attendance_workshop
ON attendance(workshop_id);
 
 
CREATE INDEX idx_production_date
ON production_records(production_date);
 
 
CREATE INDEX idx_production_order
ON production_records(production_order_id);
 
 
CREATE INDEX idx_production_machine
ON production_records(machine_id);
 
 
CREATE INDEX idx_machine_logs_machine
ON machine_logs(machine_id);
 
 
CREATE INDEX idx_machine_logs_order
ON machine_logs(production_order_id);
 
 
CREATE INDEX idx_product_processes_product
ON product_processes(product_id);
 
 
CREATE INDEX idx_product_processes_process
ON product_processes(process_id);
 
 
CREATE INDEX idx_orders_workshop
ON production_orders(workshop_id);
 
 
CREATE INDEX idx_orders_product
ON production_orders(product_id);
 
 
CREATE INDEX idx_orders_status
ON production_orders(status);
 
 
CREATE INDEX idx_quality_production
ON quality_inspections(production_record_id);
 
 
-- ============================================================
-- HOÀN TẤT SCHEMA
-- ============================================================

-- ------------------------------------------------------------
-- SAU KHI CHẠY FILE NÀY (và seed.sql), chạy tiếp:
--     py scripts/setup_permissions.py
-- để tạo phân quyền theo máy: machine_assignments, Row Level Security,
-- role ai_scoped/ai_admin và 5 tổ trưởng mẫu.
-- ------------------------------------------------------------
