"""Read-only, session-scoped conversational queries for MES technicians.

Task/report ownership is always tied to app_users.id of the authenticated user.
Machine/order visibility is limited to machine IDs obtained from server-side scope.
"""
from __future__ import annotations

import re
from backend.ai_conversation import _normalize

TASK_LABELS = {
    'assigned': 'Đã giao', 'in_progress': 'Đang thực hiện',
    'submitted': 'Đã nộp, chờ duyệt', 'approved': 'Đã duyệt',
    'returned': 'Bị trả lại', 'completed': 'Hoàn thành',
    'cancelled': 'Đã hủy',
}
ORDER_LABELS = {
    'pending_lead': 'Chờ Tổ trưởng duyệt', 'pending_admin': 'Chờ Admin duyệt',
    'in_production': 'Đang sản xuất', 'completed': 'Đã hoàn thành',
    'rejected': 'Đã từ chối',
}


def detect_technician_intent(question: str) -> str | None:
    q = _normalize(question)
    if not q:
        return None
    def has(*terms):
        return any(term in q for term in terms)
    task = has('cong viec', 'nhiem vu', 'viec duoc giao', 'viec cua toi', 'task', 'giao viec')
    report = has('bao cao', 'luot nop', 'lan nop')
    order = has('cong don', 'don san xuat', 'don cd', 'ma cd', 'don hang') or bool(re.search(r'\bcd\s*\d{7}\b', q))
    machine = has('may', 'thiet bi', 'cong tram')

    if report:
        if has('bi tra lai', 'da tra lai', 'khong duoc duyet', 'returned'):
            return 'reports_returned'
        if has('cho duyet', 'cho to truong', 'da nop chua duyet', 'dang cho', 'pending'):
            return 'reports_pending'
        if has('gan nhat', 'moi nhat', 'lich su', 'danh sach', 'liet ke', 'nhung bao cao', 'cac bao cao'):
            return 'reports_history'
        if has('bao nhieu', 'so luong', 'tong', 'da nop', 'toi nop', 'cua toi', 'da gui'):
            return 'reports_count'
    if task:
        if has('bi tra lai', 'da tra lai', 'lam lai', 'returned'):
            return 'tasks_returned'
        if has('cho duyet', 'da nop', 'submitted', 'dang cho duyet'):
            return 'tasks_submitted'
        if has('chua hoan thanh', 'chua xong', 'can lam', 'chua lam', 'dang lam', 'dang thuc hien', 'can xu ly'):
            return 'tasks_open'
        if has('da hoan thanh', 'da duyet', 'duoc duyet', 'approved', 'hoan tat', 'ket thuc'):
            return 'tasks_approved'
        if has('sap den han', 'gan den han', 'qua han', 'tre han', 'han chot', 'deadline', 'han hoan thanh'):
            return 'tasks_deadlines'
        if has('lich su', 'tat ca', 'thong ke', 'trang thai', 'bao nhieu', 'danh sach', 'liet ke', 'cua toi', 'duoc giao'):
            return 'tasks_overview'
    if machine:
        if has('bao tri', 'maintenance'):
            return 'machines_maintenance'
        if has('bi loi', 'loi may', 'may loi', 'fault', 'error'):
            return 'machines_fault'
        if has('dang dung', 'ngung chay', 'stopped', 'khong hoat dong', 'khong chay'):
            return 'machines_stopped'
        if has('dang chay', 'running', 'hoat dong'):
            return 'machines_running'
        if has('duoc giao', 'phan cong', 'cua toi', 'toi phu trach', 'bao nhieu', 'danh sach', 'may nao', 'nhung may', 'may gi', 'trang thai'):
            return 'machines_all'
    if order:
        if has('bi tu choi', 'da tu choi', 'rejected'):
            return 'orders_rejected'
        if has('chua hoan thanh', 'chua xong', 'chua ket thuc'):
            return 'orders_unfinished'
        if has('da hoan thanh', 'hoan tat', 'completed'):
            return 'orders_completed'
        if has('dang san xuat', 'dang lam', 'in production'):
            return 'orders_in_production'
        if has('cho admin hoan thanh', 'cho admin xac nhan', 'cho hoan thanh'):
            return 'orders_waiting_completion'
        if has('tien do', 'bao nhieu', 'danh sach', 'liet ke', 'cua toi', 'lien quan', 'tham gia', 'ma cd') or re.search(r'cd\s*\d{7}',q):
            return 'orders_overview'
    if has('toi can lam gi', 'hom nay lam gi', 'viec toi can lam', 'toi can xu ly gi', 'can lam gi', 'nhiem vu hom nay'):
        return 'my_actions'
    return None


