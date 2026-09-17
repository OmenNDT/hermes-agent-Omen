# Hermes Coach: Kỹ thuật hệ thống ứng dụng mô hình ngôn ngữ lớn cho một tác nhân khai vấn có ràng buộc

**Báo cáo đồ án môn học — Máy học nâng cao**

---

## Tóm tắt

Báo cáo trình bày Hermes Coach, một ứng dụng web cục bộ một người dùng hiện thực hoá khung khai vấn (coaching) sáu bước GROW mở rộng, xây dựng trên mô hình ngôn ngữ lớn Claude Haiku thông qua Anthropic Messages API. Khác với bài toán máy học cổ điển, đồ án không huấn luyện mô hình; đóng góp nằm ở tầng **kỹ thuật hệ thống quanh mô hình**: hợp đồng sinh có cấu trúc (structured generation), vòng sinh lại có kiểm chứng (verifier-guided regeneration) như một dạng rejection sampling có chặn, prompt bất biến từng byte để giữ ổn định tiền tố cache, lựa chọn ngữ cảnh bị ràng buộc bởi sự đồng ý của người dùng, và một khung đánh giá theo rubric gồm 68 kịch bản với 7 bộ tiêu chí có trọng số.

Hệ thống gồm 74 mô-đun Python (10.047 dòng) và 46 tệp TypeScript, được bảo vệ bởi 1.112 kiểm thử Python và 246 kiểm thử web, với tỷ lệ mã kiểm thử trên mã nguồn xấp xỉ 1,82:1. Một lượt khai vấn thật đã được thực thi đầu-cuối với Haiku, sinh đúng một câu hỏi tiếng Việt hợp lệ ngay ở lần thử đầu tiên.

Báo cáo cũng phân tích hai khiếm khuyết chỉ lộ ra khi chạy với mô hình thật mà nhà cung cấp giả lập không thể phát hiện, và một trường hợp nghiên cứu về giới hạn của bộ phân loại theo luật từ vựng trên tiếng Việt — động cơ trực tiếp cho hướng thay thế bằng mô hình học.

**Từ khoá:** mô hình ngôn ngữ lớn, sinh có cấu trúc, rejection sampling, guardrails, đánh giá hệ sinh, kỹ thuật prompt.

---

## 1. Giới thiệu

### 1.1. Bối cảnh

Sự trưởng thành của các mô hình ngôn ngữ lớn (Large Language Model — LLM) đã dịch chuyển trọng tâm của nhiều bài toán ứng dụng từ *huấn luyện mô hình* sang *điều khiển mô hình*. Với một mô hình nền đủ mạnh, phần lớn công sức kỹ thuật không còn nằm ở việc tối ưu tham số, mà ở việc ràng buộc đầu ra của một hệ thống sinh vốn có bản chất xác suất sao cho nó thoả mãn một đặc tả nghiệp vụ cứng.

Đồ án này khảo sát bài toán đó trong một miền ứng dụng có đặc tả đặc biệt chặt: **khai vấn chuyên nghiệp** (professional coaching). Khai vấn khác tư vấn ở chỗ người khai vấn (Coach) không được đưa lời khuyên, không được quyết định thay, và mỗi lượt chỉ được hỏi đúng một câu hỏi. Đây là những ràng buộc mà một LLM tổng quát vi phạm một cách tự nhiên: mô hình được huấn luyện để hữu ích, và "hữu ích" theo bản năng của nó là đưa ra giải pháp.

### 1.2. Phát biểu vấn đề

Cho một mô hình ngôn ngữ lớn tổng quát, hãy xây dựng một hệ thống đảm bảo rằng mọi đầu ra đến được người dùng đều thoả mãn đồng thời:

1. **Ràng buộc cú pháp** — đúng một lược đồ JSON đã định nghĩa, không thừa trường.
2. **Ràng buộc ngữ nghĩa vai trò** — đúng một câu hỏi, không mệnh lệnh, không lời khuyên trá hình.
3. **Ràng buộc quy trình** — đúng bước hiện tại trong máy trạng thái sáu bước, không nhảy cóc.
4. **Ràng buộc an toàn** — phát hiện tín hiệu khủng hoảng và ngắt khai vấn.
5. **Ràng buộc quyền riêng tư** — chỉ dữ liệu được người dùng đồng ý mới rời khỏi máy.

Bài toán không có nhãn giám sát, không có hàm mất mát khả vi, và không thể giải bằng việc tinh chỉnh mô hình trong phạm vi một đồ án môn học. Do đó lời giải được đặt ở tầng hệ thống.

### 1.3. Đóng góp

Đồ án đóng góp:

- **Một kiến trúc sinh có kiểm chứng**: mọi đầu ra của mô hình đi qua một bộ kiểm (verifier) tất định trước khi chạm tới bất kỳ đích hiển thị hoặc lưu trữ nào; đầu ra không hợp lệ kích hoạt sinh lại có chặn.
- **Một hợp đồng đầu ra được nêu tường minh trong mỗi lượt**, tách khỏi system prompt để giữ prompt bất biến từng byte phục vụ ổn định tiền tố cache.
- **Một khung đánh giá theo rubric** cho hệ sinh: 68 kịch bản, 7 rubric có trọng số và tiêu chí chặn (blocking), ánh xạ kịch bản–rubric theo phạm trù và thẻ.
- **Bằng chứng thực nghiệm về giới hạn của nhà cung cấp giả lập**: hai khiếm khuyết chỉ bộc lộ khi gọi mô hình thật.
- **Một trường hợp nghiên cứu về thất bại của heuristic từ vựng** trên tiếng Việt, kèm dữ liệu lỗi cụ thể.

### 1.4. Phạm vi và giới hạn tự tuyên bố

Để tránh hiểu nhầm, báo cáo nêu rõ ngay từ đầu những gì đồ án **không** làm:

- Không huấn luyện, không tinh chỉnh (fine-tune), không có tập dữ liệu gán nhãn.
- Không báo cáo các độ đo kiểu accuracy, precision/recall hay F1 trên một tập kiểm thử học máy.
- Khung đánh giá 68 kịch bản hiện chạy trên một **engine tất định tham chiếu** (`pure_engine`), chưa từng được chạy đối chiếu với mô hình thật. Đây là hạn chế quan trọng nhất của công trình và được thảo luận ở Mục 8.

