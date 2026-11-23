"""
Tạo / đổi mật khẩu tài khoản đăng nhập.
 
Ví dụ:
  py scripts/manage_users.py add admin "Quản trị viên" admin           (hỏi mật khẩu)
  py scripts/manage_users.py add admin "Quản trị viên" admin 123456    (đặt luôn mật khẩu)
  py scripts/manage_users.py sync-staff 123456
        -> tự tạo tài khoản cho mọi nhân viên ĐANG LÀM có chức vụ Tổ trưởng / Kỹ thuật viên / Kỹ sư:
           tên đăng nhập = mã nhân viên, mật khẩu = 123456 (người đã có tài khoản sẽ được bỏ qua)
  py scripts/manage_users.py passwd NV-001
  py scripts/manage_users.py list
  py scripts/manage_users.py disable NV-001

Phân quyền theo máy (tổ trưởng / kỹ thuật viên chỉ thấy máy được gán; admin thấy tất cả):
  py scripts/manage_users.py scope NV-011                       (xem các máy của NV-011)
  py scripts/manage_users.py assign NV-011 MC001                (gán 1 máy, mặc định team_lead)
  py scripts/manage_users.py assign NV-002 MC001 member         (kỹ sư/kỹ thuật viên: member)
  py scripts/manage_users.py assign-workshop NV-011 LINE01      (gán mọi máy của 1 xưởng)
  py scripts/manage_users.py unassign NV-011 MC001
"""
import getpass
import os
import sys
import unicodedata
 
import psycopg2
from dotenv import load_dotenv
 
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # để import được auth.py ở thư mục gốc
 
from backend.auth import ROLE_LABELS, hash_password  # noqa: E402
 
load_dotenv(os.path.join(ROOT, ".env"))
 
CREATE_SQL = open(os.path.join(ROOT, "database", "auth.sql"), encoding="utf-8").read()
 
ACTIVE_STATUSES = ("đang làm", "đang làm việc", "active")
 
 
def connect():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DATABASE"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )
 
 
def norm(text):
    return unicodedata.normalize("NFC", (text or "")).strip().lower()
 
 
def role_for_position(position):
    """Tổ trưởng -> team_lead; Kỹ thuật viên / Kỹ sư (viết 'kỹ' hoặc 'kĩ') -> technician."""
    p = norm(position)
    if "tổ trưởng" in p:
        return "team_lead"
    if any(k in p for k in ("kỹ thuật", "kĩ thuật", "kỹ sư", "kĩ sư")):
        return "technician"
    return None
 
 
def check_password(pw):
    if len(pw) < 6:
        sys.exit("Mật khẩu quá ngắn (tối thiểu 6 ký tự).")
    if len(pw) < 8 or pw.isdigit():
        print("CẢNH BÁO: mật khẩu yếu, dễ bị đoán. Nên đổi sang mật khẩu mạnh hơn.")
    return pw
 
 
def ask_password():
    pw = getpass.getpass("Mật khẩu: ")
    if pw != getpass.getpass("Nhập lại mật khẩu: "):
        sys.exit("Hai lần nhập không khớp.")
    return check_password(pw)
 
 
