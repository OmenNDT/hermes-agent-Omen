# Bản thảo điền vào mẫu báo cáo UIT

> **Dành cho agent Microsoft 365.** Tài liệu này cung cấp toàn bộ nội dung để điền vào
> `1 Mẫu thực hiện đồ án/1 Mẫu thực hiện đồ án/1. Mẫu Báo cáo đồ án.docx`.
> Tiêu đề các mục dưới đây trùng khớp với tiêu đề trong mẫu.
> **Phần A** là các ô cần thay placeholder. **Phần B** là nội dung từng mục.
> Những chỗ đánh dấu 🔴 là thông tin người dùng phải tự cung cấp — không được tự bịa.

---

# PHẦN A — Thông tin điền vào placeholder

| Placeholder trong mẫu | Giá trị điền |
|---|---|
| `<TÊN SINH VIÊN>` | 🔴 **Người dùng cung cấp** |
| `<MÃ SINH VIÊN>` | 🔴 **Người dùng cung cấp** |
| `<TÊN NGÀNH>` | 🔴 **Người dùng cung cấp** |
| `<TÊN ĐỒ ÁN MÔN HỌC>` | Hermes Coach: Tác nhân khai vấn dựa trên mô hình ngôn ngữ lớn với đầu ra có ràng buộc và kiểm chứng |
| `<Tên Tiếng Anh>` | Hermes Coach: A Constraint-Verified Large Language Model Agent for Professional Coaching |
| Tên môn học | Máy học nâng cao |
| Giảng viên hướng dẫn | 🔴 **Người dùng cung cấp** |
| Năm / học kỳ | 🔴 **Người dùng cung cấp** |
| Đơn vị | Trung tâm Phát triển Công nghệ Thông tin — Trường Đại học Công nghệ Thông tin, ĐHQG TP. Hồ Chí Minh *(đã có sẵn trong mẫu)* |

## DANH MỤC TỪ VIẾT TẮT

| Từ viết tắt | Nghĩa đầy đủ |
|---|---|
| API | Application Programming Interface |
| AST | Abstract Syntax Tree — cây cú pháp trừu tượng |
| CAS | Compare-And-Set |
| GROW | Goal – Reality – Options – Will (khung khai vấn) |
| JSON | JavaScript Object Notation |
| KV cache | Key–Value cache (bộ nhớ đệm khoá–giá trị của Transformer) |
| LLM | Large Language Model — mô hình ngôn ngữ lớn |
| RAG | Retrieval-Augmented Generation |
| RLHF | Reinforcement Learning from Human Feedback |
| RPC | Remote Procedure Call |
| SQL | Structured Query Language |
| UI | User Interface — giao diện người dùng |
| WAL | Write-Ahead Logging |

## DANH MỤC HÌNH VẼ

| Số hiệu | Tên hình | Nguồn |
|---|---|---|
| Hình 3.1 | Sơ đồ khối kiến trúc tổng thể hệ thống | Mục 3.1, sơ đồ dạng text — cần vẽ lại |
| Hình 3.2 | Máy trạng thái sáu bước của phiên khai vấn | Mục 3.2 — cần vẽ lại |
| Hình 3.3 | Lưu đồ vòng sinh có kiểm chứng | Mục 3.3, mã giả — cần vẽ lại thành lưu đồ |
| Hình 4.1 | Phân bố số lần gọi mô hình trên 12 lượt đo | Bảng 4.3 — cần vẽ biểu đồ cột |
| Hình 4.2 | Chi phí token đầu vào theo số lần thử | Bảng 4.4 — cần vẽ biểu đồ cột |
| Hình 4.3 | Ảnh chụp giao diện web khi chạy thật | 🔴 **Người dùng chụp màn hình** |

## DANH MỤC BẢNG

| Số hiệu | Tên bảng |
|---|---|
| Bảng 2.1 | So sánh các hướng tiếp cận ràng buộc đầu ra mô hình sinh |
| Bảng 3.1 | Các trường của hợp đồng đầu ra `CoachOutput` |
| Bảng 3.2 | Mười hai mã từ chối của bộ kiểm chính sách câu hỏi |
| Bảng 3.3 | Bốn mức trạng thái an toàn và chế độ đầu ra tương ứng |
| Bảng 4.1 | Cấu hình mô hình và môi trường triển khai |
| Bảng 4.2 | Kết quả bộ kiểm thử tự động |
| Bảng 4.3 | Độ trễ và chi phí token trên 12 lượt khai vấn thật |
| Bảng 4.4 | Chi phí token theo số lần thử |
| Bảng 4.5 | Cấu trúc khung đánh giá theo kịch bản |

---

# PHẦN B — Nội dung các mục

## TÓM TẮT ĐỒ ÁN

Đồ án xây dựng Hermes Coach, một tác nhân khai vấn (coaching agent) chạy cục bộ trên máy người dùng, hiện thực hoá khung khai vấn sáu bước GROW mở rộng trên nền mô hình ngôn ngữ lớn Claude Haiku thông qua Anthropic Messages API.

Bài toán trọng tâm không phải là chất lượng sinh văn bản mà là **bảo đảm hành vi**: khai vấn chuyên nghiệp cấm người khai vấn đưa lời khuyên, cấm quyết định thay, và bắt buộc mỗi lượt chỉ hỏi đúng một câu hỏi — những ràng buộc mà một mô hình ngôn ngữ tổng quát vi phạm một cách tự nhiên, vì nó được huấn luyện để hữu ích và "hữu ích" theo bản năng của nó là đưa ra giải pháp.

Lời giải được đặt ở tầng hệ thống gồm bốn cơ chế phối hợp: hợp đồng đầu ra có cấu trúc với lược đồ cấm trường thừa; vòng sinh lại có kiểm chứng và có chặn trên; máy trạng thái sáu bước đặt ở phía máy chủ chứ không ở phía mô hình; và bộ chọn ngữ cảnh bị ràng buộc bởi sự đồng ý của người dùng.

Hệ thống gồm 74 mô-đun Python (10.047 dòng) và 46 tệp TypeScript, được bảo vệ bởi 1.112 kiểm thử Python và 246 kiểm thử web, tỷ lệ mã kiểm thử trên mã nguồn xấp xỉ 1,82:1. Thực nghiệm trên 12 lượt khai vấn thật với Haiku cho: tỷ lệ hợp lệ ngay lần thử đầu 75%, độ trễ mô hình trung vị 2,47 giây, và **100% số lượt mở đúng ở bước Pre-Coaching** thay vì nhảy thẳng sang bước Goal. Đồ án cũng định lượng được rằng chi phí token của vòng sinh lại tăng siêu tuyến tính theo số lần thử — gấp 2,55 lần ở hai lần thử và 4,48 lần ở ba lần thử.

**Từ khoá:** mô hình ngôn ngữ lớn, tác nhân, sinh có cấu trúc, rejection sampling, guardrails, đánh giá hệ sinh.

---

## MỞ ĐẦU

Sự trưởng thành của các mô hình ngôn ngữ lớn đã dịch chuyển trọng tâm của nhiều bài toán ứng dụng từ *huấn luyện mô hình* sang *điều khiển mô hình*. Với một mô hình nền đủ mạnh, phần lớn công sức kỹ thuật không còn nằm ở việc tối ưu tham số, mà ở việc ràng buộc đầu ra của một hệ thống sinh vốn mang bản chất xác suất sao cho nó thoả mãn một đặc tả nghiệp vụ cứng.

Đồ án khảo sát bài toán đó trong một miền ứng dụng có đặc tả đặc biệt chặt — khai vấn chuyên nghiệp — và trình bày một kiến trúc tác nhân trong đó mọi đầu ra đến được người dùng đều đã đi qua kiểm chứng tất định.

Báo cáo được viết trên cơ sở một hệ thống đã chạy được đầu-cuối với mô hình thật, và mọi số liệu nêu trong báo cáo đều được đo trực tiếp từ mã nguồn hoặc từ các lượt chạy thực tế, không ước lượng.