def technician_answer(intent: str, scope, fetch_all, question: str = '') -> str:
    if scope.role != 'technician':
        return 'Chức năng này dành cho tài khoản Kỹ thuật viên.'
    # User identity is server-provided. The prompt never contributes a user ID.
    identity = fetch_all("""SELECT id FROM app_users
         WHERE lower(username)=lower(%s) AND role='technician' AND is_active=TRUE""", (scope.username,))
    if not identity:
        return 'Không xác định được tài khoản Kỹ thuật viên đang đăng nhập.'
    uid = int(identity[0]['id'])
    mids = list(scope.machine_ids)
    if not mids or scope.is_empty:
        return 'Bạn chưa được phân công máy nên hiện chưa có dữ liệu sản xuất để tra cứu.'

    if intent.startswith('machines_'):
        rows = fetch_all("""SELECT m.machine_code,m.machine_name,m.status,w.workshop_name
            FROM machines m JOIN workshops w ON w.id=m.workshop_id
            WHERE m.id=ANY(%s::integer[]) ORDER BY m.machine_code""", (mids,))
        if intent == 'machines_running':
            rows = [r for r in rows if str(r.get('status') or '').lower() == 'running']
            label='đang chạy'
        elif intent == 'machines_fault':
            rows = [r for r in rows if str(r.get('status') or '').lower() in ('fault','error','broken','failed')]
            label='bị lỗi'
        elif intent == 'machines_maintenance':
            rows = [r for r in rows if str(r.get('status') or '').lower() in ('maintenance','bao tri')]
            label='đang bảo trì'
        elif intent == 'machines_stopped':
            rows = [r for r in rows if str(r.get('status') or '').lower() in ('stopped','stop','idle','offline')]
            label='đang dừng'
        else:
            label='được phân công cho bạn'
        if not rows:
            return f'Hiện không có máy nào {label} trong phạm vi được phân công của bạn.'
        lines=[f'Bạn có **{len(rows)} máy {label}**:']
        lines += [f"• **{r['machine_code']}** · {r.get('machine_name') or 'Máy'} · {r.get('workshop_name') or 'Chưa rõ xưởng'} · {r.get('status') or 'Chưa rõ trạng thái'}" for r in rows]
        return '\n\n'.join((lines[0], '\n'.join(lines[1:])))

    if intent.startswith('reports_'):
        if intent == 'reports_count':
            result=fetch_all('SELECT COUNT(*)::bigint AS total FROM task_reports WHERE author_id=%s',(uid,))
            total=int(result[0]['total'] or 0) if result else 0
            return f'Bạn đã nộp **{total} lượt báo cáo công việc**.'
        # Report history is tied to the author AND assigned task, never coworkers.
        rows=fetch_all("""SELECT r.id,r.created_at,t.title,t.status,m.machine_code,
              (SELECT rv.decision FROM task_reviews rv
               WHERE rv.report_id=r.id ORDER BY rv.created_at DESC,rv.id DESC LIMIT 1) AS decision
            FROM task_reports r JOIN tasks t ON t.id=r.task_id
            JOIN machines m ON m.id=t.machine_id
            WHERE r.author_id=%s AND t.assigned_to=%s AND t.machine_id=ANY(%s::integer[])
            ORDER BY r.created_at DESC,r.id DESC LIMIT 101""", (uid,uid,mids))
        if intent == 'reports_pending':
            rows=[r for r in rows if r.get('status')=='submitted' and not r.get('decision')]
            label='đang chờ duyệt'
        elif intent == 'reports_returned':
            rows=[r for r in rows if r.get('decision')=='returned']
            label='đã bị trả lại'
        else:
            label='đã nộp gần đây'
        if len(rows)>100:
            return 'Bạn có hơn 100 lượt báo cáo phù hợp. Hãy thu hẹp phạm vi câu hỏi.'
        if not rows:
            return f'Hiện bạn không có báo cáo nào {label}.'
        lines=[f'Bạn có **{len(rows)} lượt báo cáo {label}**:']
        lines += [f"• **Báo cáo #{r['id']}** · {r['title']} · {r['machine_code']}" for r in rows]
        return '\n\n'.join((lines[0], '\n'.join(lines[1:])))

    if intent.startswith('tasks_') or intent=='my_actions':
        rows=fetch_all("""SELECT t.id,t.title,t.status,t.due_at,m.machine_code
            FROM tasks t JOIN machines m ON m.id=t.machine_id
            WHERE t.assigned_to=%s AND t.machine_id=ANY(%s::integer[])
            ORDER BY t.created_at DESC,t.id DESC LIMIT 101""", (uid,mids))
        if intent == 'tasks_open' or intent=='my_actions':
            rows=[r for r in rows if r.get('status') not in ('approved','completed','cancelled')]
            label='chưa hoàn thành'
        elif intent == 'tasks_approved':
            rows=[r for r in rows if r.get('status') in ('approved','completed')]
            label='đã được duyệt'
        elif intent == 'tasks_submitted':
            rows=[r for r in rows if r.get('status')=='submitted']
            label='đã nộp, chờ duyệt'
        elif intent == 'tasks_returned':
            rows=[r for r in rows if r.get('status')=='returned']
            label='bị trả lại'
        elif intent == 'tasks_deadlines':
            rows=[r for r in rows if r.get('status') not in ('approved','completed','cancelled')]
            label='chưa hoàn thành (kèm hạn xử lý)'
        else:
            label='được giao'
        if len(rows)>100:
            return 'Có hơn 100 công việc phù hợp. Hãy hỏi thêm trạng thái để lọc danh sách.'
        if not rows:
            return ('Hiện bạn không có công việc nào cần xử lý.' if intent=='my_actions'
                    else f'Hiện bạn không có công việc nào {label}.')
        lines=[f'Bạn có **{len(rows)} công việc {label}**:']
        for r in rows:
            due = f" · Hạn: {r['due_at'].strftime('%d/%m/%Y %H:%M')}" if r.get('due_at') and hasattr(r['due_at'],'strftime') else ''
            lines.append(f"• **#{r['id']} – {r['title']}** · {r['machine_code']} · {TASK_LABELS.get(r['status'],r['status'])}{due}")
        return '\n\n'.join((lines[0], '\n'.join(lines[1:])))

    if intent.startswith('orders_'):
        rows=fetch_all("""SELECT co.id,co.status,co.quantity,
          co.completion_requested_at, w.workshop_name,
          CASE WHEN co.status='completed' THEN 100
             WHEN co.quantity>0 AND co.status='in_production' AND COALESCE(st.stages,0)>0
             THEN LEAST(100,GREATEST(0,ROUND(100.0*st.done/(co.quantity*st.stages),2)))
             ELSE 0 END AS progress
          FROM customer_orders co JOIN workshops w ON w.id=co.workshop_id
          LEFT JOIN LATERAL (SELECT COUNT(*) stages,COALESCE(SUM(quantity_completed),0) done
                            FROM customer_order_stage_progress WHERE customer_order_id=co.id) st ON TRUE
          WHERE co.deleted_at IS NULL AND EXISTS (
            SELECT 1 FROM customer_order_machines cm
            WHERE cm.customer_order_id=co.id AND cm.machine_id=ANY(%s::integer[]))
          ORDER BY co.id DESC LIMIT 101""", (mids,))
        q=_normalize(question)
        match=re.search(r'cd\s*(\d{7})',q)
        if match:
            rows=[r for r in rows if int(r['id'])==int(match.group(1))]
        if intent == 'orders_completed':
            rows=[r for r in rows if r.get('status')=='completed']; label='đã hoàn thành'
        elif intent == 'orders_rejected':
            rows=[r for r in rows if r.get('status')=='rejected']; label='đã bị từ chối'
        elif intent == 'orders_unfinished':
            rows=[r for r in rows if r.get('status') in ('pending_lead','pending_admin','in_production')]; label='chưa hoàn thành'
        elif intent == 'orders_in_production':
            rows=[r for r in rows if r.get('status')=='in_production']; label='đang sản xuất'
        elif intent == 'orders_waiting_completion':
            rows=[r for r in rows if r.get('status')=='in_production' and r.get('completion_requested_at')]; label='chờ Admin hoàn thành'
        else:
            label='liên quan đến máy bạn được phân công'
        if len(rows)>100:
            return 'Có hơn 100 công đơn liên quan đến máy bạn phụ trách. Hãy hỏi theo mã CD hoặc trạng thái.'
        if not rows:
            return f'Hiện không có công đơn nào {label} trong phạm vi máy bạn được phân công.'
        lines=[f'Có **{len(rows)} công đơn {label}**:']
        for r in rows:
            note=' · Đã gửi Admin xác nhận hoàn thành' if r.get('status')=='in_production' and r.get('completion_requested_at') else ''
            lines.append(f"• **CD-{int(r['id']):07d}** · {ORDER_LABELS.get(r['status'],r['status'])} · {float(r.get('progress') or 0):g}% · {r.get('workshop_name') or 'Chưa xác định xưởng'}{note}")
        return '\n\n'.join((lines[0], '\n'.join(lines[1:])))
    return 'Tôi chưa xác định được loại dữ liệu bạn muốn xem. Bạn có thể hỏi về máy, công việc hoặc báo cáo của mình.'
