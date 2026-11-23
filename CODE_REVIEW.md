# Đánh giá và chuẩn bị mã nguồn TestMES2 lên GitHub

**Nguồn:** `testmes2(6).zip`, bản mã nguồn chụp tại thời điểm xuất ZIP. Không đồng nghĩa với bản triển khai VPS hiện tại.

## Thực hiện trong bản Git-ready

1. **Đã loại** file `database/DATABASE_TONG_HOP.sql`: tổng hợp SQL để giáo viên xem, tất cả nội dung nghiệp vụ chỉ nằm trong chú thích; không thấy mã thực thi tham chiếu đến đường dẫn này.
2. **Đã loại** `.env` có bí mật ra khỏi bản chia sẻ. **Không** chia sẻ hoặc push file này.
3. **Đã loại** `__pycache__/` và các file `*.pyc`; đã mở rộng `.gitignore` cho `.venv312/`, `.python-runtime/`, backup, file khóa.
4. **Đã thêm** `README.md`, `tests/` và `.github/workflows/ci.yml` (test không cần DB, API key).
5. **Không chỉnh sửa** logic nghiệp vụ, đường dẫn route hay SQL production trong bản Git-ready để tránh ảnh hưởng Dashboard.

## Ưu tiên xử lý sau

| Ưu tiên | File | Nhận xét / giải pháp đề xuất |
| --- | --- | --- |
| **Cao** | `backend/auth.py`, `app.py` | Cookie chứa role phiên 8 giờ; khi khóa tài khoản/đổi quyền cần kiểm tra lại trạng thái DB cho các request nhạy cảm; `set_cookie` chưa có `secure=True` trong code ZIP. |
| **Cao** | `scripts/manage_users.py` | Chấp nhận mật khẩu 6 ký tự và mật khẩu dưới dạng CLI args (`add`/`sync-staff`); chuyển sang `getpass`, tối thiểu 12 ký tự, tránh mật khẩu dùng chung. |
| **Cao** | `backend/scope.py`, `backend/db.py`, các route | Kiểm thử tích hợp các truy vấn có sử dụng `fetch_all` quyền chủ bảng, đảm bảo dữ liệu bị giới hạn đúng trên cả AI và API. `testmes_app` là owner nên có thể vượt RLS. Không bật `FORCE RLS` mà không kiểm tra nghiệp vụ ghi. |
| **Trung bình** | `backend/routes_data.py` | Tránh trả lỗi PostgreSQL nguyên văn về client; ghi log phía server, trả thông báo chung. |
| **Trung bình** | `backend/routes_ai_history.py` | Tự chạy `CREATE TABLE` trong request dù đã có `023_ai_chat_history.sql`; nên thực hiện migration trước khi khởi động. |
| **Trung bình** | `app.py` (~1.500 dòng), `static/js/app.js`, `static/css/style.css`, `backend/routes_customer_orders.py` | Tách nhỏ theo domain khi có test tích hợp; không nên viết lại ồ ạt trước khi demo. |
| **Trung bình** | `database/migrations/` | Hai file đầu số `002` (`002_tasks.sql` và `002_tasks_reviews.sql`); thống nhất trình tự/version và lưu lại migration nào đã chạy. `apply_phase2.py` chỉ tham chiếu file thứ nhất. |
| **Thấp** | `static/css/ai-vanna-shadow-phase12.css` | Không thấy được tham chiếu trong mã ZIP; có thể bỏ sau khi đối chiếu giao diện thực tế và tài nguyên tải động. |
| **Thấp** | `scripts/khoi_phuc_tai_khoan_oppo_pgadmin4.sql` | Script khôi phục thủ công cho tài khoản cụ thể; không phải runtime. Nên cất riêng `ops/` hoặc nội bộ, không cần công bố công khai nếu không còn sử dụng. |

## Lưu ý phạm vi xác minh

- Có kiểm tra cú pháp tĩnh (Python/JS) và bộ test logic authentication/scope.
- **Chưa** kiểm thử PostgreSQL với dữ liệu trên VPS, Vanna AI gọi OpenAI, trình duyệt, ghi/duyệt công đơn hoặc phân quyền toàn hệ thống.
- Thay đổi cấu trúc folder như đổi `backend/`, `static/`, `database/` cần cập nhật import, route, đường dẫn trong code và được test đầy đủ. Vì thế bản này chủ động giữ nguyên cấu trúc runtime.
- Mã nguồn ZIP có thể không hoàn toàn khớp code đang chạy tại `/opt/testmes2` do VPS đã được chỉnh sửa trong quá trình triển khai. Trước khi deploy thay thế, so sánh `git diff` và backup hiện trạng VPS.
