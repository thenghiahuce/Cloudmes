import os
import re
from typing import Any
 
from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from vanna import Agent
from vanna.core.registry import ToolRegistry
from vanna.core.user import UserResolver, User, RequestContext
from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna.core.tool import Tool, ToolContext, ToolResult
from pydantic import BaseModel, Field
from typing import Type
 
 
from vanna.capabilities.sql_runner.models import RunSqlToolArgs
from vanna.servers.fastapi import VannaFastAPIServer
from vanna.servers.base import ChatStreamChunk
from vanna.components import RichTextComponent
from vanna.servers.base import ChatHandler, ChatRequest
from fastapi import Request
from fastapi.responses import StreamingResponse
 
from knowledge.ai import FactorySystemPromptBuilder
from backend.auth import (
    AuthMiddleware, login_page_html, ROLE_LABELS, COOKIE_NAME, SESSION_SECONDS,
    _DUMMY_HASH, clear_fails, is_locked, make_token, register_fail, verify_password,
    read_token, ROLE_ADMIN, ROLE_TECHNICIAN,
)
from fastapi.responses import HTMLResponse, JSONResponse
from backend.db import fetch_all
from backend.ai_conversation import conversational_answer
from backend.routes_ai_history import router as ai_history_router, record_exchange
from backend.routes_data import router as data_router
from backend.scope import (
    Scope, fetch_all_scoped, list_scope_machines, load_scope,
    scope_from_request, scoped_cursor,
)
 
load_dotenv()
 
required_vars = [
    "OPENAI_API_KEY",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DATABASE",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise RuntimeError("Thiếu biến môi trường: " + ", ".join(missing_vars))
 
 
class SimpleUserResolver(UserResolver):
    """Xác định người đang chat từ cookie đăng nhập (không còn gán cứng admin).

    Không đọc được phiên -> coi như vai trò thấp nhất (kỹ thuật viên)."""

    async def resolve_user(self, request_context: RequestContext) -> User:
        session = None
        try:
            token = None
            get_cookie = getattr(request_context, "get_cookie", None)
            if callable(get_cookie):
                token = get_cookie(COOKIE_NAME)
            if not token:
                cookies = getattr(request_context, "cookies", None) or {}
                token = cookies.get(COOKIE_NAME)
            if token:
                session = read_token(token)
        except Exception:
            session = None

        username = session["username"] if session else "guest"
        role = session["role"] if session else ROLE_TECHNICIAN
        groups = ["users", f"role:{role}"]
        try:
            return User(
                id=username,
                email=f"{username}@factory.local",
                group_memberships=groups,
                metadata={"role": role},
            )
        except TypeError:
            return User(id=username, email=f"{username}@factory.local",
                        group_memberships=groups)


# Bảng chỉ admin mới được hỏi qua chatbot.
ADMIN_ONLY_TABLES = ("employees", "attendance", "machine_assignments")
_MAX_AI_ROWS = 200   # số dòng tối đa đưa lại cho AI
_NO_MACHINE_MSG = (
    "Tài khoản này chưa được phân công máy nào nên chưa có dữ liệu để truy vấn. "
    "Hãy liên hệ quản trị viên để được gán máy."
)

# Chặn cả khi nằm TRONG chuỗi '...': guard bên dưới xóa nội dung chuỗi trước khi kiểm
# tra, nên nếu thiếu lớp này thì query_to_xml('...') có thể chạy SQL tùy ý.
_DANGEROUS_ANYWHERE = re.compile(
    r"query_to_xml\w*|table_to_xml\w*|cursor_to_xml|schema_to_xml\w*|database_to_xml\w*|"
    r"set_config|current_setting|app_scope\w*|session_user|"
    r"\b(?:set|reset)\s+(?:local\s+|session\s+)?(?:role|session)\b|"
    r"\bpg_\w+",
    flags=re.IGNORECASE,
)
_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|"
    r"call|do|execute|merge|vacuum|reindex|comment|lock|set|reset|"
    r"pg_sleep|pg_read\w*|pg_ls\w*|pg_terminate\w*|pg_cancel\w*|"
    r"lo_\w+|dblink\w*|set_config)\b",
    flags=re.IGNORECASE,
)


def _sql_guard(sql: str, role: str | None) -> str | None:
    """Trả về thông báo lỗi nếu SQL không được phép, ngược lại trả về None.

    Đây chỉ là lớp kiểm tra đầu tiên (để có thông báo thân thiện). Lớp chặn thật sự là
    role chỉ-đọc + Row Level Security ở database (xem backend/scope.py).
    """
    text = sql or ""
    if _DANGEROUS_ANYWHERE.search(text):
        return "Câu SQL chứa hàm/lệnh hệ thống không được phép."
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)   # chú thích /* */
    text = re.sub(r"--[^\n]*", " ", text)                        # chú thích --
    text = re.sub(r"'(?:[^']|'')*'", "''", text)                  # nội dung chuỗi
    text = text.strip().rstrip(";").strip()

    if not text:
        return "Câu SQL trống."
    if ";" in text:
        return "Chỉ được chạy một câu SQL mỗi lần."
    if not re.match(r"(select|with)\b", text, flags=re.IGNORECASE):
        return "Chỉ được phép truy vấn đọc dữ liệu (SELECT)."
    if _FORBIDDEN_SQL.search(text):
        return "Câu SQL chứa lệnh không được phép (chỉ được đọc dữ liệu)."
    if role != ROLE_ADMIN:
        for table in ADMIN_ONLY_TABLES:
            if re.search(rf"\b{table}\b", text, flags=re.IGNORECASE):
                return "Bạn không có quyền truy cập dữ liệu nhân viên và chấm công."
    return None
 
 
llm = OpenAILlmService(
    model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
    api_key=os.getenv("OPENAI_API_KEY"),
)
 
 
 
 
class CustomerOrderLookupArgs(BaseModel):
    status: str = Field(default="all", description="all, pending_lead, pending_admin, pending_completion_approval, in_production, completed, rejected")
    order_code: str = Field(default="", description="Mã CD-0000001 (không bắt buộc)")


# Công đơn chờ Admin xác nhận HOÀN THÀNH không có status riêng trong DB.
# Điều kiện này phải được dùng thống nhất với Dashboard (không dựa vào status='pending_admin').
_PENDING_COMPLETION_SQL = """(
    co.status = 'in_production'
    AND co.completion_requested_at IS NOT NULL
    AND co.completed_at IS NULL
    AND (co.completion_returned_at IS NULL
         OR co.completion_requested_at > co.completion_returned_at)
)"""


def _customer_order_where(scope, status: str, order_code: str = ""):
    clauses = ["co.deleted_at IS NULL"]
    params = []
    if status == "pending_completion_approval":
        clauses.append(_PENDING_COMPLETION_SQL)
    elif status != "all":
        clauses.append("co.status=%s")
        params.append(status)
    if order_code:
        clauses.append("co.id=%s")
        params.append(int(order_code[3:]))
    if not scope.all_machines:
        # KTV chỉ được thấy công đơn có CHÍNH máy được giao tham gia.
        if scope.role == "technician":
            clauses.append("EXISTS (SELECT 1 FROM customer_order_machines cm WHERE cm.customer_order_id=co.id AND cm.machine_id=ANY(%s::integer[]))")
        else:
            clauses.append("co.workshop_id IN (SELECT DISTINCT m.workshop_id FROM machines m WHERE m.id=ANY(%s::integer[]))")
        params.append(list(scope.machine_ids))
    return " AND ".join(clauses), tuple(params)


class CustomerOrderLookupTool(Tool[CustomerOrderLookupArgs]):
    """Tra cứu công đơn, đếm chính xác và giới hạn dữ liệu theo vai trò thực."""
    @property
    def name(self) -> str:
        return "lookup_customer_orders"

    @property
    def description(self) -> str:
        return ("Tra cứu/đếm công đơn CD theo trạng thái và mã. "
                "pending_completion_approval là công đơn đang chờ Admin XÁC NHẬN HOÀN THÀNH "
                "(khác pending_admin). Tool trả total_count chính xác trước khi phân trang. "
                "Admin xem toàn bộ, Tổ trưởng theo xưởng, KTV theo máy có tham gia công đơn.")

    @property
    def access_groups(self) -> list[str]:
        return ["users"]

    def get_args_schema(self) -> Type[CustomerOrderLookupArgs]:
        return CustomerOrderLookupArgs

    async def execute(self, context: ToolContext, args: CustomerOrderLookupArgs) -> ToolResult:
        import json
        username = getattr(getattr(context, "user", None), "id", None)
        scope = load_scope(username)
        if scope.role not in ("admin", "team_lead", "technician") or scope.is_empty:
            return ToolResult(success=False, result_for_llm="Tài khoản không có quyền/phạm vi truy vấn công đơn.")
        status = (args.status or "all").strip().lower()
        allowed = {"all", "pending_lead", "pending_admin", "pending_completion_approval", "in_production", "completed", "rejected"}
        if status not in allowed:
            return ToolResult(success=False, result_for_llm="Trạng thái không hợp lệ.")
        code = (args.order_code or "").strip().upper()
        if code and not re.fullmatch(r"CD-\d{7}", code):
            return ToolResult(success=False, result_for_llm="Mã công đơn phải theo dạng CD-0000001.")
        where_sql, params = _customer_order_where(scope, status, code)
        try:
            count_rows = fetch_all("SELECT COUNT(*)::integer AS total FROM customer_orders co WHERE " + where_sql, params)
            total_count = int(count_rows[0]["total"])
            rows = fetch_all("""
                SELECT co.id, 'CD-' || LPAD(co.id::text,7,'0') AS order_code,
                       co.status, co.quantity, co.expected_date,
                       w.workshop_name, p.product_name, cc.company_name
                FROM customer_orders co
                LEFT JOIN workshops w ON w.id=co.workshop_id
                LEFT JOIN products p ON p.id=co.product_id
                LEFT JOIN customer_companies cc ON cc.id=co.company_id
                WHERE """ + where_sql + " ORDER BY co.created_at DESC, co.id DESC LIMIT 100", params)
            return ToolResult(success=True, result_for_llm=json.dumps({
                "status_filter": status, "total_count": total_count,
                "items_returned": len(rows), "limit": 100, "truncated": total_count > len(rows),
                "orders": rows,
                "notice": "Dùng total_count để trả lời hỏi SỐ LƯỢNG; danh sách chỉ gồm tối đa 100 công đơn trong phạm vi tài khoản."
            }, ensure_ascii=False, default=str))
        except Exception as exc:
            return ToolResult(success=False, result_for_llm=f"Không thể truy vấn công đơn: {type(exc).__name__}")


