"""Read-only, workshop-scoped MES answers for the authenticated team lead.

All SQL predicates derive the workshop from server-side machine scope; the
prompt can never select another workshop. No changes to business workflow.
"""
from __future__ import annotations

from backend.ai_conversation import _normalize


STATUS = {
    'pending_lead': 'Chờ Tổ trưởng duyệt',
    'pending_admin': 'Chờ Admin duyệt',
    'in_production': 'Đang sản xuất',
    'completed': 'Đã hoàn thành',
    'rejected': 'Đã từ chối',
    'assigned': 'Đã giao',
    'in_progress': 'Đang thực hiện',
    'submitted': 'Chờ duyệt báo cáo',
    'approved': 'Đã duyệt',
    'returned': 'Bị trả lại',
}


def detect_lead_intent(question: str) -> str | None:
    """Route specific business intents before generic workshop summaries.

    Negations and status names are checked in precedence order. This prevents
    "chưa hoàn thành" from becoming "đã hoàn thành", and ensures that
    pending Admin approval differs from Admin completion confirmation.
    """
    q = _normalize(question)
    if not q:
        return None

    def has(*terms: str) -> bool:
        return any(term in q for term in terms)

    order = has('cong don', 'don hang', 'don san xuat', 'ma cd', 'don cd')
    task = has('cong viec', 'giao viec', 'nhiem vu', 'task')
    reports = has('bao cao', 'nop bao cao')
    machine = has('may', 'cong tram', 'thiet bi')

    # Reporting requests outrank the generic word 'công việc' inside the question.
    if reports and has('cho duyet', 'chua duyet', 'can duyet', 'da nop',
                       'da gui', 'cho toi', 'nhan vien nop'):
        return 'submitted_reports'
    if reports and has('bi tra lai', 'da tra lai'):
        return 'tasks_returned'

    # A task status must never be interpreted as a customer order status.
    if task:
        if has('cho duyet', 'cho toi duyet', 'cho to truong', 'da nop bao cao'):
            return 'submitted_reports'
        if has('bi tra lai', 'da tra lai', 'returned'):
            return 'tasks_returned'
        if has('chua hoan thanh', 'chua xong', 'dang lam', 'chua duoc duyet', 'chua duyet'):
            return 'tasks_unfinished'
        if has('da duyet', 'da hoan thanh', 'hoan tat', 'approved'):
            return 'tasks_approved'
        if has('theo trang thai', 'thong ke', 'tinh hinh', 'tong quan', 'da giao',
               'cong viec nao', 'liet ke', 'danh sach', 'bao nhieu', 'cua toi'):
            return 'lead_tasks'

    if reports:
        if has('cho duyet', 'chua duyet', 'can duyet', 'da nop',
               'da gui', 'cho toi', 'nhan vien nop'):
            return 'submitted_reports'

    if order:
        if has('cho toi xu ly', 'can toi xu ly', 'cho toi giai quyet', 'can toi giai quyet'):
            return 'lead_actions'
        # Specific statuses first. A request that is ALREADY with Admin must
        # not be answered by the list needing a new submission.
        if has('cho admin hoan thanh', 'cho admin xac nhan',
               'cho xac nhan hoan thanh', 'da gui admin', 'cho hoan thanh',
               'cho admin xac nhan hoan thanh', 'da nop len admin'):
            return 'orders_waiting_admin_completion'
        if 'admin' in q and has('cho', 'duyet', 'phe duyet', 'can duyet'):
            return 'orders_pending_admin_approval'
        if has('chua duoc duyet', 'chua duyet'):
            return 'orders_pending_approval'
        if has('chua hoan thanh', 'chua xong', 'chua ket thuc',
               'chua hoan tat', 'khong duoc hoan thanh'):
            return 'orders_unfinished'
        if has('da tu choi', 'bi tu choi', 'tu choi', 'rejected'):
            return 'orders_rejected'
        if has('da hoan thanh', 'hoan tat', 'completed', 'ket thuc'):
            return 'orders_completed'
        if has('dang san xuat', 'dang lam san xuat', 'in production'):
            return 'orders_in_production'
        if has('cho tiep nhan', 'cho to truong duyet', 'cho toi duyet',
               'cho duyet', 'can duyet'):
            return 'pending_lead_orders'
        if has('gui admin', 'gui len admin', 'du dieu kien hoan thanh',
               'du 100', 'dat 100', 'cho gui hoan thanh', 'can gui hoan thanh'):
            return 'completion_ready'
        if has('cua toi', 'phu trach', 'tong quan', 'tinh hinh', 'bao nhieu',
               'liet ke', 'danh sach', 'nhung cong don', 'cac cong don', 'cong don nao'):
            return 'lead_workshops'

    if machine:
        if has('bao tri', 'maintenance'):
            return 'machines_maintenance'
        if has('bi loi', 'loi', 'fault', 'error'):
            return 'machines_fault'
        if has('dang dung', 'ngung chay', 'stopped', 'stop'):
            return 'machines_stopped'
        if has('khong chay', 'khong hoat dong', 'khong running'):
            return 'machines_not_running'
        if has('dang chay', 'running', 'dang hoat dong'):
            return 'machines_running'
        if has('may nao', 'bao nhieu', 'danh sach', 'duoc giao', 'phu trach',
               'trong xuong', 'cua toi', 'tinh trang', 'trang thai'):
            return 'lead_machines'

    if 'xuong' in q and has('cua toi', 'phu trach', 'tong quan', 'tinh hinh',
                             'bao nhieu', 'liet ke', 'danh sach'):
        return 'lead_workshops'

    if has('toi can xu ly gi', 'toi phai lam gi', 'viec can xu ly',
           'to truong can xu ly', 'can toi xu ly'):
        return 'lead_actions'
    return None