---

## Chương 1: TỔNG QUAN VỀ ĐỀ TÀI

### 1.1 Đặt vấn đề và tính cấp thiết

**Tại sao cần một tác nhân, không phải một hộp thoại hỏi–đáp?**

Khai vấn không phải là hoạt động hỏi–đáp một lượt. Nó là một tiến trình có trạng thái, kéo dài qua nhiều phiên, trong đó mỗi bước chỉ được đóng lại khi người được khai vấn (Coachee) xác nhận rõ ràng, và trong đó những gì được ghi nhớ giữa các phiên quyết định chất lượng của phiên sau. Một mô hình hỏi–đáp thụ động không giữ được tiến trình đó: nó không biết đang ở bước nào, không biết bước trước đã đóng hay chưa, và không phân biệt được một đề xuất với một bản ghi đã được xác nhận.

**Tại sao bài toán khó?**

Đặc tả nghề nghiệp của khai vấn đi ngược lại xu hướng mặc định của mô hình ngôn ngữ:

| Quy tắc khai vấn | Xu hướng mặc định của LLM |
|---|---|
| Không đưa lời khuyên | Đưa giải pháp ngay khi nhận ra vấn đề |
| Mỗi lượt đúng một câu hỏi | Hỏi nhiều câu, hoặc hỏi kèm giải thích dài |
| Không nhảy bước | Đi thẳng vào mục tiêu khi người dùng nhắc tới mục tiêu |
| Không quyết định thay | Chủ động đề xuất phương án tối ưu |

Sự lệch pha này không thể khắc phục chỉ bằng cách viết prompt cẩn thận hơn, vì một mô hình tuân thủ 99% vẫn vi phạm ở lượt thứ 100 — và trong miền khai vấn, một lần đưa lời khuyên sai thời điểm có thể phá hỏng toàn bộ quan hệ khai vấn.

**Tính cấp thiết.** Các ứng dụng trợ lý dựa trên LLM đang được triển khai rộng trong những miền có ràng buộc nghiệp vụ và đạo đức chặt: y tế, giáo dục, tài chính, sức khoẻ tinh thần. Câu hỏi kỹ thuật chung của cả nhóm ứng dụng này không phải "làm sao cho mô hình trả lời hay hơn" mà "làm sao bảo đảm mô hình không bao giờ trả lời theo cách bị cấm". Đồ án đóng góp một kiến trúc tham chiếu cho câu hỏi đó.

### 1.2 Mục tiêu nghiên cứu

**Mục tiêu tổng quát:** xây dựng một tác nhân khai vấn dựa trên LLM trong đó mọi đầu ra đến được người dùng đều thoả mãn đồng thời năm nhóm ràng buộc, và chứng minh điều đó bằng hệ thống chạy thật cùng bộ kiểm thử tự động.

**Mục tiêu cụ thể:**

1. Thiết kế hợp đồng đầu ra có cấu trúc, cấm trường thừa, và ràng buộc "đúng một câu hỏi" ở mức lược đồ.
2. Xây dựng vòng sinh lại có kiểm chứng với cận trên xác định, bảo đảm không đầu ra nào chạm tới đích hiển thị hoặc lưu trữ trước khi được kiểm.
3. Hiện thực máy trạng thái sáu bước ở phía máy chủ, sao cho giao diện và mô hình đều không thể tự quyết định một bước đã đóng.
4. Thiết kế bộ chọn ngữ cảnh tối thiểu hoá lượng dữ liệu rời khỏi máy và tôn trọng việc rút lại đồng ý ngay ở yêu cầu kế tiếp.
5. Xây dựng khung đánh giá theo rubric cho hệ sinh, có thể thực thi lặp lại.
6. Đo độ trễ và chi phí token trên các lượt chạy thật.

### 1.3 Đối tượng và phạm vi nghiên cứu

**Đối tượng nghiên cứu:** kiến trúc phần mềm của tác nhân dựa trên LLM trong miền có ràng buộc cứng; các cơ chế ràng buộc đầu ra sinh.

**Phạm vi:**

| Hạng mục | Lựa chọn |
|---|---|
| Mô hình nền | Claude Haiku (`claude-haiku-4-5-20251001`), gọi trực tiếp qua Anthropic Messages API |
| Framework tác nhân | Không dùng LangChain/LangGraph/AutoGen — tự hiện thực để kiểm soát hoàn toàn ranh giới kiến trúc |
| Nền tảng | Windows, ứng dụng web cục bộ, chỉ lắng nghe trên loopback |
| Người dùng | Một người dùng duy nhất, không có mô hình tài khoản |
| Ngôn ngữ giao tiếp | Tiếng Việt |
| Cơ sở dữ liệu | SQLite (WAL) |

**Phạm vi đồ án KHÔNG bao gồm** — nêu rõ để tránh hiểu nhầm:

- Không huấn luyện, không tinh chỉnh mô hình, không có tập dữ liệu gán nhãn.
- Không báo cáo các độ đo kiểu accuracy/precision/recall/F1 trên tập kiểm thử học máy.
- Không triển khai nhiều người dùng, không có xác thực đăng nhập, không cho truy cập qua mạng LAN.

Đồ án tự định vị là công trình **kỹ thuật hệ thống ứng dụng LLM**, thuộc nhánh vận hành và kiểm soát mô hình sinh.

### 1.4 Cấu trúc báo cáo

**Chương 1** trình bày bối cảnh, phát biểu vấn đề, mục tiêu và phạm vi.

**Chương 2** trình bày cơ sở lý thuyết về học trong ngữ cảnh, sinh có cấu trúc, bộ kiểm chứng, guardrails và đánh giá hệ sinh; đồng thời khảo sát các nghiên cứu liên quan.

**Chương 3** là chương trọng tâm, trình bày kiến trúc tổng thể, máy trạng thái khai vấn, vòng sinh có kiểm chứng, bộ kiểm chính sách, định tuyến an toàn và thiết kế cơ sở dữ liệu.

**Chương 4** trình bày môi trường triển khai, kết quả chạy thật với 12 lượt khai vấn đo được, kết quả bộ kiểm thử tự động và khung đánh giá theo kịch bản.

**Chương 5** kết luận và nêu hướng phát triển.

---

## Chương 2: CƠ SỞ LÝ THUYẾT

### 2.1 Tổng quan các nghiên cứu liên quan

#### 2.1.1 Tổng quan ngoài nước

**Học trong ngữ cảnh.** Brown và cộng sự [1] cho thấy hành vi của mô hình ngôn ngữ lớn được định hình bởi chuỗi token đầu vào mà không cần cập nhật trọng số. Hệ quả kỹ thuật là prompt trở thành một cấu phần phần mềm: nó có phiên bản, có hợp đồng, và có thể hồi quy.

**Sinh có dẫn hướng.** Willard và Louf [2] trình bày kỹ thuật giải mã bị ràng buộc bởi máy trạng thái hữu hạn, cho phép bảo đảm đầu ra khớp ngữ pháp ngay trong quá trình sinh. Đây là hướng thay thế cho tiếp cận hậu kiểm mà đồ án sử dụng; so sánh ở Bảng 2.1.

**Bộ kiểm chứng.** Cobbe và cộng sự [3] chứng minh rằng huấn luyện một bộ kiểm chứng để lọc các lời giải sinh ra cải thiện đáng kể độ chính xác trên bài toán toán học. Ý tưởng tổng quát — sinh nhiều mẫu, giữ mẫu vượt kiểm chứng — là nền tảng cho vòng sinh lại của đồ án, với khác biệt là bộ kiểm ở đây tất định thay vì học được.

**Tự nhất quán và tự phản tỉnh.** Wang và cộng sự [9] lấy mẫu song song rồi bỏ phiếu; Shinn và cộng sự [4] đưa phản hồi ngôn ngữ vào lần thử kế tiếp. Đồ án dùng biến thể tuần tự có phản hồi, nhưng phản hồi đến từ bộ kiểm tất định chứ không từ chính mô hình.

