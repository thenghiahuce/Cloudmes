"""Read-only, role-scoped MES analysis reports.

Formatting contains no database or LLM calls. Callers must supply rows already
filtered by authenticated permissions (never trust a role in chat text).
"""
import re
from collections import Counter

ANALYSIS_WORDS = ('phân tích', 'phan tich', 'đánh giá', 'danh gia',
                  'báo cáo tổng hợp', 'bao cao tong hop', 'tình hình', 'tinh hinh')
LABELS = {
    'pending_lead': 'Chờ tiếp nhận', 'pending_admin': 'Chờ được duyệt',
    'in_production': 'Đang sản xuất', 'completed': 'Đã hoàn thành',
    'rejected': 'Từ chối',
}


def wants_analysis(question):
    q = re.sub(r'\s+', ' ', (question or '').casefold())
    return any(k in q for k in ANALYSIS_WORDS)


def fmt_number(number):
    return f'{int(number or 0):,}'.replace(',', '.')


def fmt_percent(number):
    return f'{float(number or 0):.2f}'.rstrip('0').rstrip('.') + '%'


def customer_report(question, orders):
    """Detailed but external-only report; orders MUST be creator/company scoped."""
    q = (question or '').casefold()
    match = re.search(r'\bcd\s*[-–]?\s*0*(\d+)\b', q)
    if match:
        filtered = [o for o in orders if int(o['id']) == int(match.group(1))]
        if not filtered:
            return 'Không tìm thấy công đơn này trong phạm vi tài khoản của bạn.'
    else:
        filtered = list(orders)
        if 'đang sản xuất' in q:
            filtered = [o for o in filtered if o['status']=='in_production']
        elif 'đã hoàn thành' in q:
            filtered = [o for o in filtered if o['status']=='completed']
        elif 'chờ tiếp nhận' in q:
            filtered = [o for o in filtered if o['status'] in ('pending_lead','pending_admin')]
        elif 'bị từ chối' in q or 'đã từ chối' in q:
            filtered = [o for o in filtered if o['status']=='rejected']
    if not filtered:
        return 'Không có công đơn phù hợp trong phạm vi tài khoản để phân tích.'
    counts = Counter(o['status'] for o in filtered)
    total_quantity = sum(int(o.get('quantity') or 0) for o in filtered)
    lines = [
        '**BÁO CÁO CÔNG ĐƠN CỦA BẠN**',
        '',
        '**TỔNG QUAN**',
        f'- Tổng công đơn: **{len(filtered)}**; tổng số lượng đặt: **{fmt_number(total_quantity)} sản phẩm**.',
        '- Trạng thái: ' + '; '.join(f'{LABELS.get(k,k)}: {v}' for k,v in sorted(counts.items())) + '.',
        '',
        '**CHI TIẾT CÔNG ĐƠN**',
    ]
    for o in filtered[:50]:
        lines.append(
            f"- **{o['code']}** – {o.get('product_name') or 'Sản phẩm chưa xác định'}: "
            f"{fmt_number(o.get('quantity'))} sản phẩm; {LABELS.get(o.get('status'),o.get('status'))}; "
            f"tiến độ công đoạn {fmt_percent(o.get('progress_percent'))}."
        )
    if len(filtered)>50:
        lines.append(f'- Chỉ hiển thị chi tiết 50/{len(filtered)} công đơn.')
    lines += ['', '**LƯU Ý**',
              '- Tiến độ là mức hoàn thành công đoạn được ghi nhận, không phải tỷ lệ sản phẩm đã xuất xưởng.',
              '- Không hiển thị PO nội bộ, danh sách máy, nhân sự, QC hoặc downtime.']
    return '\n'.join(lines)


def _plain_cell(value):
    """Keep model data as Markdown text, not a way to inject table cells."""
    return str(value if value is not None else 'Chưa xác định').replace('|', '／').replace('\n', ' ').replace('\r', ' ').strip()


def internal_report(rows, machine_counts=None, label='phạm vi được phân quyền', code=None):
    """Clear mobile-friendly report without tables or escaped Markdown tokens.

    Vanna currently renders raw pipe tables and escaped headings inconsistently.
    Short, readable one-line records avoid display errors in its rich-text widget.
    Inputs must already be filtered by authenticated permissions.
    """
    machine_counts = machine_counts or []
    counts = Counter(o['status'] for o in rows)
    total = sum(int(o.get('quantity') or 0) for o in rows)
    single = len(rows) == 1 and 'CD-' in label
    lines = [
        '**Báo cáo sản xuất MES**',
        f'Phạm vi: {_plain_cell(label)}',
        '',
        '**Tổng quan**',
        f'• Công đơn: **{fmt_number(len(rows))}**',
        f'• Sản lượng kế hoạch: **{fmt_number(total)} sản phẩm**',
    ]
    priority = ('pending_lead', 'pending_admin', 'in_production', 'completed', 'rejected')
    status_parts = [f'{LABELS.get(k,k)}: {counts[k]}' for k in priority if counts.get(k)]
    status_parts += [f'{LABELS.get(k,k)}: {v}' for k, v in sorted(counts.items()) if k not in priority]
    if status_parts:
        lines.extend(['', '**Trạng thái công đơn**', *('• ' + part for part in status_parts)])
    lines.extend(['', '**Chi tiết công đơn**'])
    if not rows:
        lines.append('Không có công đơn phù hợp trong phạm vi truy cập.')
    for o in rows[:50]:
        cd = f"CD-{int(o['id']):07d}"
        status = _plain_cell(LABELS.get(o.get('status'), o.get('status')))
        quantity = fmt_number(o.get('quantity'))
        progress = fmt_percent(o.get('progress_percent'))
        workshop = _plain_cell(o.get('workshop_name') or 'Chưa xác định')
        lines.append(f'• **{cd}** · {status} · {progress} · {quantity} SP')
        if single:
            lines.append(f'  Xưởng: {workshop}')
        else:
            # Keep each order compact but show its workshop unambiguously.
            lines[-1] += f' · {workshop}'
    if len(rows) > 50:
        lines.extend(['', f'Chỉ hiển thị 50/{len(rows)} công đơn. Hãy lọc theo mã CD hoặc xưởng.'])
    lines.extend(['', '**Máy đã gán**' if single else '**Máy đang hoạt động**'])
    if not machine_counts:
        lines.append('Chưa có thông tin máy phù hợp phạm vi báo cáo.')
    for machine in machine_counts[:30]:
        code = _plain_cell(machine.get('machine_code') or 'Chưa xác định')
        status = _plain_cell(machine.get('status') or 'Chưa xác định')
        active = machine.get('active_order_count')
        if not single and active is not None:
            lines.append(f'• {code} · {status} · {int(active)} công đơn đang sản xuất')
        else:
            lines.append(f'• {code} · {status}')
    if len(machine_counts) > 30:
        lines.append(f'Chỉ hiển thị 30/{len(machine_counts)} máy.')
    done = [o for o in rows if o.get('status') == 'in_production'
            and float(o.get('progress_percent') or 0) >= 100]
    if done:
        lines.extend(['', '**Điểm cần chú ý**',
                      f'Có {len(done)} công đơn đạt 100% tiến độ nhưng chưa được Admin xác nhận hoàn thành.'])
    return '\n'.join(lines)