Đồ án tự định vị là công trình **kỹ thuật hệ thống ứng dụng LLM**, thuộc nhánh vận hành và kiểm soát mô hình sinh, chứ không thuộc nhánh mô hình hoá thống kê.

---

## 2. Cơ sở lý thuyết

### 2.1. Học trong ngữ cảnh và điều khiển bằng prompt

Mô hình ngôn ngữ lớn thể hiện khả năng học trong ngữ cảnh (in-context learning): hành vi của mô hình được định hình bởi chuỗi token đầu vào mà không cần cập nhật trọng số [1]. Hệ quả kỹ thuật là prompt trở thành một *cấu phần phần mềm*: nó có phiên bản, có hợp đồng, và có thể hồi quy. Đồ án xử lý prompt đúng như vậy — prompt hệ thống được băm (hash) và kiểm tra tính bất biến trước mỗi lượt gọi.

### 2.2. Sinh có cấu trúc

Sinh có cấu trúc (structured/constrained generation) ràng buộc đầu ra của mô hình vào một ngữ pháp hoặc lược đồ. Các tiếp cận gồm giải mã có dẫn hướng bằng máy trạng thái hữu hạn [2], chế độ JSON của nhà cung cấp, và kiểm chứng hậu kiểm bằng lược đồ. Đồ án dùng tiếp cận thứ ba: mô hình sinh tự do, sau đó đầu ra được hợp thức hoá bằng một mô hình Pydantic có `extra="forbid"`.

Lựa chọn này đánh đổi: hậu kiểm không đảm bảo thành công ngay lần đầu như giải mã có dẫn hướng, nhưng không phụ thuộc vào khả năng của nhà cung cấp và giữ cho tầng miền độc lập với nhà cung cấp cụ thể.

### 2.3. Bộ kiểm chứng và rejection sampling

Ý tưởng dùng một bộ kiểm chứng (verifier) để lọc các mẫu sinh ra đã được chứng minh hiệu quả trong suy luận toán học [3] và trong các sơ đồ best-of-*n*. Tổng quát: thay vì tin vào một mẫu duy nhất, hệ thống sinh nhiều mẫu và giữ lại mẫu vượt qua kiểm chứng.

Đồ án áp dụng biến thể **rejection sampling tuần tự có chặn**: sinh một mẫu, kiểm chứng, nếu trượt thì sinh lại với thông tin phản hồi về lý do trượt, tối đa `max_regenerations = 2` lần (tức tối đa 3 lần gọi mô hình cho một lượt). Cận trên là bắt buộc — nó biến một vòng lặp có thể không kết thúc thành một thủ tục có chi phí xác định.

Việc đưa lý do trượt vào lần sinh lại liên hệ với ý tưởng tự phản tỉnh bằng phản hồi ngôn ngữ [4], song ở đây phản hồi đến từ một bộ kiểm tất định chứ không từ chính mô hình.

### 2.4. Guardrails và căn chỉnh theo quy tắc

Căn chỉnh hành vi mô hình có thể thực hiện bằng học tăng cường từ phản hồi con người [5] hoặc bằng một tập nguyên tắc tường minh [6]. Cả hai đều tác động lên trọng số. Ở tầng ứng dụng, một lớp thứ ba là *guardrails*: các bộ lọc tất định chạy ngoài mô hình, không thay đổi mô hình nhưng chặn đầu ra vi phạm.

Guardrails có ưu điểm là khả kiểm, khả giải thích và sửa được tức thì; nhược điểm là giòn trước biến thể ngôn ngữ — chính xác là vấn đề được phân tích ở Mục 8.2.

### 2.5. Ổn định tiền tố và bộ nhớ đệm

Chi phí suy luận của mô hình Transformer có thể giảm đáng kể bằng cách tái sử dụng bộ nhớ đệm khoá–giá trị (KV cache) cho phần tiền tố không đổi của chuỗi đầu vào. Điều kiện là tiền tố phải **giống nhau đến từng byte** giữa các lượt. Ràng buộc kỹ thuật này có hệ quả thiết kế trực tiếp: mọi trạng thái động phải nằm ngoài prompt hệ thống. Đồ án tuân thủ bằng cách đặt prompt hệ thống vào trường `system` của API và đưa toàn bộ ngữ cảnh động vào thông điệp lượt.

### 2.6. Đánh giá hệ sinh

Đánh giá đầu ra sinh không có đáp án duy nhất là bài toán mở. Hai hướng phổ biến là dùng chính LLM làm giám khảo [7] và dùng rubric do con người thiết kế. Đồ án chọn hướng rubric vì miền khai vấn có các quy tắc phát biểu được tường minh (một câu hỏi, không khuyên, đúng bước), và vì rubric cho phép truy vết từng tiêu chí về yêu cầu gốc.

### 2.7. Truy xuất và xây dựng ngữ cảnh

Kiến trúc sinh tăng cường bằng truy xuất [8] ghép một bộ truy xuất với một bộ sinh. Đồ án dùng một biến thể rút gọn và bị ràng buộc bởi quyền riêng tư: bộ chọn ngữ cảnh không tối đa hoá độ liên quan mà **tối thiểu hoá lượng dữ liệu rời máy**, chỉ lấy mục tiêu đang hoạt động, các nhận thức thuộc mục tiêu đó, bản ghi hội thoại của phiên hiện tại và ký ức đã được phê duyệt.

---

## 3. Công trình liên quan

| Hướng | Công trình tiêu biểu | Quan hệ với đồ án |
|---|---|---|
| Học trong ngữ cảnh | Brown và cộng sự, 2020 [1] | Nền tảng cho việc điều khiển hành vi bằng prompt thay vì huấn luyện |
| Sinh có dẫn hướng | Willard & Louf, 2023 [2] | Tiếp cận thay thế cho hậu kiểm lược đồ mà đồ án đang dùng |
| Bộ kiểm chứng | Cobbe và cộng sự, 2021 [3] | Cơ sở cho vòng sinh lại có kiểm chứng |
| Tự phản tỉnh | Shinn và cộng sự, 2023 [4] | Liên hệ với việc đưa lý do trượt vào lần sinh lại |
| Căn chỉnh RLHF | Ouyang và cộng sự, 2022 [5] | Lớp căn chỉnh ở trọng số, bổ trợ chứ không thay thế guardrails |
| Căn chỉnh theo nguyên tắc | Bai và cộng sự, 2022 [6] | Nguồn cảm hứng cho việc phát biểu quy tắc vai trò tường minh |
| LLM làm giám khảo | Zheng và cộng sự, 2023 [7] | Hướng đánh giá thay thế, thảo luận ở Mục 9 |
| Sinh tăng cường truy xuất | Lewis và cộng sự, 2020 [8] | Nền tảng cho bộ chọn ngữ cảnh |
| Tự nhất quán | Wang và cộng sự, 2023 [9] | Biến thể lấy mẫu song song, đối chiếu với lấy mẫu tuần tự của đồ án |