**Căn chỉnh.** Ouyang và cộng sự [5] căn chỉnh bằng học tăng cường từ phản hồi con người; Bai và cộng sự [6] dùng một tập nguyên tắc tường minh. Cả hai tác động lên trọng số, bổ trợ chứ không thay thế lớp guardrails ở tầng ứng dụng.

**Đánh giá.** Zheng và cộng sự [7] khảo sát việc dùng chính LLM làm giám khảo. Đồ án chọn hướng rubric do con người thiết kế, vì miền khai vấn có các quy tắc phát biểu được tường minh và rubric cho phép truy vết từng tiêu chí về yêu cầu gốc.

**Truy xuất.** Lewis và cộng sự [8] ghép bộ truy xuất với bộ sinh. Đồ án dùng biến thể rút gọn, trong đó tiêu chí chọn không phải độ liên quan mà là lượng dữ liệu tối thiểu được phép rời máy.

**Khoảng trống nghiên cứu.** Các công trình trên tối ưu *chất lượng trung bình* của đầu ra. Đồ án hướng tới *xác suất vi phạm bằng không* trên một tập ràng buộc cứng — bài toán bảo đảm hơn là bài toán chất lượng. Đây là khoảng trống mà đồ án nhắm tới.

#### 2.1.2 Tổng quan trong nước

> 🔴 **CẦN NGƯỜI DÙNG BỔ SUNG.**
>
> Tác giả báo cáo chưa thực hiện khảo sát hệ thống các công trình tiếng Việt về chủ đề này,
> và **không** đưa vào đây bất kỳ trích dẫn nào chưa được kiểm chứng.
>
> Gợi ý từ khoá tìm kiếm trên Google Scholar, thư viện số các trường và tạp chí trong nước:
> *"mô hình ngôn ngữ lớn tiếng Việt"*, *"tác nhân AI"*, *"trợ lý ảo tư vấn tâm lý"*,
> *"xử lý ngôn ngữ tự nhiên tiếng Việt"*, *"chatbot hỗ trợ tư vấn"*, *"PhoBERT"*, *"ViGPT"*.
>
> Cấu trúc đề xuất cho mục này: (a) tình hình nghiên cứu LLM tiếng Việt; (b) các ứng dụng
> trợ lý/chatbot trong nước thuộc miền tư vấn hoặc giáo dục; (c) khoảng trống — theo hiểu biết
> của tác giả, chưa có công trình trong nước công bố về kiến trúc bảo đảm ràng buộc vai trò
> cho tác nhân khai vấn.

### 2.2 Kiến trúc và các thành phần của AI Agent

Một tác nhân dựa trên LLM thường gồm bốn thành phần cốt lõi. Bảng dưới đối chiếu mô hình chuẩn với lựa chọn của đồ án:

| Thành phần | Mô hình chuẩn | Lựa chọn của Hermes Coach |
|---|---|---|
| **Lập kế hoạch** (Planning) | Mô hình tự phân rã nhiệm vụ, tự chọn bước kế tiếp | Máy trạng thái sáu bước **ở phía máy chủ**; mô hình đề xuất, tầng miền quyết định |
| **Bộ nhớ** (Memory) | Ngắn hạn trong cửa sổ ngữ cảnh, dài hạn trong vector database | Ngắn hạn: bản ghi hội thoại của phiên. Dài hạn: SQLite có cấu trúc, chỉ gồm bản ghi **đã được người dùng xác nhận** |
| **Sử dụng công cụ** (Tool use) | Function calling để tác nhân hành động lên môi trường | **Không cấp công cụ nào** — xem lập luận bên dưới |
| **Hành động** (Action) | Tác nhân thực thi trực tiếp | Tác nhân chỉ sinh **một câu hỏi**; mọi thay đổi dữ liệu do người dùng xác nhận |

**Vì sao đồ án cố ý không dùng function calling.** Đây là điểm mà đồ án lệch khỏi kiến trúc tác nhân thông dụng, và lệch có chủ đích chứ không phải do thiếu sót kỹ thuật.

Định nghĩa nghề nghiệp của khai vấn đặt quyền hành động hoàn toàn về phía người được khai vấn. Một Coach gọi được công cụ là một Coach có thể hành động thay họ — đặt lịch, gửi thư, tạo mục tiêu — và mỗi hành động như vậy đều lấy đi một quyết định lẽ ra thuộc về người được khai vấn. Ràng buộc này được cưỡng chế ở mức mã: bộ điều hợp thời gian chạy **từ chối khởi tạo** bất kỳ tác nhân nào khai báo có công cụ, và có kiểm thử riêng cho việc đó.

Hệ quả là mọi bản ghi mà mô hình đề xuất — mục tiêu, nhận thức, cam kết, ký ức — chỉ tồn tại ở dạng **ứng viên** (candidate). Trò chuyện không xác nhận được bản ghi; người dùng phải chấp nhận, sửa hoặc loại bỏ **từng cái một** trong giao diện, không có thao tác gộp.

### 2.3 Mô hình ngôn ngữ lớn (LLM) và cơ chế suy luận của Agent

**Nền tảng.** Mô hình ngôn ngữ lớn là mạng nơ-ron kiến trúc Transformer, huấn luyện tự giám sát trên khối lượng văn bản lớn để dự đoán token kế tiếp. Khả năng thực hiện nhiệm vụ mới chỉ từ mô tả trong prompt — không cần cập nhật trọng số — là tính chất then chốt mà đồ án khai thác.

**Sinh có cấu trúc.** Có ba hướng ràng buộc đầu ra:

**Bảng 2.1: So sánh các hướng tiếp cận ràng buộc đầu ra mô hình sinh**

| Hướng | Cách làm | Ưu điểm | Nhược điểm | Đồ án |
|---|---|---|---|---|
| Giải mã có dẫn hướng | Ràng buộc không gian token ngay khi sinh | Bảo đảm hợp lệ ngay lần đầu | Phụ thuộc quyền truy cập bộ giải mã | Không dùng |
| Chế độ JSON của nhà cung cấp | Bật cờ ở API | Đơn giản | Phụ thuộc nhà cung cấp cụ thể | Không dùng |
| **Hậu kiểm bằng lược đồ** | Sinh tự do, hợp thức hoá sau | Độc lập nhà cung cấp, kiểm được cả ngữ nghĩa | Có thể trượt lần đầu, tốn thêm lượt gọi | **Đang dùng** |

Lựa chọn hậu kiểm giữ cho tầng miền độc lập với nhà cung cấp, và quan trọng hơn: nó cho phép kiểm cả những ràng buộc **ngữ nghĩa** mà lược đồ JSON không biểu diễn được, ví dụ "không được là lời khuyên trá hình".

**Ổn định tiền tố và bộ nhớ đệm.** Chi phí suy luận Transformer giảm đáng kể khi tái sử dụng bộ nhớ đệm khoá–giá trị cho phần tiền tố không đổi. Điều kiện là tiền tố phải giống nhau **đến từng byte**. Ràng buộc này có hệ quả thiết kế trực tiếp: mọi trạng thái động phải nằm ngoài prompt hệ thống. Đồ án tuân thủ bằng cách đặt prompt hệ thống vào trường `system` của API, băm nó để kiểm tính bất biến trước mỗi lượt, và đưa toàn bộ ngữ cảnh động vào thông điệp lượt.

**Guardrails.** Ngoài hai lớp căn chỉnh tác động lên trọng số (RLHF, nguyên tắc tường minh), lớp thứ ba là các bộ lọc tất định chạy ngoài mô hình. Guardrails khả kiểm, khả giải thích và sửa được tức thì; nhược điểm là giòn trước biến thể ngôn ngữ — hạn chế này được phân tích định lượng ở Mục 5.1.

---