class AdminOperationalArgs(BaseModel):
    topic: str = Field(description="Một trong: stations, lowest_progress, missing_task_reports, submitted_reports, technicians, machine_assignments")
    order_code: str = Field(default="", description="Mã CD-0000001; bắt buộc nếu topic=stations")


class AdminOperationalTool(Tool[AdminOperationalArgs]):
    """Các truy vấn nghiệp vụ đọc-only, tham số hóa, có kiểm tra vai trò thật."""
    @property
    def name(self) -> str:
        return "admin_operations_lookup"

    @property
    def description(self) -> str:
        return ("Admin tra cứu dữ liệu thật: stations=lịch sử công trạm của công đơn CD, "
                "lowest_progress=công đơn đang sản xuất tiến độ thấp nhất theo cùng công thức Dashboard, "
                "missing_task_reports=kỹ thuật viên chưa nộp báo cáo công việc được giao, "
                "submitted_reports=thống kê số báo cáo công việc đã nộp, "
                "technicians=danh sách kỹ thuật viên, machine_assignments=phân công kỹ thuật viên/máy. "
                "BẮT BUỘC dùng công cụ này cho bốn loại câu hỏi, không đoán tên bảng SQL.")

    @property
    def access_groups(self) -> list[str]:
        return ["users"]

    def get_args_schema(self) -> Type[AdminOperationalArgs]:
        return AdminOperationalArgs

    async def execute(self, context: ToolContext, args: AdminOperationalArgs) -> ToolResult:
        import json
        username = getattr(getattr(context, "user", None), "id", None)
        scope = load_scope(username)
        if scope.role not in ("admin", "team_lead") or scope.is_empty:
            return ToolResult(success=False, result_for_llm="Không có quyền truy cập công cụ nghiệp vụ theo vai trò/phạm vi hiện tại.")
        scope_ids = list(scope.machine_ids)
        topic = (args.topic or "").strip().lower()
        try:
            if topic == "stations":
                code = (args.order_code or "").strip().upper()
                if not re.fullmatch(r"CD-\d{7}", code):
                    return ToolResult(success=False, result_for_llm="Cần mã công đơn CD-0000001 hợp lệ.")
                order_id = int(code[3:])
                orders = fetch_all("SELECT id,status,quantity,workshop_id FROM customer_orders WHERE id=%s AND deleted_at IS NULL", (order_id,))
                if orders and not scope.all_machines:
                    allowed = fetch_all("SELECT 1 FROM machines WHERE workshop_id=%s AND id=ANY(%s::integer[]) LIMIT 1", (orders[0]["workshop_id"],scope_ids))
                    if not allowed:
                        orders=[]
                if not orders:
                    return ToolResult(success=True, result_for_llm=json.dumps({"found":False,"code":code}, ensure_ascii=False))
                stations = fetch_all("""SELECT s.process_order,m.machine_code,m.machine_name,s.quantity_completed,s.is_current
                    FROM customer_order_stage_progress s JOIN machines m ON m.id=s.machine_id
                    WHERE s.customer_order_id=%s ORDER BY s.process_order""", (order_id,))
                if not stations:
                    stations = fetch_all("""SELECT cm.process_order,m.machine_code,m.machine_name,
                        0::integer AS quantity_completed,FALSE AS is_current
                        FROM customer_order_machines cm JOIN machines m ON m.id=cm.machine_id
                        WHERE cm.customer_order_id=%s ORDER BY cm.process_order""", (order_id,))
                result={"found":True,"order_code":code,"status":orders[0]["status"],"stations":stations,
                    "note":"Công trạm đã cấu hình không đồng nghĩa đã hoàn thành; chỉ dựa quantity_completed để xác định có ghi nhận xử lý. Không suy đoán lịch sử thời điểm nếu chưa được lưu."}
            elif topic == "lowest_progress":
                rows = fetch_all("""SELECT co.id,'CD-'||LPAD(co.id::text,7,'0') AS order_code,
                    co.quantity,co.status,
                    CASE WHEN COUNT(sp.machine_id)>0 AND co.quantity>0 THEN
                      LEAST(100,GREATEST(0,ROUND(100.0*COALESCE(SUM(sp.quantity_completed),0)/
                       (co.quantity*COUNT(sp.machine_id)),2))) ELSE 0 END AS progress_percent
                    FROM customer_orders co LEFT JOIN customer_order_stage_progress sp ON sp.customer_order_id=co.id
                    WHERE co.deleted_at IS NULL AND co.status='in_production'
                      AND (%s::boolean OR co.workshop_id IN (SELECT DISTINCT workshop_id FROM machines WHERE id=ANY(%s::integer[])))
                    GROUP BY co.id,co.quantity,co.status
                    ORDER BY progress_percent ASC,co.id ASC LIMIT 100""", (scope.all_machines,scope_ids))
                result={"orders":rows,"count_returned":len(rows),"note":"Tiến độ tính như Dashboard; đơn không có dữ liệu công đoạn hiển thị 0%. Nếu đạt giới hạn, không khẳng định đầy đủ."}
            elif topic == "missing_task_reports":
                normal = fetch_all("""SELECT u.id AS user_id,u.full_name,t.id AS task_id,t.title,
                    t.status,t.due_at,m.machine_code
                    FROM tasks t JOIN app_users u ON u.id=t.assigned_to
                    LEFT JOIN machines m ON m.id=t.machine_id
                    WHERE u.role='technician' AND u.is_active=TRUE
                      AND t.status IN ('assigned','in_progress','returned')
                      AND NOT EXISTS (SELECT 1 FROM task_reports r WHERE r.task_id=t.id)
                      AND (%s::boolean OR t.machine_id=ANY(%s::integer[]))
                    ORDER BY t.due_at NULLS LAST,t.id LIMIT 100""", (scope.all_machines,scope_ids))
                result = {
                    "unreported_regular_tasks": normal,
                    "regular_task_count": len(normal),
                    "distinct_technician_count": len({r['user_id'] for r in normal}),
                    "note": "Chưa nộp = công việc được giao chưa có báo cáo. Tối đa 100 bản ghi."
                }
            elif topic == "submitted_reports":
                # Count actual submitted report records, not task status or guessed column names.
                # Use the privileged, parameter-free server-owned fetch_all query after Admin RBAC.
                normal_count = fetch_all("SELECT COUNT(*)::bigint AS total FROM task_reports r JOIN tasks t ON t.id=r.task_id WHERE %s::boolean OR t.machine_id=ANY(%s::integer[])", (scope.all_machines,scope_ids))
                normal = int(normal_count[0]["total"] if normal_count else 0)
                result = {
                    "regular_task_report_submissions": normal,
                    "total_report_submissions": normal,
                    "note": "Tổng số lượt báo cáo công việc thường đã nộp."
                }
            elif topic in ("technicians", "machine_assignments"):
                # Truy cập danh sách nhân viên không kèm tài khoản/mật khẩu.
                rows = fetch_all("""SELECT e.employee_code,e.employee_name,w.workshop_name,
                    m.machine_code,m.machine_name
                    FROM employees e JOIN workshops w ON w.id=e.workshop_id
                    JOIN app_users u ON u.employee_id=e.id AND u.role='technician' AND u.is_active=TRUE
                    LEFT JOIN machine_assignments ma ON ma.employee_id=e.id
                    LEFT JOIN machines m ON m.id=ma.machine_id
                    WHERE (%s::boolean OR e.workshop_id IN
                      (SELECT DISTINCT workshop_id FROM machines WHERE id=ANY(%s::integer[])))
                      AND (%s::boolean OR m.id=ANY(%s::integer[]))
                    ORDER BY w.workshop_name,e.employee_name,m.machine_code LIMIT 500""",
                    (scope.all_machines,scope_ids,scope.all_machines,scope_ids))
                result={"technician_machine_assignments": rows,
                        "note":"Mỗi dòng là một máy của kỹ thuật viên; gộp theo nhân viên để tránh đếm trùng. Chỉ thuộc phạm vi xưởng được quản lý."}
            else:
                return ToolResult(success=False,result_for_llm="Chủ đề không hợp lệ. Chọn stations, lowest_progress, missing_task_reports, submitted_reports, technicians hoặc machine_assignments.")
            return ToolResult(success=True,result_for_llm=json.dumps(result,ensure_ascii=False,default=str))
        except Exception as exc:
            return ToolResult(success=False,result_for_llm=f"Không truy vấn được {topic}: {type(exc).__name__}; cần kiểm tra schema/log máy chủ, không được bịa kết quả.")




