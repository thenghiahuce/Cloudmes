"""Chạy một lần: py scripts/setup_tasks.py (không seed, không thay PO)."""
import os, sys
from pathlib import Path
import psycopg2
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
conn=psycopg2.connect(host=os.getenv('POSTGRES_HOST'),port=os.getenv('POSTGRES_PORT','5432'),dbname=os.getenv('POSTGRES_DATABASE'),user=os.getenv('POSTGRES_USER'),password=os.getenv('POSTGRES_PASSWORD'))
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute((ROOT/'database/migrations/002_giao_viec_bao_cao.sql').read_text(encoding='utf-8'))
    print('Đã tạo tasks, task_reports, task_reviews. Không sửa PO và dữ liệu nhân viên.')
except Exception as e:
    print('Migration lỗi; transaction đã rollback:',e)
    sys.exit(1)
finally:
    conn.close()