## Chương 3: PHÂN TÍCH VÀ THIẾT KẾ HỆ THỐNG

### 3.1 Thiết kế kiến trúc tổng thể

#### 3.1.1 Sơ đồ khối toàn hệ thống

**Hình 3.1** — sơ đồ khối (cần vẽ lại từ mô tả sau):

```text
┌─────────────────────────────────────────────┐
│  Người dùng — Giao diện web React            │
│  (46 tệp TypeScript, hash routing, 8 màn hình)│
└───────────────────┬─────────────────────────┘
                    │ JSON-RPC trên WebSocket (chỉ loopback)
┌───────────────────▼─────────────────────────┐
│  Tầng API — xác thực loopback 4 lớp,         │
│  điều phối RPC, quản lý huỷ lượt             │
├─────────────────────────────────────────────┤
│  Tầng ứng dụng — dịch vụ lượt khai vấn,      │
│  chọn ngữ cảnh, đồng ý, an toàn, lưu trữ     │
├─────────────────────────────────────────────┤
│  Tầng miền — máy trạng thái sáu bước,        │
│  quy tắc mục tiêu, quy tắc lựa chọn          │
├─────────────────────────────────────────────┤
│  Tầng hạ tầng — SQLite (WAL), các kho dữ liệu│
│  bộ điều hợp thời gian chạy                  │
└───────────────────┬─────────────────────────┘
                    │ Anthropic Messages API
            ┌───────▼────────┐
            │  Claude Haiku   │
            └────────────────┘
```

**Ranh giới kiến trúc được cưỡng chế tự động.** Gói `hermes_coach` bị cấm nhập khẩu bất kỳ mô-đun nào của tác nhân chủ. Lệnh cấm không phải quy ước tài liệu mà là một kiểm thử duyệt cây cú pháp trừu tượng (AST) của toàn bộ mã nguồn, nên bắt được cả lệnh nhập khẩu lồng trong hàm. Hệ quả thiết kế cụ thể: bộ cung cấp mô hình phải nằm **ngoài** gói, ở tầng giao diện dòng lệnh, và được tiêm vào qua một điểm nối (`agent_factory`).

#### 3.1.2 Yêu cầu chức năng và phi chức năng

**Yêu cầu chức năng:**

1. Dẫn một phiên khai vấn qua sáu bước, mỗi lượt sinh đúng một câu hỏi.
2. Đề xuất ứng viên bản ghi (mục tiêu, nhận thức, cam kết, ký ức) và cho người dùng xác nhận từng cái.
3. Ghi và truy xuất bản ghi hội thoại, mục tiêu, nhận thức theo phiên.
4. Ghi nhận và rút lại sự đồng ý gửi dữ liệu tới mô hình.
5. Phát hiện tín hiệu an toàn và định tuyến sang chế độ phù hợp.
6. Dọn dữ liệu hết hạn theo chính sách lưu trữ.

**Yêu cầu phi chức năng:**

| Yêu cầu | Mục tiêu | Kết quả đo (Chương 4) |
|---|---|---|
| Độ trễ một lượt | Đủ nhanh cho hội thoại | Trung vị 2,47 s |
| Chi phí token có cận trên | Không vượt 3 lần gọi/lượt | Tối đa 3, đúng thiết kế |
| Tính ổn định | Không đầu ra không hợp lệ nào lọt tới người dùng | 12/12 lượt hợp lệ |
| Bảo mật | Chỉ truy cập được từ máy này | 4 lớp kiểm độc lập |
| Quyền riêng tư | Dữ liệu chưa đồng ý không rời máy | Kiểm lại đồng ý mỗi lượt |

### 3.2 Thiết kế cơ chế lập kế hoạch và sử dụng công cụ

#### 3.2.1 Máy trạng thái khai vấn

**Hình 3.2** — máy trạng thái (cần vẽ lại):

```text
Pre-Coaching ──► Goal ──► Reality ──► Options ──► Will ──► Review
      ▲                                                        │
      └──────── quay lui có mục tiêu cụ thể ◄──────────────────┘
```

Quy tắc chuyển trạng thái:

- **Không nhảy bước.** Pre-Coaching là bước duy nhất tuyệt đối không được bỏ qua.
- Một bước chỉ hoàn tất khi vị từ của bước đã đủ, Coach hỏi đúng một câu chốt dạng Có/Không nêu rõ cả hai cực, và phản hồi là một sự đồng ý rõ ràng.
- Câu đã giả định sẵn câu trả lời (*"Bạn sẵn sàng chứ?"*) là câu dẫn dắt, không phải câu chốt. Câu hai lựa chọn (*"A, hay B?"*) là câu chọn, không phải câu chốt.
- Quay lui phải có bước đích cụ thể, vô hiệu hoá cổng đích và mọi cổng phía sau.

**Điểm thiết kế cốt lõi: máy trạng thái nằm ở phía máy chủ, không ở phía mô hình.** Mô hình đề xuất bước kế tiếp, nhưng việc một cổng có mở hay không do tầng miền quyết định. Giao diện cũng không tự suy diễn trạng thái — nó chỉ hiển thị lại những gì máy chủ báo. Nguyên tắc này loại bỏ cả một lớp lỗi trong đó ba thành phần cùng tin vào ba phiên bản khác nhau của tiến trình.

#### 3.2.2 Lựa chọn mô hình nền và bộ công cụ

**Vì sao chọn Claude Haiku?** Nhiệm vụ mỗi lượt là sinh một câu hỏi ngắn theo lược đồ cố định — không đòi hỏi suy luận dài. Haiku là mô hình có độ trễ thấp và chi phí thấp trong họ Claude, phù hợp với một ứng dụng hội thoại chạy cục bộ. Kết quả đo ở Mục 4.3 xác nhận độ trễ trung vị 2,47 giây là chấp nhận được cho hội thoại.

**Vì sao không trang bị công cụ nào?** Đã lập luận ở Mục 2.2. Tóm tắt: quyền hành động thuộc về người được khai vấn; bộ điều hợp từ chối mọi tác nhân khai báo có công cụ, và đây là ràng buộc được kiểm thử.

### 3.3 Thiết kế phần mềm và tích hợp AI

#### 3.3.1 Hợp đồng đầu ra có cấu trúc

**Bảng 3.1: Các trường của hợp đồng đầu ra `CoachOutput`**

| Trường | Kiểu | Ràng buộc |
|---|---|---|
| `question` | chuỗi | Đúng một dấu hỏi, và phải kết thúc bằng dấu hỏi |
| `coaching_stage` | enum | Một trong sáu bước |
| `candidate_insights` / `_goals` / `_commitments` / `_memories` | bộ | Mỗi mảng phải khớp đúng loại bản ghi |
| `goal_smart_status` | enum | Mặc định `unassessed` |
| `safety_signal` | enum | Mặc định `none` |

Lược đồ cấu hình `extra="forbid"` (từ chối trường thừa) và `frozen=True` (bất biến). Ràng buộc "đúng một dấu hỏi" được hiện thực ở tầng validator, nghĩa là một đầu ra vi phạm **không bao giờ tồn tại** dưới dạng một đối tượng hợp lệ trong bộ nhớ.

#### 3.3.2 Lưu đồ thuật toán: vòng sinh có kiểm chứng

Đây là thuật toán trung tâm của hệ thống. **Hình 3.3** — cần vẽ lại thành lưu đồ từ mã giả sau:

