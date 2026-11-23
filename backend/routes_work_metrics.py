"""Thống kê kết quả công việc KTV, KHÔNG thay thế chấm công vào/ra.
Đọc tasks/task_reviews; không ghi vào attendance.
"""
from datetime import date
from fastapi import APIRouter, HTTPException, Request
import psycopg2.extras
from backend.db import get_connection
from backend.scope import scope_from_request

router = APIRouter(prefix='/api/work-metrics', tags=['work-metrics'])


def _actor(cur, scope):
    if scope.role not in ('admin', 'team_lead', 'technician') or not scope.username:
        raise HTTPException(403, 'Không có quyền')
    cur.execute('''SELECT id, employee_id FROM app_users
        WHERE lower(username)=lower(%s) AND is_active''', (scope.username,))
    user = cur.fetchone()
    if not user:
        raise HTTPException(403, 'Tài khoản không hợp lệ')
    return user


@router.get('/technicians')
def technician_summary(request: Request, from_date: date, to_date: date):
    """Tổng hợp theo kỳ. Công việc = giao trong kỳ; hoàn thành = Tổ trưởng duyệt trong kỳ.
    Số lượng là số công việc/plan riêng biệt, không phải số lần nộp lại.
    """
    if to_date < from_date or (to_date - from_date).days > 366:
        raise HTTPException(422, 'Khoảng ngày không hợp lệ (tối đa 366 ngày)')
    scope = scope_from_request(request)
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            user = _actor(cur, scope)
            cur.execute('''SELECT e.id, e.employee_code, e.employee_name,
                       w.workshop_code, w.workshop_name, au.id AS user_id
                 FROM app_users au JOIN employees e ON e.id=au.employee_id
                 JOIN workshops w ON w.id=e.workshop_id
                 WHERE au.is_active AND au.role='technician'
                   AND e.employment_status='Đang làm'
                   AND (%s='admin' OR (%s='technician' AND au.id=%s) OR
                       (%s='team_lead' AND EXISTS (
                         SELECT 1 FROM machine_assignments ma
                         WHERE ma.employee_id=e.id AND ma.machine_id=ANY(%s::integer[]))))
                 ORDER BY w.workshop_code,e.employee_code''',
                 (scope.role, scope.role, user['id'], scope.role, list(scope.machine_ids)))
            people = [dict(x) for x in cur.fetchall()]
            for person in people:
                # Work assigned DURING period, attributable only to the named technician.
                cur.execute('''SELECT COUNT(DISTINCT t.id) AS n
                    FROM tasks t WHERE t.assigned_to=%s
                    AND t.machine_id=ANY(%s::integer[])
                    AND (t.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date BETWEEN %s AND %s''',
                    (person['user_id'], list(scope.machine_ids) if not scope.all_machines else _all_machine_ids(cur), from_date, to_date))
                assigned = cur.fetchone()['n']
                cur.execute('''SELECT COUNT(DISTINCT t.id) AS n
                    FROM tasks t JOIN task_reviews rv ON rv.task_id=t.id
                    JOIN app_users reviewer ON reviewer.id=rv.reviewer_id
                    WHERE t.assigned_to=%s AND t.machine_id=ANY(%s::integer[])
                      AND rv.decision='approved' AND reviewer.role='team_lead'
                      AND (rv.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date BETWEEN %s AND %s''',
                    (person['user_id'], list(scope.machine_ids) if not scope.all_machines else _all_machine_ids(cur), from_date, to_date))
                task_done = cur.fetchone()['n']
                person.update(tasks_assigned=assigned, tasks_completed=task_done)
                person.pop('user_id', None)
            return {'from_date': from_date, 'to_date': to_date,
                    'note': 'Chỉ số kết quả công việc; không xác nhận có mặt hoặc ngày công.',
                    'technicians': people}
    finally:
        conn.close()


def _all_machine_ids(cur):
    cur.execute('SELECT id FROM machines')
    return [x['id'] for x in cur.fetchall()]
