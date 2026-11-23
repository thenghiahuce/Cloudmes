"""
Xác thực và phân quyền nội bộ (chỉ dùng thư viện chuẩn của Python).
 
Vai trò:
  - admin       : xem tất cả (Dashboard, AI Assistant, Nhân viên, Chấm công, /docs) và TẤT CẢ máy
  - team_lead   : Tổ trưởng      -> Dashboard + AI Assistant, chỉ trên các máy được gán
  - technician  : Kỹ thuật viên / Kỹ sư -> Dashboard + AI Assistant, chỉ trên các máy được gán
Danh sách máy được gán nằm ở bảng machine_assignments (xem backend/scope.py).
 
Phiên đăng nhập là cookie HttpOnly được ký HMAC-SHA256 bằng AUTH_SECRET.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from http.cookies import SimpleCookie
 
# Tự nạp file .env (để đọc AUTH_SECRET dù module này được import trước load_dotenv() của app).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
 
COOKIE_NAME = "session"
SESSION_SECONDS = 8 * 3600  # 8 giờ
 
ROLE_ADMIN = "admin"
ROLE_TEAM_LEAD = "team_lead"
ROLE_TECHNICIAN = "technician"
ROLE_CUSTOMER = "customer"
ROLE_LABELS = {
    ROLE_ADMIN: "Quản trị viên",
    ROLE_TEAM_LEAD: "Tổ trưởng",
    ROLE_TECHNICIAN: "Kỹ thuật viên",
    ROLE_CUSTOMER: "Khách hàng",
}
 
# Chỉ admin được gọi các đường dẫn này (khớp theo tiền tố).
ADMIN_ONLY_PREFIXES = (
    "/api/employees",
    "/api/attendance",
    "/docs",
    "/redoc",
    "/openapi.json",
)
# Không cần đăng nhập.
PUBLIC_PATHS = {"/login", "/api/auth/login", "/favicon.ico"}
 
_secret_env = os.getenv("AUTH_SECRET", "").strip()
if _secret_env:
    _SECRET = _secret_env.encode("utf-8")
else:
    # Không có AUTH_SECRET: tạo ngẫu nhiên, mọi người sẽ phải đăng nhập lại khi khởi động lại server.
    _SECRET = secrets.token_bytes(32)
    print("[AUTH] Chưa đặt AUTH_SECRET trong .env - dùng khóa tạm, "
          "phiên đăng nhập sẽ mất khi khởi động lại server.")
 
 
# ------------------------------------------------------------
# Mật khẩu
# ------------------------------------------------------------
_N, _R, _P = 2 ** 14, 8, 1
 
 
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P,
        base64.b64encode(salt).decode(),
        base64.b64encode(dk).decode(),
    )
 
 
def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False
 
 
# Băm giả để thời gian phản hồi không lộ việc tên đăng nhập có tồn tại hay không.
_DUMMY_HASH = hash_password("dummy-password-for-timing")
 
 
# ------------------------------------------------------------
# Token phiên
# ------------------------------------------------------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
 
 
def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
 
 
def make_token(username: str, full_name: str, role: str) -> str:
    payload = {"u": username, "n": full_name, "r": role,
               "exp": int(time.time()) + SESSION_SECONDS}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64e(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"
 
 
def read_token(token: str):
    try:
        body, sig = token.split(".")
        expected = _b64e(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(body))
        if payload.get("exp", 0) < time.time():
            return None
        if payload.get("r") not in ROLE_LABELS:
            return None
        return {"username": payload["u"], "full_name": payload.get("n") or payload["u"],
                "role": payload["r"]}
    except Exception:
        return None
 
 
def session_from_scope(scope):
    """Đọc cookie phiên từ scope ASGI (http hoặc websocket)."""
    for key, value in scope.get("headers", []):
        if key == b"cookie":
            jar = SimpleCookie()
            try:
                jar.load(value.decode("latin-1"))
            except Exception:
                return None
            morsel = jar.get(COOKIE_NAME)
            return read_token(morsel.value) if morsel else None
    return None
 
 
# ------------------------------------------------------------
# Giới hạn đăng nhập sai (chống dò mật khẩu)
# ------------------------------------------------------------
_MAX_FAILS = 5
_LOCK_SECONDS = 300
_fails: dict[str, list] = {}
 
 
def is_locked(key: str) -> bool:
    entry = _fails.get(key)
    if not entry:
        return False
    count, until = entry
    if until and until > time.time():
        return True
    if until and until <= time.time():
        _fails.pop(key, None)
    return False
 
 
def register_fail(key: str) -> None:
    count, until = _fails.get(key, [0, 0])
    count += 1
    until = time.time() + _LOCK_SECONDS if count >= _MAX_FAILS else 0
    _fails[key] = [count, until]
 
 
def clear_fails(key: str) -> None:
    _fails.pop(key, None)
 
 
# ------------------------------------------------------------
# Middleware ASGI thuần (an toàn với SSE/WebSocket của Vanna)
# ------------------------------------------------------------
class AuthMiddleware:
    def __init__(self, app):
        self.app = app
 
    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
 
        path = scope.get("path", "")
        if scope.get("method") == "OPTIONS" or path in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
 
        session = session_from_scope(scope)
        if session is None:
            await self._deny(scope, send, 401)
            return
        if session["role"] != ROLE_ADMIN and path.startswith(ADMIN_ONLY_PREFIXES):
            await self._deny(scope, send, 403)
            return
 
        # Customer accounts may only access their own customer-order APIs, auth and public UI assets.
        # Block legacy production endpoints, SQL-powered AI and websocket routes.
        if session['role'] == ROLE_CUSTOMER:
            allowed = (path in ('/', '/index.html', '/api/auth/me', '/api/auth/logout')
                       or path.startswith('/static/') or path.startswith('/api/customer-orders')
                       or path == '/api/ai-history' or path.startswith('/api/ai-history/'))
            if not allowed:
                await self._deny(scope, send, 403)
                return
        scope.setdefault("state", {})["user"] = session
        await self.app(scope, receive, send)
 
    @staticmethod
    async def _deny(scope, send, status):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
 
        path = scope.get("path", "")
        if status == 401 and not path.startswith("/api/"):
            await send({"type": "http.response.start", "status": 302,
                        "headers": [(b"location", b"/login"), (b"content-length", b"0")]})
            await send({"type": "http.response.body", "body": b""})
            return
 
        message = "Chưa đăng nhập" if status == 401 else "Bạn không có quyền truy cập"
        body = json.dumps({"detail": message}, ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
 
 
# ------------------------------------------------------------
# Trang đăng nhập: đọc từ file login.html (sửa file này để đổi giao diện,
# không cần khởi động lại server)
# ------------------------------------------------------------
LOGIN_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "login.html"
)
 
 
def login_page_html() -> str:
    try:
        with open(LOGIN_FILE, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "<h1>Không tìm thấy file login.html</h1>"
 