```text
Đầu vào: yêu cầu lượt r, prompt hệ thống P (bất biến), cận N = 2
Đầu ra:  CoachOutput hợp lệ, hoặc lỗi có kiểu

1.  kiểm vân tay của P; nếu lệch → dừng, lỗi prompt_unstable
2.  m ← soạn thông điệp lượt từ r, kèm hợp đồng đầu ra
3.  lý_do ← ∅;  lần ← 0
4.  while lần ≤ N:
5.      lần ← lần + 1
6.      nếu lần > 1: m ← m + khối [regenerate] kèm lý_do
7.      thô ← gọi mô hình(P, m)        # lỗi truyền tải → provider_error
8.      cộng dồn hạch toán sử dụng
9.      thô ← gỡ hàng rào markdown(thô)
10.     thử: out ← hợp_thức_hoá_lược_đồ(thô)
11.     nếu trượt: lý_do ← {schema_invalid}; continue
12.     phán ← kiểm_chứng_câu_hỏi(out.question, đầu vào Coachee)
13.     nếu phán hợp lệ:
14.         phát ra out              ◄── ĐIỂM DUY NHẤT out chạm sink
15.         return out, lần
16.     lý_do ← mã lý do của phán
17. dừng, lỗi có kiểu (schema_error hoặc policy_error)
```

Ba tính chất được kiểm thử tường minh:

1. **Không đầu ra nào chạm sink trước khi hợp lệ.** Dòng 14 là điểm phát duy nhất, nằm sau cả hai lớp kiểm.
2. **Luân phiên vai trò nghiêm ngặt.** Lần sinh lại được nối vào cùng hội thoại như một nỗ lực khác cho *cùng lượt đó*, không phải như một thông điệp người dùng bịa ra. Làm sai sẽ tạo hai lượt người dùng liên tiếp và mô hình hiểu sai bối cảnh.
3. **Chi phí có cận trên.** Tối đa 3 lần gọi mỗi lượt, `max_tokens = 1024` mỗi lần.

#### 3.3.3 Thiết kế prompt: hợp đồng nêu trong lượt

Hai yêu cầu xung đột: mô hình cần biết lược đồ, nhưng prompt hệ thống phải bất biến từng byte để giữ tiền tố cache. Lời giải là đặt hợp đồng vào **thông điệp lượt**:

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

Danh sách bước được sinh từ chính enum trong mã, nên hợp đồng không thể lệch khỏi lược đồ khi lược đồ thay đổi.

#### 3.3.4 Bộ kiểm chính sách câu hỏi

**Bảng 3.2: Mười hai mã từ chối của bộ kiểm chính sách câu hỏi**

| Nhóm | Mã từ chối |
|---|---|
| Cấu trúc | `empty`, `multiple_questions`, `not_a_question`, `standalone_statement`, `multiple_focuses` |
| Vai trò | `imperative`, `disguised_advice`, `leading_answer`, `authority_claim` |
| Đạo đức nghề | `judgment`, `diagnosis_or_label`, `inferred_cause` |

Bộ kiểm chuẩn hoá Unicode và bỏ dấu tiếng Việt trước khi khớp mẫu, dùng biểu thức chính quy cho lời khuyên trá hình (`bạn nên`, `tại sao bạn không`, `lựa chọn tốt nhất`…), mệnh đề ghép, và tiền tố phản ánh.

Điểm phương pháp đáng lưu ý: nhóm **Vai trò** và **Đạo đức nghề** chính là thứ phân biệt khai vấn với tư vấn, và chúng **không thể** được đảm bảo bằng lược đồ JSON. Đây là lý do hệ thống cần một bộ kiểm ngữ nghĩa bên cạnh bộ kiểm cú pháp.

#### 3.3.5 Định tuyến an toàn

**Bảng 3.3: Bốn mức trạng thái an toàn và chế độ đầu ra tương ứng**

| Trạng thái | Chế độ đầu ra | Hành vi |
|---|---|---|
| `normal` | `coaching_question` | Khai vấn bình thường |
| `sensitive` | `permission_question` | Xin phép trước khi đào sâu |
| `possible_crisis` | `safety_check` | Tạm dừng khai vấn, kiểm tra an toàn |
| `urgent` | `direct_safety_guidance` / `blocked` | Ngắt khai vấn, chỉ phát hướng dẫn đã được phê duyệt |

**Nguyên tắc fail-closed:** ở mức `urgent`, nếu bằng chứng phê duyệt hướng dẫn trực tiếp rỗng hoặc bịa, hệ thống trả `blocked` chứ không trả nội dung. Hệ thống không bao giờ tự hạ mức an toàn hay tự động tiếp tục khai vấn.

Ở phía giao diện, trạng thái `urgent` **thay thế** khai vấn chứ không phải phủ một biểu ngữ lên trên: các điều khiển sáu bước biến mất, nên không còn đường tiếp tục khai vấn xuyên qua nó.

#### 3.3.6 Bộ chọn ngữ cảnh

Bộ chọn ngữ cảnh là cổng cuối cùng trước khi dữ liệu rời máy, áp hai bộ lọc độc lập:

1. Các kho dữ liệu đã loại sẵn hàng trong Thùng rác, hàng hết hạn và hàng chưa xác nhận.
2. Mỗi mục còn phải nằm trong một phạm vi mà sự đồng ý **hiện vẫn còn hiệu lực**.

Sự đồng ý được đọc lại tại đây thay vì tin vào kết quả của lượt trước, để việc rút lại đồng ý có hiệu lực ngay ở yêu cầu kế tiếp.

Phạm vi lấy dữ liệu cố ý hẹp: mục tiêu đang hoạt động, các nhận thức thuộc mục tiêu đó, bản ghi hội thoại của phiên hiện tại, và ký ức đã được phê duyệt. **Có dữ liệu không phải là lý do để gửi đi.**

### 3.4 Thiết kế cơ sở dữ liệu

**Hệ quản trị:** SQLite, chế độ WAL, `isolation_level=None` với `BEGIN IMMEDIATE` để kiểm soát giao dịch tường minh.

**Các nhóm bảng chính:**

| Nhóm | Bảng tiêu biểu | Vai trò |
|---|---|---|
| Hồ sơ | `coachee_profile`, `career_snapshot` | Một người dùng duy nhất; ảnh chụp nghề nghiệp có tính lịch sử |
| Phiên | `coaching_session`, `session_message` | Phiên khai vấn và bản ghi hội thoại |
| Bản ghi | `goal`, `insight`, `commitment`, `memory_item` | Bản ghi bền vững, đã xác nhận |
| Ứng viên | `candidate_record` | Đề xuất chưa xác nhận, có hạn 90 ngày |
| Quyền riêng tư | `consent_event`, `egress_audit`, `trash_entry` | Bằng chứng đồng ý, nhật ký gửi dữ liệu, Thùng rác |
| Nội bộ | `internal_session_revision`, `internal_idempotency` | Kiểm soát đồng thời lạc quan và chống lặp lệnh |

**Ba cơ chế đáng nêu:**

1. **Kiểm soát đồng thời lạc quan.** Mỗi lệnh thay đổi mang theo số hiệu phiên bản (revision) của phiên. Máy chủ từ chối lệnh dựng trên một góc nhìn đã lỗi thời. Yêu cầu là khớp **chính xác**, không phải "nhỏ hơn hoặc bằng": một máy khách khai báo phiên bản chưa từng tồn tại cũng sai như một máy khách tụt hậu.

2. **Chống lặp lệnh theo khoá bất biến.** Một lệnh gửi lại sẽ phát lại kết quả lần đầu thay vì áp dụng lần hai.

3. **Xác nhận bản ghi bằng ý định dùng một lần.** Việc xác nhận một ứng viên diễn ra hai bước: đúc một ý định (intent) gắn chặt với người dùng, phiên, ứng viên, hành động và nội dung đã sửa; rồi tiêu thụ ý định đó. Token ý định **chỉ được lưu dưới dạng băm SHA-256**, không bao giờ lưu nguyên văn. Việc cập nhật hàng ứng viên dùng compare-and-set.

**Chính sách lưu trữ:** dữ liệu tạm thời 90 ngày, Thùng rác 30 ngày. Bản ghi hội thoại **được giữ vô thời hạn** cho tới khi người dùng xoá — một quyết định sản phẩm đảo ngược quy tắc ban đầu, vì việc xoá hội thoại trong khi vẫn giữ các kết luận rút ra từ nó là kiểu mất mát gây hại nhất.