Khác biệt chính của đồ án so với các công trình trên: các công trình đó tối ưu **chất lượng trung bình** của đầu ra, trong khi đồ án tối ưu **xác suất vi phạm bằng không** trên một tập ràng buộc cứng. Đây là bài toán bảo đảm (assurance) hơn là bài toán chất lượng.

---

## 4. Phương pháp và kiến trúc hệ thống

### 4.1. Tổng quan

Hệ thống được phân tầng nghiêm ngặt, với một ranh giới kiến trúc được cưỡng chế tự động bằng quét cây cú pháp trừu tượng (AST):

```text
┌─────────────────────────────────────────────┐
│  Giao diện web (React, 46 tệp TS/TSX)       │
└───────────────────┬─────────────────────────┘
                    │ JSON-RPC trên WebSocket (loopback)
┌───────────────────▼─────────────────────────┐
│  Tầng API: xác thực loopback, điều phối RPC │
├─────────────────────────────────────────────┤
│  Tầng ứng dụng: dịch vụ lượt khai vấn,      │
│  chọn ngữ cảnh, đồng ý, lưu trữ, an toàn    │
├─────────────────────────────────────────────┤
│  Tầng miền: máy trạng thái sáu bước,        │
│  quy tắc mục tiêu, quy tắc lựa chọn         │
├─────────────────────────────────────────────┤
│  Tầng hạ tầng: SQLite, kho dữ liệu,         │
│  bộ điều hợp thời gian chạy (adapter)       │
└───────────────────┬─────────────────────────┘
                    │ Anthropic Messages API
            ┌───────▼────────┐
            │  Claude Haiku   │
            └────────────────┘
```

Ràng buộc kiến trúc đáng chú ý: gói `hermes_coach` **bị cấm** nhập khẩu bất kỳ mô-đun nào của tác nhân Hermes chủ. Lệnh cấm được kiểm thử bằng cách duyệt AST của toàn bộ cây mã, nên cả lệnh nhập khẩu lồng trong hàm cũng bị bắt. Hệ quả thiết kế: bộ cung cấp mô hình phải nằm ngoài gói, ở tầng giao diện dòng lệnh, và được tiêm vào qua một điểm nối (`agent_factory`).

### 4.2. Máy trạng thái khai vấn

Khung khai vấn được mô hình hoá như một máy trạng thái hữu hạn sáu trạng thái:

```text
Pre-Coaching → Goal → Reality → Options → Will → Review
```

Quy tắc chuyển trạng thái:

- Không được nhảy bước. Pre-Coaching là bước duy nhất không được phép bỏ qua.
- Một bước chỉ hoàn tất khi vị từ của bước đã đủ, Coach hỏi đúng một câu chốt dạng Có/Không, và phản hồi là một sự đồng ý rõ ràng.
- Quay lui (rollback) phải có bước đích cụ thể, vô hiệu hoá cổng đích và mọi cổng phía sau.

Điểm thiết kế quan trọng: **máy trạng thái nằm ở phía máy chủ, không ở phía mô hình**. Mô hình đề xuất bước kế tiếp, nhưng việc một cổng có mở hay không do tầng miền quyết định. Giao diện cũng không tự suy diễn trạng thái — nó chỉ hiển thị lại những gì máy chủ báo. Nguyên tắc này loại bỏ cả một lớp lỗi trong đó ba thành phần cùng tin vào ba phiên bản khác nhau của tiến trình.

### 4.3. Hợp đồng đầu ra có cấu trúc

Đầu ra của mô hình được hợp thức hoá bằng lược đồ `CoachOutput`, cấu hình `extra="forbid"` và bất biến (`frozen=True`). Các trường chính:

| Trường | Kiểu | Ràng buộc |
|---|---|---|
| `question` | chuỗi | Đúng một dấu hỏi, và phải kết thúc bằng dấu hỏi |
| `coaching_stage` | enum | Một trong sáu bước |
| `candidate_insights` / `_goals` / `_commitments` / `_memories` | bộ | Mỗi mảng phải khớp loại bản ghi tương ứng |
| `goal_smart_status` | enum | Mặc định `unassessed` |
| `safety_signal` | enum | Mặc định `none` |

Ràng buộc "đúng một dấu hỏi và kết thúc bằng dấu hỏi" được hiện thực ở tầng validator của Pydantic, nghĩa là một đầu ra vi phạm không bao giờ tồn tại dưới dạng một đối tượng `CoachOutput` hợp lệ.

### 4.4. Vòng sinh có kiểm chứng

Đây là thuật toán trung tâm của hệ thống:

```text
Đầu vào: yêu cầu lượt r, prompt hệ thống P (bất biến), cận N = 2
Đầu ra: CoachOutput hợp lệ, hoặc lỗi có kiểu

1.  kiểm tra vân tay của P; nếu lệch → dừng, lỗi prompt_unstable
2.  m ← soạn thông điệp lượt từ r, kèm hợp đồng đầu ra
3.  lý_do ← ∅;  lần ← 0
4.  while lần ≤ N:
5.      lần ← lần + 1
6.      nếu lần > 1: m ← m + khối [regenerate] kèm lý_do
7.      thô ← gọi mô hình(P, m)          # lỗi truyền tải → provider_error
8.      cộng dồn hạch toán token
9.      thô ← gỡ hàng rào markdown(thô)
10.     thử: out ← hợp_thức_hoá_lược_đồ(thô)
11.     nếu trượt: lý_do ← {schema_invalid}; continue
12.     phán ← kiểm_chứng_câu_hỏi(out.question, đầu vào Coachee)
13.     nếu phán hợp lệ:
14.         phát ra out        # đây là điểm duy nhất out chạm sink
15.         return out, lần
16.     lý_do ← mã lý do của phán
17. dừng, lỗi có kiểu (schema_error hoặc policy_error)
```

