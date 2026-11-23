# coding: utf-8
"""Read-only, authenticated Admin intent handlers for MES.

Use only from the verified Admin branch of the chat endpoint. All quantities
come from PostgreSQL; this module never executes user-supplied SQL.
"""
import re
from backend.ai_conversation import _normalize


def detect_admin_intent(question: str) -> str | None:
    q = _normalize(question)
    if not q:
        return None
    # Hành động quản trị trên CÔNG ĐƠN CD, không phải task được giao.
    # Đặt trước các intent công việc/máy để tránh nhầm "việc cần xử lý" thành tasks.
    order_context = any(t in q for t in ('cong don', 'don hang', 'don san xuat', 'cd-'))
    admin_action_context = any(t in q for t in (
        'admin', 'quan tri', 'toi can xu ly', 'toi phai lam gi',
        'viec can xu ly', 'can toi xu ly', 'cho toi xu ly', 'cong viec gi can xu ly',
        'can toi duyet', 'cho toi duyet', 'cho admin duyet',
        'cho hoan thanh', 'xac nhan hoan thanh'))
    if order_context and any(t in q for t in (
        'cho hoan thanh', 'xac nhan hoan thanh', 'cho admin hoan thanh',
        'cho toi hoan thanh', 'da gui hoan thanh')):
        return 'admin_orders_completion'
    if order_context and any(t in q for t in (
        'cho duyet', 'cho phe duyet', 'cho admin duyet',
        'cho toi duyet', 'can duyet', 'duyet hoac tu choi')):
        return 'admin_orders_approval'
    if (admin_action_context and any(t in q for t in (
        'toi can xu ly', 'toi phai lam gi', 'viec can xu ly', 'cong viec gi can xu ly',
        'can toi xu ly', 'cho toi xu ly', 'admin can xu ly',
        'can toi duyet', 'cho toi duyet', 'cho admin duyet',
        'cho hoan thanh', 'xac nhan hoan thanh')) and
            (order_context or 'toi can xu ly' in q or 'toi phai lam gi' in q
             or 'viec can xu ly' in q or 'cong viec gi can xu ly' in q or 'admin can xu ly' in q)):
        return 'admin_order_actions'
    # Specific intents take precedence over generic counts. This prevents
    # "deleted accounts" from being answered with the active account total.
    if ('tai khoan' in q or 'nguoi dung' in q) and any(t in q for t in (
        'da xoa', 'bi xoa', 'vo hieu hoa', 'khong hoat dong', 'bi khoa', 'ngung hoat dong')):
        return 'inactive_accounts'
    if ('cong don' in q or 'don hang' in q) and 'tu choi' in q and 'xuong' in q:
        return 'rejected_orders_by_workshop'
    if ('cong don' in q or 'don hang' in q) and 'dang san xuat' in q and 'xuong' in q and any(t in q for t in (
        'so sanh', 'tung xuong', 'giua', 'phan bo', 'bao nhieu')):
        return 'production_by_workshop'
    if ('cong viec' in q or 'task' in q or 'viec duoc giao' in q) and any(t in q for t in (
        'chua hoan thanh', 'chua xong', 'dang lam', 'chua duyet', 'chua duoc duyet')):
        return 'unfinished_tasks'
    if ('may' in q or 'thiet bi' in q) and any(t in q for t in (
        'dung', 'loi', 'bao tri', 'ngung', 'khong chay', 'khong hoat dong')):
        return 'nonrunning_machines'
    if ('bao cao' in q or 'report' in q) and any(t in q for t in (
        'da nop', 'da gui', 'cua toi', 'toi nop', 'minh nop')):
        return 'my_reports'
    if ('xuong cua toi' in q or 'cac xuong cua toi' in q or 'xuong toi' in q or
        ('cac xuong' in q and any(w in q for w in ('cong don', 'don hang', 'tinh hinh')))):
        return 'my_workshops'
    if ('cong viec' in q or 'giao viec' in q or 'task' in q) and any(x in q for x in (
        'bao nhieu', 'thong ke', 'tong quan', 'tinh hinh', 'theo trang thai', 'da giao')):
        return 'tasks_overview'
    if any(x in q for x in ('may', 'thiet bi')) and any(x in q for x in (
        'bao nhieu', 'thong ke', 'tong quan', 'tinh hinh', 'theo trang thai')):
        return 'machines_overview'
    if any(x in q for x in ('nhan su', 'tai khoan', 'nhan vien')) and any(x in q for x in (
        'bao nhieu', 'thong ke', 'tong quan', 'theo vai tro')):
        return 'users_overview'
    return None