---

## Chương 4: KẾT QUẢ THỰC NGHIỆM

### 4.1 Môi trường và công cụ triển khai

**Bảng 4.1: Cấu hình mô hình và môi trường triển khai**

| Hạng mục | Giá trị |
|---|---|
| Hệ điều hành | Windows 11 |
| Ngôn ngữ backend | Python 3.12 |
| Framework web | FastAPI + uvicorn (WebSocket) |
| Cơ sở dữ liệu | SQLite, chế độ WAL |
| Giao diện | React 19, Vite, TypeScript, nanostores |
| Mô hình | `claude-haiku-4-5-20251001` |
| Giao thức gọi mô hình | Anthropic Messages API (gọi trực tiếp, không qua framework tác nhân) |
| `max_tokens` | 1.024 |
| Công cụ cấp cho mô hình | Không có |
| Số lần sinh lại tối đa | 2 (tối đa 3 lần gọi mỗi lượt) |
| Kiểm chất lượng mã | `ruff` (lint), `ty` (kiểm kiểu), `pytest`, `vitest`, ESLint, `tsc` |

**Quy mô hệ thống:**

| Thành phần | Số tệp | Số dòng |
|---|---:|---:|
| Mã nguồn `hermes_coach` | 74 | 10.047 |
| Kiểm thử `tests/hermes_coach` | 74 | 18.298 |
| Giao diện web (TS/TSX) | 46 | — |

Tỷ lệ mã kiểm thử trên mã nguồn xấp xỉ **1,82:1**.

### 4.2 Kết quả triển khai

#### 4.2.1 Luồng hoạt động thực tế

Hệ thống khởi chạy bằng một lệnh, in ra đường dẫn kèm token phiên:

```text
Hermes Coach — profile default
  Dữ liệu Coach lưu trên máy này và không được mã hoá. Người hoặc tiến trình
  có quyền đọc tệp đều đọc được nội dung.
  http://127.0.0.1:8976?token=4TnYoNjeaqZs83gWK3KOUkZSgif4oZcqfulgI7U5m1Q
```

Dòng công bố về việc dữ liệu không được mã hoá được in **trước khi** máy chủ khởi động, vì người dùng cần biết điều đó trước khi đưa bất kỳ nội dung nào vào.

Một lượt khai vấn thật, đầu-cuối:

| Mục | Nội dung |
|---|---|
| Đầu vào | *"Tôi muốn chuyển sang vai trò kiến trúc sư nhưng chưa biết bắt đầu từ đâu."* |
| Câu hỏi sinh ra | *"Bây giờ bạn cảm thấy như thế nào khi nghĩ về ý định chuyển sang kiến trúc sư này?"* |
| Bước | `pre_coaching` |
| Số lần thử | 1 |
| Ghi bền trước khi phát | Có |

Kết quả này có ba điểm đáng phân tích. Thứ nhất, **mô hình không nhảy cóc**: đầu vào nói về mục tiêu nghề nghiệp, và một mô hình hữu ích theo bản năng sẽ đi thẳng vào bước Goal; mô hình mở ở `pre_coaching` và hỏi về trạng thái cảm xúc. Thứ hai, đúng một câu hỏi và không kèm lời khuyên. Thứ ba, bản ghi hội thoại đã commit **trước khi** câu trả lời được phát ra.

#### 4.2.2 Giao diện người dùng

Giao diện web gồm tám màn hình: Hôm nay, Bắt đầu, Phiên coaching, Mục tiêu, Hành trình, Nhận thức, Check-in, Quyền riêng tư. Trang được phục vụ từ **chính cổng của máy chủ** — đây là ràng buộc kỹ thuật chứ không phải lựa chọn: trang đọc `window.location.port` để tìm socket, nên một giao diện đặt ở cổng khác sẽ đưa trình duyệt tới sai địa chỉ.

> 🔴 **CẦN NGƯỜI DÙNG BỔ SUNG:** ảnh chụp màn hình giao diện khi chạy thật (Hình 4.3).

### 4.3 Đánh giá và kiểm thử

#### 4.3.1 Kết quả bộ kiểm thử tự động

**Bảng 4.2: Kết quả bộ kiểm thử tự động**

| Bộ | Số lượng | Kết quả |
|---|---:|---|
| Kiểm thử Python | 1.112 | 1.108 đạt / 4 trượt |
| Kiểm thử web (Vitest) | 246 | 246 đạt |
| `ruff` (lint) | — | Sạch |
| `ty` (kiểm kiểu) | — | Sạch |
| `tsc --noEmit` | — | Sạch |
| ESLint | — | Sạch |

Bốn trường hợp trượt đều thuộc vùng không nằm trên đường thực thi của vòng sinh, và được phân tích ở Mục 5.1.

Kiểm thử được tổ chức theo năm nhóm: quy tắc miền thuần tuý (20 tệp), thời gian chạy (25), lưu trữ (14), hợp đồng kiến trúc (7), và khung đánh giá (7).

Một kỹ thuật được dùng xuyên suốt là **khẳng định tập chính xác** làm bộ phát hiện thay đổi: bề mặt RPC được khẳng định bằng một tập đúng bằng, nên việc thêm một phương thức mới buộc lập trình viên cập nhật khẳng định một cách có ý thức.

#### 4.3.2 Đo độ trễ và chi phí token trên lượt chạy thật

Thực nghiệm chạy 12 lượt khai vấn thật với Haiku, mỗi lượt là lượt đầu của một phiên riêng, đi qua đúng đường end-to-end của `coach.turn` (bao gồm cả ghi SQLite).

**Lưu ý về phương pháp đo:** số token lấy trực tiếp từ trường `usage` mà Anthropic trả về. Bộ hạch toán bên trong bộ điều hợp **không** được dùng, vì nó hiện đếm số từ tách theo khoảng trắng — chú thích trong mã nêu rõ đó là chỗ tạm cho tới khi nhà cung cấp báo số thật. Đây cũng là một khiếm khuyết cần khắc phục, nêu ở Mục 5.2.

**Bảng 4.3: Độ trễ và chi phí token trên 12 lượt khai vấn thật**

| Lượt | Số lần thử | Độ trễ mô hình (s) | Độ trễ đầu-cuối (s) | Token vào | Token ra | Bước |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 2 | 6,495 | 6,501 | 5.861 | 513 | pre_coaching |
| 2 | 1 | 2,197 | 2,199 | 2.283 | 129 | pre_coaching |
| 3 | 2 | 5,724 | 5,726 | 5.809 | 486 | pre_coaching |
| 4 | 3 | 6,410 | 6,412 | 10.240 | 468 | pre_coaching |
| 5 | 1 | 2,507 | 2,508 | 2.286 | 195 | pre_coaching |
| 6 | 1 | 2,681 | 2,682 | 2.289 | 220 | pre_coaching |
| 7 | 1 | 2,027 | 2,027 | 2.282 | 169 | pre_coaching |
| 8 | 1 | 2,378 | 2,379 | 2.281 | 183 | pre_coaching |
| 9 | 1 | 2,809 | 2,810 | 2.280 | 224 | pre_coaching |
| 10 | 1 | 1,744 | 1,744 | 2.291 | 107 | pre_coaching |
| 11 | 1 | 2,276 | 2,277 | 2.283 | 176 | pre_coaching |
| 12 | 1 | 2,431 | 2,431 | 2.277 | 148 | pre_coaching |

**Tổng hợp:**

| Chỉ số | Giá trị |
|---|---|
| Số lượt | 12 |
| Thành công | **12 / 12 (100%)** |
| Hợp lệ ngay lần thử đầu | **9 / 12 (75%)** |
| Tổng số lần gọi mô hình | 16 |
| Độ trễ mô hình — trung vị | **2,47 s** |
| Độ trễ mô hình — trung bình | 3,31 s |
| Độ trễ mô hình — min / max | 1,74 s / 6,50 s |
| Độ trễ đầu-cuối — trung vị | 2,47 s |
| Token vào — trung bình mỗi lượt | 3.538,5 |
| Token ra — trung bình mỗi lượt | 251,5 |
| Tổng token vào / ra | 42.462 / 3.018 |