class TechnicianSelfLookupArgs(BaseModel):
    topic: str = Field(description="Chọn: order_progress, my_machines, my_open_work, my_submitted_reports")
    order_code: str = Field(default="", description="Mã CD-0000001, dùng cho order_progress")


class TechnicianSelfLookupTool(Tool[TechnicianSelfLookupArgs]):
    """Công cụ CHỈ ĐỌC dữ liệu của chính KTV, không cấp lịch sử công trạm."""
    @property
    def name(self) -> str:
        return "technician_self_lookup"

    @property
    def description(self) -> str:
        return ("Kỹ thuật viên: order_progress=tiến độ công đơn có máy được phân công tham gia; "
                "my_machines=máy được giao cho chính mình; my_open_work=công việc chưa hoàn thành của mình; "
                "my_submitted_reports=số lượt báo cáo công việc của mình. "
                "KHÔNG hỗ trợ xem lịch sử công trạm và không trả dữ liệu người khác.")

    @property
    def access_groups(self) -> list[str]:
        return ["users"]

    def get_args_schema(self) -> Type[TechnicianSelfLookupArgs]:
        return TechnicianSelfLookupArgs

    async def execute(self, context: ToolContext, args: TechnicianSelfLookupArgs) -> ToolResult:
        import json
        scope = load_scope(getattr(getattr(context, "user", None), "id", None))
        if scope.role != "technician" or scope.is_empty:
            return ToolResult(success=False, result_for_llm="Công cụ chỉ dành cho kỹ thuật viên có máy được phân công.")
        tech = fetch_all("SELECT id, employee_id FROM app_users WHERE lower(username)=lower(%s) AND role='technician' AND is_active=TRUE", (scope.username,))
        if not tech:
            return ToolResult(success=False, result_for_llm="Không xác định được tài khoản kỹ thuật viên đang đăng nhập.")
        uid = tech[0]["id"]
        ids = list(scope.machine_ids)
        topic = (args.topic or "").strip().lower()
        try:
            if topic == "order_progress":
                code = (args.order_code or "").strip().upper()
                if code and not re.fullmatch(r"CD-\d{7}", code):
                    return ToolResult(success=False, result_for_llm="Mã công đơn phải có dạng CD-0000001.")
                sql = """SELECT co.id, co.status, co.quantity,
                    CASE WHEN co.status='completed' THEN 100
                         WHEN co.quantity>0 AND co.status='in_production' AND COALESCE(t.stage_count,0)>0
                         THEN LEAST(100,GREATEST(0,ROUND(100.0*t.quantity_sum/(co.quantity*t.stage_count),2)))
                         ELSE 0 END AS progress_percent
                    FROM customer_orders co
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS stage_count, COALESCE(SUM(quantity_completed),0) AS quantity_sum
                        FROM customer_order_stage_progress WHERE customer_order_id=co.id
                    ) t ON TRUE
                    WHERE co.deleted_at IS NULL
                    AND EXISTS (SELECT 1 FROM customer_order_machines cm WHERE cm.customer_order_id=co.id AND cm.machine_id=ANY(%s::integer[]))"""
                params = [ids]
                if code:
                    sql += " AND co.id=%s"
                    params.append(int(code[3:]))
                sql += " ORDER BY co.id DESC LIMIT 100"
                rows=fetch_all(sql,tuple(params))
                result={"orders":[{"order_code":f"CD-{int(r['id']):07d}",
                    "status":r['status'],"quantity":int(r['quantity'] or 0),
                    "progress_percent":float(r['progress_percent'] or 0)} for r in rows],
                    "note":"Chỉ trả về tỷ lệ tiến độ tổng hợp của công đơn có máy được phân công tham gia; không công bố lịch sử công trạm."}
                if code and not rows:
                    result={"found":False,"note":"Không tìm thấy công đơn trong phạm vi được phân quyền."}
            elif topic == "my_machines":
                result={"machines":fetch_all("""SELECT m.machine_code,m.machine_name,w.workshop_name
                    FROM machines m JOIN workshops w ON w.id=m.workshop_id
                    WHERE m.id=ANY(%s::integer[]) ORDER BY m.machine_code""",(ids,))}
            elif topic == "my_open_work":
                tasks=fetch_all("""SELECT t.id,t.title,t.status,m.machine_code,t.due_at
                    FROM tasks t LEFT JOIN machines m ON m.id=t.machine_id
                    WHERE t.assigned_to=%s AND t.status NOT IN ('approved','completed','cancelled')
                    AND t.machine_id=ANY(%s::integer[]) ORDER BY t.id DESC LIMIT 100""",(uid,ids))
                result={"regular_tasks":tasks,"note":"Công việc chưa hoàn thành gồm chờ báo cáo, chờ duyệt và yêu cầu làm lại."}
            elif topic == "my_submitted_reports":
                a=fetch_all("SELECT COUNT(*)::integer AS total FROM task_reports WHERE author_id=%s",(uid,))
                x=int(a[0]["total"])
                result={"regular_report_submissions":x,"total_report_submissions":x,
                        "note":"Số lượt báo cáo công việc do chính tài khoản này nộp."}
            else:
                return ToolResult(success=False,result_for_llm="Chủ đề không hỗ trợ. Không được gọi stations/lịch sử công trạm cho kỹ thuật viên.")
            return ToolResult(success=True,result_for_llm=json.dumps(result,ensure_ascii=False,default=str))
        except Exception as exc:
            return ToolResult(success=False,result_for_llm=f"Truy vấn dữ liệu cá nhân thất bại: {type(exc).__name__}; không suy đoán số liệu.")


class RunSqlArgs(BaseModel):
    sql: str = Field(description="SQL query PostgreSQL cần thực thi")
 
 
class SafeRunSqlTool(Tool[RunSqlToolArgs]):
    """
    SQL tool tự quản lý.
 
    Khác với việc bọc RunSqlTool bằng subclass, tool này là Tool riêng nên
    registry chỉ thấy đúng một tool SQL của ứng dụng; luôn áp dụng kiểm tra quyền và SQL chỉ-đọc.
    """
    @property
    def name(self) -> str:
        return "run_sql"
 
    @property
    def description(self) -> str:
        return (
            "Chạy SQL PostgreSQL chỉ-đọc cho số liệu sản xuất trong phạm vi được phép. "
            "Với công đơn CD, ưu tiên công cụ lookup_customer_orders hoặc công cụ theo vai trò."
        )
 
    @property
    def access_groups(self) -> list[str]:
        return ["users"]
 
    def get_args_schema(self) -> Type[RunSqlToolArgs]:
        return RunSqlToolArgs
 
    async def execute(
        self,
        context: ToolContext,
        args: RunSqlToolArgs,
    ) -> ToolResult:
        import json

        sql = (args.sql or "").strip()

        # Không bao giờ cho AI đọc bảng tài khoản đăng nhập (chứa mật khẩu đã băm).
        if re.search(r"\bapp_users\b|\bpassword_hash\b", sql, flags=re.IGNORECASE):
            return ToolResult(
                success=False,
                result_for_llm="Không có quyền truy cập dữ liệu tài khoản đăng nhập.",
            )

        # Vai trò và danh sách máy được đọc từ DATABASE theo tài khoản đang chat.
        ctx_user = getattr(context, "user", None)
        username = getattr(ctx_user, "id", None)
        try:
            scope = load_scope(username)
        except Exception as exc:
            return ToolResult(
                success=False,
                result_for_llm=f"Không xác định được phạm vi dữ liệu: {exc}",
            )
        print(f"[SQL GUARD] user={username!r} role={scope.role!r} "
              f"all={scope.all_machines} machines={len(scope.machine_ids)}")

        if scope.is_empty:
            return ToolResult(success=False, result_for_llm=_NO_MACHINE_MSG)

        # customer_orders chưa được bảo vệ bởi RLS trong migration máy hiện tại.
        # Không cho AI không phải Admin truy vấn SQL tự do vào bảng đó.
        if scope.role != ROLE_ADMIN and re.search(r"\bcustomer_orders\b", sql, flags=re.IGNORECASE):
            return ToolResult(success=False, result_for_llm=(
                "Hãy dùng công cụ lookup_customer_orders để tra cứu công đơn theo phạm vi xưởng."
            ))
        # Kỹ thuật viên không được xem lịch sử/danh sách công trạm qua SQL tự do.
        # Chỉ công cụ technician_self_lookup được dùng stage_progress nội bộ để TÍNH % tổng.
        if scope.role == "technician" and re.search(
            r"\b(customer_order_stage_progress|customer_order_machines)\b", sql, flags=re.IGNORECASE
        ):
            return ToolResult(success=False, result_for_llm=(
                "Kỹ thuật viên không có quyền xem lịch sử công trạm. "
                "Để xem tỷ lệ tiến độ, hãy dùng technician_self_lookup với topic=order_progress."
            ))
        denied = _sql_guard(sql, scope.role)
        if denied:
            return ToolResult(success=False, result_for_llm=denied)

        # SQL thông thường: chạy dưới role chỉ-đọc + RLS theo phạm vi máy.
        try:
            rows = fetch_all_scoped(scope, sql)
            payload = {
                "success": True,
                "rows": rows[:_MAX_AI_ROWS],
                "row_count": len(rows),
            }
            if len(rows) > _MAX_AI_ROWS:
                payload["truncated"] = True
            return ToolResult(
                success=True,
                result_for_llm=json.dumps(payload, ensure_ascii=False, default=str),
            )
        except Exception as exc:
            import traceback

            print("\n[SQL TOOL ERROR]")
            traceback.print_exc()

            return ToolResult(
                success=False,
                result_for_llm=(
                    f"SQL execution error: {type(exc).__name__}: {exc}"
                ),
            )