def main():
    argv = sys.argv
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd = argv[1]
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(CREATE_SQL)
 
            if cmd == "add" and len(argv) in (5, 6):
                username, full_name, role = argv[2], argv[3], argv[4]
                if role not in ROLE_LABELS:
                    sys.exit("Vai trò phải là: " + ", ".join(ROLE_LABELS))
                password = check_password(argv[5]) if len(argv) == 6 else ask_password()
                cur.execute(
                    "INSERT INTO app_users (username, full_name, password_hash, role) "
                    "VALUES (%s, %s, %s, %s)",
                    (username, full_name, hash_password(password), role))
                print(f"Đã tạo tài khoản {username} ({ROLE_LABELS[role]}).")
 
            elif cmd == "sync-staff" and len(argv) == 3:
                password = check_password(argv[2])
                pw_hash = hash_password(password)  # cùng mật khẩu, băm một lần cho nhanh
                cur.execute("SELECT id, employee_code, employee_name, position, employment_status "
                            "FROM employees ORDER BY employee_code")
                created, skipped_exist, skipped_inactive, ignored = [], 0, 0, 0
                for emp_id, code, name, position, status in cur.fetchall():
                    role = role_for_position(position)
                    if role is None:
                        ignored += 1
                        continue
                    if norm(status) not in ACTIVE_STATUSES:
                        skipped_inactive += 1
                        continue
                    cur.execute(
                        "INSERT INTO app_users (username, full_name, password_hash, role, employee_id) "
                        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (username) DO NOTHING",
                        (code, name, pw_hash, role, emp_id))
                    if cur.rowcount:
                        created.append((code, name, ROLE_LABELS[role]))
                    else:
                        skipped_exist += 1
                # Tài khoản đã có từ trước mà chưa liên kết nhân viên thì liên kết luôn.
                cur.execute("UPDATE app_users u SET employee_id = e.id FROM employees e "
                            "WHERE e.employee_code = u.username AND u.employee_id IS NULL")
                for code, name, label in created:
                    print(f"  + {code:10} {name:28} {label}")
                print(f"Đã tạo {len(created)} tài khoản. Đã có sẵn: {skipped_exist}. "
                      f"Bỏ qua (đã nghỉ): {skipped_inactive}. "
                      f"Không phải tổ trưởng/kỹ thuật viên/kỹ sư: {ignored}.")
 
            elif cmd == "passwd" and len(argv) == 3:
                cur.execute("UPDATE app_users SET password_hash=%s, is_active=TRUE WHERE username=%s",
                            (hash_password(ask_password()), argv[2]))
                print("Đã đổi mật khẩu." if cur.rowcount else "Không tìm thấy tài khoản.")
 
            elif cmd == "disable" and len(argv) == 3:
                cur.execute("UPDATE app_users SET is_active=FALSE WHERE username=%s", (argv[2],))
                print("Đã khóa tài khoản." if cur.rowcount else "Không tìm thấy tài khoản.")
 
            elif cmd == "assign" and len(argv) in (4, 5):
                emp_code, machine_code = argv[2], argv[3]
                a_role = argv[4] if len(argv) == 5 else "team_lead"
                if a_role not in ("team_lead", "member"):
                    sys.exit("Vai trò gán máy phải là: team_lead hoặc member")
                cur.execute("SELECT id FROM employees WHERE employee_code=%s", (emp_code,))
                emp = cur.fetchone()
                cur.execute("SELECT id FROM machines WHERE machine_code=%s", (machine_code,))
                mach = cur.fetchone()
                if not emp or not mach:
                    sys.exit("Không tìm thấy nhân viên hoặc máy.")
                cur.execute(
                    "INSERT INTO machine_assignments (machine_id, employee_id, assignment_role, assigned_by) "
                    "VALUES (%s, %s, %s, 'cli') "
                    "ON CONFLICT (machine_id, employee_id) DO UPDATE SET assignment_role = EXCLUDED.assignment_role",
                    (mach[0], emp[0], a_role))
                print(f"Đã gán {machine_code} cho {emp_code} ({a_role}).")

            elif cmd == "assign-workshop" and len(argv) in (4, 5):
                emp_code, ws_code = argv[2], argv[3]
                a_role = argv[4] if len(argv) == 5 else "team_lead"
                if a_role not in ("team_lead", "member"):
                    sys.exit("Vai trò gán máy phải là: team_lead hoặc member")
                cur.execute("SELECT id FROM employees WHERE employee_code=%s", (emp_code,))
                emp = cur.fetchone()
                if not emp:
                    sys.exit("Không tìm thấy nhân viên.")
                cur.execute(
                    "INSERT INTO machine_assignments (machine_id, employee_id, assignment_role, assigned_by) "
                    "SELECT m.id, %s, %s, 'cli' FROM machines m "
                    "JOIN workshops w ON w.id = m.workshop_id WHERE w.workshop_code = %s "
                    "ON CONFLICT (machine_id, employee_id) DO UPDATE SET assignment_role = EXCLUDED.assignment_role",
                    (emp[0], a_role, ws_code))
                print(f"Đã gán {cur.rowcount} máy của xưởng {ws_code} cho {emp_code} ({a_role}).")

            elif cmd == "unassign" and len(argv) == 4:
                cur.execute(
                    "DELETE FROM machine_assignments ma USING employees e, machines m "
                    "WHERE ma.employee_id = e.id AND ma.machine_id = m.id "
                    "AND e.employee_code = %s AND m.machine_code = %s", (argv[2], argv[3]))
                print("Đã bỏ gán." if cur.rowcount else "Không có phân công nào khớp.")

            elif cmd == "scope" and len(argv) == 3:
                cur.execute(
                    "SELECT m.machine_code, m.machine_name, ma.assignment_role "
                    "FROM machine_assignments ma JOIN employees e ON e.id = ma.employee_id "
                    "JOIN machines m ON m.id = ma.machine_id WHERE e.employee_code = %s "
                    "ORDER BY m.machine_code", (argv[2],))
                rows = cur.fetchall()
                for mc, mn, ar in rows:
                    print(f"  {mc:8} {mn:30} {ar}")
                print(f"{argv[2]}: {len(rows)} máy.")

            elif cmd == "list":
                cur.execute("SELECT username, full_name, role, is_active FROM app_users ORDER BY role, username")
                for u, n, r, a in cur.fetchall():
                    print(f"{u:14} {n or '':28} {ROLE_LABELS.get(r, r):15} {'hoạt động' if a else 'đã khóa'}")
            else:
                sys.exit(__doc__)
    finally:
        conn.close()
 
 
if __name__ == "__main__":
    main()
 