**Nhận xét 1 — kỷ luật bước đạt tuyệt đối.** Cả 12/12 lượt đều mở ở `pre_coaching`, dù nhiều đầu vào nói thẳng về mục tiêu (*"Tôi muốn học tiếng Anh tốt hơn trong sáu tháng tới"*). Đây là bằng chứng mạnh cho hiệu lực của việc nêu hợp đồng đầu ra trong lượt kết hợp với prompt hệ thống quy định rõ thứ tự bước.

**Nhận xét 2 — độ trễ chấp nhận được cho hội thoại.** Trung vị 2,47 giây; chênh lệch giữa độ trễ mô hình và độ trễ đầu-cuối chỉ khoảng 2–6 mili-giây, nghĩa là toàn bộ chi phí ghi SQLite, chọn ngữ cảnh và kiểm chứng là **không đáng kể** so với thời gian chờ mô hình. Tối ưu hoá, nếu cần, phải nhắm vào lời gọi mô hình chứ không vào phần còn lại của hệ thống.

**Nhận xét 3 — chi phí sinh lại tăng siêu tuyến tính.** Đây là phát hiện định lượng đáng chú ý nhất:

**Bảng 4.4: Chi phí token theo số lần thử**

| Số lần thử | Số lượt | Token vào trung bình | Bội số so với 1 lần |
|---:|---:|---:|---:|
| 1 | 9 | 2.284 | 1,00× |
| 2 | 2 | 5.835 | **2,55×** |
| 3 | 1 | 10.240 | **4,48×** |

Nguyên nhân: mỗi lần sinh lại được nối vào **cùng một hội thoại** như một nỗ lực khác cho cùng lượt đó — thiết kế này là bắt buộc để giữ luân phiên vai trò nghiêm ngặt (Mục 3.3.2) — nên mỗi lần thử lại phải gửi kèm toàn bộ lịch sử đã tích luỹ. Chi phí do đó tăng theo cấp số cộng của độ dài hội thoại, tức xấp xỉ bậc hai theo số lần thử.

Hệ quả thiết kế: **cận trên N = 2 không chỉ là biện pháp chống vòng lặp vô hạn mà còn là biện pháp kiểm soát chi phí.** Nếu để N = 5, một lượt xấu nhất có thể tốn hơn mười lần một lượt bình thường. Với tỷ lệ hợp lệ lần đầu 75% đo được, cận N = 2 là lựa chọn hợp lý; nhưng con số này cần kiểm định lại trên mẫu lớn hơn.

**Nhận xét 4 — token đầu vào của lượt một lần thử rất ổn định**, dao động 2.277–2.291 (biên độ dưới 0,7%). Điều này xác nhận rằng prompt hệ thống thực sự bất biến và ngữ cảnh động được kiểm soát chặt về kích thước.

#### 4.3.3 Khung đánh giá theo kịch bản

Ngoài các phép đo trên, đồ án xây dựng một khung đánh giá theo rubric có thể thực thi lặp lại.

**Bảng 4.5: Cấu trúc khung đánh giá theo kịch bản**

| Thành phần | Số lượng | Mô tả |
|---|---:|---|
| Kịch bản | 68 | Phân bố qua 8 tệp theo chủ đề; riêng an toàn có 12 kịch bản biên |
| Rubric | 7 | `RUB-QUESTION`, `RUB-COMPANION`, `RUB-STAGE`, `RUB-GOAL`, `RUB-OPTIONS`, `RUB-SAFETY`, rubric quyền riêng tư |
| Cổng kiểm duyệt bên ngoài | 3 | Do con người có chuyên môn ký duyệt, máy không tự đóng được |

Mỗi kịch bản khai báo bước hiện tại, đầu vào của người được khai vấn, khối kỳ vọng (bước kế tiếp, các cờ), và hai danh sách `must_do` / `must_not_do`; mỗi kịch bản truy vết ngược về mã yêu cầu nguồn và mã tiêu chí chấp nhận.

Công thức chấm một rubric:

$$\text{score} = \sum_{c \in C} w_c \cdot s_c$$

$$\text{passed} = (\text{score} \ge \text{minimum\_score}) \wedge (\nexists\, c \in C_{\text{blocking}} : s_c < 1)$$

Một tiêu chí **chặn** bị trượt làm rubric trượt bất kể tổng điểm có trọng số. Lựa chọn có chủ ý: các ràng buộc vai trò trong khai vấn không đánh đổi được bằng điểm cao ở tiêu chí khác.

Ba cổng kiểm duyệt bên ngoài mã hoá tường minh rằng một số quyết định — đặc biệt là ngưỡng an toàn trong miền sức khoẻ tinh thần — không thuộc thẩm quyền của một bộ kiểm thử tự động. Cả ba hiện ở trạng thái chờ duyệt.

> **Hạn chế quan trọng:** khung 68 kịch bản hiện chạy trên một engine tất định tham chiếu, **chưa từng chạy đối chiếu với mô hình thật**. Đây là hạn chế lớn nhất của phần đánh giá và là hạng mục ưu tiên số một ở Mục 5.2.

---

## Chương 5: KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN

### 5.1 Kết luận

#### 5.1.1 Đối chiếu với mục tiêu đề ra

| Mục tiêu (Mục 1.2) | Kết quả |
|---|---|
| 1. Hợp đồng đầu ra có cấu trúc | **Đạt** — lược đồ cấm trường thừa, ràng buộc một câu hỏi ở mức validator |
| 2. Vòng sinh lại có kiểm chứng, có cận | **Đạt** — cận 3 lần gọi; 12/12 lượt thật cho đầu ra hợp lệ |
| 3. Máy trạng thái phía máy chủ | **Đạt** — 12/12 lượt mở đúng ở Pre-Coaching |
| 4. Bộ chọn ngữ cảnh theo đồng ý | **Đạt** — đồng ý được đọc lại mỗi lượt |
| 5. Khung đánh giá theo rubric | **Đạt một phần** — khung có 68 kịch bản, nhưng chưa chạy với mô hình thật |
| 6. Đo độ trễ và chi phí token | **Đạt** — trung vị 2,47 s; định lượng được chi phí sinh lại siêu tuyến tính |

#### 5.1.2 Nhìn nhận thực tế những gì chưa tốt

Báo cáo nêu thẳng các vấn đề còn tồn tại, vì che đi thì kết luận mất giá trị.

**(a) Bộ phân loại theo luật từ vựng gãy trên tiếng Việt.** Hàm phân loại câu trả lời của người được khai vấn tại cổng chuyển bước được hiện thực bằng luật từ vựng. Bộ kiểm thử đối kháng phát hiện ba thất bại thật:

| Đầu vào | Nhãn hệ thống | Nhãn đúng | Hệ quả |
|---|---|---|---|
| *"Có vấn đề"* | `YES` | `UNCLEAR` | **Cổng mở sai** |
| *"Có một lựa chọn khác"* | `YES` | `UNCLEAR` | **Cổng mở sai** |
| *"Có, tôi không đồng ý với phần thời hạn"* | `NO` | `UNCLEAR` | Phân loại sai chiều |

Hai thất bại đầu có cùng nguyên nhân: `"có"` nằm trong tập khẳng định yếu và luật tiền tố khiến **mọi** câu mở đầu bằng "Có " được đọc là đồng ý. Đây là đặc thù ngôn ngữ học của tiếng Việt: "có" vừa là tiểu từ khẳng định, vừa là động từ tồn tại — *"Có vấn đề"* nghĩa là *tồn tại một vấn đề*, gần với phản đối hơn là đồng ý.