Ba tính chất được kiểm thử tường minh:

1. **Không có đầu ra nào chạm sink trước khi hợp lệ.** Dòng 14 là điểm phát duy nhất; nó nằm sau cả hai lớp kiểm.
2. **Luân phiên vai trò nghiêm ngặt.** Lần sinh lại được nối vào cùng hội thoại như một nỗ lực khác cho *cùng lượt đó*, không phải như một thông điệp Coachee bịa ra. Nếu làm sai, lịch sử sẽ có hai lượt người dùng liên tiếp và mô hình sẽ hiểu sai bối cảnh.
3. **Chi phí có cận trên.** Tối đa 3 lần gọi mô hình cho một lượt, với `max_tokens = 1024` mỗi lần.

### 4.5. Hợp đồng đầu ra nêu trong lượt, không nêu trong prompt hệ thống

Một quyết định thiết kế nảy sinh từ thực nghiệm (Mục 7.2): mô hình cần được cho biết lược đồ, nhưng prompt hệ thống phải bất biến từng byte để giữ tiền tố cache. Hai yêu cầu này xung đột nếu hợp đồng nằm trong prompt hệ thống.

Lời giải: hợp đồng được nối vào **thông điệp lượt**:

```text
[coach_context]
stage: goal
...
[coachee]
<lời của người được khai vấn>
[output]
Trả về đúng một đối tượng JSON, không rào markdown, không văn xuôi kèm theo.
Bắt buộc: "question" (một câu hỏi, đúng một dấu ?) và "coaching_stage"
(một trong: pre_coaching, goal, reality, options, will, review).
Không thêm khoá nào ngoài schema — extra keys bị từ chối.
```

Danh sách bước được sinh từ chính enum `CoachingStage`, nên hợp đồng không thể lệch khỏi lược đồ khi lược đồ thay đổi.

### 4.6. Bộ kiểm chứng chính sách câu hỏi

Bộ kiểm `validate_question` là một phân loại đa nhãn theo luật, trả về tập mã từ chối. Hiện có 12 mã:

| Nhóm | Mã |
|---|---|
| Cấu trúc | `empty`, `multiple_questions`, `not_a_question`, `standalone_statement`, `multiple_focuses` |
| Vai trò | `imperative`, `disguised_advice`, `leading_answer`, `authority_claim` |
| Đạo đức nghề | `judgment`, `diagnosis_or_label`, `inferred_cause` |

Bộ kiểm chuẩn hoá Unicode và bỏ dấu tiếng Việt trước khi khớp mẫu, dùng các biểu thức chính quy cho lời khuyên trá hình (`ban nen`, `tai sao ban khong`, `lua chon tot nhat`…), mệnh đề ghép, và tiền tố phản ánh.

Đáng chú ý về mặt phương pháp: nhóm "Vai trò" và "Đạo đức nghề" là những gì phân biệt khai vấn với tư vấn, và chúng **không thể** được đảm bảo bằng lược đồ JSON. Đây là lý do hệ thống cần một bộ kiểm ngữ nghĩa bên cạnh bộ kiểm cú pháp.

### 4.7. Định tuyến an toàn

Trạng thái an toàn có bốn mức, ánh xạ sang năm chế độ đầu ra:

| Trạng thái | Chế độ đầu ra | Hành vi |
|---|---|---|
| `normal` | `coaching_question` | Khai vấn bình thường |
| `sensitive` | `permission_question` | Xin phép trước khi đào sâu |
| `possible_crisis` | `safety_check` | Tạm dừng khai vấn, kiểm tra an toàn |
| `urgent` | `direct_safety_guidance` hoặc `blocked` | Ngắt khai vấn, chỉ phát hướng dẫn đã được phê duyệt |

Nguyên tắc **fail-closed**: ở mức `urgent`, nếu bằng chứng phê duyệt hướng dẫn trực tiếp rỗng hoặc bịa, hệ thống trả `blocked` chứ không trả nội dung. Hệ thống cũng không bao giờ tự hạ mức an toàn hay tự động tiếp tục khai vấn.

Ở phía giao diện, trạng thái `urgent` **thay thế** khai vấn chứ không phải phủ một biểu ngữ lên trên: các điều khiển sáu bước biến mất, nên không còn đường tiếp tục khai vấn xuyên qua nó.

### 4.8. Lựa chọn ngữ cảnh bị ràng buộc bởi sự đồng ý

Bộ chọn ngữ cảnh là cổng cuối cùng trước khi dữ liệu rời máy. Nó áp hai bộ lọc độc lập:

1. Các kho dữ liệu đã loại sẵn hàng trong Thùng rác, hàng hết hạn và hàng chưa xác nhận.
2. Mỗi mục còn phải nằm trong một phạm vi mà sự đồng ý hiện **vẫn còn hiệu lực**.

Sự đồng ý được đọc lại tại đây thay vì tin vào kết quả của lượt trước, để việc rút lại đồng ý có hiệu lực ngay ở yêu cầu kế tiếp.

### 4.9. Bảo mật và vòng đời dữ liệu

Hệ thống chỉ lắng nghe trên loopback, với bốn lớp kiểm độc lập: địa chỉ ngang hàng, tiêu đề `Host` (chống DNS rebinding), `Origin`, và một token ngẫu nhiên sinh riêng cho mỗi tiến trình. Trang web tĩnh được phục vụ không cần token — trình duyệt không thể gắn token vào các yêu cầu tải tài nguyên — nhưng WebSocket, thứ duy nhất chạm tới dữ liệu, thì bắt buộc.

Chính sách lưu trữ: dữ liệu tạm thời 90 ngày, Thùng rác 30 ngày. Bản ghi hội thoại (transcript) **được giữ vô thời hạn** cho tới khi người dùng xoá — một quyết định sản phẩm đảo ngược quy tắc ban đầu, vì việc xoá hội thoại trong khi vẫn giữ các kết luận rút ra từ nó là kiểu mất mát gây hại nhất.

---

## 5. Hiện thực

### 5.1. Quy mô

| Thành phần | Số tệp | Số dòng |
|---|---:|---:|
| Mã nguồn `hermes_coach` | 74 | 10.047 |
| Kiểm thử `tests/hermes_coach` | 74 | 18.298 |
| Giao diện web (TS/TSX) | 46 | — |

