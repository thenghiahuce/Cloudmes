"""Create or associate business customers without deleting staff history.

Run after database/migrations/004_cong_don_khach_hang.sql.
Examples:
  py scripts/setup_customers.py add Samsung samsung_customer
  py scripts/setup_customers.py add Apple apple_customer
  py scripts/setup_customers.py convert-technicians Samsung
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / '.env')
from backend.db import get_connection
from backend.auth import hash_password
from getpass import getpass


def main():
    if len(sys.argv)<3 or sys.argv[1] not in ('add','convert-technicians'):
        raise SystemExit('Sử dụng: py scripts/setup_customers.py add <tên-công-ty> <username> | convert-technicians <tên-công-ty>')
    action,name=sys.argv[1:3]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO customer_companies(company_name) VALUES (%s) ON CONFLICT(company_name) DO UPDATE SET company_name=EXCLUDED.company_name RETURNING id',(name,))
            company_id=cur.fetchone()[0]
            if action=='add':
                if len(sys.argv)!=4: raise SystemExit('Cần username')
                password=getpass('Mật khẩu tài khoản khách hàng (không hiển thị): ')
                if len(password)<12: raise SystemExit('Mật khẩu cần ít nhất 12 ký tự')
                cur.execute('''INSERT INTO app_users(username,full_name,password_hash,role,customer_company_id)
                  VALUES(%s,%s,%s,'customer',%s)''',(sys.argv[3],name,hash_password(password),company_id))
                print('Đã tạo tài khoản khách hàng:',sys.argv[3])
            else:
                cur.execute("SELECT count(*) FROM app_users WHERE role='technician'")
                count=cur.fetchone()[0]
                confirmation=input(f'Chuyển {count} tài khoản KỸ THUẬT VIÊN sang khách hàng công ty {name}? Lịch sử nhân sự vẫn giữ. Nhập CHUYEN để xác nhận: ')
                if confirmation!='CHUYEN': raise SystemExit('Hủy, chưa thay đổi tài khoản')
                cur.execute("UPDATE app_users SET role='customer',customer_company_id=%s WHERE role='technician'",(company_id,))
                print('Đã chuyển',cur.rowcount,'tài khoản. Đăng nhập lại để cập nhật quyền.')
        conn.commit()
if __name__=='__main__': main()