Nghiêm trọng hơn cả tần suất là **chiều thất bại**: hệ thống fail *open*. Một người nói "Có vấn đề" sẽ khiến bước khai vấn đóng lại như thể họ đã xác nhận, vi phạm trực tiếp quy tắc lõi "mỗi bước chỉ hoàn tất sau một sự đồng ý rõ ràng".

Đây là minh hoạ điển hình cho lý do các bài toán phân loại ngôn ngữ tự nhiên chuyển từ hệ luật sang hệ học: không gian biến thể ngôn ngữ quá lớn để liệt kê, và mỗi luật vá thêm lại mở ra một ca biên mới.

**(b) Hạch toán token trong bộ điều hợp là số ước lượng.** Bộ đếm hiện tại đếm số từ tách theo khoảng trắng, không phải token thật. Mọi con số chi phí lấy từ đó đều không dùng được. Phép đo ở Mục 4.3.2 phải lấy trực tiếp từ API để vòng tránh khiếm khuyết này.

**(c) Khung đánh giá chưa chạy với mô hình thật.** Nêu ở Mục 4.3.3.

**(d) Cỡ mẫu nhỏ.** 12 lượt là đủ để thấy xu hướng nhưng không đủ để suy rộng, đặc biệt với tỷ lệ hợp lệ lần đầu 75% — khoảng tin cậy của con số này còn rất rộng.

#### 5.1.3 Ba kết luận phương pháp luận

Quá trình xây dựng cho ba kết luận có giá trị vượt ra ngoài phạm vi đồ án:

**Thứ nhất: nhà cung cấp giả lập kiểm chứng đường xử lý, không kiểm chứng giao tiếp.** Trước lượt chạy thật đầu tiên, toàn bộ kiểm thử bộ điều hợp đều dùng nhà cung cấp giả và đều đạt. Lượt chạy thật thất bại ngay, và truy nguyên cho thấy prompt hệ thống **chưa từng nêu lược đồ** cho mô hình — nó chỉ nói "output phải theo schema". Mô hình đoán, và đoán sai ba cách: sai tên trường, thừa một khoá bị cấm, và bọc kết quả trong hàng rào markdown. Không lỗi nào thuộc về mô hình. Một nhà cung cấp giả luôn trả về đúng lược đồ thì không bao giờ phát hiện được rằng lược đồ chưa từng được truyền đạt.

**Thứ hai: thông tin mà máy khách không được thấy, người vận hành vẫn phải thấy.** Bộ điều phối cố tình loại bỏ chi tiết lỗi để không rò rỉ đường dẫn hệ thống và nội dung prompt ra máy khách — nhưng nó cũng không ghi chi tiết đó vào bất kỳ đâu khác. Một lỗi nội bộ không để lại dấu vết ở đâu cả, và đó là thứ khiến hai khiếm khuyết trên tốn một vòng tái dựng đầy đủ mới truy ra được.

**Thứ ba: khi kiểm thử và mã bất đồng, phải truy ý định trước khi chọn bên nào sai.** Đồ án gặp hai tình huống có triệu chứng giống hệt nhau nhưng kết luận ngược nhau. Ở trường hợp (a) nêu trên, chú thích của chính hàm phát biểu quy tắc đúng còn mã hiện thực sai — mã sai. Ở một trường hợp khác về chính sách lưu trữ, ba nguồn bằng chứng độc lập (chú thích hàm, một migration cơ sở dữ liệu, và mã ghi dữ liệu) cùng cho thấy kiểm thử mới là tàn dư của quy tắc cũ đã bị đảo có chủ ý — sửa theo kiểm thử sẽ xoá đúng phần dữ liệu mà sản phẩm vừa cam kết giữ.

### 5.2 Hướng phát triển

**Ưu tiên 1 — Chạy khung đánh giá với mô hình thật.** Giá trị cao nhất, chi phí thấp nhất: bộ máy đã tồn tại và thực thi được, chỉ cần thay engine tất định bằng bộ điều hợp thật. Đầu ra sẽ là ma trận điểm rubric × kịch bản, cho phép báo cáo tỷ lệ vượt cổng và định vị các phạm trù yếu.

**Ưu tiên 2 — Thay bộ phân loại cổng bằng mô hình học.** Từ phân tích ở Mục 5.1.2(a), hướng tự nhiên là huấn luyện một bộ phân loại ba lớp (`YES` / `NO` / `UNCLEAR`) cho câu trả lời cổng tiếng Việt. Dữ liệu khởi tạo từ các ca kiểm thử hiện có, mở rộng bằng sinh tổng hợp và gán nhãn thủ công. Nền tảng khả dĩ: tinh chỉnh một mô hình encoder đa ngữ, hoặc phân loại few-shot bằng chính LLM. Hàm mất mát nên **bất đối xứng**, phạt nặng lỗi fail-open (dự đoán `YES` khi nhãn thật là `UNCLEAR`) hơn lỗi ngược lại, vì hai loại lỗi có hậu quả rất khác nhau trong miền này.

**Ưu tiên 3 — Sửa hạch toán token.** Đọc `usage` từ phản hồi của nhà cung cấp thay vì đếm số từ. Việc này mở đường cho hiển thị chi phí thật cho người dùng và cho việc đặt hạn mức.

**Ưu tiên 4 — Giảm chi phí sinh lại.** Từ phát hiện ở Mục 4.3.2, một hướng là gửi lần thử lại như một yêu cầu độc lập kèm tóm tắt lý do trượt, thay vì nối vào hội thoại đang dài dần. Cần cân nhắc đánh đổi với tính nhất quán của ngữ cảnh.

**Ưu tiên 5 — Mở rộng cỡ mẫu và đo theo bước.** Hiện mọi phép đo đều ở lượt đầu tiên (bước Pre-Coaching). Cần đo cả các bước sau, nơi ngữ cảnh dài hơn và chi phí token cao hơn.

**Ưu tiên 6 — Đo lường bộ kiểm chính sách câu hỏi.** Xây tập câu hỏi khai vấn được gán nhãn bởi người có chuyên môn, rồi đo precision/recall của 12 mã từ chối, biến một bộ lọc hiện chỉ được kiểm bằng ví dụ thành một bộ phân loại có số liệu.

---

## TÀI LIỆU THAM KHẢO

> 🔴 **Người dùng cần đối chiếu lại từng mục trước khi nộp.** Danh sách dưới đây gồm các công trình mốc,
> nhưng chi tiết hội nghị và năm cần được kiểm tra trên nguồn gốc.

[1] T. Brown và cộng sự, "Language Models are Few-Shot Learners," *Advances in Neural Information Processing Systems (NeurIPS)*, 2020.

[2] B. T. Willard và R. Louf, "Efficient Guided Generation for Large Language Models," *arXiv preprint*, 2023.

[3] K. Cobbe và cộng sự, "Training Verifiers to Solve Math Word Problems," *arXiv preprint*, 2021.

[4] N. Shinn và cộng sự, "Reflexion: Language Agents with Verbal Reinforcement Learning," *Advances in Neural Information Processing Systems (NeurIPS)*, 2023.

[5] L. Ouyang và cộng sự, "Training Language Models to Follow Instructions with Human Feedback," *Advances in Neural Information Processing Systems (NeurIPS)*, 2022.

[6] Y. Bai và cộng sự, "Constitutional AI: Harmlessness from AI Feedback," *arXiv preprint*, 2022.

[7] L. Zheng và cộng sự, "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena," *NeurIPS Datasets and Benchmarks Track*, 2023.

[8] P. Lewis và cộng sự, "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," *Advances in Neural Information Processing Systems (NeurIPS)*, 2020.

[9] X. Wang và cộng sự, "Self-Consistency Improves Chain of Thought Reasoning in Language Models," *International Conference on Learning Representations (ICLR)*, 2023.

[10] J. Wei và cộng sự, "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models," *Advances in Neural Information Processing Systems (NeurIPS)*, 2022.
