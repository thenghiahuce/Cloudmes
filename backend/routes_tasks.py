"""Giai đoạn 2 - phân quyền được kiểm tra server-side ở mỗi thao tác."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import psycopg2.extras
from backend.db import get_connection
from backend.scope import scope_from_request

router = APIRouter(prefix='/api/work')

def context(request):
    scope=scope_from_request(request)
    if not scope.username or not scope.role:
        raise HTTPException(403,'Không có quyền')
    return scope

def query(sql, args=(), one=False):
    conn=get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql,args)
            result=cur.fetchone() if one else cur.fetchall()
            return dict(result) if one and result else ([dict(r) for r in result] if not one else None)
    finally: conn.close()

def actor(cur,scope):
    cur.execute('SELECT id, employee_id, role FROM app_users WHERE lower(username)=lower(%s) AND is_active FOR SHARE',(scope.username,))
    user=cur.fetchone()
    if not user: raise HTTPException(403,'Tài khoản không hợp lệ')
    return user

def permitted(cur,scope,machine_id):
    if scope.all_machines: return True
    cur.execute('SELECT 1 FROM machine_assignments ma JOIN app_users u ON u.employee_id=ma.employee_id WHERE lower(u.username)=lower(%s) AND u.is_active AND ma.machine_id=%s',(scope.username,machine_id))
    return cur.fetchone() is not None

def load_task(cur,scope,task_id,user):
    cur.execute('SELECT * FROM tasks WHERE id=%s FOR UPDATE',(task_id,))
    task=cur.fetchone()
    if not task: raise HTTPException(404,'Không có công việc')
    if not permitted(cur,scope,task['machine_id']): raise HTTPException(403,'Máy ngoài phạm vi')
    if scope.role=='technician' and task['assigned_to'] != user['id']:
        raise HTTPException(403,'Không phải công việc của bạn')
    return task

@router.get('/staff')
def staff(request: Request):
    s=context(request)
    if s.role not in ('admin','team_lead'): raise HTTPException(403,'Chỉ tổ trưởng hoặc admin')
    # Không dựa vào workshop_id của cookie. Tổ trưởng lấy xưởng từ employee_id đã đăng nhập.
    sql='''SELECT e.id, e.employee_code, e.employee_name, e.position, w.workshop_code, w.workshop_name,
           CASE WHEN u.is_active THEN u.username ELSE NULL END AS username,
           (SELECT COUNT(*) FROM machine_assignments ma WHERE ma.employee_id=e.id AND ma.machine_id = ANY(%s::integer[])) AS shared_machines
           FROM employees e JOIN workshops w ON w.id=e.workshop_id
           LEFT JOIN app_users u ON u.employee_id=e.id AND u.is_active
           WHERE e.employment_status = 'Đang làm'
           AND (%s OR e.workshop_id=(SELECT e2.workshop_id FROM app_users a JOIN employees e2 ON e2.id=a.employee_id WHERE lower(a.username)=lower(%s) AND a.is_active))
           ORDER BY w.workshop_code,e.employee_code'''
    return query(sql,(list(s.machine_ids),s.all_machines,s.username))

@router.get('/staff/{employee_id}/lead-activity')
def lead_activity(employee_id:int,request:Request):
    scope=context(request)
    if scope.role!='admin': raise HTTPException(403,'Chỉ Admin được xem lịch sử tổ trưởng')
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id,employee_name,employee_code,position FROM employees WHERE id=%s",(employee_id,))
            emp=cur.fetchone()
            if not emp: raise HTTPException(404,'Không tìm thấy nhân sự')
            if 'tổ trưởng' not in (emp['position'] or '').lower(): raise HTTPException(422,'Không phải tổ trưởng')
            cur.execute("SELECT id FROM app_users WHERE employee_id=%s AND role='team_lead'",(employee_id,))
            user_ids=[r['id'] for r in cur.fetchall()]
            if not user_ids:return {'employee':dict(emp),'orders':[],'assigned_tasks':[],'reviewed_tasks':[]}
            cur.execute('''SELECT o.id,o.status,o.quantity,o.created_at,o.completed_at,o.lead_reviewed_at,o.rejection_reason,
                c.company_name,p.product_name,w.workshop_name
                FROM customer_orders o JOIN customer_companies c ON c.id=o.company_id
                JOIN products p ON p.id=o.product_id JOIN workshops w ON w.id=o.workshop_id
                WHERE o.lead_reviewer = ANY(%s::int[]) ORDER BY o.lead_reviewed_at DESC LIMIT 200''',(user_ids,))
            orders=[dict(r) for r in cur.fetchall()]
            cur.execute('''SELECT t.id,t.title,t.status,t.created_at,t.due_at,m.machine_code,
                COALESCE(receiver.employee_name,'—') AS receiver_name
                FROM tasks t JOIN machines m ON m.id=t.machine_id
                LEFT JOIN app_users a ON a.id=t.assigned_to LEFT JOIN employees receiver ON receiver.id=a.employee_id
                WHERE t.assigned_by = ANY(%s::int[]) ORDER BY t.created_at DESC LIMIT 200''',(user_ids,))
            assigned=[dict(r) for r in cur.fetchall()]
            cur.execute('''SELECT t.id,t.title,rv.decision,rv.comment,rv.created_at,m.machine_code
                FROM task_reviews rv JOIN tasks t ON t.id=rv.task_id JOIN machines m ON m.id=t.machine_id
                WHERE rv.reviewer_id = ANY(%s::int[]) ORDER BY rv.created_at DESC LIMIT 200''',(user_ids,))
            reviewed=[dict(r) for r in cur.fetchall()]
            return {'employee':dict(emp),'orders':orders,'assigned_tasks':assigned,'reviewed_tasks':reviewed}

@router.get('/staff/{employee_id}/history')
def employee_history(employee_id:int,request:Request):
    # Lịch sử công việc có kiểm tra phân quyền
    s=context(request)
    if s.role not in ('admin','team_lead'): raise HTTPException(403,'Không có quyền xem lịch sử nhân viên')
    conn=get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute('''SELECT e.id,e.employee_name,e.employee_code,e.workshop_id
                FROM employees e WHERE e.id=%s''',(employee_id,))
            emp=cur.fetchone()
            if not emp: raise HTTPException(404,'Không tìm thấy nhân viên')
            if s.role=='team_lead':
                cur.execute('''SELECT 1 FROM app_users a JOIN employees e ON e.id=a.employee_id
                    WHERE lower(a.username)=lower(%s) AND a.is_active AND e.workshop_id=%s''',
                    (s.username,emp['workshop_id']))
                if not cur.fetchone():raise HTTPException(403,'Nhân viên ngoài xưởng được quản lý')
            cur.execute('''SELECT t.id,t.title,t.description,t.created_at,t.due_at,t.status,
                    m.machine_code, giver.employee_id AS giver_employee_id,
                    (SELECT max(r.created_at) FROM task_reports r WHERE r.task_id=t.id) AS last_submitted_at
                FROM tasks t JOIN machines m ON m.id=t.machine_id
                JOIN app_users receiver ON receiver.id=t.assigned_to
                JOIN app_users giver ON giver.id=t.assigned_by
                WHERE receiver.employee_id=%s
                  AND (%s OR t.machine_id=ANY(%s::integer[]))
                ORDER BY t.created_at DESC,t.id DESC''',
                (employee_id,s.all_machines,list(s.machine_ids)))
            tasks_history = [dict(r) for r in cur.fetchall()]
            return {'employee':{'id':emp['id'],'employee_name':emp['employee_name'],'employee_code':emp['employee_code']},
                    'tasks':tasks_history}
    finally:conn.close()

@router.get('/machines')
def machines(request: Request):
    s=context(request)
    return query('SELECT m.id, m.machine_code, m.machine_name, w.workshop_code, w.workshop_name FROM machines m JOIN workshops w ON w.id=m.workshop_id WHERE %s OR m.id=ANY(%s::integer[]) ORDER BY m.machine_code',(s.all_machines,list(s.machine_ids)))

@router.get('/assignees')
def assignees(request: Request, machine_id:int):
    s=context(request)
    if s.role!='team_lead': raise HTTPException(403,'Chỉ Tổ trưởng được giao việc')
    if not s.all_machines and machine_id not in s.machine_ids: raise HTTPException(403,'Máy ngoài phạm vi')
    return query('''SELECT u.id, u.username, e.employee_name FROM app_users u
       JOIN employees e ON e.id=u.employee_id JOIN machine_assignments ma ON ma.employee_id=e.id
       WHERE u.is_active AND u.role='technician' AND e.employment_status='Đang làm' AND ma.machine_id=%s ORDER BY u.username''',(machine_id,))
       
@router.get('/tasks')
def tasks(request: Request):
    s=context(request)
    return query('''SELECT t.id,t.title,t.description,t.machine_id,m.machine_code,w.workshop_code,t.due_at,t.status,
       t.created_at, giver.username AS giver, receiver.username AS receiver,
       COALESCE(NULLIF(TRIM(giver_emp.employee_name), ''), giver.username) AS giver_name,
       COALESCE(NULLIF(TRIM(receiver_emp.employee_name), ''), receiver.username) AS receiver_name,
       (SELECT MAX(r.created_at) FROM task_reports r WHERE r.task_id=t.id) AS last_submitted_at,
       (SELECT COUNT(*) FROM task_reports r WHERE r.task_id=t.id) AS report_count,
       EXISTS (SELECT 1 FROM task_reviews rv JOIN app_users au ON au.id=rv.reviewer_id WHERE rv.task_id=t.id AND rv.decision='approved' AND au.role='admin') AS admin_approved,
       EXISTS (SELECT 1 FROM task_reviews rv JOIN app_users lu ON lu.id=rv.reviewer_id WHERE rv.task_id=t.id AND rv.decision='approved' AND lu.role='team_lead') AS lead_approved
       FROM tasks t JOIN machines m ON m.id=t.machine_id JOIN workshops w ON w.id=m.workshop_id
       JOIN app_users giver ON giver.id=t.assigned_by JOIN app_users receiver ON receiver.id=t.assigned_to
       LEFT JOIN employees giver_emp ON giver_emp.id=giver.employee_id
       LEFT JOIN employees receiver_emp ON receiver_emp.id=receiver.employee_id
       WHERE (%s OR t.machine_id=ANY(%s::integer[])) AND (%s <> 'technician' OR lower(receiver.username)=lower(%s))
       ORDER BY t.created_at DESC,t.id DESC''',(s.all_machines,list(s.machine_ids),s.role,s.username))

class TaskIn(BaseModel):
    machine_id:int
    assigned_to:int
    title:str=Field(min_length=3,max_length=255)
    description:str=Field(default='',max_length=10000)
    due_at:datetime

@router.post('/tasks',status_code=201)
def create_task(payload:TaskIn,request:Request):
    s=context(request)
    if s.role!='team_lead':raise HTTPException(403,'Chỉ tổ trưởng được giao việc trong luồng duyệt này')
    if payload.due_at.tzinfo is None or payload.due_at<=datetime.now(timezone.utc):
        raise HTTPException(422,'Hạn hoàn thành phải là thời điểm tương lai có múi giờ')
    # MES: thời hạn giao phải trong cùng ngày sản xuất, tính theo giờ Việt Nam.
    local_zone=ZoneInfo('Asia/Ho_Chi_Minh')
    if payload.due_at.astimezone(local_zone).date()!=datetime.now(local_zone).date():
        raise HTTPException(422,'Công việc cần có hạn hoàn thành trong ngày giao (giờ Việt Nam)')
    conn=get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u=actor(cur,s)
                if not permitted(cur,s,payload.machine_id):raise HTTPException(403,'Máy ngoài phạm vi')
                cur.execute('''SELECT 1 FROM app_users au
                       JOIN employees e ON e.id=au.employee_id
                       JOIN machine_assignments ma ON ma.employee_id=e.id
                       WHERE au.id=%s AND au.is_active AND au.role='technician'
                         AND e.employment_status='Đang làm' AND ma.machine_id=%s''',(payload.assigned_to,payload.machine_id))
                if not cur.fetchone():raise HTTPException(403,'Kỹ thuật viên không được gán máy này')
                cur.execute('''INSERT INTO tasks(machine_id,assigned_by,assigned_to,title,description,due_at)
                    VALUES (%s,%s,%s,%s,%s,%s) RETURNING id''',(payload.machine_id,u['id'],payload.assigned_to,payload.title.strip(),payload.description,payload.due_at))
                return dict(cur.fetchone())
    finally:conn.close()

@router.post('/tasks/{task_id}/start')
def start(task_id:int,request:Request):
    s=context(request)
    if s.role!='technician':raise HTTPException(403,'Chỉ kỹ thuật viên nhận việc')
    conn=get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u=actor(cur,s); t=load_task(cur,s,task_id,u)
                if t['assigned_to']!=u['id'] or t['status'] not in ('assigned','returned'):raise HTTPException(409,'Không thể bắt đầu trạng thái này')
                cur.execute("UPDATE tasks SET status='in_progress', updated_at=now() WHERE id=%s",(task_id,))
        return {'status':'in_progress'}
    finally:conn.close()

class ReportIn(BaseModel):
    summary:str=Field(min_length=3,max_length=10000)
    errors:str=Field(default='',max_length=10000)

@router.post('/tasks/{task_id}/reports',status_code=201)
def report(task_id:int,payload:ReportIn,request:Request):
    s=context(request)
    if s.role!='technician':raise HTTPException(403,'Chỉ kỹ thuật viên nộp báo cáo')
    conn=get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u=actor(cur,s); t=load_task(cur,s,task_id,u)
                if t['assigned_to']!=u['id'] or t['status'] not in ('assigned','in_progress','returned'):raise HTTPException(409,'Chỉ người được giao mới có thể nộp báo cáo công việc chưa được duyệt')
                cur.execute('INSERT INTO task_reports(task_id,author_id,summary,errors) VALUES (%s,%s,%s,%s) RETURNING id',(task_id,u['id'],payload.summary.strip(),payload.errors))
                rid=cur.fetchone()['id']
                cur.execute("UPDATE tasks SET status='submitted',updated_at=now() WHERE id=%s",(task_id,))
                return {'id':rid,'status':'submitted'}
    finally:conn.close()

class ReviewIn(BaseModel):
    decision:str
    comment:str=Field(default='',max_length=10000)

@router.post('/tasks/{task_id}/reviews',status_code=201)
def review(task_id:int,payload:ReviewIn,request:Request):
    s=context(request)
    if s.role!='team_lead':raise HTTPException(403,'Chỉ tổ trưởng được duyệt báo cáo')
    if payload.decision not in ('approved','returned'):raise HTTPException(422,'Quyết định không hợp lệ')
    if payload.decision=='returned' and not payload.comment.strip(): raise HTTPException(422,'Cần ghi lý do trả lại')
    conn=get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u=actor(cur,s);t=load_task(cur,s,task_id,u)
                if t['status']!='submitted':raise HTTPException(409,'Chỉ duyệt báo cáo đã nộp')
                cur.execute('SELECT id FROM task_reports WHERE task_id=%s ORDER BY id DESC LIMIT 1',(task_id,))
                r=cur.fetchone()
                if not r:raise HTTPException(409,'Chưa có báo cáo')
                cur.execute('INSERT INTO task_reviews(task_id,report_id,reviewer_id,decision,comment) VALUES (%s,%s,%s,%s,%s)',(task_id,r['id'],u['id'],payload.decision,payload.comment))
                cur.execute('UPDATE tasks SET status=%s,updated_at=now() WHERE id=%s',(payload.decision,task_id))
                return {'status':payload.decision}
    finally:conn.close()

@router.post('/tasks/{task_id}/admin-review')
def admin_review_disabled(task_id:int, request:Request):
    raise HTTPException(403, 'Quy trình mới: Tổ trưởng duyệt là hoàn thành; Admin chỉ được xem')

@router.get('/tasks/{task_id}/history')
def history(task_id:int,request:Request):
    s=context(request)
    conn=get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            u=actor(cur,s);load_task(cur,s,task_id,u)
            cur.execute('''SELECT r.id,r.summary,r.errors,r.created_at,
                COALESCE(NULLIF(TRIM(author_emp.employee_name), ''),
                         NULLIF(TRIM(a.full_name), ''), a.username) AS author,
                v.decision,v.comment,v.created_at AS reviewed_at,
                COALESCE(NULLIF(TRIM(reviewer_emp.employee_name), ''),
                         NULLIF(TRIM(b.full_name), ''), b.username) AS reviewer
                FROM task_reports r JOIN app_users a ON a.id=r.author_id
                LEFT JOIN employees author_emp ON author_emp.id=a.employee_id
                LEFT JOIN task_reviews v ON v.report_id=r.id
                LEFT JOIN app_users b ON b.id=v.reviewer_id
                LEFT JOIN employees reviewer_emp ON reviewer_emp.id=b.employee_id
                WHERE r.task_id=%s ORDER BY r.id DESC,v.id DESC''',(task_id,))
            return [dict(x) for x in cur.fetchall()]
    finally:conn.close()