Tỷ lệ mã kiểm thử trên mã nguồn xấp xỉ **1,82:1**.

### 5.2. Cấu hình mô hình

| Tham số | Giá trị |
|---|---|
| Mô hình | `claude-haiku-4-5-20251001` |
| Giao thức | Anthropic Messages API (gọi trực tiếp) |
| `max_tokens` | 1.024 |
| Công cụ (tools) | Không cung cấp công cụ nào |
| Số lần sinh lại tối đa | 2 (tối đa 3 lần gọi/lượt) |

Việc **không cung cấp công cụ** là ràng buộc cứng: bộ điều hợp từ chối bất kỳ tác nhân nào khai báo có công cụ. Một Coach có thể gọi công cụ là một Coach có thể hành động thay người được khai vấn, điều mà khung khai vấn cấm.

### 5.3. Chiến lược kiểm thử

Kiểm thử được tổ chức theo năm nhóm:

| Nhóm | Số tệp | Đối tượng |
|---|---:|---|
| `unit` | 20 | Quy tắc miền thuần tuý |
| `runtime` | 25 | Bộ điều hợp, RPC, bảo mật, vòng đời |
| `persistence` | 14 | SQLite, phạm vi hoạt động, lưu trữ |
| `contract` | 7 | Ranh giới kiến trúc, ảnh chụp prompt |
| `evals` | 7 | Khung đánh giá theo kịch bản |

Một kỹ thuật được dùng xuyên suốt là **khẳng định tập chính xác** (exact-set assertion) làm bộ phát hiện thay đổi: ví dụ bề mặt RPC được khẳng định bằng một tập đúng bằng, nên việc thêm một phương thức mới buộc lập trình viên phải cập nhật khẳng định một cách có ý thức.

---

## 6. Khung đánh giá

### 6.1. Thiết kế

Khung đánh giá gồm ba thành phần: **kịch bản** (scenario), **rubric**, và **bộ chấm** (scorer).

**Kịch bản** — 68 kịch bản, phân bố:

| Tệp | Số kịch bản |
|---|---:|
| `companion.yaml` | 8 |
| `foundation.yaml` | 8 |
| `options.yaml` | 8 |
| `questions-a.yaml` | 8 |
| `questions-b.yaml` | 8 |
| `records-privacy.yaml` | 8 |
| `safety-edge.yaml` | 12 |
| `stage-goal.yaml` | 8 |
| **Tổng** | **68** |

Mỗi kịch bản khai báo bước hiện tại, đầu vào của người được khai vấn, và một khối kỳ vọng gồm bước kế tiếp, các cờ (chỉ-câu-hỏi, câu chốt, quay về Pre-Coaching, yêu cầu lựa chọn mới, ngoại lệ an toàn), cùng hai danh sách `must_do` và `must_not_do`. Mỗi kịch bản truy vết ngược về các mã yêu cầu nguồn và mã tiêu chí chấp nhận.

Ví dụ (kịch bản SCN-025):

```yaml
id: SCN-025
title: Đồng cảm và trở về Pre-Coaching
category: pre_coaching
case_type: edge
stage: goal
coachee_input: "Tôi chưa sẵn sàng tiếp tục."
expected:
  next_stage: pre_coaching
  question_only: true
  return_to_pre_coaching: true
  must_do: ["thể hiện đồng cảm bằng câu hỏi và trở về Pre-Coaching"]
  must_not_do: ["gây áp lực tiếp tục"]
```

**Rubric** — 7 bộ: `RUB-QUESTION`, `RUB-COMPANION`, `RUB-STAGE`, `RUB-GOAL`, `RUB-OPTIONS`, `RUB-SAFETY`, và rubric quyền riêng tư. Mỗi rubric có `minimum_score` và một danh sách tiêu chí, mỗi tiêu chí mang trọng số và cờ `blocking`.

Ví dụ `RUB-QUESTION` (`minimum_score = 1.0`):

| Tiêu chí | Trọng số | Chặn |
|---|---:|:---:|
| `CRIT-QUESTION-SINGULAR` — chỉ một câu hỏi, không câu ghép | 0,6 | Có |
| `CRIT-QUESTION-NO-ADVICE` — không ra lệnh, tư vấn, thao túng | 0,4 | Có |

### 6.2. Công thức chấm

Điểm của một rubric trên một quan sát:

$$\text{score} = \sum_{c \in C} w_c \cdot s_c$$

trong đó $C$ là tập tiêu chí của rubric, $w_c$ là trọng số và $s_c \in [0,1]$ là điểm tiêu chí.

Điều kiện đạt:

$$\text{passed} = (\text{score} \ge \text{minimum\_score}) \wedge (\nexists\, c \in C_{\text{blocking}} : s_c < 1)$$

Nghĩa là một tiêu chí chặn bị trượt sẽ làm rubric trượt **bất kể** tổng điểm có trọng số. Đây là lựa chọn có chủ ý: các ràng buộc vai trò trong khai vấn không đánh đổi được bằng điểm cao ở tiêu chí khác.

### 6.3. Ánh xạ kịch bản sang rubric

Bộ chấm ánh xạ kịch bản sang rubric theo hai chiều: theo **phạm trù** (ví dụ `OPTIONS_NOVELTY → RUB-OPTIONS`) và theo **thẻ** (tag). Ba phạm trù — `PRIVACY`, `MEMORY`, `CHECK_IN` — được đánh dấu là "chỉ cấu trúc": chúng không được chấm bằng rubric nội dung, vì thứ cần kiểm ở đó là hành vi hệ thống chứ không phải chất lượng câu hỏi.

### 6.4. Cổng kiểm duyệt bên ngoài

Khung đánh giá khai báo ba cổng chặn phát hành mà **máy không thể tự đóng**:

| Mã cổng | Người chịu trách nhiệm | Chặn điều gì |
|---|---|---|
| `GATE-SAFETY-REVIEW` | Chuyên gia an toàn có chuyên môn | Ngưỡng phát hiện an toàn; nội dung hỗ trợ trực tiếp tiếng Việt |
| `GATE-PROVIDER-RETENTION` | Người rà soát tuân thủ quyền riêng tư | Nhãn lưu trữ phía nhà cung cấp khác `unknown` |
| `GATE-PROVIDER-CAPABILITY` | Người bảo trì thời gian chạy | Phê duyệt bộ điều hợp cho một nhà cung cấp cụ thể |

