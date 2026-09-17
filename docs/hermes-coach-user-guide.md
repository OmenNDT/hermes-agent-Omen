# Hermes Coach — Hướng dẫn chạy

Ứng dụng coaching cục bộ, một người dùng, chỉ chạy trên loopback. Không đăng nhập, không truy cập từ máy khác.

Mọi lệnh và kết quả dưới đây đã chạy thật trên Windows 11, lần kiểm gần nhất 2026-09-17. Phần nào chưa chạy được thì ghi rõ ở [Chưa hoạt động](#chưa-hoạt-động).

---

## 1. Chuẩn bị

Cần Python 3.12+, Node 20+, và một credential Anthropic.

```bash
# Python
.venv/Scripts/python.exe -m pip install -e .

# Web UI — bắt buộc, nếu không thì mở link chỉ ra 404
npm install
npm run -w apps/hermes-coach build
```

`npm run build` đặt kết quả ở `apps/hermes-coach/dist/`. Backend tự tìm thư mục đó khi khởi động.

### Credential

Coach dùng Claude Haiku qua Anthropic Messages API, và đọc **đúng một nguồn** credential: token OAuth của Claude Code ở `~/.claude/.credentials.json`. Chạy `claude login` để tạo.

Đây là credential thuê bao cấp cho Claude Code, dùng lại cho Coach là lựa chọn có chủ ý chứ không phải mặc định. `ANTHROPIC_API_KEY` **không được đọc** — đặt biến đó sẽ không có tác dụng gì. Hỗ trợ nó là ba dòng, cố ý chưa viết cho tới khi thật sự có key.

Không có credential nào thì Coach **vẫn chạy** — nó báo một dòng cảnh báo, mọi dữ liệu đã lưu vẫn xem được, chỉ `coach.turn` trả `provider_not_configured`.

---

## 2. Chạy

```bash
hermes coach
```

In ra:

```text
Hermes Coach — profile default
  Dữ liệu Coach lưu trên máy này và không được mã hoá. Người hoặc tiến trình
  có quyền đọc tệp đều đọc được nội dung.
  http://127.0.0.1:8976?token=4TnYoNjeaqZs83gWK3KOUkZSgif4oZcqfulgI7U5m1Q
```

**Mở đúng link đó trong trình duyệt.** Không gõ lại địa chỉ mà bỏ `?token=` — trang cần token trong URL để mở WebSocket, không có thì nó vào trạng thái offline.

Cổng mặc định là ngẫu nhiên còn trống. Token là mới mỗi lần chạy, chỉ nằm trong bộ nhớ, không ghi ra đĩa và không ghi vào `localStorage` của trình duyệt.

### Cờ

| Cờ | Việc |
| --- | --- |
| `--port 8976` | Cố định cổng thay vì chọn ngẫu nhiên |
| `--profile <tên>` | Dùng hồ sơ khác, mỗi hồ sơ một cơ sở dữ liệu riêng |
| `--no-provider` | Chạy không mô hình; đọc dữ liệu vẫn được |

Mỗi hồ sơ chỉ chạy được một tiến trình. Chạy lần hai trên cùng hồ sơ sẽ báo hồ sơ đang bị khoá và thoát.

---

## 3. Dữ liệu nằm ở đâu

```text
C:\Users\<bạn>\AppData\Local\hermes\coach\<profile>\
```

Chứa cơ sở dữ liệu SQLite và tệp khoá hồ sơ. **Không mã hoá** — đó là nội dung của dòng disclosure in lúc khởi động, và trang onboarding hiện lại nó trước khi hỏi bạn đồng ý.

Sao lưu bằng cách copy cả thư mục khi Coach đã tắt.

---

## 4. Mô hình bảo mật

Chỉ một cổng, ba lớp kiểm tra độc lập, mỗi lớp riêng lẻ đều giả mạo được nên phải đủ cả ba:

| Lớp | Kiểm |
| --- | --- |
| Peer | Kết nối đến từ chính máy này (`127.0.0.1` hoặc `::1`) |
| Host | Header `Host` trỏ về loopback của đúng cổng này — chống DNS rebinding, vì kiểu tấn công đó đến dưới dạng peer loopback hợp lệ |
| Origin | Nếu trình duyệt gửi Origin, nó phải là loopback origin của cổng này |
| Token | Chuỗi ngẫu nhiên sinh riêng cho tiến trình này |

**Trang và bundle JS được phục vụ không cần token; WebSocket thì cần.** Trình duyệt không thể gắn token vào các request tải asset mà `index.html` sinh ra, nên nếu chặn thì trang không bao giờ tải nổi. Trang và bundle không chứa dữ liệu nào của bạn; WebSocket là thứ duy nhất chạm tới dữ liệu, và nó vẫn kiểm token đầy đủ. Peer/Host/Origin thì cả hai đường đều kiểm y hệt nhau.

Đã kiểm chứng thật:

```text
GET /  từ Origin http://127.0.0.1:8976   → 200
GET /  từ Origin https://evil.example.com → 403
WS  /api/coach/ws với Origin loopback     → 101
WS  /api/coach/ws với Origin lạ           → 403
WS  /api/coach/ws với token sai           → đóng, mã 1008
```

---

## 5. Giao diện

React, hash routing, phục vụ từ chính cổng backend. Tám điểm đến: Hôm nay, Bắt đầu, Phiên coaching, Mục tiêu, Hành trình, Nhận thức, Check-in, Quyền riêng tư.

Phục vụ từ **cùng một cổng** là bắt buộc, không phải lựa chọn: trang đọc `window.location.port` để biết backend ở đâu. Chạy Vite dev server ở cổng khác thì trang sẽ nối WebSocket vào chính cổng dev server và hỏng handshake.

Sáu bước của một phiên: Pre-Coaching → Goal → Reality → Options → Will → Review. Coach không được phép bỏ qua Pre-Coaching, kể cả khi bạn vào thẳng bằng một câu hỏi về mục tiêu.

Mọi mục tiêu, nhận thức, cam kết và ghi nhớ mà mô hình đề xuất đều chỉ là **candidate**. Trò chuyện không xác nhận được record — bạn accept/edit/discard từng cái một trong UI, không có nút gộp.

---

## 6. Chạy test

```bash
# Python
.venv/Scripts/python.exe -m pytest tests/hermes_coach -q     # 1112 tests

# Web
npm run -w apps/hermes-coach typecheck
npm run -w apps/hermes-coach lint
npm run -w apps/hermes-coach test                            # 246 tests
npm run -w apps/hermes-coach build
```

Không cần credential và không cần mạng: mọi test provider đều dùng client giả.

Hiện có **4 test Python trượt**, đều có sẵn từ trước — xem [Lỗi đang mở](#lỗi-đang-mở).

---

## 7. Khi hỏng

| Triệu chứng | Nguyên nhân |
| --- | --- |
| Mở link ra 404 | Chưa build UI. Chạy `npm run -w apps/hermes-coach build` |
| Trang hiện nhưng báo offline | Mở địa chỉ không có `?token=`. Copy nguyên link launcher in ra |
| `provider_not_configured` | Không tìm thấy credential Claude Code. Chạy `claude login` |
| Báo hồ sơ đang bị khoá | Đã có một tiến trình Coach chạy trên hồ sơ đó |
| `internal_error` | Xem console của backend — traceback đầy đủ nằm ở đó. Client cố tình không nhận chi tiết để tránh rò rỉ đường dẫn và nội dung prompt |

---

## Lỗi đang mở

Bốn test trượt, hai nguyên nhân. Không cái nào chạm tới luồng khởi động, onboarding hay retention.

| Test | Nguyên nhân đã kiểm | Cách sửa |
| --- | --- | --- |
| `test_descriptive_or_contradictory_co_prefix_is_not_explicit_yes` (3 tham số) | Hai vấn đề tách biệt trong `classify_gate_answer`. (a) "Có" nằm trong `_WEAK_AFFIRMATIONS` và luật tiền tố `startswith("co ")` khiến mọi câu mở đầu bằng "Có " thành YES — "Có vấn đề" và "Có một lựa chọn khác" đều đóng gate. (b) "Có, tôi không đồng ý với phần thời hạn" trả NO vì nhánh cụm từ chối chạy trước nhánh qualifier | (a) "Có" đứng đầu câu tiếng Việt thường là động từ tồn tại, không phải lời đồng ý — chỉ nhận YES khi "Có" đứng một mình hoặc ngay trước ranh giới mệnh đề, không phải trước một danh ngữ. (b) Cho nhánh qualifier chạy trước nhánh từ chối, đúng như docstring của chính hàm đã nói: một phủ định ở giữa câu là người chưa quyết, không phải người từ chối |
| `test_the_prompt_has_exactly_one_definition_site` | Guard khẳng định `assigned == ["COACH_SYSTEM_PROMPT"]`, nhưng module giờ có thêm `CLOSING_QUESTION_EXAMPLE` — một hằng có chủ ý, kèm test riêng, để lời hướng dẫn trong prompt và `open_closing_gate` không lệch nhau | Bất biến mà guard thật sự bảo vệ là "prompt là một literal, không ráp từ mảnh" — và `test_the_prompt_is_a_literal_not_a_computed_value` đã giữ phần đó. Siết lại đúng ý: `COACH_SYSTEM_PROMPT` được gán đúng một lần, thay vì cấm mọi hằng khác ở cấp module |

Mức nghiêm trọng khác nhau: hai ca đầu của lỗi (a) **fail open** — gate đóng trên câu trả lời không phải sự đồng ý, trái đúng quy tắc "mỗi bước chỉ hoàn tất sau một Yes rõ ràng". Lỗi thứ hai chỉ là guard quá rộng, không ảnh hưởng hành vi chạy.

---

## Chưa hoạt động

| Việc | Cần gì để xong |
| --- | --- |
| Bước `profile` của onboarding còn trống | Gọi `coach.turn` với `goal_id: null` để lấy câu hỏi career-snapshot |
| `dist` chưa đóng vào wheel | Copy `apps/hermes-coach/dist` sang `hermes_coach/web/` lúc build và khai báo trong `package-data`. Resolver đã tìm sẵn ở đó, chỉ thiếu bước copy |
| Chưa có E2E trình duyệt | Playwright, để Phase 7 |