tools = ToolRegistry()
tools.register_local_tool(CustomerOrderLookupTool(), access_groups=["users"])
tools.register_local_tool(AdminOperationalTool(), access_groups=["users"])
tools.register_local_tool(TechnicianSelfLookupTool(), access_groups=["users"])
tools.register_local_tool(
    SafeRunSqlTool(),   
    access_groups=["users"],
)
 
 
# Vanna 2.x yêu cầu agent_memory khi khởi tạo Agent.
# Dùng DemoAgentMemory để đáp ứng interface; không đăng ký các
# memory tools nên memory không được dùng để thay thế dữ liệu SQL.
agent_memory = DemoAgentMemory(max_items=1)
 
agent = Agent(
    llm_service=llm,
    tool_registry=tools,
    user_resolver=SimpleUserResolver(),
    agent_memory=agent_memory,
    system_prompt_builder=FactorySystemPromptBuilder(),
)
 
server = VannaFastAPIServer(
    agent,
    config={
        "cors": {
            "enabled": True,
            "allow_origins": [
                o.strip() for o in os.getenv(
                    "ALLOWED_ORIGINS",
                    "http://localhost:8000,http://127.0.0.1:8000",
                ).split(",") if o.strip()
            ],
            "allow_credentials": True,
            "allow_methods": ["GET", "POST"],
            "allow_headers": ["Authorization", "Content-Type"],
        },
        "static_folder": "static",
    },
)
 
# Vanna 2.x exposes create_app(), allowing custom FastAPI routes to coexist
# with /api/vanna/v2/chat_*.
app = server.create_app()
 
# Bắt buộc đăng nhập cho toàn bộ ứng dụng (kể cả /api/vanna/* và /static/*).
app.add_middleware(AuthMiddleware)
app.include_router(ai_history_router)
 
 
@app.get("/login", include_in_schema=False)
async def login_page():
    return HTMLResponse(login_page_html())
 
 
