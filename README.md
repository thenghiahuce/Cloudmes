# TestMES2 – Vanna AI & Production Dashboard

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

File `database/DATABASE_TONG_HOP.sql` (phục vụ minh chứng báo cáo đồ án) đã được loại khỏi bản chuẩn bị Git. Các file SQL thực thi vẫn giữ nguyên.

## 2. Yêu cầu

- Python **3.12** (phù hợp với môi trường đã triển khai trên VPS).
- PostgreSQL (môi trường VPS sử dụng PostgreSQL 17, cổng 5433; máy mới có thể dùng cổng 5432).
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

Mở `.env` và điền cấu hình **trên máy của bạn** (không gửi lên GitHub):

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

Tạo `AUTH_SECRET` mạnh bằng:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> Không dùng nguyên mẫu mật khẩu, secret hoặc API key thật trong README. `.env` đã bị loại khỏi ZIP này và được `.gitignore` chặn.

## 4. Cơ sở dữ liệu (đọc kỹ trước khi chạy)

- **VPS/production có dữ liệu:** không chạy lại `database/schema.sql`, `database/seeds/seed.sql` hay toàn bộ migration. Sao lưu và đối chiếu migration với schema hiện tại trước khi thay đổi.
- **CSDL mới hoàn toàn:** có thể tham khảo `database/schema.sql`, sau đó `database/auth.sql`, các migration cần thiết. `schema.sql` có `DROP TABLE`, chỉ thực hiện khi chắc chắn DB đang trống và có bản sao lưu.
- `scripts/apply_migration.py --no-seed` chỉ thực hiện một phần cài đặt phân quyền (`auth.sql` + `001_machine_scope.sql`), **không** tự áp dụng tất cả migration.
- `scripts/apply_phase2.py` chỉ chạy `002_tasks.sql` (không chạy `002_tasks_reviews.sql`).
- `database/seeds/` là dữ liệu minh họa; **không dùng để ghi đè dữ liệu thật**.

Do lịch sử migration chưa có trình quản lý phiên bản thống nhất, bước khởi tạo database hoàn chỉnh từ số 0 cần được kiểm chứng trên một database thử nghiệm riêng trước khi công bố là quy trình cài đặt tự động.

## 5. Chạy ứng dụng

Sau khi bảo đảm CSDL và các role `ai_scoped` / `ai_admin` được cấu hình đúng:

```bash
python app.py
```

Theo code hiện tại, Uvicorn lắng nghe tại **http://127.0.0.1:8000** (mặc định chỉ truy cập từ chính máy chủ). Mở `/login` và đăng nhập bằng tài khoản đã tạo trong `app_users`. Trên VPS, đặt Nginx làm reverse proxy HTTPS; không đổi trực tiếp Uvicorn sang `0.0.0.0` khi chưa cấu hình bảo mật.

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

## 7. Đẩy lên GitHub (từ thư mục `testmes2`)

```bash
git init
git add .
git status --short
git commit -m "Prepare TestMES2 source, docs and unit tests"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

Thay `YOUR_USERNAME/YOUR_REPO` bằng repository **của bạn**. Nếu repository đã có `origin`, xem `git remote -v` trước khi thêm. **Kiểm tra `git status` và `git ls-files` để chắc chắn không có `.env`, file khóa, backup dữ liệu hoặc môi trường Python.** Nếu bí mật từng được commit vào lịch sử Git, chỉ `.gitignore` không đủ: phải thu hồi/đổi bí mật và xử lý lịch sử repository.

## 8. Việc nên ưu tiên trước khi dùng công khai

- Bảo đảm cookie đăng nhập có `Secure` khi chạy qua HTTPS; cookie hiện dùng `HttpOnly` và `SameSite=Lax`.
- Khi tài khoản bị vô hiệu hóa hoặc đổi role, xác minh lại quyền từ database thay vì chỉ dựa vào role của cookie còn hạn.
- Đổi mật khẩu mẫu/yếu, bỏ cách truyền mật khẩu qua tham số dòng lệnh, áp dụng chính sách mật khẩu mạnh.
- Kiểm thử tích hợp RLS theo từng tài khoản và từng máy: role `testmes_app` đang là chủ sở hữu các bảng nên có thể vượt RLS nếu truy vấn trực tiếp bằng role chủ sở hữu.
- Tránh trả lỗi PostgreSQL chi tiết cho trình duyệt.
- Kiểm thử các luồng CRUD, duyệt công đơn và hỏi đáp AI trước khi cập nhật VPS.

Chi tiết phân tích và các file nên dọn: xem [`CODE_REVIEW.md`](CODE_REVIEW.md).