# The scope is supplied by the authenticated caller, never by the LLM or text.
# Same workshop containment model as the MES customer-order permission checks.
WORKSHOP_PRED = ('co.workshop_id IN (SELECT DISTINCT m.workshop_id FROM machines m '
                 'WHERE m.id=ANY(%s::integer[]))')


def _count(fetch_all, sql, params):
    result = fetch_all(sql, params)
    return int(result[0]['total'] or 0) if result else 0


def lead_answer(intent: str, scope, fetch_all) -> str:
    if scope.role != 'team_lead' or scope.is_empty:
        return 'Bạn chưa được phân công xưởng để tra cứu dữ liệu này.'
    ids = list(scope.machine_ids)
    status_intents = {
        'orders_pending_admin_approval': ('pending_admin', 'chờ Admin duyệt công đơn'),
        'orders_waiting_admin_completion': ('in_production', 'chờ Admin xác nhận hoàn thành'),
        'orders_in_production': ('in_production', 'đang sản xuất'),
        'orders_completed': ('completed', 'đã hoàn thành'),
        'orders_rejected': ('rejected', 'đã bị từ chối'),
        'orders_unfinished': (None, 'chưa hoàn thành'),
        'orders_pending_approval': (None, 'chưa được duyệt'),
    }
    if intent in status_intents:
        status, label = status_intents[intent]
        extra = (' AND co.completion_requested_at IS NOT NULL AND co.completed_at IS NULL'
                 if intent == 'orders_waiting_admin_completion' else '')
        status_filter = ("co.status IN ('pending_lead','pending_admin','in_production')"
                         if intent == 'orders_unfinished' else
                         "co.status IN ('pending_lead','pending_admin')"
                         if intent == 'orders_pending_approval' else 'co.status=%s')
        rows = fetch_all('''SELECT co.id,co.status,co.completion_requested_at,
                w.workshop_name
              FROM customer_orders co
              JOIN workshops w ON w.id=co.workshop_id
              WHERE co.deleted_at IS NULL AND ''' + status_filter + ' AND ' + WORKSHOP_PRED +
              extra + ''' ORDER BY co.id DESC LIMIT 101''',
              (ids,) if status is None else (status, ids))
        if len(rows) > 100:
            return f'Có hơn 100 công đơn {label} trong phạm vi xưởng bạn phụ trách. Vui lòng lọc thêm theo mã.'
        if not rows:
            response = f'Hiện không có công đơn nào {label} trong xưởng bạn phụ trách.'
            if intent == 'orders_pending_admin_approval':
                return response + ' Lưu ý, công đơn chờ Admin duyệt ban đầu khác với công đơn chờ Admin xác nhận hoàn thành.'
            return response
        lines = [f'Hiện có **{len(rows)} công đơn {label}** trong xưởng bạn phụ trách:']
        for r in rows:
            note = (' · Đã gửi yêu cầu, chờ Admin hoàn thành'
                    if intent in ('orders_in_production', 'orders_unfinished') and r.get('completion_requested_at') else '')
            lines.append(f"• **CD-{int(r['id']):07d}** · {r['workshop_name']}{note}")
        if intent == 'orders_pending_admin_approval':
            lines.append('Đây là bước Admin phê duyệt công đơn, không phải bước xác nhận hoàn thành sản xuất.')
        if intent == 'orders_unfinished':
            lines.append('Danh sách trên không tính công đơn đã từ chối vì quy trình đã kết thúc.')
        if intent == 'orders_pending_approval':
            lines.append('Danh sách bao gồm cả bước chờ Tổ trưởng duyệt và chờ Admin duyệt ban đầu.')
        return '\n\n'.join((lines[0], '\n'.join(lines[1:])))
    if intent == 'pending_lead_orders' or intent == 'lead_actions':
        rows = fetch_all('''SELECT co.id,w.workshop_name
            FROM customer_orders co JOIN workshops w ON w.id=co.workshop_id
            WHERE co.deleted_at IS NULL AND co.status='pending_lead' AND ''' + WORKSHOP_PRED +
            ' ORDER BY co.id DESC LIMIT 101', (ids,))
        if len(rows) > 100:
            return 'Có hơn 100 công đơn chờ duyệt trong xưởng phụ trách. Hãy lọc theo xưởng hoặc mã CD.'
        if intent == 'pending_lead_orders':
            if not rows:
                return 'Hiện không có công đơn nào đang chờ bạn duyệt trong xưởng phụ trách.'
            lines = [f'Hiện có **{len(rows)} công đơn đang chờ bạn duyệt**:']
            lines.extend(f"• **CD-{int(r['id']):07d}** · {r['workshop_name']}" for r in rows)
            lines.append('Bạn có thể duyệt hoặc từ chối tại màn Tổng quan công đơn.')
            return '\n\n'.join((lines[0], '\n'.join(lines[1:-1]), lines[-1]))
        pending = rows
    else:
        pending = []

    # Công đơn đã gửi yêu cầu hoàn thành: chỉ theo dõi, không gửi lại.
    if intent in ('completion_ready', 'lead_actions'):
        waiting_admin = fetch_all('''SELECT co.id,w.workshop_name
          FROM customer_orders co JOIN workshops w ON w.id=co.workshop_id
          WHERE co.deleted_at IS NULL AND co.status='in_production'
            AND co.completion_requested_at IS NOT NULL AND co.completed_at IS NULL
            AND ''' + WORKSHOP_PRED + '''
          ORDER BY co.id DESC LIMIT 101''', (ids,))
        if len(waiting_admin) > 100:
            return 'Có hơn 100 công đơn chờ Admin hoàn thành. Hãy mở danh sách công đơn để theo dõi.'
    else:
        waiting_admin = []

    if intent == 'completion_ready' or intent == 'lead_actions':
        # Identical eligibility to routes_customer_orders.submit_customer_order_completion:
        # all assigned stations must have recorded the exact planned quantity.
        ready = fetch_all('''SELECT co.id,w.workshop_name
          FROM customer_orders co JOIN workshops w ON w.id=co.workshop_id
          WHERE co.deleted_at IS NULL AND co.status='in_production'
            AND co.completion_requested_at IS NULL AND ''' + WORKSHOP_PRED + '''
            AND EXISTS (SELECT 1 FROM customer_order_machines cm
                WHERE cm.customer_order_id=co.id)
            AND (SELECT COUNT(*) FROM customer_order_stage_progress sp
                WHERE sp.customer_order_id=co.id) =
                (SELECT COUNT(*) FROM customer_order_machines cm
                 WHERE cm.customer_order_id=co.id)
            AND NOT EXISTS (SELECT 1 FROM customer_order_stage_progress sp
                WHERE sp.customer_order_id=co.id AND sp.quantity_completed<>co.quantity)
          ORDER BY co.id DESC LIMIT 101''', (ids,))
        if len(ready) > 100:
            return 'Có hơn 100 công đơn đủ điều kiện gửi hoàn thành. Hãy lọc theo xưởng hoặc mã CD.'
        if intent == 'completion_ready':
            if not ready:
                if waiting_admin:
                    lines = ['Hiện không có công đơn nào cần gửi yêu cầu hoàn thành mới.',
                             f'Có **{len(waiting_admin)} công đơn đã gửi và đang chờ Admin xác nhận hoàn thành**:']
                    lines += [f"• **CD-{int(r['id']):07d}** · {r['workshop_name']}" for r in waiting_admin]
                    return '\n\n'.join((lines[0], lines[1], '\n'.join(lines[2:])))
                return 'Hiện chưa có công đơn nào đủ điều kiện để gửi Admin xác nhận hoàn thành.'
            lines = [f'Có **{len(ready)} công đơn** đã đủ sản lượng ở tất cả công trạm và chưa gửi Admin:']
            lines += [f"• **CD-{int(r['id']):07d}** · {r['workshop_name']}" for r in ready]
            lines += ['Bạn có thể gửi yêu cầu hoàn thành trên màn Tổng quan công đơn.']
            return '\n\n'.join((lines[0], '\n'.join(lines[1:-1]), lines[-1]))
        # Other information for a comprehensive action list below.
    else:
        ready = []

    if intent == 'submitted_reports' or intent == 'lead_actions':
        reports = fetch_all('''SELECT t.id,t.title,m.machine_code
            FROM tasks t JOIN machines m ON m.id=t.machine_id
            WHERE t.status='submitted' AND m.workshop_id IN
              (SELECT DISTINCT workshop_id FROM machines WHERE id=ANY(%s::integer[]))
            ORDER BY t.id DESC LIMIT 101''', (ids,))
        if len(reports) > 100:
            return 'Có hơn 100 báo cáo đang chờ duyệt. Hãy vào Công việc giao ngay để xem đầy đủ.'
        if intent == 'submitted_reports':
            if not reports:
                return 'Hiện không có báo cáo công việc nào đang chờ bạn duyệt.'
            lines = [f'Có **{len(reports)} công việc đã nộp báo cáo** đang chờ bạn duyệt:']
            lines += [f"• Công việc #{r['id']} · {r['title']} · Máy {r['machine_code']}" for r in reports]
            lines += ['Bạn có thể duyệt hoặc trả lại báo cáo ở mục Công việc giao ngay.']
            return '\n\n'.join((lines[0], '\n'.join(lines[1:-1]), lines[-1]))
    else:
        reports = []

    if intent == 'lead_actions':
        total = len(pending) + len(ready) + len(reports)
        result = ([f'Hiện có **{total} mục bạn cần xử lý** trong xưởng phụ trách:']
                  if total else ['Hiện không có công đơn hoặc báo cáo nào cần bạn xử lý ngay.'])
        if total:
            result.extend((f'• **{len(pending)}** công đơn chờ bạn duyệt hoặc từ chối',
                           f'• **{len(ready)}** công đơn đủ điều kiện gửi yêu cầu hoàn thành',
                           f'• **{len(reports)}** báo cáo công việc chờ duyệt'))
        if waiting_admin:
            result.append(f'**Đang chờ Admin xác nhận hoàn thành: {len(waiting_admin)} công đơn**')
            result += [f"• **CD-{int(r['id']):07d}** · {r['workshop_name']}" for r in waiting_admin]
            result.append('Các công đơn này đã gửi yêu cầu, bạn không cần gửi lại.')
        return '\n\n'.join((result[0], '\n'.join(result[1:])))

    if intent in ('tasks_unfinished', 'tasks_approved', 'tasks_returned'):
        if intent == 'tasks_unfinished':
            status_sql = "t.status NOT IN ('approved')"
            label = 'chưa được duyệt hoàn thành'
        elif intent == 'tasks_approved':
            status_sql = "t.status='approved'"
            label = 'đã duyệt'
        else:
            status_sql = "t.status='returned'"
            label = 'bị trả lại'
        rows = fetch_all('''SELECT t.id,t.title,t.status,m.machine_code
            FROM tasks t JOIN machines m ON m.id=t.machine_id
            WHERE ''' + status_sql + ''' AND m.workshop_id IN
              (SELECT DISTINCT workshop_id FROM machines WHERE id=ANY(%s::integer[]))
            ORDER BY t.id DESC LIMIT 101''', (ids,))
        if len(rows)>100:
            return 'Có hơn 100 công việc phù hợp; vui lòng xem thêm tại Công việc giao ngay.'
        if not rows:
            return f'Hiện không có công việc nào {label} trong xưởng bạn phụ trách.'
        lines = [f'Có **{len(rows)} công việc {label}** trong xưởng bạn phụ trách:']
        lines += [f"• Công việc #{r['id']} · {r['title']} · {STATUS.get(r['status'],r['status'])} · Máy {r['machine_code']}" for r in rows]
        return '\n\n'.join((lines[0], '\n'.join(lines[1:])))

    if intent == 'lead_tasks':
        rows = fetch_all('''SELECT t.status,COUNT(*)::integer AS total
           FROM tasks t JOIN machines m ON m.id=t.machine_id
           WHERE m.workshop_id IN
               (SELECT DISTINCT workshop_id FROM machines WHERE id=ANY(%s::integer[]))
           GROUP BY t.status ORDER BY t.status''', (ids,))
        if not rows:
            return 'Chưa có công việc nào trong xưởng bạn phụ trách.'
        total = sum(int(r['total']) for r in rows)
        details = '\n'.join(f"• {STATUS.get(r['status'],r['status'])}: **{r['total']}**" for r in rows)
        return f'Xưởng bạn phụ trách hiện có **{total} công việc**.\n\n{details}'

    if intent in ('machines_not_running', 'machines_running',
                  'machines_fault', 'machines_maintenance', 'machines_stopped'):
        status_predicates = {
            'machines_running': "lower(m.status)='running'",
            'machines_not_running': "coalesce(lower(m.status),'')<>'running'",
            'machines_fault': "lower(coalesce(m.status,'')) SIMILAR TO '%(error|fault|lỗi|loi|broken)%'",
            'machines_maintenance': "lower(coalesce(m.status,'')) SIMILAR TO '%(maintenance|bảo trì|bao tri|service)%'",
            'machines_stopped': "lower(coalesce(m.status,'')) SIMILAR TO '%(stopped|stop|idle|dừng|dung)%'",
        }
        labels = {
            'machines_running': 'đang hoạt động', 'machines_not_running': 'không ở trạng thái hoạt động',
            'machines_fault': 'đang báo lỗi', 'machines_maintenance': 'đang bảo trì',
            'machines_stopped': 'đang dừng',
        }
        rows = fetch_all('''SELECT m.machine_code,m.status,w.workshop_name
          FROM machines m JOIN workshops w ON w.id=m.workshop_id
          WHERE m.workshop_id IN
            (SELECT DISTINCT workshop_id FROM machines WHERE id=ANY(%s::integer[]))
          AND ''' + status_predicates[intent] +
          ' ORDER BY m.machine_code LIMIT 101', (ids,))
        label = labels[intent]
        if not rows:
            return f'Hiện không có máy nào {label} trong xưởng bạn phụ trách.'
        if len(rows)>100:
            return f'Có hơn 100 máy {label}; hãy xem danh sách máy của xưởng.'
        lines = [f'Có **{len(rows)} máy {label}** trong xưởng bạn phụ trách:']
        lines += [f"• {r['machine_code']} · {r['status'] or 'Chưa xác định'} · {r['workshop_name']}" for r in rows]
        return '\n\n'.join((lines[0], '\n'.join(lines[1:])))

    if intent == 'lead_machines':
        machines = fetch_all('''SELECT m.machine_code,m.status,w.workshop_name
          FROM machines m JOIN workshops w ON w.id=m.workshop_id
          WHERE m.workshop_id IN
            (SELECT DISTINCT workshop_id FROM machines WHERE id=ANY(%s::integer[]))
          ORDER BY w.workshop_name,m.machine_code LIMIT 101''', (ids,))
        if len(machines) > 100:
            return 'Xưởng phụ trách có hơn 100 máy. Hãy lọc theo xưởng hoặc trạng thái.'
        if not machines:
            return 'Chưa có máy nào trong phạm vi xưởng bạn phụ trách.'
        lines = [f'Xưởng bạn phụ trách có **{len(machines)} máy**:']
        lines += [f"• {r['machine_code']} · {r['status']} · {r['workshop_name']}" for r in machines]
        return '\n\n'.join((lines[0], '\n'.join(lines[1:])))

    if intent == 'lead_workshops':
        rows = fetch_all('''SELECT w.workshop_name,co.status,COUNT(DISTINCT co.id)::integer AS total
          FROM workshops w JOIN machines m ON m.workshop_id=w.id
          LEFT JOIN customer_orders co ON co.workshop_id=w.id AND co.deleted_at IS NULL
          WHERE m.id=ANY(%s::integer[])
          GROUP BY w.id,w.workshop_name,co.status ORDER BY w.workshop_name,co.status''', (ids,))
        if not rows:
            return 'Chưa có công đơn nào trong xưởng bạn phụ trách.'
        groups = {}
        for r in rows:
            group = groups.setdefault(r['workshop_name'], {})
            if r['status']:
                group[r['status']] = int(r['total'])
        total = sum(sum(d.values()) for d in groups.values())
        result = [f'Bạn đang theo dõi **{len(groups)} xưởng**, với **{total} công đơn**:']
        for name, statuses in groups.items():
            detail = ', '.join(f'{STATUS.get(k,k)} {v}' for k,v in statuses.items()) or 'chưa có công đơn'
            result.append(f'• **{name}**: {sum(statuses.values())} công đơn · {detail}')
        # Hiển thị mã CD thật để Tổ trưởng có thể mở đúng công đơn.
        orders = fetch_all('''SELECT co.id,co.status,co.completion_requested_at,w.workshop_name
            FROM customer_orders co JOIN workshops w ON w.id=co.workshop_id
            WHERE co.deleted_at IS NULL AND ''' + WORKSHOP_PRED +
            ' ORDER BY co.id DESC LIMIT 51', (ids,))
        if orders:
            result.append('**Danh sách công đơn**')
            for r in orders[:50]:
                current_status = STATUS.get(r['status'], r['status'])
                if r['status'] == 'in_production' and r.get('completion_requested_at'):
                    current_status = 'Đang sản xuất · Chờ Admin hoàn thành'
                result.append(f"• CD-{int(r['id']):07d} · {current_status} · {r['workshop_name']}")
            if len(orders) > 50:
                result.append('Danh sách còn nhiều công đơn; hãy lọc theo trạng thái để xem tiếp.')
        return '\n\n'.join((result[0], '\n'.join(result[1:])))
    return ''