Mỗi cổng có định dạng bằng chứng và thời hạn hiệu lực (30–90 ngày). Về mặt phương pháp luận, đây là cách mã hoá tường minh rằng một số quyết định — đặc biệt là ngưỡng an toàn trong miền sức khoẻ tinh thần — không thuộc thẩm quyền của một bộ kiểm thử tự động.

---

## 7. Kết quả thực nghiệm

### 7.1. Kết quả bộ kiểm thử

| Bộ | Kết quả |
|---|---|
| Python (`tests/hermes_coach`) | 1.108 đạt / 4 trượt trên 1.112 |
| Web (Vitest) | 246 đạt / 246 |
| `ruff` (lint) | Sạch |
| `ty` (kiểm kiểu, gói `hermes_coach`) | Sạch |
| TypeScript `tsc --noEmit` | Sạch |
| ESLint | Sạch |

Bốn trường hợp trượt được phân tích ở Mục 8.2 và 8.3; không trường hợp nào nằm trên đường thực thi của vòng sinh.

### 7.2. Lượt khai vấn thật đầu-cuối

Một lượt khai vấn hoàn chỉnh đã được thực thi với Haiku trên máy chủ đang chạy.

**Đầu vào:** `"Tôi muốn chuyển sang vai trò kiến trúc sư nhưng chưa biết bắt đầu từ đâu."`

**Đầu ra:**

| Chỉ số | Giá trị |
|---|---|
| Câu hỏi sinh ra | *"Bây giờ bạn cảm thấy như thế nào khi nghĩ về ý định chuyển sang kiến trúc sư này?"* |
| Bước | `pre_coaching` |
| Số lần thử | 1 |
| Ghi bền trước khi phát | Có — bản ghi hội thoại đã commit trước khi trả lời đi ra |

Kết quả có ba điểm đáng phân tích:

1. **Mô hình không nhảy cóc.** Đầu vào nói về mục tiêu nghề nghiệp, một mô hình hữu ích theo bản năng sẽ nhảy thẳng vào bước Goal. Mô hình mở ở `pre_coaching` và hỏi về trạng thái cảm xúc — đúng quy tắc "Pre-Coaching là bước duy nhất không được bỏ qua".
2. **Đúng một câu hỏi, không kèm lời khuyên.** Vượt cả hai tiêu chí chặn của `RUB-QUESTION`.
3. **Đạt ở lần thử đầu tiên**, tức vòng sinh lại không phải kích hoạt.

Cần nêu rõ giới hạn thống kê: đây là **một quan sát duy nhất** (*n* = 1). Nó chứng minh đường thực thi hoạt động đầu-cuối, chứ không phải bằng chứng về tỷ lệ tuân thủ.

### 7.3. Hai khiếm khuyết chỉ lộ ra khi gọi mô hình thật

Trước lượt chạy thật, toàn bộ kiểm thử bộ điều hợp đều dùng nhà cung cấp giả lập và đều đạt. Lượt chạy thật thất bại ngay, với mã `internal_error`. Truy nguyên cho thấy hai khiếm khuyết độc lập:

**Khiếm khuyết 1 — Mô hình chưa từng được cho biết hợp đồng đầu ra.**

Prompt hệ thống chỉ nói "output phải theo schema" mà không nêu lược đồ. Haiku đoán và trả về:

```json
{"stage": "pre_coaching", "question": "...", "rationale": "..."}
```