@app.post("/api/auth/login", include_in_schema=False)
async def auth_login(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    client_ip = request.client.host if request.client else "?"
    lock_key = f"{client_ip}|{username.lower()}"
 
    if is_locked(lock_key):
        return JSONResponse(
            {"detail": "Đăng nhập sai quá nhiều lần. Vui lòng thử lại sau 5 phút."},
            status_code=429,
        )
 
    rows = fetch_all(
        "SELECT username, full_name, password_hash, role FROM app_users "
        "WHERE lower(username) = lower(%s) AND is_active",
        (username,),
    ) if username else []
    row = rows[0] if rows else None
    ok = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
 
    if not (row and ok):
        register_fail(lock_key)
        return JSONResponse({"detail": "Sai tên đăng nhập hoặc mật khẩu."}, status_code=401)
 
    clear_fails(lock_key)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        COOKIE_NAME,
        make_token(row["username"], row["full_name"] or row["username"], row["role"]),
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response
 
 
@app.post("/api/auth/logout", include_in_schema=False)
async def auth_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
 
 
@app.get("/api/auth/me", include_in_schema=False)
async def auth_me(request: Request):
    user = request.scope.get("state", {}).get("user") or {}
    machines, all_machines = [], user.get("role") == ROLE_ADMIN
    try:
        scope = load_scope(user.get("username"))
        all_machines = scope.all_machines
        machines = list_scope_machines(scope)
    except Exception as exc:  # chưa chạy migration: vẫn cho đăng nhập bình thường
        print(f"[SCOPE] không đọc được phạm vi máy: {exc}")
    return {
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "role": user.get("role"),
        "role_label": ROLE_LABELS.get(user.get("role"), ""),
        "all_machines": all_machines,
        "machines": machines,
    }
 
 
# ============================================================
# MES CHAT HANDLER: dữ liệu nghiệp vụ CD và phân quyền theo người đăng nhập.
# ============================================================
mes_chat_handler = ChatHandler(agent)
 
 
def _extract_user_text(body: dict) -> str:
    """Best-effort extraction for Vanna ChatRequest across minor schema changes."""
    for key in ("message", "question", "prompt", "text"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
 
    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        for item in reversed(messages):
            if isinstance(item, dict) and item.get("role") == "user":
                content = item.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
    return ""
 
 
def _history_stream_text(chunk):
    """Extract human-readable text from Vanna's heterogeneous SSE event schemas.

    Recent Vanna versions send partial text through different component wrappers
    (content/text/markdown, sometimes under data.content). Never persist tool
    arguments, SQL snippets, error events, or task-progress payloads as AI replies.
    """
    try:
        data = chunk.model_dump(mode='json', exclude_none=True) if hasattr(chunk, 'model_dump') else chunk
    except Exception:
        return ''

    def walk(obj, depth=0, parent_text=False):
        if depth > 14:
            return []
        if isinstance(obj, list):
            result=[]
            for child in obj:
                result.extend(walk(child, depth+1, parent_text))
            return result
        if not isinstance(obj, dict):
            return []
        kind = str(obj.get('type') or obj.get('component_type') or obj.get('kind') or obj.get('_type') or obj.get('name') or '').lower()
        role = str(obj.get('role') or '').lower()
        if role in ('user', 'system', 'tool') or any(x in kind for x in ('tool', 'task', 'error', 'sql', 'status', 'progress')):
            return []
        is_text = parent_text or any(x in kind for x in ('richtext','rich_text','markdown','text','assistant','message','content')) or role == 'assistant'
        found=[]
        for key in ('text','content','markdown','answer','value','message'):
            value=obj.get(key)
            # Vanna emits a component envelope without a type marker in some
            # releases. Inside a component or text-like payload, string content
            # is a visible answer even when its kind is absent.
            if isinstance(value,str) and value.strip() and (is_text or key in ('answer','markdown') or
                (key in ('text','content') and not kind)):
                found.append(value.strip())
        if found:
            return found
        # Vanna's normal SSE emits both `rich` and `simple` component
        # representations, rather than putting the answer in `data`.
        for key in ('rich','simple','component','components','data','payload','message','messages','value','content','parts','delta','output','props','properties'):
            if isinstance(obj.get(key),(dict,list)):
                found.extend(walk(obj[key],depth+1,is_text))
        return found
    parts = walk(data)
    return '\n'.join(dict.fromkeys(x for x in parts if x.strip()))


def _history_id_from_request(request, body):
    """The Vanna widget may omit the custom header on some transport versions."""
    import uuid
    value = str(request.headers.get('x-mes-history-id') or '').strip()
    try:
        return str(uuid.UUID(value))
    except (TypeError,ValueError,AttributeError):
        pass
    value = str((body or {}).get('conversation_id') or '').strip()
    try:
        return str(uuid.UUID(value))
    except (TypeError,ValueError,AttributeError):
        # Still save one question/answer pair instead of silently losing it.
        return str(uuid.uuid4())


async def _save_ai_history(request, history_id, question, answer):
    if not history_id or not answer.strip() or not question.strip():return
    try:
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(record_exchange,request,history_id,question,answer)
    except Exception:
        # A history write must never turn a successful AI response into an error.
        import logging
        logging.getLogger('mes.ai_history').exception('Không thể lưu lịch sử AI')


# Remove the Vanna-generated SSE route so our wrapper becomes the only route
# for the endpoint used by the current frontend.
app.router.routes = [
    route
    for route in app.router.routes
    if getattr(route, "path", None) != "/api/vanna/v2/chat_sse"
]
 
 
def _simple_mes_greeting(question: str, role: str | None = None) -> str | None:
    """Role-bound greetings, help, thanks; no business-data claims."""
    return conversational_answer(question, role)


def _mes_rich_text_sse(answer: str, body: dict):
    """Build the same Vanna RichText message schema used by live answers."""
    chunk = ChatStreamChunk.from_component(
        RichTextComponent(content=answer, markdown=True),
        conversation_id=body.get('conversation_id') or '',
        request_id=body.get('request_id') or '',
    )
    return f'data: {chunk.model_dump_json()}\n\n'


@app.post("/api/customer-orders/assistant/vanna-sse")
async def customer_vanna_sse(request: Request):
    """Vanna web-component transport, with customer-only data service.

    NEVER forwards customer input to internal SQL/Vanna agent routes.
    Customer company and creator restrictions are applied in the existing
    customer_assistant_chat service using the authenticated DB identity.
    """
    import json
    from starlette.concurrency import run_in_threadpool
    from backend.routes_customer_orders import customer_assistant_chat, CustomerChatRequest
    body = await request.json()
    if not isinstance(body, dict):
        body = {}
    question = _extract_user_text(body).strip()
    # Authorize even initialization requests: no chat traffic may bypass role checks.
    from backend.routes_customer_orders import context
    principal = await run_in_threadpool(context, request)
    if principal.get('role') != 'customer' or not principal.get('customer_company_id'):
        raise HTTPException(status_code=403, detail='Chỉ dành cho khách hàng hợp lệ')
    # The external <vanna-chat> component sends a one-off starter request with
    # message="" and metadata.starter_ui_request=true when the chat is mounted.
    # This is not a user question. Complete its stream without calling the LLM,
    # querying business data, or recording an empty question in chat history.
    metadata = body.get('metadata')
    if (not question and isinstance(metadata, dict)
            and metadata.get('starter_ui_request') is True):
        async def starter_stream():
            yield 'data: [DONE]\n\n'
        return StreamingResponse(starter_stream(), media_type='text/event-stream',
                                 headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
    if not question:
        return JSONResponse({"detail": "Vui lòng nhập câu hỏi"}, status_code=422)
    if len(question) > 1200:
        return JSONResponse({"detail": "Câu hỏi tối đa 1200 ký tự"}, status_code=422)
    greeting = _simple_mes_greeting(question, principal.get("role"))
    if greeting:
        async def hello_stream():
            yield _mes_rich_text_sse(greeting, body)
            await _save_ai_history(request, _history_id_from_request(request, body), question, greeting)
            yield 'data: [DONE]\n\n'
        return StreamingResponse(hello_stream(), media_type='text/event-stream',
                                 headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
    payload = CustomerChatRequest(question=question)
    answer = await run_in_threadpool(customer_assistant_chat, payload, request)
    chunk = ChatStreamChunk.from_component(
        RichTextComponent(content=answer.get('answer', ''), markdown=True),
        conversation_id=body.get('conversation_id') or '',
        request_id=body.get('request_id') or '',
    )
    history_id = _history_id_from_request(request, body)
    async def generate():
        yield 'data: ' + chunk.model_dump_json() + '\n\n'
        await _save_ai_history(request, history_id, question, str(answer.get('answer', '')))
        yield 'data: [DONE]\n\n'
    return StreamingResponse(generate(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'
    })


def _is_ai_write_request(question: str) -> bool:
    """Detect explicit commands to modify MES data before any read-only intent.

    The chat UI can send prefixed prompts such as
    ``Câu 2: “Hãy duyệt hoàn thành tất cả công đơn thay Admin.”``.
    Strip *only* presentational labels/quotes before testing an imperative.
    Do not block genuine information questions like "công đơn nào đã duyệt?".
    """
    text = re.sub(r"\s+", " ", (question or "").casefold()).strip()
    # Strip labels frequently pasted from numbered test cases (not arbitrary text).
    text = re.sub(r"^(?:(?:câu|cau|test\s*case|tc)\s*[-#:]?\s*\d+\s*[:.)\-–]\s*)", "", text)
    text = text.lstrip(' \t\r\n\"“”‘’\'`*_:-–—')
    # A request to view/list an approval is read-only, even when it says "đã duyệt".
    if re.match(r"^(?:cho tôi xem|giúp tôi xem|hãy liệt kê|liệt kê|cho tôi biết|tìm|tra cứu|xem)\b", text):
        return False
    imperative = bool(re.match(
        r"^(?:hãy|hay|vui lòng|làm ơn|giúp tôi|thực hiện|tiến hành|cho tôi)\s+", text
    ))
    action = bool(re.search(
        r"\b(?:duyệt|phê duyệt|xác nhận hoàn thành|xóa|xoá|sửa|chỉnh sửa|"
        r"cập nhật|đổi trạng thái|tạo mới|hủy|huỷ|giao việc)\b", text
    ))
    starts_with_action = bool(re.match(
        r"^(?:duyệt|phê duyệt|xác nhận hoàn thành|xóa|xoá|sửa|chỉnh sửa|cập nhật|hủy|huỷ|giao việc)\b", text
    ))
    return action and (imperative or starts_with_action)



def _ai_write_request_target(question: str) -> str:
    """Classify a write command by the business object it attempts to change.

    This is only used after `_is_ai_write_request` determined that the
    message is an action request.  It never authorizes any operation.
    """
    text = re.sub(r"\s+", " ", (question or "").casefold())
    # Report questions take precedence over generic work/order words.
    if any(term in text for term in ("báo cáo", "bao cao", "report")):
        return "task_report"
    if any(term in text for term in ("công đơn", "cong don", "đơn sản xuất", "production order")):
        return "customer_order"
    if any(term in text for term in ("công việc", "cong viec", "giao việc", "task")):
        return "task"
    return "general"


def _ai_write_denial_answer(role: str | None, question: str) -> str:
    """Explain read-only AI behavior without mixing up MES actor permissions.

    Roles must come from the authenticated server-side scope, never from the
    prompt.  A write request always remains denied in the AI chat.
    """
    target = _ai_write_request_target(question)
    intro = ("AI Assistant chỉ hỗ trợ tra cứu dữ liệu; không thể thực hiện "
             "duyệt, xóa, sửa hoặc cập nhật thông tin qua hội thoại.")
    if target == "task_report":
        if role == "technician":
            return (intro + " Kỹ thuật viên không có quyền tự duyệt báo cáo công việc của mình. "
                    "Báo cáo cần được Tổ trưởng xem xét và duyệt trên giao diện hệ thống.")
        if role == "team_lead":
            return (intro + " Tổ trưởng có thể xem xét và duyệt báo cáo công việc "
                    "thuộc phạm vi được phân quyền bằng chức năng trên giao diện.")
        if role == "admin":
            return (intro + " Việc duyệt báo cáo công việc thực hiện theo quy trình "
                    "phân quyền trên giao diện; AI không thể duyệt thay người dùng.")
        return intro + " Bạn không có quyền duyệt báo cáo công việc nội bộ qua AI."
    if target == "customer_order":
        if role == "team_lead":
            return (intro + " Tổ trưởng không có quyền xác nhận hoàn thành công đơn "
                    "thay Admin; hãy sử dụng chức năng đúng quyền trên giao diện.")
        if role == "technician":
            return (intro + " Kỹ thuật viên không có quyền duyệt hoặc xác nhận "
                    "hoàn thành công đơn; chức năng này được thực hiện bởi vai trò có thẩm quyền.")
        if role == "admin":
            return (intro + " Admin cần sử dụng chức năng quản lý công đơn "
                    "trên giao diện nếu muốn thực hiện thao tác được phép.")
        return intro + " Bạn không có quyền thay đổi công đơn qua AI."
    if target == "task":
        if role == "technician":
            return intro + " Kỹ thuật viên chỉ thực hiện các thao tác công việc trong phạm vi được giao trên giao diện."
        if role == "team_lead":
            return intro + " Tổ trưởng có thể sử dụng chức năng giao việc và xử lý công việc trên giao diện."
        return intro + " Hãy sử dụng chức năng phù hợp quyền của tài khoản trên giao diện."
    return intro + " Hãy sử dụng chức năng phù hợp quyền của tài khoản trên giao diện."


def _is_running_machine_question(question: str) -> bool:
    """Question specifically about which machines are running/producing."""
    text = re.sub(r"\s+", " ", (question or "").casefold()).strip()
    has_machine = any(k in text for k in ("máy", "máy móc", "thiết bị"))
    asks_running = any(k in text for k in (
        "đang sản xuất", "đang chạy", "đang hoạt động", "đang vận hành", "running"
    ))
    asks_list = any(k in text for k in (
        "nào", "liệt kê", "danh sách", "bao nhiêu", "có mấy", "những máy"
    ))
    return has_machine and asks_running and asks_list


def _query_running_machines(scope):
    """Server-owned parameterized query; respects scope at machine-ID level."""
    sql = """
        SELECT m.machine_code, m.machine_name, w.workshop_name,
               COUNT(DISTINCT co.id)::integer AS active_order_count
        FROM machines m
        LEFT JOIN workshops w ON w.id = m.workshop_id
        JOIN customer_order_machines cm ON cm.machine_id = m.id
        JOIN customer_orders co ON co.id = cm.customer_order_id
             AND co.status = 'in_production' AND co.deleted_at IS NULL
        WHERE lower(m.status) = 'running'
          AND (%s::boolean OR m.id = ANY(%s::integer[]))
        GROUP BY m.id, m.machine_code, m.machine_name, w.workshop_name
        ORDER BY w.workshop_name, m.machine_code
    """
    return fetch_all(sql, (scope.all_machines, list(scope.machine_ids)))


def _format_running_machines(rows):
    if not rows:
        return "Không có máy nào ở trạng thái Running đồng thời tham gia công đơn đang sản xuất trong phạm vi tài khoản."
    lines = [
        f"- {r['machine_code']} ({r.get('workshop_name') or 'Chưa xác định xưởng'}): "
        f"{int(r['active_order_count'])} công đơn đang sản xuất"
        for r in rows
    ]
    return (f"Có {len(rows)} máy ở trạng thái Running và tham gia công đơn đang sản xuất trong phạm vi tài khoản:\n"
            + "\n".join(lines)
            + "\nLưu ý: Running là trạng thái lưu trong Database, không phải phép đo cảm biến theo thời gian thực.")


@app.post("/api/vanna/v2/chat_sse")
async def custom_chat_sse(request: Request):
    """
    Vanna-compatible SSE endpoint.
 
    Trả lời trực tiếp các câu hỏi nghiệp vụ CD phổ biến theo scope tài khoản.
    Các câu hỏi khác dùng Vanna với SQL chỉ-đọc và các tool phân quyền.
    """
    import json
    import traceback
 
    raw_body = await request.json()
    body = raw_body if isinstance(raw_body, dict) else {}
    user_text = _extract_user_text(body)
    # Resolve the user's real role from the authenticated session, not the prompt.
    try:
        greeting_role = scope_from_request(request).role
    except Exception:
        greeting_role = None
    if greeting_role not in ('admin', 'team_lead', 'technician'):
        raise HTTPException(status_code=403, detail='Không có quyền dùng AI nội bộ')
    # Mã CO/PO cũ không còn là mã công đơn do trợ lý MES hỗ trợ.
    # Chặn trước Vanna để không phát sinh truy vấn/mẫu trả lời theo chuẩn cũ.
    if re.search(r"\b(?:PO-[A-Z0-9-]+|CO-\d+)\b", user_text, re.IGNORECASE):
        answer = ("Trợ lý MES hiện tra cứu công đơn theo mã CD-0000001. "
                  "Mã PO/CO cũ không được tự động quy đổi. "
                  "Vui lòng cung cấp mã CD hợp lệ hoặc hỏi tổng quan công đơn trong phạm vi tài khoản.")
        async def old_code_stream():
            yield _mes_rich_text_sse(answer, body)
            await _save_ai_history(request, _history_id_from_request(request, body), user_text, answer)
            yield 'data: [DONE]\n\n'
        return StreamingResponse(old_code_stream(), media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    greeting = _simple_mes_greeting(user_text, greeting_role)
    if greeting:
        async def hello_stream():
            yield _mes_rich_text_sse(greeting, body)
            await _save_ai_history(request, _history_id_from_request(request, body), user_text, greeting)
            yield 'data: [DONE]\n\n'
        return StreamingResponse(hello_stream(), media_type='text/event-stream',
                                 headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
 
    # Ưu tiên hành động trước tra cứu, tránh 'hãy duyệt ... thay Admin'
    # bị diễn giải thành câu hỏi công đơn chờ duyệt.
    if _is_ai_write_request(user_text):
        # Read role exclusively from the authenticated request; never infer it
        # from a role name appearing in the user's question.
        try:
            request_scope = scope_from_request(request)
            caller_role = request_scope.role
        except Exception:
            caller_role = None  # Safe fallback: no role-specific permission.
        answer = _ai_write_denial_answer(caller_role, user_text)
        async def readonly_stream():
            yield _mes_rich_text_sse(answer, body)
            await _save_ai_history(request, _history_id_from_request(request, body), user_text, answer)
            yield 'data: [DONE]\n\n'
        return StreamingResponse(readonly_stream(), media_type='text/event-stream',
                                 headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    # Admin: bộ định tuyến tường minh cho các câu hỏi tổng hợp và "của tôi".
    # Các thống kê dùng Database thực, không cho Vanna đoán vai trò hay số liệu.
    from backend.ai_admin_intents import detect_admin_intent, admin_answer, split_numbered_questions
    admin_questions = split_numbered_questions(user_text) if greeting_role == 'admin' else []
    admin_intent = detect_admin_intent(user_text) if greeting_role == 'admin' and not admin_questions else None
    if admin_intent or admin_questions:
        try:
            authenticated_scope = scope_from_request(request)
            if authenticated_scope.role != 'admin' or authenticated_scope.is_empty:
                answer = 'Tài khoản không có quyền truy vấn số liệu quản trị.'
            else:
                if admin_questions:
                    segments = []
                    for i, question in enumerate(admin_questions, 1):
                        intent = detect_admin_intent(question)
                        if intent is None:
                            segment = 'Câu hỏi này cần truy vấn chuyên sâu; vui lòng gửi riêng để nhận kết quả chính xác.'
                        else:
                            segment = admin_answer(intent, authenticated_scope.username, fetch_all)
                        segments.append(f'{i}. **{question}**\n{segment}')
                    answer = '\n\n'.join(segments)
                else:
                    answer = admin_answer(admin_intent, authenticated_scope.username, fetch_all)
        except Exception:
            answer = 'Chưa thể truy vấn số liệu quản trị từ Database lúc này. Vui lòng thử lại.'
        async def admin_stream():
            yield _mes_rich_text_sse(answer, body)
            await _save_ai_history(request, _history_id_from_request(request, body), user_text, answer)
            yield 'data: [DONE]\n\n'
        return StreamingResponse(admin_stream(), media_type='text/event-stream',
                                 headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    # Tổ trưởng: trả lời nghiệp vụ theo xưởng lấy từ phân quyền thật của phiên đăng nhập.
    # Không để những câu hỏi chờ duyệt/cần xử lý bị Vanna suy đoán từ schema.
    if greeting_role == 'team_lead':
        from backend.ai_lead_intents import detect_lead_intent, lead_answer
        lead_intent = detect_lead_intent(user_text)
        if lead_intent:
            try:
                lead_scope = scope_from_request(request)
                answer = lead_answer(lead_intent, lead_scope, fetch_all)
            except Exception:
                answer = 'Chưa thể tra cứu dữ liệu xưởng phụ trách lúc này. Vui lòng thử lại.'
            async def lead_stream():
                yield _mes_rich_text_sse(answer, body)
                await _save_ai_history(request, _history_id_from_request(request, body), user_text, answer)
                yield 'data: [DONE]\n\n'
            return StreamingResponse(lead_stream(), media_type='text/event-stream',
                                     headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    # Kỹ thuật viên: định tuyến nghiệp vụ theo tài khoản và máy đã được cấp quyền.
    # Hỏi theo trạng thái cụ thể trước, tránh fallback sang Vanna suy đoán phạm vi.
    if greeting_role == 'technician':
        from backend.ai_technician_intents import detect_technician_intent, technician_answer
        technician_intent = detect_technician_intent(user_text)
        if technician_intent:
            try:
                technician_scope = scope_from_request(request)
                answer = technician_answer(technician_intent, technician_scope, fetch_all, user_text)
            except Exception:
                answer = 'Tôi chưa thể tra cứu dữ liệu của bạn lúc này. Bạn vui lòng thử lại.'
            async def technician_stream():
                yield _mes_rich_text_sse(answer, body)
                await _save_ai_history(request, _history_id_from_request(request, body), user_text, answer)
                yield 'data: [DONE]\n\n'
            return StreamingResponse(technician_stream(), media_type='text/event-stream',
                                     headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    # Luồng tự tra cứu: không để LLM đoán vai trò hoặc hỏi lại quyền đã xác thực.
    # Các câu này đã có nguồn dữ liệu rõ ràng nên phải truy vấn trực tiếp, không fallback sang Vanna.
    from backend.ai_conversation import _normalize as _normalize_intent
    normalized_intent = _normalize_intent(user_text)
    asks_my_reports = (
        ('bao cao' in normalized_intent and
         any(x in normalized_intent for x in ('da nop', 'toi nop', 'cua toi', 'minh nop', 'da gui')))
        or ('so bao cao' in normalized_intent and 'toi' in normalized_intent)
    )
    asks_my_workshop_orders = (
        greeting_role == 'team_lead' and
        ('xuong cua toi' in normalized_intent or 'xuong toi' in normalized_intent) and
        any(x in normalized_intent for x in ('cong don', 'don hang', 'don nao', 'danh sach don'))
    )
    if asks_my_reports or asks_my_workshop_orders:
        try:
            scoped_user = scope_from_request(request)
            if asks_my_reports:
                if scoped_user.role != 'technician':
                    answer = ('Câu hỏi này dùng để thống kê báo cáo do chính kỹ thuật viên nộp. '
                              'Tài khoản hiện tại không có thống kê cá nhân theo chức năng này.')
                elif scoped_user.is_empty:
                    answer = 'Tài khoản kỹ thuật viên chưa có phạm vi máy được phân công.'
                else:
                    tech = fetch_all(
                        "SELECT id FROM app_users WHERE lower(username)=lower(%s) "
                        "AND role='technician' AND is_active=TRUE", (scoped_user.username,))
                    if not tech:
                        answer = 'Không xác định được kỹ thuật viên trong phiên đăng nhập.'
                    else:
                        count_rows = fetch_all(
                            'SELECT COUNT(*)::integer AS total FROM task_reports WHERE author_id=%s',
                            (tech[0]['id'],))
                        total = int(count_rows[0]['total'])
                        answer = (f'Bạn đã nộp **{total} lượt báo cáo công việc**. '
                                  'Số liệu được lấy theo tài khoản kỹ thuật viên đang đăng nhập.')
            elif scoped_user.role != 'team_lead' or scoped_user.is_empty:
                answer = 'Tài khoản chưa có xưởng được phân quyền để tra cứu công đơn.'
            else:
                where_sql, where_params = _customer_order_where(scoped_user, 'all')
                orders = fetch_all(
                    'SELECT co.id, co.status, co.quantity, w.workshop_name '
                    'FROM customer_orders co LEFT JOIN workshops w ON w.id=co.workshop_id '
                    'WHERE ' + where_sql + ' ORDER BY co.id DESC LIMIT 101', where_params)
                if len(orders) > 100:
                    answer = 'Có hơn 100 công đơn trong xưởng phụ trách; vui lòng lọc theo trạng thái hoặc mã CD.'
                elif not orders:
                    answer = 'Chưa có công đơn nào trong phạm vi xưởng bạn phụ trách.'
                else:
                    from backend.analysis_reports import LABELS, fmt_number
                    lines = [f'**Công đơn trong xưởng phụ trách: {len(orders)}**', '']
                    for order in orders:
                        lines.append(
                            f"• **CD-{int(order['id']):07d}** · "
                            f"{LABELS.get(order['status'], order['status'])} · "
                            f"{fmt_number(order['quantity'])} SP · "
                            f"{order['workshop_name'] or 'Chưa xác định xưởng'}")
                    answer = '\n'.join(lines)
        except Exception:
            answer = 'Chưa thể tra cứu dữ liệu từ Database lúc này. Vui lòng thử lại.'
        async def scoped_intent_stream():
            yield _mes_rich_text_sse(answer, body)
            await _save_ai_history(request, _history_id_from_request(request, body), user_text, answer)
            yield 'data: [DONE]\n\n'
        return StreamingResponse(scoped_intent_stream(), media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    # Hỏi các máy đang sản xuất: truy vấn máy Running + liên kết công đơn,
    # luôn kiểm tra scope theo ID máy trước khi trả thông tin cho AI.
    if _is_running_machine_question(user_text):
        try:
            scope = scope_from_request(request)
            if scope.role not in ('admin', 'team_lead', 'technician') or scope.is_empty:
                answer = "Tài khoản không có quyền hoặc phạm vi máy để tra cứu."
            else:
                answer = _format_running_machines(_query_running_machines(scope))
        except Exception:
            answer = "Không thể kiểm tra trạng thái máy lúc này. Vui lòng thử lại."
        async def running_stream():
            yield _mes_rich_text_sse(answer, body)
            await _save_ai_history(request, _history_id_from_request(request, body), user_text, answer)
            yield 'data: [DONE]\n\n'
        return StreamingResponse(running_stream(), media_type='text/event-stream',
                                 headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    # Câu hỏi nghiệp vụ cố định: trạng thái chờ Admin xác nhận hoàn thành.
    # Không để mô hình nhầm với customer_orders.status='pending_admin' (duyệt ban đầu).
    normalized = user_text.casefold()
    is_completion_question = (
        ("admin" in normalized or "quản trị" in normalized)
        and any(k in normalized for k in ("duyệt", "xác nhận", "chờ"))
        and any(k in normalized for k in ("hoàn thành", "kết thúc", "kết thuc"))
        and any(k in normalized for k in ("công đơn", "đơn", "bao nhiêu", "những"))
    )
    if is_completion_question:
        try:
            scope = scope_from_request(request)
            if scope.role not in ("admin", "team_lead") or scope.is_empty:
                answer = "Tài khoản không được phép tra cứu danh sách công đơn chờ Admin xác nhận hoàn thành."
            else:
                where_sql, params = _customer_order_where(scope, "pending_completion_approval")
                rows = fetch_all("""SELECT co.id, co.quantity, w.workshop_name
                    FROM customer_orders co LEFT JOIN workshops w ON w.id=co.workshop_id
                    WHERE """ + where_sql + " ORDER BY co.completion_requested_at DESC, co.id DESC LIMIT 100", params)
                total = int(fetch_all("SELECT COUNT(*)::integer AS total FROM customer_orders co WHERE " + where_sql, params)[0]["total"])
                if not total:
                    answer = "Hiện không có công đơn nào đang chờ Admin xác nhận hoàn thành trong phạm vi tài khoản."
                else:
                    lines = [f"- CD-{int(r['id']):07d}: {r['workshop_name'] or 'Chưa xác định xưởng'}, {int(r['quantity'] or 0)} sản phẩm" for r in rows]
                    answer = f"Có {total} công đơn đang chờ Admin xác nhận hoàn thành trong phạm vi tài khoản:\n" + "\n".join(lines)
                    if total > len(rows):
                        answer += f"\nĐang hiển thị {len(rows)}/{total} công đơn."
            async def completion_stream():
                yield _mes_rich_text_sse(answer, body)
                await _save_ai_history(request, _history_id_from_request(request, body), user_text, answer)
                yield 'data: [DONE]\n\n'
            return StreamingResponse(completion_stream(), media_type="text/event-stream",
                                     headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
        except Exception:
            # Không fallback sang LLM với câu hỏi đã biết mà query lỗi: tránh trả 0 bịa.
            answer = "Không thể kiểm tra dữ liệu công đơn chờ Admin duyệt lúc này. Vui lòng thử lại."
            async def completion_error_stream():
                yield _mes_rich_text_sse(answer, body)
                yield 'data: [DONE]\n\n'
            return StreamingResponse(completion_error_stream(), media_type="text/event-stream")

    # Chế độ phân tích chi tiết công đơn CD / sản xuất theo đúng quyền người đăng nhập.
    from backend.analysis_reports import wants_analysis, internal_report
    cd_match = re.search(r"\bCD-?(0*\d+)\b", user_text, flags=re.IGNORECASE)
    normalized_analysis = user_text.casefold()
    analyze_cd_or_overview = wants_analysis(user_text) and (
        cd_match is not None or any(word in normalized_analysis for word in (
            'nhà máy', 'toàn hệ thống', 'toàn bộ', 'xưởng', 'công đơn',
            'sản xuất', 'hiệu suất', 'tổng quan', 'tình hình', 'máy'))
    )
    # Chưa có dữ liệu công việc/nhân sự trong báo cáo CD: để công cụ nghiệp vụ
    # hiện hữu xử lý thay vì trả một báo cáo sai chủ đề.
    if not cd_match and any(term in normalized_analysis for term in (
            'kỹ thuật viên', 'nhân viên', 'giao việc', 'báo cáo công việc')):
        analyze_cd_or_overview = False
    if analyze_cd_or_overview:
        try:
            analysis_scope = scope_from_request(request)
            if analysis_scope.role not in ('admin', 'team_lead', 'technician') or analysis_scope.is_empty:
                answer = 'Tài khoản không có quyền hoặc phạm vi dữ liệu để phân tích nội bộ.'
            else:
                where_sql, where_params = _customer_order_where(analysis_scope, 'all')
                if cd_match:
                    where_sql += ' AND co.id=%s'
                    where_params += (int(cd_match.group(1)),)
                if not cd_match:
                    order_status = ('in_production' if 'đang sản xuất' in normalized_analysis
                                    else 'completed' if 'đã hoàn thành' in normalized_analysis
                                    else 'rejected' if 'bị từ chối' in normalized_analysis
                                    else None)
                    if order_status:
                        where_sql += ' AND co.status=%s'
                        where_params += (order_status,)
                # Áp dụng bộ lọc đối tượng được hỏi, không trả cả xưởng khi
                # người dùng hỏi một xưởng hay một máy cụ thể.
                requested_machine = re.search(r'\bMC\d{3}\b', user_text, re.I)
                workshop_token = next((part for part in ('chip', 'smt', 'lắp ráp')
                                       if part in normalized_analysis), None)
                if requested_machine:
                    where_sql += (" AND EXISTS (SELECT 1 FROM customer_order_machines cm "
                                  "JOIN machines req_m ON req_m.id=cm.machine_id "
                                  "WHERE cm.customer_order_id=co.id "
                                  "AND upper(req_m.machine_code)=%s)")
                    where_params += (requested_machine.group(0).upper(),)
                if workshop_token:
                    where_sql += ' AND EXISTS (SELECT 1 FROM workshops req_w WHERE req_w.id=co.workshop_id AND req_w.workshop_name ILIKE %s)'
                    where_params += ('%' + workshop_token + '%',)
                scoped_orders = fetch_all("""SELECT co.id, co.status, co.quantity, co.expected_date,
                        w.workshop_name,
                        CASE WHEN co.status='completed' THEN 100
                             WHEN co.status='in_production' AND co.quantity>0
                                  AND COALESCE(progress.stage_count,0)>0
                             THEN LEAST(100,GREATEST(0,ROUND(100.0*progress.quantity_sum/
                                  (co.quantity*progress.stage_count),2)))
                             ELSE 0 END AS progress_percent
                    FROM customer_orders co
                    LEFT JOIN workshops w ON w.id=co.workshop_id
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS stage_count,
                               COALESCE(SUM(s.quantity_completed),0) AS quantity_sum
                        FROM customer_order_stage_progress s
                        WHERE s.customer_order_id=co.id
                    ) progress ON TRUE
                    WHERE """ + where_sql + ' ORDER BY co.id DESC LIMIT 501', where_params)
                if len(scoped_orders)>500:
                    answer = 'Có hơn 500 công đơn trong phạm vi truy cập. Vui lòng thu hẹp theo mã CD hoặc xưởng để có báo cáo đầy đủ.'
                elif cd_match and not scoped_orders:
                    answer = 'Không tìm thấy công đơn CD trong phạm vi tài khoản được phép xem.'
                else:
                    machines_for_report = []
                    if cd_match:
                        # A completed CD has historical assignments even when no
                        # machine is currently Running. Read only this scoped CD.
                        machines_for_report = fetch_all("""SELECT m.machine_code, m.status
                            FROM customer_order_machines cm
                            JOIN machines m ON m.id=cm.machine_id
                            WHERE cm.customer_order_id=%s
                            ORDER BY m.machine_code""", (int(cd_match.group(1)),))
                    elif any(k in normalized_analysis for k in ('nhà máy', 'xưởng', 'máy', 'sản xuất', 'toàn bộ')):
                        machines_for_report = _query_running_machines(analysis_scope)
                        if requested_machine:
                            machines_for_report = [m for m in machines_for_report
                                                   if m['machine_code'].upper() == requested_machine.group(0).upper()]
                        if workshop_token:
                            machines_for_report = [m for m in machines_for_report
                                                   if workshop_token in (m.get('workshop_name') or '').casefold()]
                        machines_for_report = [dict(m, status='Running') for m in machines_for_report]
                    report_label = ('công đơn CD-' + str(int(cd_match.group(1))).zfill(7)) if cd_match else 'phạm vi tài khoản'
                    if requested_machine: report_label += ', máy ' + requested_machine.group(0).upper()
                    if workshop_token: report_label += ', xưởng ' + workshop_token
                    answer = internal_report(scoped_orders, machines_for_report, label=report_label)
        except Exception:
            answer = 'Không thể tổng hợp báo cáo phân tích từ Database lúc này. Vui lòng thử lại.'
        async def analysis_stream():
            yield _mes_rich_text_sse(answer, body)
            await _save_ai_history(request, _history_id_from_request(request, body), user_text, answer)
            yield 'data: [DONE]\n\n'
        return StreamingResponse(analysis_stream(), media_type='text/event-stream',
                                 headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    # Các câu hỏi không thuộc luồng nghiệp vụ cố định được xử lý qua Vanna.
    chat_request = ChatRequest(**body)
    if not user_text:
        candidate = getattr(chat_request, 'message', None)
        if isinstance(candidate, str):
            user_text = candidate.strip()
        elif isinstance(candidate, dict):
            user_text = _extract_user_text(candidate)
    metadata = getattr(chat_request, "metadata", None) or {}
    chat_request.metadata = metadata
    chat_request.request_context = RequestContext(
        cookies=dict(request.cookies),
        headers=dict(request.headers),
        remote_addr=request.client.host if request.client else None,
        query_params=dict(request.query_params),
        metadata=chat_request.metadata,
    )
 
    history_id = _history_id_from_request(request, body)
    async def generate():
        try:
            visible_answer = ''
            async for chunk in mes_chat_handler.handle_stream(chat_request):
                text_piece = _history_stream_text(chunk)
                if text_piece:
                    if text_piece.startswith(visible_answer) and len(text_piece)>len(visible_answer):
                        visible_answer=text_piece  # cumulative streaming content
                    elif text_piece != visible_answer and not visible_answer.endswith(text_piece):
                        visible_answer += ('\n' if visible_answer and len(text_piece)>100 else '') + text_piece
                yield f"data: {chunk.model_dump_json()}\n\n"
            if not visible_answer.strip() or not user_text.strip():
                import logging
                logging.getLogger('mes.ai_history').warning(
                    'History exchange missing input: question_chars=%s answer_chars=%s session=%s',
                    len(user_text or ''),len(visible_answer or ''),history_id)
            await _save_ai_history(request, history_id, user_text, visible_answer)
            yield "data: [DONE]\n\n"
        except Exception:
            import logging
            logging.getLogger('mes.ai').exception('Vanna chat stream failed')
            yield _mes_rich_text_sse(
                'Hiện chưa lấy được câu trả lời từ AI. Vui lòng thử gửi lại câu hỏi hoặc kiểm tra kết nối máy chủ.',
                body,
            )
            yield 'data: [DONE]\n\n'
 
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
 
# Serve toàn bộ file frontend trong thư mục static
static_dir = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "static"
)
 
app.mount(
    "/static",
    StaticFiles(directory=static_dir),
    name="static"
)
 
 
# ============================================================
# STEP 5 - OPERATIONS DASHBOARD
# Frontend derives operational KPIs from the existing PO endpoint.
# No new database tables or unverified OEE assumptions are introduced.
# ============================================================
# STEP 4 - FRONTEND ANALYSIS API
# The PO endpoint already exposes structured analysis for the dashboard UI.
# ============================================================
# CUSTOM HOME PAGE
# ============================================================
 
# Xóa route "/" mặc định của Vanna
app.router.routes = [
    route
    for route in app.router.routes
    if getattr(route, "path", None) != "/"
]
 
 
@app.get("/", include_in_schema=False)
async def custom_home():
    return FileResponse(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "static",
            "index.html",
        ),
        headers={"Cache-Control": "no-store, max-age=0"},
    )
 
 
# Các API dữ liệu (nhân viên, chấm công, xưởng, dashboard) nằm ở routes_data.py.
app.include_router(data_router)


def _check_scope_ready() -> None:
    """Cảnh báo sớm nếu chưa chạy migration phân quyền theo máy."""
    try:
        row = fetch_all(
            "SELECT to_regclass('public.machine_assignments') IS NOT NULL AS tbl, "
            "to_regclass('public.app_scope_sessions') IS NOT NULL AS sess, "
            "EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_scoped') AS r1, "
            "EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_admin') AS r2"
        )[0]
        if not all(row.values()):
            print("[SCOPE] CẢNH BÁO: chưa có đủ bảng/role phân quyền theo máy "
                  f"({row}). Hãy chạy: py scripts/apply_migration.py")
    except Exception as exc:
        print(f"[SCOPE] Không kiểm tra được phân quyền theo máy: {exc}")


_check_scope_ready()


# Giai đoạn 2: công việc và duyệt
from backend.routes_tasks import router as work_router
app.include_router(work_router)


# Thống kê kết quả công việc kỹ thuật viên
from backend.routes_work_metrics import router as work_metrics_router
app.include_router(work_metrics_router)

# API quản lý Production Order: chỉ Admin được tạo/ghi sản lượng/hoàn thành
from backend.routes_production_orders import router as production_order_router
app.include_router(production_order_router)


from backend.routes_customer_orders import router as customer_orders_router
# Place the customer API routes ahead of broad Vanna-generated routes.
# Otherwise the POST /companies path may be consumed by an earlier GET route (405).
_customer_route_start = len(app.router.routes)
app.include_router(customer_orders_router)
_customer_routes = app.router.routes[_customer_route_start:]
del app.router.routes[_customer_route_start:]
app.router.routes[0:0] = _customer_routes

# V43: Vanna may register a broad catch-all route ahead of application APIs.
# Give the per-account history API priority over the Vanna catch-all;
# otherwise GET /api/ai-history can incorrectly return 404 "Not Found".
_history_routes = [route for route in app.router.routes
                   if str(getattr(route, 'path', '')).startswith('/api/ai-history')]
if _history_routes:
    app.router.routes = [route for route in app.router.routes if route not in _history_routes]
    app.router.routes[0:0] = _history_routes

if __name__ == "__main__":
    import uvicorn
 
    print("VANNA AI + Production Dashboard")
    print("URL: http://127.0.0.1:8000")
 
    # Đặt DEV_RELOAD=1 để server tự khởi động lại khi sửa file .py (chỉ dùng khi phát triển).
    dev_reload = os.getenv("DEV_RELOAD") == "1"
    uvicorn.run(
        "app:app" if dev_reload else app,
        host="127.0.0.1",
        port=8000,
        reload=dev_reload,
    )

