"""Kết nối PostgreSQL dùng chung cho các API dữ liệu."""
import os
from typing import Any


def get_connection():
    # psycopg2 is the conventional driver used by the Postgres Vanna stack.
    import psycopg2
    import psycopg2.extras
 
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DATABASE"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )
 
 
def fetch_all(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    import psycopg2.extras
 
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
