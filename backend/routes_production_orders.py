"""Production Order CRUD (admin only) using actual PostgreSQL records.
No implicit creation of production data or automatic completion.
"""
from datetime import date, datetime
from typing import Literal
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from backend.db import get_connection
from backend.scope import scope_from_request

router = APIRouter(prefix='/api/production-orders', tags=['Production Orders'])


def admin_only(request: Request):
    s = scope_from_request(request)
    if s.role != 'admin' or not s.all_machines:
        raise HTTPException(status_code=403, detail='Chỉ Admin được quản lý Production Order')


def sql_rows(sql, args=()):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, args)
            return [dict(x) for x in cur.fetchall()]
    finally:
        conn.close()


@router.get('/options')
def options(request: Request):
    admin_only(request)
    return {
        'workshops': sql_rows('SELECT id, workshop_code, workshop_name FROM workshops ORDER BY workshop_code'),
        'products': sql_rows('SELECT id, product_code, product_name FROM products ORDER BY product_code'),
        'machines': sql_rows('SELECT id, machine_code, machine_name, workshop_id FROM machines ORDER BY machine_code'),
    }


class CreatePO(BaseModel):
    workshop_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    planned_quantity: int = Field(gt=0, le=100000000)
    planned_start: date
    planned_end: date
    machine_ids: list[int] = Field(min_length=1, max_length=30)
    status: Literal['Planned', 'In Progress'] = 'Planned'

    @model_validator(mode='after')
    def dates_and_machines(self):
        if self.planned_end < self.planned_start:
            raise ValueError('Ngày kết thúc kế hoạch không được trước ngày bắt đầu')
        if len(set(self.machine_ids)) != len(self.machine_ids):
            raise ValueError('Không được chọn trùng máy')
        return self


@router.post('', status_code=201)
def create_po(payload: CreatePO, request: Request):
    admin_only(request)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute('SELECT id FROM workshops WHERE id=%s', (payload.workshop_id,))
                if not cur.fetchone():
                    raise HTTPException(422, 'Xưởng không tồn tại')
                cur.execute('SELECT id FROM products WHERE id=%s', (payload.product_id,))
                if not cur.fetchone():
                    raise HTTPException(422, 'Sản phẩm không tồn tại')
                cur.execute('SELECT id FROM machines WHERE workshop_id=%s AND id=ANY(%s::int[])',
                            (payload.workshop_id, payload.machine_ids))
                found = {r['id'] for r in cur.fetchall()}
                if found != set(payload.machine_ids):
                    raise HTTPException(422, 'Tất cả máy phải thuộc xưởng đã chọn')
                cur.execute("SELECT 'PO-' || LPAD(nextval('production_order_code_seq')::text,7,'0') AS generated_code")
                order_code=cur.fetchone()['generated_code']
                try:
                    cur.execute('''INSERT INTO production_orders
                        (order_code,workshop_id,product_id,planned_quantity,planned_start,planned_end,status,actual_start)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,order_code''',
                        (order_code, payload.workshop_id, payload.product_id,
                         payload.planned_quantity, payload.planned_start, payload.planned_end,
                         payload.status, datetime.now() if payload.status == 'In Progress' else None))
                except psycopg2.errors.UniqueViolation:
                    raise HTTPException(409, 'Mã PO đã tồn tại')
                po = dict(cur.fetchone())
                if not _has_assignment_table(cur):
                    raise HTTPException(409, 'Thiếu bảng po_machine_assignments. Hãy chạy database/migrations/production_orders/005_po_machine_assignments.sql trong pgAdmin trước khi tạo PO mới.')
                for machine_id in payload.machine_ids:
                    cur.execute('INSERT INTO po_machine_assignments (production_order_id,machine_id) VALUES (%s,%s)',
                                (po['id'], machine_id))
                return po
    finally:
        conn.close()


class ProductionRecordIn(BaseModel):
    machine_id: int = Field(gt=0)
    production_date: date
    shift: str = Field(min_length=1, max_length=50)
    quantity_produced: int = Field(ge=0)
    quantity_defective: int = Field(ge=0)
    production_minutes: int = Field(ge=0, le=1440)