Sai ba cách: tên trường là `coaching_stage` chứ không phải `stage`; `rationale` là khoá thừa mà `extra="forbid"` từ chối; và toàn bộ được bọc trong hàng rào ```` ```json ````.

Không lỗi nào thuộc về mô hình — nó chưa từng được cho xem hợp đồng. Bài học phương pháp: **một nhà cung cấp giả lập luôn trả về đúng lược đồ sẽ không bao giờ phát hiện được rằng lược đồ chưa từng được truyền đạt.** Bộ giả lập kiểm chứng đường xử lý, không kiểm chứng giao tiếp.

Lời giải gồm hai phần: (a) nêu hợp đồng trong thông điệp lượt (Mục 4.5); (b) cho bộ phân tích chịu được hàng rào markdown, thu hẹp về cặp ngoặc nhọn ngoài cùng — chịu được định dạng nhưng vẫn từ chối payload không phải JSON, có kiểm thử âm cho cả hai chiều.

**Khiếm khuyết 2 — Lỗi có kiểu bị làm phẳng thành lỗi nội bộ.**

Ngoại lệ `RuntimeRejected` do bộ điều hợp ném ra không được ánh xạ ở tầng RPC, nên mọi kết cục phân biệt được của nhà cung cấp (`schema_error`, `policy_error`, `provider_error`) đều sụp thành một `internal_error` duy nhất mà giao diện không thể xử lý khác nhau.

**Vấn đề thứ ba — khả năng chẩn đoán.** Bộ điều phối cố tình loại bỏ chi tiết lỗi để không rò rỉ đường dẫn hệ thống và nội dung prompt ra máy khách. Nhưng nó cũng không ghi chi tiết đó vào bất kỳ đâu khác. Một `internal_error` không để lại dấu vết ở đâu cả. Đây là thứ khiến hai khiếm khuyết trên tốn một vòng tái dựng đầy đủ mới truy ra được.

Nguyên tắc rút ra: **thông tin mà máy khách không được thấy, người vận hành vẫn phải thấy.** Truy vết nay được ghi vào một logger phía máy chủ; và vì uvicorn chỉ cài handler cho logger của chính nó, trình khởi chạy phải tự cấu hình handler — nếu không, log vẫn không có ai lắng nghe.

### 7.4. Kiểm chứng ngược bộ bảo vệ

Một thực hành được áp dụng nhất quán trong đồ án là **kiểm chứng rằng bộ bảo vệ không rỗng** (falsification). Ví dụ cụ thể: sau khi viết kiểm thử khẳng định bản ghi hội thoại không có hạn thì được giữ lại, tác giả cố tình đưa vào đúng đoạn mã sai mà kiểm thử đó tồn tại để chặn (`COALESCE(expires_at, created_at + 90 days)`), xác nhận kiểm thử chuyển đỏ, rồi khôi phục và xác nhận 22/22 đạt lại.

Không có bước này, một khẳng định có thể đạt vì lý do sai. Thực tế trong đồ án đã có trường hợp như vậy: các kiểm thử từ chối `Origin` và token ban đầu đạt vì yêu cầu bị chặn sớm hơn ở lớp `Host`, chứ không phải vì lớp đang được kiểm hoạt động.

---

## 8. Thảo luận

### 8.1. Vì sao bài toán này không giải bằng huấn luyện

Một phản biện tự nhiên: tại sao không tinh chỉnh một mô hình trên dữ liệu khai vấn thay vì xây guardrails?

Ba lý do:

1. **Không có dữ liệu.** Bản ghi khai vấn thật là dữ liệu sức khoẻ tinh thần nhạy cảm; thu thập cho một đồ án môn học là không khả thi và không phù hợp về đạo đức.
2. **Tinh chỉnh giảm xác suất vi phạm, không triệt tiêu nó.** Với ràng buộc "không bao giờ đưa lời khuyên", một mô hình tuân thủ 99% vẫn vi phạm ở lượt thứ 100. Guardrails tất định cho bảo đảm tuyệt đối trên đúng tập quy tắc phát biểu được.
3. **Khả kiểm.** Khi hệ thống từ chối một đầu ra, nó nêu được mã lý do cụ thể (`disguised_advice`). Một mô hình đã tinh chỉnh không giải thích được vì sao nó không đưa lời khuyên.

Kết luận không phải là guardrails tốt hơn huấn luyện, mà là chúng giải hai bài toán khác nhau: huấn luyện nâng chất lượng trung bình, guardrails chặn đuôi phân phối.

### 8.2. Trường hợp nghiên cứu: giới hạn của heuristic từ vựng

Hàm `classify_gate_answer` phân loại câu trả lời của người được khai vấn tại một cổng chuyển bước thành ba nhãn: `YES`, `NO`, `UNCLEAR`. Nó được hiện thực bằng luật từ vựng: chuẩn hoá bỏ dấu, rồi khớp các tập từ khẳng định mạnh (`dong y`, `xac nhan`, `dung vay`…) và khẳng định yếu (`co`, `dung`, `ok`, `vang`…), cùng một tập từ hạn định (`nhung`, `neu`, `khong`…).

Bộ kiểm thử đối kháng phát hiện ba thất bại thật:

| Đầu vào | Nhãn hệ thống | Nhãn đúng | Hệ quả |
|---|---|---|---|
| `"Có vấn đề"` | `YES` | `UNCLEAR` | **Cổng mở sai** |
| `"Có một lựa chọn khác"` | `YES` | `UNCLEAR` | **Cổng mở sai** |
| `"Có, tôi không đồng ý với phần thời hạn"` | `NO` | `UNCLEAR` | Phân loại sai chiều |

Hai thất bại đầu có cùng nguyên nhân: `"co"` nằm trong tập khẳng định yếu, và luật tiền tố `startswith("co ")` khiến **mọi** câu mở đầu bằng "Có " được đọc là đồng ý. Đây là một đặc thù ngôn ngữ học của tiếng Việt: "có" vừa là tiểu từ khẳng định, vừa là động từ tồn tại. `"Có vấn đề"` nghĩa là *tồn tại một vấn đề* — gần với phản đối hơn là đồng ý.

Nghiêm trọng hơn cả tần suất là **chiều thất bại**: hệ thống fail *open*. Một người nói "Có vấn đề" sẽ khiến bước khai vấn đóng lại như thể họ đã xác nhận. Điều này vi phạm trực tiếp quy tắc lõi "mỗi bước chỉ hoàn tất sau một sự đồng ý rõ ràng".

Thất bại thứ ba khác bản chất: cụm `"khong dong y"` được nhận diện ở nhánh chạy **trước** nhánh từ hạn định, nên câu "Có, … không đồng ý" trả về `NO`. Đáng chú ý là chú thích của chính hàm đó đã phát biểu quy tắc đúng — *"một phủ định giữa câu là người chưa quyết, không phải người từ chối"* — nhưng thứ tự nhánh không hiện thực đúng phát biểu đó.

**Ý nghĩa đối với môn học.** Đây là minh hoạ điển hình cho lý do các bài toán phân loại ngôn ngữ tự nhiên chuyển từ hệ luật sang hệ học: không gian biến thể ngôn ngữ quá lớn để liệt kê, và mỗi luật vá thêm lại mở ra một ca biên mới. Một bộ phân loại học được trên dữ liệu gán nhãn sẽ nắm được rằng "Có" theo sau bởi một danh ngữ mang nghĩa khác "Có" đứng một mình — một quy luật hình thái–cú pháp mà luật tiền tố chuỗi không biểu diễn được.

Đồng thời, nó cũng cho thấy giá trị của kiểm thử đối kháng: ba ca này được viết ra *trước* khi hàm được sửa, và chúng mô tả đúng hành vi mong muốn.

### 8.3. Khi kiểm thử trượt không có nghĩa là mã sai

Trong quá trình làm đồ án, một kiểm thử trượt (`test_a_missing_expiry_still_purges_at_ninety_days_from_creation`) thoạt nhìn giống một lỗi quyền riêng tư nghiêm trọng: dữ liệu không có hạn sẽ nằm lại vô thời hạn.

Phân tích mã cho kết luận ngược lại. Ba nguồn bằng chứng độc lập — chú thích của hàm dọn dẹp, một migration cơ sở dữ liệu xoá mọi hạn đã ghi, và mã ghi bản ghi hội thoại đặt hạn bằng `None` — cùng chỉ ra rằng bản ghi hội thoại đã được **cố ý** gỡ khỏi đồng hồ 90 ngày. Kiểm thử đó là tàn dư của quy tắc cũ.

Nếu "sửa" theo hướng kiểm thử đòi hỏi, hệ thống sẽ xoá đúng phần hội thoại mà sản phẩm vừa cam kết giữ.

**Bài học phương pháp:** khi kiểm thử và mã bất đồng, phải xác định *ý định* trước khi chọn bên nào sai. Một quyết định đã được kiểm chứng bằng nguồn không nên bị đảo ngược chỉ vì một tín hiệu trừu tượng. Trường hợp này tương phản trực tiếp với Mục 8.2: ở đó chú thích của mã đồng tình với kiểm thử, nên mã sai; ở đây chú thích của mã phản bác kiểm thử, nên kiểm thử sai.

### 8.4. Hạn chế

| Hạn chế | Mức ảnh hưởng |
|---|---|
| Khung 68 kịch bản chạy trên engine tất định, chưa chạy với mô hình thật | **Cao** — chưa có số liệu về tỷ lệ tuân thủ của Haiku |
| Chỉ một lượt khai vấn thật được đo (*n* = 1) | **Cao** — không suy rộng được |
| Không có so sánh giữa các mô hình hay các chiến lược prompt | Trung bình |
| Bộ kiểm chính sách câu hỏi chưa được đo precision/recall trên tập gán nhãn | Trung bình |
| Ba cổng kiểm duyệt bên ngoài đều ở trạng thái `pending` | Trung bình — chặn phát hành, không chặn nghiên cứu |
| Bốn kiểm thử trượt chưa được khắc phục | Thấp — đã phân tích, không nằm trên đường sinh |

---

## 9. Hướng phát triển

**Ngắn hạn — chạy khung đánh giá với mô hình thật.** Đây là việc có giá trị cao nhất và chi phí thấp nhất: bộ máy đã tồn tại và có thể thực thi, chỉ cần thay engine tất định bằng bộ điều hợp thật. Đầu ra sẽ là ma trận điểm rubric × kịch bản, cho phép báo cáo tỷ lệ vượt cổng và định vị các phạm trù yếu.

**Thay bộ phân loại cổng bằng mô hình học.** Từ phân tích ở Mục 8.2, hướng tự nhiên là huấn luyện một bộ phân loại ba lớp cho câu trả lời cổng tiếng Việt. Dữ liệu có thể khởi tạo từ các ca kiểm thử hiện có, mở rộng bằng sinh tổng hợp và gán nhãn thủ công. Nền tảng khả dĩ gồm tinh chỉnh một mô hình encoder đa ngữ hoặc phân loại few-shot bằng chính LLM. Tiêu chí đánh giá nên bất đối xứng: phạt nặng lỗi fail-open (dự đoán `YES` khi nhãn thật là `UNCLEAR`) hơn lỗi ngược lại.

**Đo lường bộ kiểm chính sách câu hỏi.** Xây một tập câu hỏi khai vấn được gán nhãn bởi người có chuyên môn, rồi đo precision/recall của 12 mã từ chối. Điều này biến một bộ lọc hiện chỉ được kiểm bằng ví dụ thành một bộ phân loại có số liệu.

**Phân tích chi phí của vòng sinh lại.** Thu thập phân phối số lần thử trên nhiều lượt thật để ước lượng chi phí kỳ vọng mỗi lượt và kiểm định xem cận `N = 2` có phải lựa chọn tốt không.

**So sánh với giải mã có dẫn hướng.** Đối chiếu tiếp cận hậu kiểm hiện tại với giải mã bị ràng buộc bởi ngữ pháp về tỷ lệ hợp lệ lần đầu và chi phí token.

---

## 10. Kết luận

Đồ án xây dựng một hệ thống ứng dụng mô hình ngôn ngữ lớn trong đó bài toán trọng tâm không phải là chất lượng mô hình mà là **bảo đảm hành vi**. Trên một mô hình nền không được huấn luyện lại, hệ thống đạt được các ràng buộc vai trò cứng của khai vấn thông qua bốn cơ chế phối hợp: hợp đồng đầu ra có cấu trúc, vòng sinh lại có kiểm chứng và có chặn, máy trạng thái đặt ở phía máy chủ, và bộ chọn ngữ cảnh bị ràng buộc bởi sự đồng ý.

Kết quả thực nghiệm còn khiêm tốn — một lượt thật đạt ở lần thử đầu, và khung đánh giá 68 kịch bản chưa chạy với mô hình thật — nhưng quá trình xây dựng cho ba kết luận phương pháp luận có giá trị vượt ra ngoài đồ án:

1. **Nhà cung cấp giả lập kiểm chứng đường xử lý, không kiểm chứng giao tiếp.** Hai khiếm khuyết nghiêm trọng nhất tồn tại qua toàn bộ bộ kiểm thử dùng mô hình giả và chỉ lộ ra ở lần gọi thật đầu tiên.
2. **Thông tin mà máy khách không được thấy, người vận hành vẫn phải thấy.** Một lỗi không để lại dấu vết là một lỗi không chẩn đoán được.
3. **Khi kiểm thử và mã bất đồng, phải truy ý định trước khi chọn bên.** Hai trường hợp trong đồ án có triệu chứng giống nhau nhưng kết luận ngược nhau.

Hướng phát triển rõ ràng nhất — chạy khung đánh giá đã có với mô hình thật, và thay bộ phân loại cổng theo luật bằng một mô hình học — sẽ đưa đồ án từ một công trình kỹ thuật hệ thống sang một công trình có thành phần thực nghiệm máy học đầy đủ.

---

## Tài liệu tham khảo

[1] T. Brown và cộng sự, "Language Models are Few-Shot Learners," *Advances in Neural Information Processing Systems (NeurIPS)*, 2020.

[2] B. T. Willard và R. Louf, "Efficient Guided Generation for Large Language Models," *arXiv preprint*, 2023.

[3] K. Cobbe và cộng sự, "Training Verifiers to Solve Math Word Problems," *arXiv preprint*, 2021.

[4] N. Shinn và cộng sự, "Reflexion: Language Agents with Verbal Reinforcement Learning," *Advances in Neural Information Processing Systems (NeurIPS)*, 2023.

[5] L. Ouyang và cộng sự, "Training Language Models to Follow Instructions with Human Feedback," *Advances in Neural Information Processing Systems (NeurIPS)*, 2022.

[6] Y. Bai và cộng sự, "Constitutional AI: Harmlessness from AI Feedback," *arXiv preprint*, 2022.

[7] L. Zheng và cộng sự, "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena," *Advances in Neural Information Processing Systems (NeurIPS) Datasets and Benchmarks Track*, 2023.

[8] P. Lewis và cộng sự, "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," *Advances in Neural Information Processing Systems (NeurIPS)*, 2020.

[9] X. Wang và cộng sự, "Self-Consistency Improves Chain of Thought Reasoning in Language Models," *International Conference on Learning Representations (ICLR)*, 2023.

[10] J. Wei và cộng sự, "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models," *Advances in Neural Information Processing Systems (NeurIPS)*, 2022.
