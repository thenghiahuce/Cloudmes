"""
Áp dụng phân quyền theo máy (Giai đoạn 1) vào database trong .env.

  py scripts/setup_permissions.py            (migration + 5 tổ trưởng mẫu + gán máy)
  py scripts/setup_permissions.py --no-seed  (chỉ migration, không thêm dữ liệu mẫu)

Chạy theo thứ tự auth.sql -> migrations/001_phan_quyen_may.sql -> seed_team_leads.sql
trong MỘT transaction: lỗi ở bước nào thì không thay đổi gì. Chạy lại nhiều lần vẫn an toàn.

Sau đó tạo tài khoản đăng nhập cho tổ trưởng mới:
  py scripts/manage_users.py sync-staff <mật-khẩu>
"""
import os
import sys

import psycopg2
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

STEPS = [
    ("database/auth.sql", False),
    ("database/migrations/001_phan_quyen_may.sql", False),
    ("database/seeds/seed_team_leads.sql", True),   # True = dữ liệu mẫu, bỏ qua khi --no-seed
]


def main():
    skip_seed = "--no-seed" in sys.argv[1:]
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DATABASE"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )
    try:
        with conn, conn.cursor() as cur:
            for rel_path, is_seed in STEPS:
                if is_seed and skip_seed:
                    print(f"- bỏ qua {rel_path}")
                    continue
                with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
                    cur.execute(f.read())
                print(f"+ đã chạy {rel_path}")

            cur.execute("SELECT count(*) FROM machine_assignments")
            print(f"machine_assignments: {cur.fetchone()[0]} dòng")
            cur.execute(
                "SELECT e.employee_code, e.employee_name, w.workshop_code, count(*) "
                "FROM machine_assignments ma "
                "JOIN employees e ON e.id = ma.employee_id "
                "JOIN workshops w ON w.id = e.workshop_id "
                "WHERE ma.assignment_role = 'team_lead' "
                "GROUP BY 1, 2, 3 ORDER BY 1")
            for code, name, ws, n in cur.fetchall():
                print(f"  tổ trưởng {code:8} {name:20} {ws}  {n} máy")
        print("Hoàn tất. Tiếp theo: py scripts/manage_users.py sync-staff <mật-khẩu>")
    except Exception as exc:
        sys.exit(f"Lỗi, đã hoàn tác toàn bộ: {type(exc).__name__}: {exc}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