def split_numbered_questions(text: str) -> list[str]:
    """Only split a clearly numbered multi-question message, never an order CD code."""
    text = str(text or '')
    boundaries = list(re.finditer(r'(?<!\w)([1-9])\s*[.)]\s+(?=[A-Za-zÀ-ỹ])', text))
    if len(boundaries) < 2 or boundaries[0].start() > 5:
        return []
    questions = []
    for i, match in enumerate(boundaries):
        end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
        item = text[match.end():end].strip().strip(' ;\n\t')
        if item:
            questions.append(item)
    return questions if len(questions) >= 2 else []


def _scalar(fetch_all, sql, params=()):
    rows = fetch_all(sql, params)
    return int(rows[0]['total'] or 0) if rows else 0


def admin_answer(intent: str, username: str, fetch_all) -> str:
    """Only invoke after verifying the current request is authenticated Admin."""
    if intent in ('admin_order_actions', 'admin_orders_approval', 'admin_orders_completion'):
        # Một công đơn chờ duyệt lúc khởi đầu khác với một công đơn đang
        # chờ Admin nhấn Hoàn thành sau khi tổ trưởng nộp yêu cầu.
        where_approval = "co.deleted_at IS NULL AND co.status='pending_admin'"
        where_completion = """co.deleted_at IS NULL AND co.status='in_production'
            AND co.completion_requested_at IS NOT NULL AND co.completed_at IS NULL
            AND (co.completion_returned_at IS NULL
                 OR co.completion_requested_at > co.completion_returned_at)"""
        def get_orders(where):
            count = _scalar(fetch_all,
                'SELECT COUNT(*)::integer AS total FROM customer_orders co WHERE '+where)
            rows = fetch_all('SELECT co.id, w.workshop_name FROM customer_orders co '
                'LEFT JOIN workshops w ON w.id=co.workshop_id WHERE '+where+' ORDER BY co.id DESC LIMIT 50', ())
            return count, rows
        approvals, approval_rows = (0, [])
        completions, completion_rows = (0, [])
        if intent != 'admin_orders_completion':
            approvals, approval_rows = get_orders(where_approval)
        if intent != 'admin_orders_approval':
            completions, completion_rows = get_orders(where_completion)
        if intent == 'admin_orders_approval':
            lines = ([f'Có **{approvals} công đơn đang chờ bạn duyệt hoặc từ chối**.']
                     if approvals else ['Hiện không có công đơn nào đang chờ bạn duyệt.'])
        elif intent == 'admin_orders_completion':
            lines = ([f'Có **{completions} công đơn đang chờ bạn xác nhận hoàn thành**.']
                     if completions else ['Hiện chưa có công đơn nào đang chờ bạn xác nhận hoàn thành.'])
        else:
            lines = [f'Hiện có **{approvals + completions} công đơn cần bạn xử lý**:',
                     f'• Chờ duyệt hoặc từ chối: **{approvals}** công đơn.',
                     f'• Chờ xác nhận hoàn thành: **{completions}** công đơn.']
        def append_orders(label, rows, total):
            if not total:
                return
            lines.extend(['', f'**{label}**'])
            for row in rows:
                lines.append(f"• CD-{int(row['id']):07d} · {row['workshop_name'] or 'Chưa xác định xưởng'}")
            if total > len(rows):
                lines.append(f'Đang hiển thị {len(rows)}/{total} công đơn đầu tiên.')
        if intent != 'admin_orders_completion':
            append_orders('Cần duyệt hoặc từ chối', approval_rows, approvals)
        if intent != 'admin_orders_approval':
            append_orders('Cần xác nhận hoàn thành', completion_rows, completions)
        if approvals or completions:
            lines.extend(['', 'Bạn có thể vào **Tổng quan công đơn** để thực hiện thao tác tương ứng.'])
        return '\n'.join(lines)

    if intent in ('admin_order_actions', 'admin_orders_approval', 'admin_orders_completion'):
        # Một công đơn chờ duyệt lúc khởi đầu khác với một công đơn đang
        # chờ Admin nhấn Hoàn thành sau khi tổ trưởng nộp yêu cầu.
        where_approval = "co.deleted_at IS NULL AND co.status='pending_admin'"
        where_completion = """co.deleted_at IS NULL AND co.status='in_production'
            AND co.completion_requested_at IS NOT NULL AND co.completed_at IS NULL
            AND (co.completion_returned_at IS NULL
                 OR co.completion_requested_at > co.completion_returned_at)"""
        def get_orders(where):
            count = _scalar(fetch_all,
                'SELECT COUNT(*)::integer AS total FROM customer_orders co WHERE '+where)
            rows = fetch_all('SELECT co.id, w.workshop_name FROM customer_orders co '
                'LEFT JOIN workshops w ON w.id=co.workshop_id WHERE '+where+' ORDER BY co.id DESC LIMIT 50', ())
            return count, rows
        approvals, approval_rows = (0, [])
        completions, completion_rows = (0, [])
        if intent != 'admin_orders_completion':
            approvals, approval_rows = get_orders(where_approval)
        if intent != 'admin_orders_approval':
            completions, completion_rows = get_orders(where_completion)
        if intent == 'admin_orders_approval':
            lines = ([f'Có **{approvals} công đơn đang chờ bạn duyệt hoặc từ chối**.']
                     if approvals else ['Hiện không có công đơn nào đang chờ bạn duyệt.'])
        elif intent == 'admin_orders_completion':
            lines = ([f'Có **{completions} công đơn đang chờ bạn xác nhận hoàn thành**.']
                     if completions else ['Hiện chưa có công đơn nào đang chờ bạn xác nhận hoàn thành.'])
        else:
            lines = [f'Hiện có **{approvals + completions} công đơn cần bạn xử lý**:',
                     f'• Chờ duyệt hoặc từ chối: **{approvals}** công đơn.',
                     f'• Chờ xác nhận hoàn thành: **{completions}** công đơn.']
        def append_orders(label, rows, total):
            if not total:
                return
            lines.extend(['', f'**{label}**'])
            for row in rows:
                lines.append(f"• CD-{int(row['id']):07d} · {row['workshop_name'] or 'Chưa xác định xưởng'}")
            if total > len(rows):
                lines.append(f'Đang hiển thị {len(rows)}/{total} công đơn đầu tiên.')
        if intent != 'admin_orders_completion':
            append_orders('Cần duyệt hoặc từ chối', approval_rows, approvals)
        if intent != 'admin_orders_approval':
            append_orders('Cần xác nhận hoàn thành', completion_rows, completions)
        if approvals or completions:
            lines.extend(['', 'Bạn có thể vào **Tổng quan công đơn** để thực hiện thao tác tương ứng.'])
        return '\n'.join(lines)

    if intent == 'my_reports':
        users = fetch_all('SELECT id FROM app_users WHERE lower(username)=lower(%s) AND role=%s',
                          (username, 'admin'))
        if not users:
            return 'Không xác định được tài khoản Admin để thống kê báo cáo cá nhân.'
        total = _scalar(fetch_all,
                        'SELECT COUNT(*)::integer AS total FROM task_reports WHERE author_id=%s',
                        (users[0]['id'],))
        return (f'Bạn đã nộp **{total} báo cáo công việc**.' if total else
                'Bạn chưa nộp báo cáo công việc nào bằng tài khoản này.')

    if intent == 'my_workshops':
        rows = fetch_all('''
            SELECT w.workshop_name, COUNT(co.id)::integer AS total,
                   COUNT(co.id) FILTER (WHERE co.status='in_production')::integer AS in_production,
                   COUNT(co.id) FILTER (WHERE co.status='completed')::integer AS completed,
                   COUNT(co.id) FILTER (WHERE co.status='pending_lead')::integer AS pending_lead,
                   COUNT(co.id) FILTER (WHERE co.status='pending_admin')::integer AS pending_admin,
                   COUNT(co.id) FILTER (WHERE co.status='rejected')::integer AS rejected
            FROM workshops w
            LEFT JOIN customer_orders co ON co.workshop_id=w.id AND co.deleted_at IS NULL
            GROUP BY w.id, w.workshop_name ORDER BY w.workshop_name
        ''', ())
        if not rows:
            return 'Chưa có dữ liệu xưởng trong hệ thống.'
        total = sum(int(r['total'] or 0) for r in rows)
        lines = [f'Bạn đang quản lý **{len(rows)} xưởng**, với tổng cộng **{total} công đơn**. Cụ thể:', '']
        for r in rows:
            parts = [f"**{r['workshop_name']}**: {r['total']} công đơn"]
            for key, label in [('in_production', 'Đang sản xuất'), ('completed', 'Đã hoàn thành'),
                               ('pending_lead', 'Chờ tiếp nhận'), ('pending_admin', 'Chờ được duyệt'),
                               ('rejected', 'Từ chối')]:
                if r[key]:
                    parts.append(f"{label} {r[key]}")
            lines.append('• ' + ' · '.join(parts))
        return '\n'.join(lines)

    if intent == 'rejected_orders_by_workshop':
        rows = fetch_all('''
            SELECT w.workshop_name, co.id, co.quantity
            FROM customer_orders co JOIN workshops w ON w.id=co.workshop_id
            WHERE co.deleted_at IS NULL AND co.status='rejected'
            ORDER BY w.workshop_name, co.id DESC
        ''', ())
        if not rows:
            return 'Hiện không có công đơn bị từ chối trong hệ thống.'
        groups = {}
        for r in rows:
            groups.setdefault(r['workshop_name'], []).append(r)
        lines = [f'Hiện có **{len(rows)} công đơn bị từ chối**. Mình đã nhóm theo từng xưởng để bạn dễ theo dõi:', '']
        for workshop, items in groups.items():
            lines.append(f'**{workshop}** ({len(items)})')
            for r in items:
                lines.append(f"• CD-{int(r['id']):07d} · {int(r['quantity'] or 0):,} sản phẩm".replace(',', '.'))
        return '\n'.join(lines)

    if intent == 'production_by_workshop':
        rows = fetch_all('''
            SELECT w.workshop_name,
                   COUNT(co.id) FILTER (WHERE co.status='in_production')::integer AS total
            FROM workshops w LEFT JOIN customer_orders co
              ON co.workshop_id=w.id AND co.deleted_at IS NULL
            GROUP BY w.id, w.workshop_name ORDER BY total DESC,w.workshop_name
        ''', ())
        total = sum(int(r['total'] or 0) for r in rows)
        if not total:
            return 'Hiện chưa có công đơn nào đang sản xuất tại các xưởng.'
        lines = [f'Hiện có **{total} công đơn đang sản xuất** tại {len(rows)} xưởng. Phân bổ như sau:', '']
        lines += [f"• **{r['workshop_name']}**: {r['total']} công đơn" for r in rows]
        ranked = [r for r in rows if int(r['total'] or 0) > 0]
        if ranked:
            maximum = max(int(r['total'] or 0) for r in ranked)
            leaders = [r['workshop_name'] for r in ranked if int(r['total'] or 0) == maximum]
            if len(leaders) == 1:
                lines.extend(['', f'**{leaders[0]}** hiện có nhiều công đơn đang sản xuất nhất ({maximum} công đơn).'])
            else:
                lines.extend(['', f'Có {len(leaders)} xưởng cùng dẫn đầu với **{maximum} công đơn** mỗi xưởng.'])
        return '\n'.join(lines)

    if intent == 'unfinished_tasks':
        rows = fetch_all('''
            SELECT t.id,t.title,t.status,m.machine_code
            FROM tasks t JOIN machines m ON m.id=t.machine_id
            WHERE t.status <> 'approved'
            ORDER BY t.due_at ASC, t.id ASC LIMIT 50
        ''', ())
        total = _scalar(fetch_all, "SELECT COUNT(*)::integer AS total FROM tasks WHERE status <> 'approved'")
        if not total:
            return 'Hiện không có công việc nào đang chờ hoàn thành hoặc chờ duyệt.'
        names = {'assigned':'Đã giao', 'in_progress':'Đang thực hiện',
                 'submitted':'Đã nộp báo cáo', 'returned':'Bị trả lại'}
        lines = [f'Hiện còn **{total} công việc chưa hoàn thành**. Đây là danh sách công việc cần theo dõi:', '']
        for r in rows:
            lines.append(f"• Việc #{r['id']} · {r['title']} · {r['machine_code']} · "
                         f"{names.get(r['status'],r['status'])}")
        if total > len(rows):
            lines.append(f'Đang hiển thị {len(rows)}/{total} công việc đầu tiên.')
        return '\n'.join(lines)

    if intent == 'nonrunning_machines':
        rows = fetch_all('''
            SELECT status, COUNT(*)::integer AS total FROM machines
            WHERE status IS NULL OR LOWER(TRIM(status)) <> 'running'
            GROUP BY status ORDER BY status
        ''', ())
        total = sum(int(r['total'] or 0) for r in rows)
        if not total:
            return 'Hiện tất cả máy đều được ghi nhận là đang hoạt động. Chưa có máy nào được đánh dấu dừng, lỗi hoặc bảo trì.'
        lines = [f'Hiện có **{total} máy không ở trạng thái hoạt động**. Chi tiết:', '']
        lines += [f"• {r['status'] or 'Chưa xác định trạng thái'}: {r['total']} máy" for r in rows]
        lines.extend(['', 'Lưu ý: Máy không hoạt động chưa chắc đã bị lỗi; có thể đang tạm dừng hoặc bảo trì.'])
        return '\n'.join(lines)

    if intent == 'inactive_accounts':
        inactive = _scalar(fetch_all, 'SELECT COUNT(*)::integer AS total FROM app_users WHERE is_active=FALSE')
        return (f'Hiện có **{inactive} tài khoản không còn hoạt động**. '
                'Số liệu này chưa phân biệt riêng tài khoản đã xóa và tài khoản bị vô hiệu hóa.')

    if intent == 'tasks_overview':
        rows = fetch_all('SELECT status, COUNT(*)::integer AS total FROM tasks GROUP BY status ORDER BY status', ())
        total = sum(int(r['total'] or 0) for r in rows)
        names = {'assigned':'Đã giao', 'in_progress':'Đang thực hiện',
                 'submitted':'Đã nộp báo cáo','approved':'Đã duyệt','returned':'Bị trả lại'}
        lines = [f'Hiện hệ thống có **{total} công việc**. Thống kê theo trạng thái:']
        lines.extend(f"• {names.get(r['status'],r['status'])}: **{r['total']}**" for r in rows)
        return '\n'.join(lines)

    if intent == 'machines_overview':
        rows = fetch_all('SELECT status, COUNT(*)::integer AS total FROM machines GROUP BY status ORDER BY status', ())
        total = sum(int(r['total'] or 0) for r in rows)
        lines = [f'Hiện có **{total} máy** trong hệ thống. Tình trạng ghi nhận như sau:']
        lines.extend(f"• {r['status'] or 'Chưa xác định'}: **{r['total']}**" for r in rows)
        return '\n'.join(lines)

    if intent == 'users_overview':
        rows = fetch_all('''SELECT role, COUNT(*)::integer AS total
                            FROM app_users WHERE is_active=TRUE
                            GROUP BY role ORDER BY role''', ())
        total = sum(int(r['total'] or 0) for r in rows)
        labels = {'admin':'Admin','team_lead':'Tổ trưởng','technician':'Kỹ thuật viên','customer':'Khách hàng'}
        lines = [f'Hiện có **{total} tài khoản đang hoạt động**. Phân bổ theo vai trò:']
        lines.extend(f"• {labels.get(r['role'],r['role'])}: **{r['total']}**" for r in rows)
        return '\n'.join(lines)
    raise ValueError('Unsupported admin intent')
