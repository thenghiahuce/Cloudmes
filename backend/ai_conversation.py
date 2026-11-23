# coding: utf-8
"""Deterministic, role-specific conversational intents for MES AI.

Only handle non-data utterances here. Business facts must come from authenticated,
permission-scoped backend tools; never infer roles from message text.
"""
import re
import unicodedata

ROLE_NAMES = {
    'admin': 'Quản trị viên', 'team_lead': 'Tổ trưởng',
    'technician': 'Kỹ thuật viên', 'customer': 'Khách hàng',
}

CAPABILITIES = {
    'admin': [
        'Tổng hợp công đơn CD, trạng thái, tiến độ và công đơn cần xác nhận hoàn thành.',
        'Tra cứu máy, xưởng, tình hình sản xuất và các báo cáo thuộc phạm vi quản trị.',
        'Tra cứu công việc, nhân sự và báo cáo qua công cụ được cấp quyền.',
    ],
    'team_lead': [
        'Theo dõi công đơn CD và tiến độ trong các xưởng được phân quyền.',
        'Tra cứu máy, công trạm, công việc và báo cáo của xưởng phụ trách.',
        'Kiểm tra các công đơn chờ xác nhận hoàn thành theo phạm vi xưởng.',
    ],
    'technician': [
        'Tra cứu máy được phân công và công việc của chính bạn.',
        'Kiểm tra công việc chưa hoàn thành, số lượt báo cáo đã nộp.',
        'Theo dõi tiến độ công đơn CD có máy bạn tham gia khi được phép.',
    ],
    'customer': [
        'Tra cứu công đơn CD do bạn tạo thuộc công ty của bạn.',
        'Xem trạng thái, tiến độ và ngày dự kiến của công đơn.',
        'Tổng hợp số công đơn và sản lượng đặt hàng thuộc tài khoản.',
    ],
}
EXAMPLES = {
    'admin': ('Phân tích toàn bộ công đơn', 'Công đơn nào đang sản xuất?', 'Công đơn nào đang chờ hoàn thành?'),
    'team_lead': ('Xưởng của tôi có những công đơn nào?', 'Máy nào đang sản xuất?', 'Công đơn nào chờ hoàn thành?'),
    'technician': ('Tôi được phân công máy nào?', 'Công việc chưa hoàn thành của tôi?', 'Tôi đã nộp bao nhiêu báo cáo?'),
    'customer': ('Tôi có bao nhiêu công đơn?', 'Tiến độ CD-0000017 thế nào?', 'Đơn nào đang sản xuất?'),
}


def _normalize(question):
    text = unicodedata.normalize('NFKD', str(question or '').casefold())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace('đ', 'd')
    text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()


def conversational_answer(question, role):
    """Return a scoped response for purely conversational intents, else None.

    No database is queried, so replies must not state actual counts or statuses.
    """
    if role not in CAPABILITIES:
        return None
    text = _normalize(question)
    if not text:
        return None
    greetings = {
        'alo', 'a lo', 'alo ban', 'alo ai', 'alo tro ly', 'alo mes', 'aloo',
        'hello', 'helo', 'helloo', 'hi', 'hey', 'xin chao', 'chao',
        'chao ban', 'chao ai', 'chao tro ly', 'good morning', 'good afternoon',
        'good evening', 'co ai khong', 'co ai o day khong', 'ban oi', 'ai oi',
    }
    helps = {
        'help', 'tro giup', 'giup toi', 'huong dan', 'toi co the hoi gi',
        'toi hoi duoc gi', 'ban lam duoc gi', 'ban co the lam gi',
        'ai lam duoc gi', 'chuc nang cua ban', 'gioi thieu', 'ban la ai',
        'ban la gi', 'help me', 'what can you do', 'who are you',
    }
    thanks = {
        'cam on', 'cam on ban', 'thanks', 'thank you', 'thank',
        'ok cam on', 'oke cam on', 'thank u', 'cam on ai',
    }
    if text in greetings:
        return (f'Xin chào! Tôi là **trợ lý AI MES** dành cho **{ROLE_NAMES[role]}**. '
                'Tôi có thể hỗ trợ tra cứu và phân tích dữ liệu sản xuất theo quyền của tài khoản. '
                f'Bạn có thể hỏi: **{EXAMPLES[role][0]}**. '
                'Gõ **trợ giúp** để xem thêm câu hỏi gợi ý.')
    if text in helps:
        lines = [f'**Trợ lý MES · {ROLE_NAMES[role]}**', '',
                 'Tôi hỗ trợ **tra cứu và phân tích dữ liệu chỉ đọc** theo phạm vi tài khoản:', '']
        lines.extend(f'- {item}' for item in CAPABILITIES[role])
        lines.extend(['', '**Ví dụ câu hỏi:**', ''])
        lines.extend(f'- {item}' for item in EXAMPLES[role])
        lines.extend(['', 'Tôi không thể tạo, sửa, xóa hay phê duyệt dữ liệu trực tiếp trong chat. '
                           'Nếu Database không có dữ liệu phù hợp, tôi sẽ thông báo thay vì đưa số liệu giả.'])
        return '\n'.join(lines)
    if text in thanks:
        return 'Rất vui vì đã hỗ trợ được bạn. Khi cần, bạn có thể hỏi về dữ liệu MES trong phạm vi tài khoản hoặc gõ **trợ giúp**.'
    return None
