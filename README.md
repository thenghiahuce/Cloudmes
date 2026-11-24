# Cloudmes – Vanna AI & Production Dashboard

Ứng dụng hỗ trợ quản lý thông tin sản xuất, công đơn, máy móc, công việc và hỏi đáp dữ liệu bằng Vanna AI. Backend sử dụng **Python/FastAPI**, **PostgreSQL** và **Vanna AI**; frontend là HTML/CSS/JavaScript.

> **Lưu ý:** README hướng dẫn chạy mã nguồn của bản ZIP được cung cấp. Đây chưa phải bộ cài database một lệnh cho môi trường mới. Các migration lịch sử phải được xem xét theo trạng thái CSDL thực tế; **không chạy `database/schema.sql` trên CSDL đang có dữ liệu** vì file này có các lệnh `DROP TABLE`.

## 1. Cấu trúc dự án

```text
app.py                         # Điểm vào FastAPI và Vanna AI
backend/                       # Xác thực, phân quyền/RLS, các API nghiệp vụ
knowledge/                     # Prompt/tri thức cho AI
database/
  schema.sql                   # Tạo cấu trúc ban đầu, có DROP TABLE: chỉ dùng DB mới
  auth.sql                     # Bảng tài khoản
  migrations/                  # Các thay đổi CSDL theo từng giai đoạn
  seeds/                       # Dữ liệu demo, không dùng cho production
scripts/                        # Quản lý user và triển khai migration
static/                         # HTML, CSS, JS
  index.html
  login.html
tests/                          # Kiểm thử logic không cần DB/API key
.github/workflows/ci.yml        # Chạy kiểm thử khi push / PR
.env.example                    # Mẫu cấu hình, không chứa bí mật
```


## 2. Yêu cầu

- Python **3.12** .
- PostgreSQL.
- Tài khoản/cơ sở dữ liệu PostgreSQL đã được tạo, có đúng schema và migrations tương ứng.
- OpenAI API key đang hoạt động và tài khoản có quyền sử dụng model đặt trong `.env`.

## 3. Cài đặt môi trường

### Linux / Ubuntu

```bash
cd testmes2
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

### Windows PowerShell

```powershell
cd testmes2
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Mở `.env` và điền cấu hình :

```dotenv
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DATABASE=testmes
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=your_local_password
OPENAI_API_KEY=your_new_openai_key
OPENAI_MODEL=gpt-4.1-mini
AUTH_SECRET=replace_with_random_secret
```

## 4. Cơ sở dữ liệu (đọc kỹ trước khi chạy)

- **VPS/production có dữ liệu:** không chạy lại `database/schema.sql`, `database/seeds/seed.sql` hay toàn bộ migration. Sao lưu và đối chiếu migration với schema hiện tại trước khi thay đổi.
- **CSDL mới hoàn toàn:** có thể tham khảo `database/schema.sql`, sau đó `database/auth.sql`, các migration cần thiết. `schema.sql` có `DROP TABLE`, chỉ thực hiện khi chắc chắn DB đang trống và có bản sao lưu.
- `scripts/setup_permissions.py --no-seed` chỉ thực hiện một phần cài đặt phân quyền (`auth.sql` + `001_phan_quyen_may.sql`), **không** tự áp dụng tất cả migration.
- `scripts/setup_tasks.py` chỉ chạy `002_giao_viec_bao_cao.sql` (không chạy `002_giao_viec_cu.sql`).
- `database/seeds/` là dữ liệu minh họa; **không dùng để ghi đè dữ liệu thật**.

## 5. Chạy ứng dụng

Sau khi bảo đảm CSDL và các role `ai_scoped` / `ai_admin` được cấu hình đúng:

```bash
python app.py
```

Theo code hiện tại, truy cập Cloudmes.xyz. Mở `/login` và đăng nhập bằng tài khoản đã tạo trong `app_users`.

## 6. Chạy kiểm thử

Bộ test hiện tại **không cần PostgreSQL hoặc API key**; kiểm thử mật khẩu, token phiên, middleware và phạm vi máy ở mức đơn vị:

```bash
python -m unittest discover -s tests -v
python -m compileall -q app.py backend knowledge scripts
```

Nếu có Node.js:

```bash
node --check static/js/app.js
```

GitHub Actions trong `.github/workflows/ci.yml` tự chạy các bài test này mỗi lần push/pull request. **Chưa có integration test kết nối PostgreSQL, Vanna AI hoặc browser.** Test xanh không chứng minh rằng mọi API đã an toàn hay toàn bộ dashboard chạy đúng với dữ liệu thật.

## Từ điển dữ liệu và tên migration

Xem [Từ điển bảng và migration](docs/tu_dien_bang_va_migration.md). Migration đã đổi tên tiếng Việt không dấu; file 002 cũ được lưu trong ZIP lưu trữ riêng. Không chạy lại SQL chỉ vì đổi tên.

Xem [thứ tự migration 001–012 và đối chiếu tên cũ](database/README.md). Các SQL lịch sử được đưa ra ngoài mã nguồn chính, vào ZIP lưu trữ riêng.