@router.post('/{order_code}/records', status_code=201)
def add_record(order_code: str, payload: ProductionRecordIn, request: Request):
    admin_only(request)
    if payload.quantity_defective > payload.quantity_produced:
        raise HTTPException(422, 'Số lượng lỗi không thể lớn hơn số lượng sản xuất')
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute('SELECT id,status FROM production_orders WHERE order_code=%s FOR UPDATE', (order_code,))
                po = cur.fetchone()
                if not po:
                    raise HTTPException(404, 'Không tìm thấy PO')
                if po['status'] in ('Completed', 'Cancelled'):
                    raise HTTPException(409, 'PO đã đóng hoặc hủy, không được thêm sản lượng')
                has_assignments = _has_assignment_table(cur)
                machine_ids = _po_machine_ids(cur, po['id'], has_assignments)
                if payload.machine_id not in machine_ids:
                    raise HTTPException(422, 'Máy chưa thuộc PO này. Cần đồng bộ phân công máy trước khi ghi sản lượng.')
                cur.execute('''INSERT INTO production_records
                    (production_order_id,production_date,shift,quantity_produced,quantity_defective,production_minutes,machine_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                    (po['id'],payload.production_date,payload.shift,payload.quantity_produced,
                     payload.quantity_defective,payload.production_minutes,payload.machine_id))
                record_id = cur.fetchone()['id']
                cur.execute("UPDATE production_orders SET status='In Progress', actual_start=COALESCE(actual_start,%s) WHERE id=%s",
                            (payload.production_date,po['id']))
                return {'id':record_id,'status':'In Progress'}
    finally:
        conn.close()


@router.post('/{order_code}/start')
def start_po(order_code: str, request: Request):
    """Start an assigned planned PO; do not generate production records."""
    admin_only(request)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute('SELECT id,workshop_id,status FROM production_orders WHERE order_code=%s FOR UPDATE', (order_code,))
                po = cur.fetchone()
                if not po:
                    raise HTTPException(404, 'Không tìm thấy PO')
                if po['status'] != 'Planned':
                    raise HTTPException(409, 'Chỉ PO đang ở trạng thái Kế hoạch mới có thể bắt đầu')
                if not _has_assignment_table(cur):
                    raise HTTPException(409, 'Chưa có bảng phân công máy; cần chạy migration 005')
                cur.execute("""SELECT COUNT(*) AS n FROM po_machine_assignments a
                    JOIN machines m ON m.id=a.machine_id
                    WHERE a.production_order_id=%s AND m.workshop_id=%s""",
                    (po['id'], po['workshop_id']))
                if cur.fetchone()['n'] == 0:
                    raise HTTPException(409, 'Cần phân công ít nhất một máy thuộc xưởng trước khi bắt đầu sản xuất')
                cur.execute("UPDATE production_orders SET status='In Progress', actual_start=COALESCE(actual_start, NOW()) WHERE id=%s", (po['id'],))
                return {'order_code':order_code,'status':'In Progress'}
    finally:
        conn.close()


@router.post('/{order_code}/complete')
def complete_po(order_code: str, request: Request):
    admin_only(request)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute('SELECT id, planned_quantity,status FROM production_orders WHERE order_code=%s FOR UPDATE', (order_code,))
                po = cur.fetchone()
                if not po:
                    raise HTTPException(404, 'Không tìm thấy PO')
                if po['status'] != 'In Progress':
                    raise HTTPException(409, 'Chỉ PO đang sản xuất mới được xác nhận đóng')
                cur.execute('''SELECT COALESCE(SUM(pr.quantity_produced),0)::int AS qty FROM production_records pr
                    JOIN machines m ON m.id=pr.machine_id
                    LEFT JOIN production_processes pp ON pp.id=m.process_id
                    WHERE pr.production_order_id=%s AND pp.process_order=(
                      SELECT MAX(pp2.process_order) FROM production_records pr2
                      JOIN machines m2 ON m2.id=pr2.machine_id
                      JOIN production_processes pp2 ON pp2.id=m2.process_id
                      WHERE pr2.production_order_id=%s)''',(po['id'],po['id']))
                actual = cur.fetchone()['qty']
                if actual < po['planned_quantity']:
                    raise HTTPException(409, f'Chưa đủ sản lượng công đoạn cuối ({actual}/{po["planned_quantity"]}); chưa thể hoàn thành')
                cur.execute("UPDATE production_orders SET status='Completed',actual_end=now(),actual_start=COALESCE(actual_start,now()) WHERE id=%s", (po['id'],))
                return {'status':'Completed','actual_quantity':actual}
    finally:
        conn.close()

@router.post('/{order_code}/cancel')
def cancel_po(order_code: str, request: Request):
    """Cancel only a planned PO with no production records; retain its history and assignments."""
    admin_only(request)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute('SELECT id,status FROM production_orders WHERE order_code=%s FOR UPDATE', (order_code,))
                po = cur.fetchone()
                if not po:
                    raise HTTPException(404, 'Không tìm thấy PO')
                if po['status'] != 'Planned':
                    raise HTTPException(409, 'Chỉ PO ở trạng thái Kế hoạch mới được hủy')
                cur.execute('SELECT 1 FROM production_records WHERE production_order_id=%s LIMIT 1', (po['id'],))
                if cur.fetchone():
                    raise HTTPException(409, 'PO đã có dữ liệu sản xuất, không thể hủy')
                cur.execute("UPDATE production_orders SET status='Cancelled' WHERE id=%s", (po['id'],))
                return {'status': 'Cancelled', 'order_code': order_code}
    finally:
        conn.close()


def _has_assignment_table(cur):
    # Keep legacy PO readable when migration 005 was not run yet.
    cur.execute("SELECT to_regclass('public.po_machine_assignments') IS NOT NULL AS exists")
    return bool(cur.fetchone()['exists'])


def _po_machine_ids(cur, po_id, use_assignments):
    # Include old records even if assignment migration was run before they existed.
    if use_assignments:
        cur.execute('''SELECT machine_id FROM po_machine_assignments WHERE production_order_id=%s
            UNION SELECT DISTINCT machine_id FROM production_records
            WHERE production_order_id=%s AND machine_id IS NOT NULL''', (po_id, po_id))
    else:
        cur.execute('''SELECT DISTINCT machine_id FROM production_records
            WHERE production_order_id=%s AND machine_id IS NOT NULL''', (po_id,))
    return [r['machine_id'] for r in cur.fetchall()]


@router.get('/assignments')
def assignments(request: Request):
    admin_only(request)
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if _has_assignment_table(cur):
                cur.execute('''SELECT po.order_code, m.machine_code, m.machine_name
                    FROM (SELECT production_order_id, machine_id FROM po_machine_assignments
                          UNION SELECT DISTINCT production_order_id, machine_id FROM production_records
                          WHERE machine_id IS NOT NULL) a
                    JOIN production_orders po ON po.id=a.production_order_id
                    JOIN machines m ON m.id=a.machine_id ORDER BY po.order_code,m.machine_code''')
            else:
                cur.execute('''SELECT DISTINCT po.order_code, m.machine_code, m.machine_name
                    FROM production_records pr
                    JOIN production_orders po ON po.id=pr.production_order_id
                    JOIN machines m ON m.id=pr.machine_id ORDER BY po.order_code,m.machine_code''')
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.get('/{order_code}/record-details')
def record_details(order_code: str, request: Request):
    # Chi tiết các máy và nhật ký sản lượng thực sự lưu trong CSDL.
    admin_only(request)
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute('''SELECT po.id,po.order_code,po.status,po.planned_quantity,
                po.planned_start,po.planned_end,w.workshop_code,w.workshop_name,
                p.product_code,p.product_name
                FROM production_orders po
                JOIN workshops w ON w.id=po.workshop_id
                JOIN products p ON p.id=po.product_id
                WHERE po.order_code=%s''', (order_code,))
            po=cur.fetchone()
            if not po: raise HTTPException(404,'Không tìm thấy PO')
            has_assignments = _has_assignment_table(cur)
            machine_ids = _po_machine_ids(cur, po['id'], has_assignments)
            if machine_ids:
                cur.execute('''SELECT m.id,m.machine_code,m.machine_name,pp.process_name,pp.process_order
                    FROM machines m LEFT JOIN production_processes pp ON pp.id=m.process_id
                    WHERE m.id=ANY(%s::int[]) AND m.workshop_id=(
                        SELECT workshop_id FROM production_orders WHERE id=%s)
                    ORDER BY pp.process_order NULLS LAST,m.machine_code''', (machine_ids, po['id']))
                machines=[dict(r) for r in cur.fetchall()]
            else:
                machines=[]
            cur.execute('''SELECT pr.id,pr.machine_id,pr.production_date,pr.shift,
                pr.quantity_produced,pr.quantity_defective,pr.production_minutes
                FROM production_records pr WHERE pr.production_order_id=%s
                ORDER BY pr.production_date DESC,pr.id DESC''',(po['id'],))
            records=[dict(r) for r in cur.fetchall()]
            return {'order':dict(po),'machines':machines,'records':records,
                    'assignment_migration_needed':not has_assignments}
    finally:conn.close()


@router.patch('/{order_code}/records/{record_id}')
def edit_record(order_code: str,record_id:int,payload:ProductionRecordIn,request:Request):
    # Sửa nhật ký hiện có, không tạo bản ghi mới hoặc tự động cộng dồn.
    admin_only(request)
    if payload.quantity_defective > payload.quantity_produced:
        raise HTTPException(422,'Số lượng lỗi không được lớn hơn sản lượng')
    conn=get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute('SELECT id,status FROM production_orders WHERE order_code=%s FOR UPDATE',(order_code,))
                po=cur.fetchone()
                if not po:raise HTTPException(404,'Không tìm thấy PO')
                if po['status'] in ('Completed','Cancelled'):raise HTTPException(409,'PO đã đóng hoặc hủy; không thể sửa lịch sử sản lượng')
                cur.execute('SELECT id FROM production_records WHERE id=%s AND production_order_id=%s FOR UPDATE',(record_id,po['id']))
                if not cur.fetchone():raise HTTPException(404,'Bản ghi sản lượng không thuộc PO này')
                has_assignments = _has_assignment_table(cur)
                machine_ids = _po_machine_ids(cur, po['id'], has_assignments)
                if payload.machine_id not in machine_ids:
                    raise HTTPException(422,'Máy không thuộc PO này')
                cur.execute('''UPDATE production_records SET machine_id=%s,production_date=%s,shift=%s,
                    quantity_produced=%s,quantity_defective=%s,production_minutes=%s WHERE id=%s''',
                    (payload.machine_id,payload.production_date,payload.shift.strip(),payload.quantity_produced,
                    payload.quantity_defective,payload.production_minutes,record_id))
                return {'id':record_id,'updated':True}
    finally:conn.close()


class AssignPOMachines(BaseModel):
    machine_ids: list[int] = Field(min_length=1, max_length=30)


@router.put('/{order_code}/machines')
def update_po_machines(order_code: str, payload: AssignPOMachines, request: Request):
    """Admin updates PO machines, preserving machines with recorded production."""
    admin_only(request)
    if len(payload.machine_ids) != len(set(payload.machine_ids)):
        raise HTTPException(422, 'Máy bị chọn trùng')
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if not _has_assignment_table(cur):
                    raise HTTPException(409, 'Cần chạy migration 005 để phân công máy')
                cur.execute('SELECT id,workshop_id,status FROM production_orders WHERE order_code=%s FOR UPDATE', (order_code,))
                po = cur.fetchone()
                if not po: raise HTTPException(404, 'Không tìm thấy Production Order')
                if po['status'] in ('Completed','Cancelled'):
                    raise HTTPException(409, 'PO đã đóng hoặc hủy, không thể sửa phân công máy')
                cur.execute('SELECT id FROM machines WHERE workshop_id=%s AND id=ANY(%s::int[])',
                            (po['workshop_id'], payload.machine_ids))
                found = {r['id'] for r in cur.fetchall()}
                if found != set(payload.machine_ids):
                    raise HTTPException(422, 'Máy phải thuộc xưởng của PO')
                cur.execute('SELECT DISTINCT machine_id FROM production_records WHERE production_order_id=%s AND machine_id IS NOT NULL', (po['id'],))
                historical = {r['machine_id'] for r in cur.fetchall()}
                if not historical.issubset(set(payload.machine_ids)):
                    raise HTTPException(409, 'Không thể bỏ máy đã có lịch sử sản xuất: ' + ', '.join(str(x) for x in sorted(historical-set(payload.machine_ids))))
                cur.execute('DELETE FROM po_machine_assignments WHERE production_order_id=%s AND NOT (machine_id=ANY(%s::int[]))',
                            (po['id'], payload.machine_ids))
                cur.execute("""INSERT INTO po_machine_assignments(production_order_id,machine_id)
                    SELECT %s, unnest(%s::int[]) ON CONFLICT DO NOTHING""", (po['id'], payload.machine_ids))
                return {'order_code': order_code, 'machine_count': len(payload.machine_ids)}
    finally:
        conn.close()
