"""Phạm vi dữ liệu theo máy (Giai đoạn 1).

  - admin                    : thấy TẤT CẢ máy
  - team_lead / technician   : chỉ thấy các máy được gán trong machine_assignments

Phạm vi luôn được đọc từ DATABASE theo tài khoản (không tin role trong cookie
hay trong prompt). Truy vấn Dashboard và AI chạy qua `scoped_cursor`, tức là
dưới role chỉ-đọc `ai_scoped` / `ai_admin` với Row Level Security (xem
database/migrations/001_phan_quyen_may.sql), nên dù SQL do AI sinh ra có viết
sai hay cố truy cập máy khác, database vẫn tự lọc.
"""
from __future__ import annotations

import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from backend.db import fetch_all, get_connection

ROLE_ADMIN = "admin"
DB_ROLE_ADMIN = "ai_admin"
DB_ROLE_SCOPED = "ai_scoped"
STATEMENT_TIMEOUT_MS = 15000


@dataclass(frozen=True)
class Scope:
    username: str | None = None
    role: str | None = None
    all_machines: bool = False
    machine_ids: tuple[int, ...] = ()

    @property
    def db_role(self) -> str:
        return DB_ROLE_ADMIN if self.all_machines else DB_ROLE_SCOPED

    @property
    def is_empty(self) -> bool:
        """Không thấy máy nào (chưa được gán, bị khóa, hoặc không tồn tại)."""
        return not self.all_machines and not self.machine_ids


NO_ACCESS = Scope()


def load_scope(username: str | None) -> Scope:
    """Đọc vai trò và danh sách máy của tài khoản từ database.

    Tài khoản không tồn tại / bị khóa -> NO_ACCESS (không thấy gì).
    """
    if not username:
        return NO_ACCESS
    rows = fetch_all(
        """
        SELECT u.role,
               CASE WHEN u.role='team_lead' THEN
                   ARRAY(SELECT m.id FROM machines m JOIN employees e ON e.workshop_id=m.workshop_id
                         WHERE e.id=u.employee_id AND e.position='Tổ trưởng' ORDER BY m.id)
               ELSE array_remove(array_agg(DISTINCT ma.machine_id), NULL) END AS machine_ids
        FROM app_users u
        LEFT JOIN machine_assignments ma ON ma.employee_id=u.employee_id
        WHERE lower(u.username)=lower(%s) AND u.is_active
        GROUP BY u.id, u.role, u.employee_id
        """, (username,),
    )
    if not rows:
        return NO_ACCESS
    role = rows[0]["role"]
    if role == ROLE_ADMIN:
        return Scope(username=username, role=role, all_machines=True)
    ids = tuple(sorted(int(i) for i in (rows[0]["machine_ids"] or [])))
    return Scope(username=username, role=role, machine_ids=ids)


def scope_from_request(request) -> Scope:
    """Phạm vi của người đang gọi API (AuthMiddleware đã gắn user vào scope ASGI)."""
    user = request.scope.get("state", {}).get("user") or {}
    return load_scope(user.get("username"))


def list_scope_machines(scope: Scope) -> list[dict[str, Any]]:
    """Máy trong phạm vi (để hiển thị). Admin: để trống vì là tất cả máy."""
    if scope.all_machines or not scope.machine_ids:
        return []
    return fetch_all(
        "SELECT machine_code, machine_name FROM machines "
        "WHERE id = ANY(%s) ORDER BY machine_code",
        (list(scope.machine_ids),),
    )


@contextmanager
def scoped_cursor(scope: Scope, timeout_ms: int = STATEMENT_TIMEOUT_MS) -> Iterator[Any]:
    """Mở một cursor chỉ-đọc đã bị giới hạn theo `scope`.

    Mọi thứ nằm trong một transaction và luôn ROLLBACK khi kết thúc, nên dòng
    phạm vi tạm (app_scope_sessions) tự biến mất và không thể ghi được gì.
    """
    import psycopg2.extras

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            token = secrets.token_hex(16)
            # Bước này chạy bằng quyền của ứng dụng, TRƯỚC khi hạ xuống role chỉ-đọc.
            cur.execute(
                "INSERT INTO app_scope_sessions (token, all_machines, machine_ids) "
                "VALUES (%s, %s, %s::integer[])",
                (token, scope.all_machines, list(scope.machine_ids)),
            )
            cur.execute("SELECT set_config('app.scope_token', %s, true)", (token,))
            cur.execute("SELECT set_config('statement_timeout', %s, true)",
                        (str(int(timeout_ms)),))
            cur.execute(f"SET LOCAL ROLE {scope.db_role}")  # tên role cố định, không từ người dùng
            yield cur
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def fetch_all_scoped(scope: Scope, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
    """Giống fetch_all nhưng bị giới hạn theo phạm vi máy của `scope`."""
    with scoped_cursor(scope) as cur:
        # params=None (không phải ()) để dấu % trong SQL (LIKE '%abc%') không bị hiểu nhầm.
        cur.execute(sql, params or None)
        return [dict(r) for r in cur.fetchall()]
