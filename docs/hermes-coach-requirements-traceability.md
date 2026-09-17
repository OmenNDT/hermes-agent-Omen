# Hermes Coach Requirements Traceability

## Purpose

Tài liệu này phân bổ toàn bộ [Hermes Coach Product Proposal](./hermes-coach-product-proposal.md) tới kiến trúc, file implementation và verification target. Proposal là nguồn chân lý; ma trận này chỉ là chỉ mục dẫn xuất để ngăn bỏ sót.

Baseline audit ngày 2026-07-31 đã tách proposal thành 1.521 chi tiết nguyên tử:

| Source slice | Atomic details |
|---|---:|
| Phần đầu đến hết transition rules | 456 |
| Pre-Coaching đến hết quy tắc câu hỏi chốt | 356 |
| State machine đến hết data/memory model | 340 |
| Safety đến hết unresolved questions | 369 |
| **Tổng** | **1.521** |

Con số là snapshot kiểm toán, không phải ID chuẩn tắc. Khi proposal thay đổi, phải kiểm kê lại; không được dùng con số cũ để tuyên bố đủ độ phủ.

Các quyết định ngày 2026-08-01, 2026-08-09 và 2026-08-11 đã làm thay đổi nội dung nhưng không thêm heading;
vì vậy con số 1.521 chỉ còn là baseline lịch sử. Coverage hiện tại được kiểm soát
bằng heading-owned blocks và acceptance allocation, không bằng con số snapshot.

## Traceability Contract

Mỗi source block trong bảng dưới đây bao gồm **toàn bộ** nội dung từ heading được nêu đến trước heading kế tiếp cùng hoặc cao hơn cấp, gồm mọi câu, bullet, số thứ tự, câu hỏi mẫu, ví dụ, ngoại lệ, sơ đồ, bảng, field, điều cấm và ghi chú. Không được chỉ triển khai phần tóm tắt trong cột “Nội dung phân bổ”.

Trạng thái:

- `planned`: đã có owner/file/test target nhưng chưa có implementation.
- `implemented`: implementation đã tồn tại và đã được đối chiếu thủ công.
- `verified`: implementation có bằng chứng test/evaluation đạt yêu cầu.
- `blocked`: nguồn còn mâu thuẫn hoặc thiếu quyết định; không được tự diễn giải khi code.

Quy tắc hoàn tất:

1. Trace hai chiều: source → architecture/code/test và code/test → requirement family/source block.
2. Mỗi production module mới phải khai báo requirement family trong module docstring hoặc manifest.
3. Mỗi test/evaluation phải ghi requirement family hoặc `AC-xx` tương ứng.
4. Không có source block nào được phép thiếu hàng phân bổ.
5. Không được đổi `planned` thành `implemented` chỉ vì file đã được tạo; hành vi phải tồn tại.
6. Không được đổi `implemented` thành `verified` nếu test chỉ kiểm tra snapshot, mock rỗng hoặc đường không chạy thực tế.
7. Blocker phải được giải quyết trong proposal trước khi cập nhật artefact dẫn xuất.

## Phase 1 Evidence Boundary

Phase 1 has implemented and verified the contract/evaluation artifacts below;
this does not mark the later production services, repositories, API or UI as
implemented.

| Proposal/source family | Architecture owner | Actual file | Responsibility/content | Test/eval evidence |
|---|---|---|---|---|
| `SRC-031…SRC-061` / `HC-PROCESS` | Six-Step Engine and State Machine | `hermes_coach/contracts/transition_contract.py` | Ordered transitions, explicit-Yes gates, Goal completeness, rollback invalidation and readiness reset | `tests/hermes_coach/contract/test_runtime_capability.py` |
| `SRC-061`, `HC-PROCESS`, `HC-DATA-GOAL`, `HC-CHECKIN`, `HC-SAFETY` | Lifecycle and recovery | `hermes_coach/contracts/lifecycle_contract.py` | Pause/resume, early close, abandoned-goal reuse, check-in recovery, retention and safety transitions | `tests/hermes_coach/contract/test_lifecycle_contracts.py` |
| `SRC-073…SRC-075` / `HC-COMPANION` | Prompt/cache/runtime seam | `hermes_coach/contracts/runtime_contract.py` | Singular `question`, stable prompt hash, no-tool capability, buffered result/failure contract | `tests/hermes_coach/contract/test_runtime_capability.py`; `tests/hermes_coach/evals/runtime_harness.py` |
| `SRC-093…SRC-094` / `HC-EVAL` | Evaluation and Verification | `hermes_coach/contracts/evaluation_result.py`; `tests/hermes_coach/evals/scoring.py` | Scenario observation, structural failures, rubric scores and reproducible reports | `tests/hermes_coach/evals/test_eval_harness.py` |
| `SRC-026`, `SRC-091` / `HC-PRIVACY` | Privacy, Security and Egress | `hermes_coach/contracts/egress_contract.py` | Egress disclosure, trusted UI consent, one-turn authorization and atomic `provider_call_lease` | `tests/hermes_coach/contract/test_runtime_capability.py`; `tests/hermes_coach/contract/test_lifecycle_contracts.py` |
| `SRC-087…SRC-090` / `HC-SAFETY` | Safety Architecture | `hermes_coach/contracts/lifecycle_contract.py` | Urgent interruption, direct-guidance exception and explicit new Pre-Coaching requirement | `tests/hermes_coach/contract/test_lifecycle_contracts.py`; safety scenarios |
| `SRC-093` / `HC-EVAL` | Evaluation and Verification | `tests/hermes_coach/evals/external-gates.yaml` | Pending owner/evidence/expiry definitions for safety, provider retention and provider capability | `tests/hermes_coach/evals/test_eval_harness.py` |

Verified Phase 1 inventory: exactly `112` SRC, `58` AC and `33` P/T bundles;
`68` scenarios and `7` rubrics; `48` tests pass; last bounded reviewer `PASS`;
Ruff và ty pass; line coverage `91%`. Chi tiết được ghi trong báo cáo xác minh Phase 1. External safety human
review, provider-retention/capability evidence and Windows real-provider
validation remain pending; they block only affected provider/safety/release
work, not generic Phase 1 contracts.

## Machine-Verifiable Heading Coverage Index

Đơn vị coverage chuẩn là **heading-owned block**: nội dung bắt đầu ngay sau một
heading và kết thúc ngay trước heading kế tiếp ở bất kỳ cấp nào. Vì mọi dòng nội
dung trong proposal thuộc đúng một heading-owned block, 112 hàng dưới đây tạo
phân hoạch không chồng lấn và không bỏ trống toàn bộ proposal tại baseline
2026-07-31. Heading cha không có body riêng vẫn được giữ để truy vết cấu trúc.

`Source ID` ổn định trong baseline hiện tại. Khi thêm, xóa, đổi tên hoặc đổi thứ
tự heading, phải tái sinh index, kiểm tra đủ/duy nhất và cập nhật mọi tham chiếu.
`Production` và `Verification` trỏ tới bundle file chính xác ở hai bảng kế tiếp;
`Architecture destination` trỏ tới mục sở hữu trong tài liệu kiến trúc.

| Source ID | Exact source path | Family | Architecture destination | Production | Verification |
|---|---|---|---|---|---|
| `SRC-000` | Hermes Coach Product Proposal | `HC-GOV` | Overview; Requirement Ownership | `P-GOV` | `T-GOV` |
| `SRC-001` | Overview | `HC-PRODUCT` | Overview; System Context | `P-PRODUCT`, `P-RUNTIME` | `T-GOV`, `T-RUNTIME` |
| `SRC-002` | Source of Truth and Change Control | `HC-GOV` | Requirement Ownership | `P-GOV` | `T-GOV` |
| `SRC-003` | Problem Statement | `HC-PRODUCT` | Overview; Evaluation and Verification | `P-PRODUCT`, `P-RECORDS`, `P-CHECKIN` | `T-UX`, `T-CHECKIN` |
| `SRC-004` | Problem Statement > Causal Coaching Thesis | `HC-GOAL` | Goal Validation | `P-GOAL`, `P-POLICY` | `T-GOAL`, `T-POLICY` |
| `SRC-005` | Product Principles | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` |
| `SRC-006` | Product Principles > Người đồng hành ngang vị thế | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` |
| `SRC-007` | Product Principles > Nhận diện rào cản vô thức | `HC-COMPANION` | Companion Policies | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` |
| `SRC-008` | Product Principles > Vòng tròn quan tâm và vòng tròn ảnh hưởng | `HC-GOAL` | Goal Validation; Companion Policies | `P-POLICY`, `P-GOAL` | `T-GOAL`, `T-POLICY` |
| `SRC-009` | Product Principles > Niềm tin bắt buộc vào tiềm năng của Coachee | `HC-COMPANION` | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` |
| `SRC-010` | Product Principles > Chỉ đặt câu hỏi | `HC-COMPANION` | Companion Policies; Prompt and Cache | `P-POLICY`, `P-PROMPT`, `P-SAFETY`, `P-UX` | `T-POLICY`, `T-PROMPT`, `T-SAFETY` |
| `SRC-011` | Product Principles > Quyền tự chủ | `HC-RECORDS` | Application Services and Confirmation | `P-RECORDS`, `P-UX` | `T-RECORDS`, `T-UX` |
| `SRC-012` | Product Principles > Kỹ năng đặt câu hỏi — quay đầu là hỏi | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` |
| `SRC-013` | Product Principles > Kỹ năng đặt câu hỏi — quay đầu là hỏi > Tiêu chí đặt câu hỏi dành cho Coach | `HC-COMPANION` | Companion Policies; Prompt and Cache | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` |
| `SRC-014` | Product Principles > Kỹ năng đặt câu hỏi — quay đầu là hỏi > Một câu hỏi đúng phải làm được gì? | `HC-COMPANION` | Companion Policies; Evaluation and Verification | `P-POLICY` | `T-POLICY` |
| `SRC-015` | Product Principles > Lắng nghe sâu — 4 cấp độ | `HC-COMPANION` | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY` |
| `SRC-016` | Product Principles > Lắng nghe sâu — 4 cấp độ > L1 — Dừng suy nghĩ của Coach | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` |
| `SRC-017` | Product Principles > Lắng nghe sâu — 4 cấp độ > L2 — Dừng đánh giá | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` |
| `SRC-018` | Product Principles > Lắng nghe sâu — 4 cấp độ > L3 — Tập trung vào động cơ của Coachee | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` |
| `SRC-019` | Product Principles > Lắng nghe sâu — 4 cấp độ > L4 — Lắng nghe từ tâm | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` |
| `SRC-020` | Product Principles > Lắng nghe sâu — 4 cấp độ > Lắng nghe chủ động và phản ánh lại | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` |
| `SRC-021` | Product Principles > Ghi nhận trong khai vấn | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` |
| `SRC-022` | Product Principles > Ghi nhận trong khai vấn > Cấu trúc ghi nhận | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` |
| `SRC-023` | Product Principles > Phản hồi trong khai vấn | `HC-COMPANION` | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` |
| `SRC-024` | Product Principles > Phản hồi trong khai vấn > Câu hỏi theo từng bước | `HC-PROCESS` | Six-Step Engine; Companion Policies | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` |
| `SRC-025` | Product Principles > Phản hồi trong khai vấn > Kỹ thuật thay đổi góc nhìn | `HC-OPTIONS` | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-POLICY` | `T-OPTIONS`, `T-POLICY` |
| `SRC-026` | Product Principles > Local-first và minh bạch | `HC-PRIVACY` | Privacy, Security and Egress | `P-PRIVACY`, `P-DATA`, `P-DEPLOY` | `T-PRIVACY`, `T-DEPLOY` |
| `SRC-027` | Scope | `HC-PRODUCT` | Overview; Product Boundary | `P-GOV`, `P-PRODUCT` | `T-GOV` |
| `SRC-028` | Scope > MVP | `HC-PRODUCT` | Planned Repository Layout; capability sections | `P-PRODUCT`, `P-POLICY`, `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-RECORDS`, `P-DATA`, `P-API`, `P-UX`, `P-CHECKIN`, `P-PRIVACY`, `P-SAFETY`, `P-PROMPT`, `P-RUNTIME`, `P-DEPLOY` | `T-POLICY`, `T-STATE`, `T-GOAL`, `T-OPTIONS`, `T-RECORDS`, `T-DATA`, `T-API`, `T-UX`, `T-CHECKIN`, `T-PRIVACY`, `T-SAFETY`, `T-PROMPT`, `T-RUNTIME`, `T-DEPLOY` |
| `SRC-029` | Scope > Out of Scope | `HC-PRODUCT` | Existing Hermes Integration Boundary; Product Boundary | `P-GOV`, `P-PRODUCT` | `T-GOV` |
| `SRC-030` | Coaching Contract | `HC-COMPANION` | Web UX; Application Services and Confirmation; Safety | `P-UX`, `P-RECORDS`, `P-SAFETY` | `T-UX`, `T-RECORDS`, `T-SAFETY` |
| `SRC-031` | Six-Step Coaching Process | `HC-PROCESS` | Six-Step Engine and State Machine | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` |
| `SRC-032` | Six-Step Coaching Process > Vòng lặp GROW và transition gates | `HC-PROCESS` | Six-Step Engine and State Machine | `P-STATE` | `T-STATE` |
| `SRC-033` | Six-Step Coaching Process > Vòng lặp GROW và transition gates > Câu hỏi phễu | `HC-PROCESS` | Companion Policies; Six-Step Engine | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` |
| `SRC-034` | Six-Step Coaching Process > 1 — Pre-Coaching | `HC-PROCESS-PRE` | Six-Step Engine; Web UX | `P-STATE`, `P-UX` | `T-STATE`, `T-UX` |
| `SRC-035` | Six-Step Coaching Process > 1 — Pre-Coaching > Mục tiêu | `HC-PROCESS-PRE` | Six-Step Engine; Web UX | `P-STATE`, `P-UX` | `T-STATE`, `T-UX` |
| `SRC-036` | Six-Step Coaching Process > 1 — Pre-Coaching > Thấu hiểu và thỏa thuận chung | `HC-PROCESS-PRE` | Six-Step Engine; Confirmation | `P-STATE`, `P-RECORDS` | `T-STATE`, `T-RECORDS` |
| `SRC-037` | Six-Step Coaching Process > 1 — Pre-Coaching > Câu hỏi mẫu | `HC-PROCESS-PRE` | Companion Policies | `P-POLICY` | `T-POLICY` |
| `SRC-038` | Six-Step Coaching Process > 1 — Pre-Coaching > Chuẩn bị của Coach | `HC-PROCESS-PRE` | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY` |
| `SRC-039` | Six-Step Coaching Process > 1 — Pre-Coaching > Chuẩn bị tâm thế cho Coach | `HC-PROCESS-PRE` | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY` |
| `SRC-040` | Six-Step Coaching Process > 1 — Pre-Coaching > Lỗi thường gặp cần tránh | `HC-PROCESS-PRE` | Six-Step Engine; Companion Policies | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` |
| `SRC-041` | Six-Step Coaching Process > 2 — Goal | `HC-GOAL` | Goal Validation | `P-GOAL`, `P-STATE` | `T-GOAL`, `T-STATE` |
| `SRC-042` | Six-Step Coaching Process > 2 — Goal > Mục tiêu bắt buộc SMART và đúng với Coachee | `HC-GOAL` | Goal Validation | `P-GOAL`, `P-STATE` | `T-GOAL`, `T-STATE` |
| `SRC-043` | Six-Step Coaching Process > 2 — Goal > Tiêu chí mục tiêu hợp lệ | `HC-GOAL` | Goal Validation | `P-GOAL`, `P-POLICY` | `T-GOAL` |
| `SRC-044` | Six-Step Coaching Process > 2 — Goal > Case study — một câu hỏi làm lộ mục tiêu thật | `HC-GOAL` | Goal Validation; Evaluation | `P-POLICY`, `P-GOAL` | `T-GOAL`, `T-POLICY` |
| `SRC-045` | Six-Step Coaching Process > 3 — Reality | `HC-PROCESS-REALITY` | Six-Step Engine | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` |
| `SRC-046` | Six-Step Coaching Process > 3 — Reality > Làm rõ khoảng cách giữa mục tiêu và hiện thực | `HC-PROCESS-REALITY` | Six-Step Engine; Companion Policies | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` |
| `SRC-047` | Six-Step Coaching Process > 3 — Reality > Khơi gợi nhận thức sâu sắc | `HC-PROCESS-REALITY` | Six-Step Engine; Companion Policies | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` |
| `SRC-048` | Six-Step Coaching Process > 4 — Options | `HC-OPTIONS` | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-STATE` | `T-OPTIONS`, `T-STATE` |
| `SRC-049` | Six-Step Coaching Process > 4 — Options > Think Outside the Box | `HC-OPTIONS` | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-POLICY` | `T-OPTIONS` |
| `SRC-050` | Six-Step Coaching Process > 4 — Options > Dấu hiệu chạm ngưỡng trong Options | `HC-OPTIONS` | Options Novelty and Stuck Recovery | `P-OPTIONS` | `T-OPTIONS` |
| `SRC-051` | Six-Step Coaching Process > 4 — Options > Tiêu chí thành công của Options | `HC-OPTIONS` | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-STATE` | `T-OPTIONS`, `T-STATE` |
| `SRC-052` | Six-Step Coaching Process > 4 — Options > Khi Coachee chưa có giải pháp | `HC-OPTIONS` | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-POLICY`, `P-STATE` | `T-OPTIONS`, `T-POLICY` |
| `SRC-053` | Six-Step Coaching Process > 4 — Options > Cách chia nhỏ vấn đề | `HC-OPTIONS` | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-POLICY` | `T-OPTIONS` |
| `SRC-054` | Six-Step Coaching Process > 5 — Will | `HC-PROCESS-WILL` | Six-Step Engine; Confirmation | `P-STATE`, `P-RECORDS`, `P-POLICY` | `T-STATE`, `T-RECORDS` |
| `SRC-055` | Six-Step Coaching Process > 5 — Will > Way Forward — Cam kết hành động | `HC-PROCESS-WILL` | Six-Step Engine; Confirmation | `P-STATE`, `P-RECORDS`, `P-POLICY` | `T-STATE`, `T-RECORDS` |
| `SRC-056` | Six-Step Coaching Process > 6 — Review | `HC-PROCESS-REVIEW` | Six-Step Engine; Confirmation | `P-STATE`, `P-RECORDS` | `T-STATE`, `T-RECORDS` |
| `SRC-057` | Six-Step Coaching Process > 6 — Review > Tổng kết sau phiên | `HC-PROCESS-REVIEW` | Six-Step Engine; Confirmation | `P-STATE`, `P-RECORDS` | `T-STATE`, `T-RECORDS` |
| `SRC-058` | Six-Step Coaching Process > 6 — Review > Theo dõi sau phiên | `HC-CHECKIN` | Check-in and Notifications | `P-CHECKIN`, `P-RECORDS` | `T-CHECKIN` |
| `SRC-059` | Six-Step Coaching Process > 6 — Review > Kết thúc phiên | `HC-PROCESS-REVIEW` | Six-Step Engine; Check-in | `P-STATE`, `P-CHECKIN` | `T-STATE`, `T-CHECKIN` |
| `SRC-060` | Six-Step Coaching Process > Quy tắc câu hỏi chốt | `HC-PROCESS` | Six-Step Engine and State Machine | `P-STATE`, `P-RECORDS` | `T-STATE`, `T-RECORDS` |
| `SRC-061` | Coaching Session State Machine | `HC-PROCESS` | Six-Step Engine and State Machine | `P-STATE`, `P-DATA` | `T-STATE`, `T-DATA` |
| `SRC-062` | UX Flows | `HC-UX` | Web UX | `P-UX` | `T-UX` |
| `SRC-063` | UX Flows > Onboarding | `HC-UX` | Web UX | `P-UX`, `P-RECORDS` | `T-UX`, `T-RECORDS` |
| `SRC-064` | UX Flows > Home | `HC-UX` | Web UX | `P-UX` | `T-UX` |
| `SRC-065` | UX Flows > Coaching Session | `HC-UX` | Web UX; Six-Step Engine | `P-UX`, `P-STATE`, `P-RECORDS` | `T-UX`, `T-STATE`, `T-RECORDS` |
| `SRC-066` | UX Flows > Scheduled Check-in | `HC-CHECKIN` | Check-in and Notifications | `P-CHECKIN` | `T-CHECKIN` |
| `SRC-067` | UX Flows > Voice | `HC-VOICE` | Voice | `P-GOV`, `P-PRODUCT` | `T-GOV` |
| `SRC-068` | UX Flows > Privacy Center | `HC-PRIVACY` | Privacy, Security and Egress | `P-PRIVACY`, `P-UX` | `T-PRIVACY`, `T-UX` |
| `SRC-069` | Information Architecture | `HC-UX` | Web UX | `P-UX` | `T-UX` |
| `SRC-070` | Technical Architecture | `HC-PRODUCT` | System Context; Planned Repository Layout | `P-PRODUCT`, `P-RUNTIME`, `P-DATA`, `P-CHECKIN` | `T-GOV`, `T-RUNTIME` |
| `SRC-071` | Technical Architecture > Standalone web product, shared engine | `HC-PRODUCT` | Existing Hermes Integration Boundary | `P-RUNTIME`, `P-PRODUCT` | `T-RUNTIME`, `T-GOV` |
| `SRC-072` | Technical Architecture > Coach Application Layer | `HC-PRODUCT` | Application Services and Confirmation | `P-API` | `T-API` |
| `SRC-073` | Technical Architecture > Prompt and Cache Strategy | `HC-COMPANION` | Prompt, Cache and Structured Output | `P-PROMPT`, `P-RUNTIME` | `T-PROMPT`, `T-RUNTIME` |
| `SRC-074` | Technical Architecture > Structured Model Output | `HC-COMPANION` | Prompt, Cache and Structured Output | `P-PROMPT`, `P-RECORDS` | `T-PROMPT`, `T-RECORDS` |
| `SRC-075` | Technical Architecture > Question-only Validator | `HC-COMPANION` | Prompt, Cache and Structured Output | `P-PROMPT` | `T-PROMPT` |
| `SRC-076` | Data Model | `HC-DATA` | Domain Model | `P-DATA` | `T-DATA` |
| `SRC-077` | Data Model > `coachee_profile` | `HC-DATA-PROFILE` | Domain Model | `P-DATA` | `T-DATA` |
| `SRC-078` | Data Model > `career_snapshot` | `HC-DATA-SNAPSHOT` | Domain Model | `P-DATA` | `T-DATA` |
| `SRC-079` | Data Model > `goal` | `HC-DATA-GOAL` | Domain Model; Goal Validation | `P-DATA`, `P-GOAL` | `T-DATA`, `T-GOAL` |
| `SRC-080` | Data Model > `commitment` | `HC-DATA-COMMITMENT` | Domain Model; Confirmation | `P-DATA`, `P-RECORDS` | `T-DATA`, `T-RECORDS` |
| `SRC-081` | Data Model > `evidence` | `HC-DATA-EVIDENCE` | Domain Model | `P-DATA` | `T-DATA` |
| `SRC-082` | Data Model > `check_in` | `HC-DATA-CHECKIN` | Domain Model; Check-in | `P-DATA`, `P-CHECKIN` | `T-DATA`, `T-CHECKIN` |
| `SRC-083` | Data Model > `coaching_session` | `HC-DATA-SESSION` | Domain Model; Six-Step Engine | `P-DATA`, `P-STATE` | `T-DATA`, `T-STATE` |
| `SRC-084` | Data Model > `insight` | `HC-DATA-INSIGHT` | Domain Model; Confirmation | `P-DATA`, `P-RECORDS` | `T-DATA`, `T-RECORDS` |
| `SRC-085` | Data Model > `memory_item` | `HC-DATA-MEMORY` | Domain Model; Privacy | `P-DATA`, `P-PRIVACY` | `T-DATA`, `T-PRIVACY` |
| `SRC-086` | Memory Policy | `HC-MEMORY` | Domain Model; Privacy | `P-DATA`, `P-PRIVACY`, `P-RUNTIME` | `T-DATA`, `T-PRIVACY`, `T-RUNTIME` |
| `SRC-087` | Safety | `HC-SAFETY` | Safety Architecture | `P-SAFETY` | `T-SAFETY` |
| `SRC-088` | Safety > Role Boundaries | `HC-SAFETY` | Safety Architecture | `P-SAFETY`, `P-POLICY` | `T-SAFETY`, `T-POLICY` |
| `SRC-089` | Safety > Safety States | `HC-SAFETY` | Safety Architecture | `P-SAFETY`, `P-STATE` | `T-SAFETY`, `T-STATE` |
| `SRC-090` | Safety > Prohibited Behaviors | `HC-SAFETY` | Safety Architecture | `P-SAFETY`, `P-POLICY` | `T-SAFETY`, `T-POLICY` |
| `SRC-091` | Safety > Privacy Controls | `HC-PRIVACY` | Privacy, Security and Egress | `P-PRIVACY`, `P-DATA` | `T-PRIVACY`, `T-DATA` |
| `SRC-092` | Non-functional Requirements | `HC-NFR` | All architecture sections | `P-PRODUCT`, `P-POLICY`, `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-RECORDS`, `P-DATA`, `P-API`, `P-UX`, `P-CHECKIN`, `P-PRIVACY`, `P-SAFETY`, `P-PROMPT`, `P-RUNTIME`, `P-DEPLOY` | `T-GOV`, `T-POLICY`, `T-STATE`, `T-GOAL`, `T-OPTIONS`, `T-RECORDS`, `T-DATA`, `T-API`, `T-UX`, `T-CHECKIN`, `T-PRIVACY`, `T-SAFETY`, `T-PROMPT`, `T-RUNTIME`, `T-DEPLOY` |
| `SRC-093` | Evaluation Strategy | `HC-EVAL` | Evaluation and Verification | `P-POLICY`, `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-SAFETY`, `P-PROMPT`, `P-DATA`, `P-PRIVACY` | `T-POLICY`, `T-STATE`, `T-GOAL`, `T-OPTIONS`, `T-SAFETY`, `T-PROMPT`, `T-DATA`, `T-PRIVACY` |
| `SRC-094` | Acceptance Criteria | `HC-AC` | Evaluation and Verification | `P-POLICY`, `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-RECORDS`, `P-DATA`, `P-API`, `P-UX`, `P-CHECKIN`, `P-PRIVACY`, `P-SAFETY`, `P-PROMPT`, `P-RUNTIME`, `P-PRODUCT` | `T-POLICY`, `T-STATE`, `T-GOAL`, `T-OPTIONS`, `T-RECORDS`, `T-DATA`, `T-API`, `T-UX`, `T-CHECKIN`, `T-PRIVACY`, `T-SAFETY`, `T-PROMPT`, `T-RUNTIME`, `T-GOV` |
| `SRC-095` | Success Metrics | `HC-METRICS` | Evaluation and Verification | `P-METRICS` | `T-METRICS` |
| `SRC-096` | Delivery Roadmap | `HC-ROADMAP` | Delivery and Deployment | `P-GOV`, `P-PRODUCT`, `P-POLICY`, `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-RECORDS`, `P-DATA`, `P-API`, `P-UX`, `P-CHECKIN`, `P-PRIVACY`, `P-SAFETY`, `P-PROMPT`, `P-RUNTIME`, `P-DEPLOY` | `T-GOV`, `T-POLICY`, `T-STATE`, `T-GOAL`, `T-OPTIONS`, `T-RECORDS`, `T-DATA`, `T-API`, `T-UX`, `T-CHECKIN`, `T-PRIVACY`, `T-SAFETY`, `T-PROMPT`, `T-RUNTIME`, `T-DEPLOY` |
| `SRC-097` | Delivery Roadmap > Phase 0 — Contract and Evaluation | `HC-ROADMAP` | Evaluation and Verification; Delivery | `P-GOV`, `P-POLICY`, `P-PROMPT` | `T-GOV`, `T-POLICY`, `T-PROMPT` |
| `SRC-098` | Delivery Roadmap > Phase 1 — Coaching Engine | `HC-ROADMAP` | Six-Step Engine; Prompt | `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-POLICY`, `P-PROMPT` | `T-STATE`, `T-GOAL`, `T-OPTIONS`, `T-POLICY`, `T-PROMPT` |
| `SRC-099` | Delivery Roadmap > Phase 2 — Local Data Layer | `HC-ROADMAP` | Domain Model; Privacy | `P-DATA`, `P-PRIVACY`, `P-RECORDS` | `T-DATA`, `T-PRIVACY`, `T-RECORDS` |
| `SRC-100` | Delivery Roadmap > Phase 3 — Web UX | `HC-ROADMAP` | Web UX | `P-UX`, `P-API` | `T-UX`, `T-API` |
| `SRC-101` | Delivery Roadmap > Phase 4 — Check-in and Notifications | `HC-ROADMAP` | Check-in and Notifications | `P-CHECKIN` | `T-CHECKIN` |
| `SRC-102` | Delivery Roadmap > Phase 5 — Voice | `HC-ROADMAP` | Voice | `P-GOV`, `P-PRODUCT` | `T-GOV` |
| `SRC-103` | Delivery Roadmap > Phase 6 — Hardening | `HC-ROADMAP` | Delivery and Deployment; all hardening sections | `P-DEPLOY`, `P-PRIVACY`, `P-SAFETY` | `T-DEPLOY`, `T-PRIVACY`, `T-SAFETY` |
| `SRC-104` | Architecture Decision | `HC-ADR` | Overview; Integration Boundary | `P-GOV`, `P-PRODUCT`, `P-RUNTIME` | `T-GOV`, `T-RUNTIME` |
| `SRC-105` | Architecture Decision > Recommended | `HC-ADR` | Overview; Integration Boundary | `P-PRODUCT`, `P-RUNTIME` | `T-GOV`, `T-RUNTIME` |
| `SRC-106` | Architecture Decision > Alternatives Considered | `HC-ADR` | Existing Hermes Integration Boundary | `P-GOV` | `T-GOV` |
| `SRC-107` | Assumptions to Validate | `HC-ASSUMPTION` | Evaluation; Architecture Blockers | `P-STATE`, `P-POLICY`, `P-PROMPT`, `P-UX`, `P-RECORDS` | `T-STATE`, `T-POLICY`, `T-PROMPT`, `T-UX`, `T-RECORDS` |
| `SRC-108` | Decision Log | `HC-DECISION` | Requirement Ownership; Architecture Blockers | `P-GOV`, `P-PRODUCT`, `P-RUNTIME`, `P-STATE`, `P-GOAL`, `P-POLICY`, `P-CHECKIN`, `P-PRIVACY`, `P-SAFETY` | `T-GOV`, `T-RUNTIME`, `T-STATE`, `T-GOAL`, `T-POLICY`, `T-CHECKIN`, `T-PRIVACY`, `T-SAFETY` |
| `SRC-109` | References | `HC-REFERENCE` | References; Integration Boundary | `P-GOV`, `P-RUNTIME` | `T-GOV`, existing regression suites |
| `SRC-110` | Next Steps | `HC-GOV` | Delivery and Deployment | `P-GOV` | `T-GOV` |
| `SRC-111` | Unresolved Questions | `HC-BLOCKER` | Architecture Decision and Blocker Status | `P-GOV` | `T-GOV` |

Coverage gate dự kiến tại
`tests/hermes_coach/contract/test_requirements_coverage.py` phải parse proposal và
index này để khẳng định: đúng 112 source paths ở baseline; không duplicate ID/path;
không thiếu heading; mọi row có family, architecture destination, production và
verification; mọi bundle tham chiếu tồn tại trong catalog. Khi proposal thay đổi,
test phải fail cho đến khi mapping được cập nhật.

## Production File Bundles

| Bundle | Exact planned files and responsibility |
|---|---|
| `P-GOV` | `docs/hermes-coach-product-proposal.md`; `docs/hermes-coach-system-architecture.md`; `docs/hermes-coach-requirements-traceability.md`; planned `hermes_coach/requirements_map.yaml` |
| `P-PRODUCT` | `hermes_coach/bootstrap.py`; `hermes_coach/config.py`; `apps/hermes-coach/src/app/shell.tsx`; `apps/hermes-coach/src/app/routes.tsx` |
| `P-POLICY` | `hermes_coach/policies/companion_policy.py`; `hermes_coach/policies/listening_policy.py`; `hermes_coach/policies/question_policy.py`; `hermes_coach/policies/feedback_policy.py`; `hermes_coach/prompt/system_prompt.py`; `hermes_coach/prompt/question_validator.py` |
| `P-STATE` | `hermes_coach/domain/session_state.py`; `hermes_coach/domain/transitions.py`; `hermes_coach/application/coaching_service.py` |
| `P-GOAL` | `hermes_coach/domain/goal_rules.py`; `hermes_coach/application/coaching_service.py`; `hermes_coach/prompt/structured_context.py` |
| `P-OPTIONS` | `hermes_coach/domain/options_rules.py`; `hermes_coach/policies/question_policy.py`; `hermes_coach/application/coaching_service.py` |
| `P-RECORDS` | `hermes_coach/application/record_confirmation_service.py`; `hermes_coach/infrastructure/repositories/goal_repository.py`; `hermes_coach/infrastructure/repositories/commitment_repository.py`; `hermes_coach/infrastructure/repositories/session_repository.py`; `apps/hermes-coach/src/features/coach/record-confirmation.tsx` |
| `P-DATA` | `hermes_coach/domain/models.py`; `hermes_coach/domain/enums.py`; `hermes_coach/infrastructure/sqlite/database.py`; `hermes_coach/infrastructure/sqlite/schema.sql`; all versioned files under `hermes_coach/infrastructure/sqlite/migrations/`; all files under `hermes_coach/infrastructure/repositories/`, gồm planned `memory_provenance_repository.py` |
| `P-API` | `hermes_coach/api/app.py`; `hermes_coach/api/rpc.py`; `hermes_coach/api/routes/onboarding.py`; `sessions.py`; `goals.py`; `commitments.py`; `check_ins.py`; `privacy.py`; `notifications.py`; `metrics.py` within the same directory; `apps/hermes-coach/src/lib/coach-api.ts` |
| `P-UX` | `apps/hermes-coach/src/app/shell.tsx`; `apps/hermes-coach/src/app/routes.tsx`; planned `index.tsx` route entry under each of `src/features/onboarding/`, `today/`, `coach/`, `goals/`, `journey/`, `insights/`, `settings/`, `check-ins/`, `privacy/`; `src/store/session.ts`; `profile.ts`; `notifications.ts` within `src/store/` |
| `P-CHECKIN` | `hermes_coach/application/check_in_service.py`; `hermes_coach/infrastructure/scheduler_adapter.py`; `hermes_coach/api/routes/check_ins.py`; `hermes_coach/api/routes/notifications.py`; `apps/hermes-coach/src/features/check-ins/index.tsx`; `apps/hermes-coach/src/service-worker.ts` |
| `P-PRIVACY` | `hermes_coach/application/privacy_service.py`; `hermes_coach/application/retention_service.py`; `hermes_coach/application/trash_service.py`; `hermes_coach/application/context_selector.py`; `hermes_coach/infrastructure/repositories/trash_repository.py`; `hermes_coach/infrastructure/egress_audit.py`; `hermes_coach/api/routes/privacy.py`; `apps/hermes-coach/src/features/privacy/index.tsx` |
| `P-SAFETY` | `hermes_coach/policies/safety_policy.py`; `hermes_coach/application/safety_service.py`; `hermes_coach/domain/enums.py`; interruption handling in `hermes_coach/application/coaching_service.py` |
| `P-PROMPT` | `hermes_coach/prompt/system_prompt.py`; `hermes_coach/prompt/structured_context.py`; `hermes_coach/prompt/output_schema.py`; `hermes_coach/prompt/question_validator.py`; `hermes_coach/prompt/regeneration.py` |
| `P-RUNTIME` | `hermes_coach/infrastructure/hermes_runtime_adapter.py`; adapters to existing `run_agent.py`, `agent/system_prompt.py`, `agent/memory_manager.py`, `tui_gateway/`, `apps/shared/` without Coach-specific core changes |
| `P-METRICS` | `hermes_coach/application/metrics_service.py`; `hermes_coach/api/routes/metrics.py`; `apps/hermes-coach/src/features/today/metrics.tsx`; `apps/hermes-coach/src/features/insights/metrics.tsx` |
| `P-DEPLOY` | planned Coach startup/package config, loopback-only Windows launch scripts and deployment documentation; approved technical contract uses one `hermes coach` owner and unencrypted ZIP backup with manifest/checksums plus SQLite Backup API snapshot |

## Verification File Bundles

| Bundle | Exact planned test/evaluation files |
|---|---|
| `T-GOV` | `tests/hermes_coach/contract/test_requirements_coverage.py`; `tests/hermes_coach/contract/test_architecture_boundaries.py` |
| `T-POLICY` | `tests/hermes_coach/unit/test_companion_policy.py`; `tests/hermes_coach/unit/test_listening_policy.py`; `tests/hermes_coach/unit/test_question_policy.py`; `tests/hermes_coach/unit/test_feedback_policy.py`; all fixtures under `tests/hermes_coach/evals/golden_conversations/` and `tests/hermes_coach/evals/counterexamples/` |
| `T-STATE` | `tests/hermes_coach/unit/test_transitions.py`; `tests/hermes_coach/persistence/test_session_recovery.py`; `tests/hermes_coach/e2e/test_six_step_text.py` |
| `T-GOAL` | `tests/hermes_coach/unit/test_goal_rules.py`; `tests/hermes_coach/evals/scenarios/goal-*.yaml` |
| `T-OPTIONS` | `tests/hermes_coach/unit/test_options_rules.py`; `tests/hermes_coach/evals/scenarios/options-*.yaml` |
| `T-RECORDS` | `tests/hermes_coach/unit/test_record_confirmation.py`; `tests/hermes_coach/unit/test_record_confirmation_service.py`; `tests/hermes_coach/unit/test_consent_events.py`; `tests/hermes_coach/persistence/test_record_persistence.py`; candidate timing/re-confirm cases within these suites |
| `T-DATA` | `tests/hermes_coach/persistence/test_sqlite_schema.py`; `tests/hermes_coach/persistence/test_migrations.py`; `tests/hermes_coach/persistence/test_restart_recovery.py`; `tests/hermes_coach/persistence/test_memory_provenance.py` |
| `T-API` | `tests/hermes_coach/contract/test_api_contract.py`; `tests/hermes_coach/contract/test_rpc_contract.py` |
| `T-UX` | colocated `*.test.tsx` under `apps/hermes-coach/src/features/`; `tests/hermes_coach/e2e/test_onboarding.py`; `tests/hermes_coach/e2e/test_dashboard.py` |
| `T-CHECKIN` | `tests/hermes_coach/unit/test_check_in_service.py`; `tests/hermes_coach/persistence/test_scheduler_adapter.py`; `tests/hermes_coach/e2e/test_check_in.py`; `tests/hermes_coach/e2e/test_notification_privacy.py` |
| `T-PRIVACY` | `tests/hermes_coach/unit/test_context_selector.py`; `tests/hermes_coach/unit/test_retention_service.py`; `tests/hermes_coach/persistence/test_egress_manifest.py`; `tests/hermes_coach/persistence/test_trash_lifecycle.py`; `tests/hermes_coach/e2e/test_privacy_center.py`; `tests/hermes_coach/e2e/test_unencrypted_data_warning.py` |
| `T-SAFETY` | `tests/hermes_coach/unit/test_safety_policy.py`; `tests/hermes_coach/persistence/test_safety_interruption.py`; `tests/hermes_coach/evals/scenarios/safety-*.yaml` |
| `T-PROMPT` | `tests/hermes_coach/contract/test_output_schema.py`; `tests/hermes_coach/contract/test_prompt_byte_stability.py`; `tests/hermes_coach/unit/test_prompt_contract.py`; `tests/hermes_coach/unit/test_question_validator.py`; `tests/hermes_coach/unit/test_regeneration.py`; `tests/hermes_coach/evals/rubrics/question-only.yaml` |
| `T-RUNTIME` | `tests/hermes_coach/persistence/test_hermes_runtime_adapter.py`; `tests/hermes_coach/contract/test_no_core_tool.py`; existing Hermes prompt-cache regression tests |
| `T-METRICS` | `tests/hermes_coach/unit/test_metrics_service.py`; `tests/hermes_coach/contract/test_metrics_definitions.py`; `tests/hermes_coach/e2e/test_metrics_dashboard.py` |
| `T-DEPLOY` | planned loopback-only/no-login smoke, no-LAN-bind guard, unencrypted-backup warning, backup/restore, offline/degraded and Windows startup tests |

## Content Allocation Details

| Source block | Family | Architecture section | Production | Verification | Nội dung phân bổ | Status |
|---|---|---|---|---|---|---|
| `Overview` | `HC-PRODUCT` | Overview; System Context | `P-PRODUCT`, `P-RUNTIME` | `T-GOV`, `T-RUNTIME` | Một Coachee, career development, standalone responsive local-first web app, Hermes foundation, không deep fork | `planned` |
| `Source of Truth and Change Control` | `HC-GOV` | Requirement Ownership | `P-GOV` | `T-GOV` | Canonical precedence, change control, trace hai chiều, trạng thái và blocker | `implemented` |
| `Problem Statement` | `HC-PRODUCT` | System Context; Evaluation | `P-PRODUCT`, `P-RECORDS`, `P-CHECKIN` | `T-UX`, `T-CHECKIN` | Không gian liên tục, clarity, accountability, evidence, check-in không phán xét, user control | `planned` |
| `Causal Coaching Thesis` | `HC-GOAL` | Goal Validation | `P-GOAL`, `P-POLICY` | `T-GOAL`, `T-POLICY` | Mục tiêu chưa rõ → giải pháp thiếu/lặp; làm rõ mục tiêu trước; insight do Coachee | `planned` |
| `Product Principles > Người đồng hành ngang vị thế` | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` | Equal stance, không quyền uy/áp lực/tội lỗi/phụ thuộc; Coachee sở hữu output | `planned` |
| `Product Principles > Nhận diện rào cản vô thức` | `HC-COMPANION` | Companion Policies | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` | Mọi dạng rào cản, hypothesis discipline, toàn bộ câu hỏi mẫu, quay Pre-Coaching khi căng thẳng | `planned` |
| `Product Principles > Vòng tròn quan tâm và vòng tròn ảnh hưởng` | `HC-GOAL` | Goal Validation; Policies | `P-POLICY`, `P-GOAL` | `T-GOAL`, `T-POLICY` | Định nghĩa hai vòng, không phủ nhận/đổ lỗi, toàn bộ câu hỏi, rollback Goal | `planned` |
| `Product Principles > Niềm tin bắt buộc vào tiềm năng của Coachee` | `HC-COMPANION` | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` | Niềm tin bắt buộc, hành vi thể hiện, không blind praise, tìm support step | `planned` |
| `Product Principles > Chỉ đặt câu hỏi` | `HC-COMPANION` | Companion Policies; Prompt | `P-POLICY`, `P-PROMPT`, `P-SAFETY`, `P-UX` | `T-POLICY`, `T-PROMPT`, `T-SAFETY` | Đúng một câu hỏi; declarative lead-in chỉ nằm trong chính câu hỏi, có căn cứ từ lời Coachee; Safety/Product/Data UI exceptions | `planned` |
| `Product Principles > Quyền tự chủ` | `HC-RECORDS` | Confirmation | `P-RECORDS`, `P-UX` | `T-RECORDS`, `T-UX` | Confirmation trước write; refuse/stop/change/delete; không quyết định hệ trọng thay | `planned` |
| `Kỹ năng đặt câu hỏi — quay đầu là hỏi` | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` | Khi unclear/stuck/ask-answer phải quay về câu hỏi làm rõ G/R/O/W | `planned` |
| `Tiêu chí đặt câu hỏi dành cho Coach` | `HC-COMPANION` | Companion Policies; Prompt | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` | KISS, neutral, purpose, 5W/1H, Why→What, narrowing | `planned` |
| `Một câu hỏi đúng phải làm được gì?` | `HC-COMPANION` | Companion Policies; Evaluation | `P-POLICY` | `T-POLICY` | Năng lực/rào cản, đúng vấn đề, đúng current_step, ownership, không đánh giá độ sâu/độ dài | `planned` |
| `Lắng nghe sâu — 4 cấp độ` và `L1`–`L4` | `HC-COMPANION` | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY` | Toàn bộ self-check L1–L4, hiểu trước phản ánh, không right/wrong/fix/rescue/advise | `planned` |
| `Lắng nghe chủ động và phản ánh lại` | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` | Emotion, empathy, không pity/judge, 80/20; phản ánh làm lead-in cho câu hỏi confirm/correct | `planned` |
| `Ghi nhận trong khai vấn` và `Cấu trúc ghi nhận` | `HC-COMPANION` | Companion Policies | `P-POLICY` | `T-POLICY` | Trân trọng → hành vi cụ thể → câu hỏi khám phá giá trị; không tâng bốc/đánh giá | `planned` |
| `Phản hồi trong khai vấn` | `HC-COMPANION` | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` | Quan sát → Phản chiếu → Khám phá trong một câu hỏi; không standalone statement | `planned` |
| `Câu hỏi theo từng bước` | `HC-PROCESS` | Six-Step Engine; Policies | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` | Toàn bộ câu hỏi Goal/Reality/Options, dùng đúng bước và không script máy móc | `planned` |
| `Kỹ thuật thay đổi góc nhìn` | `HC-OPTIONS` | Options Recovery | `P-OPTIONS`, `P-POLICY` | `T-OPTIONS`, `T-POLICY` | Toàn bộ perspective questions; không phủ nhận/positive pressure | `planned` |
| `Way Forward — câu hỏi định hướng` | `HC-PROCESS` | Six-Step Engine | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` | Goal recheck, blocker, Coach support; examples không bắt buộc hỏi hết | `planned` |
| `Local-first và minh bạch` | `HC-PRIVACY` | Privacy and Egress | `P-PRIVACY`, `P-DATA`, `P-DEPLOY` | `T-PRIVACY`, `T-DEPLOY` | Loopback-only/no-login, retention 90/30 ngày, explicit unencrypted local/backup warning, Windows profile ACL, minimal context và egress preview | `planned` |
| `Scope > MVP` | `HC-PRODUCT` | Planned Layout; all capability sections | tất cả production bundles | tất cả verification bundles | Toàn bộ MVP capability list | `planned` |
| `Scope > Out of Scope` | `HC-PRODUCT` | Product Boundary | `P-GOV`, `P-PRODUCT` | `T-GOV` | Mọi exclusion, gồm Research/Advice mode, toàn bộ voice/STT/TTS và LAN/remote | `planned` |
| `Coaching Contract` | `HC-COMPANION` | Web UX; Confirmation; Safety | `P-UX`, `P-RECORDS`, `P-SAFETY` | `T-UX`, `T-RECORDS`, `T-SAFETY` | Tất cả disclosure, consent, Settings edit và re-confirm change | `planned` |
| `Six-Step Coaching Process` | `HC-PROCESS` | Six-Step Engine | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` | Pre + GROW + Review là framework duy nhất; không rigid questionnaire, không framework dispatcher/phụ | `planned` |
| `Vòng lặp GROW và transition gates` | `HC-PROCESS` | Six-Step Engine | `P-STATE` | `T-STATE` | Sáu explicit-Yes gates, current-step stay on No/unclear, arbitrary targeted GROW rollback, downstream invalidation, sequential replay; Phase 1 contract in `transition_contract.py` | `verified` |
| `Câu hỏi phễu` | `HC-PROCESS` | Companion Policies; State Machine | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` | Open → 5W/1H → clarify/reflect → Yes/No, chỉ hẹp khi đủ rõ, same step | `planned` |
| `1 — Pre-Coaching > Mục tiêu` | `HC-PROCESS-PRE` | Six-Step Engine; Web UX | `P-STATE`, `P-UX` | `T-STATE`, `T-UX` | Trust/agreement/safety/readiness/context/plan toàn bộ | `planned` |
| `Thấu hiểu và thỏa thuận chung` | `HC-PROCESS-PRE` | Six-Step Engine; Confirmation | `P-STATE`, `P-RECORDS` | `T-STATE`, `T-RECORDS` | Ready, roles, space, scope/challenge/usefulness, explicit Yes gate; non-gate consent dùng UI evidence | `planned` |
| `Pre-Coaching > Câu hỏi mẫu` | `HC-PROCESS-PRE` | Companion Policies | `P-POLICY` | `T-POLICY` | Toàn bộ chín câu hỏi mẫu và adaptation | `planned` |
| `Chuẩn bị của Coach` và `Chuẩn bị tâm thế cho Coach` | `HC-PROCESS-PRE` | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY` | Presence/curiosity/self-check/context permission và khoảng trống suy nghĩ | `planned` |
| `Lỗi thường gặp cần tránh` | `HC-PROCESS-PRE` | State Machine; Policies | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` | Năm lỗi, rollback Pre-Coaching, open recovery questions, toàn bộ outputs và gate | `planned` |
| `2 — Goal` và `Mục tiêu bắt buộc SMART và đúng với Coachee` | `HC-GOAL` | Goal Validation | `P-GOAL`, `P-STATE` | `T-GOAL`, `T-STATE` | SMART hard gate, đúng/thuộc Coachee, không tự đặt mục tiêu | `planned` |
| `Tiêu chí mục tiêu hợp lệ` | `HC-GOAL` | Goal Validation | `P-GOAL`, `P-POLICY` | `T-GOAL` | SMART + benefit/loss + ownership/value/need/influence được làm rõ trước closing gate | `planned` |
| `Case study — một câu hỏi làm lộ mục tiêu thật` | `HC-GOAL` | Goal Validation; Evaluation | `P-POLICY`, `P-GOAL` | `T-GOAL`, `T-POLICY` | Toàn bộ case, neutral/soft wording, không phủ nhận hoàn cảnh, insight tự nhận | `planned` |
| `3 — Reality` và các subsection | `HC-PROCESS-REALITY` | Six-Step Engine | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` | Facts/emotions/assumptions/resources/obstacles/gap; explicit Yes sau closing question bật `reality_confirmed` | `planned` |
| `4 — Options > Think Outside the Box` | `HC-OPTIONS` | Options Recovery | `P-OPTIONS`, `P-POLICY` | `T-OPTIONS` | Mọi câu hỏi mở rộng, values/resources/no-change; không cung cấp list; không có Research/Advice mode | `planned` |
| `Dấu hiệu chạm ngưỡng trong Options` | `HC-OPTIONS` | Options Recovery | `P-OPTIONS` | `T-OPTIONS` | Phase 1 scenario corpus and scoring cover repeat/same-nature/don't-know/assumption signals; production classifier/recovery remains planned | `implemented` |
| `Tiêu chí thành công của Options` | `HC-OPTIONS` | Options Recovery | `P-OPTIONS`, `P-STATE` | `T-OPTIONS`, `T-STATE` | Phase 1 contract/eval carries `novel_option_required` and `novel_option_observed`; production novelty classifier remains planned | `implemented` |
| `Khi Coachee chưa có giải pháp` | `HC-OPTIONS` | Options Recovery | `P-OPTIONS`, `P-POLICY`, `P-STATE` | `T-OPTIONS`, `T-POLICY` | Toàn bộ 10-step playbook, questions, silence, giữ đúng vai, không mode switch | `planned` |
| `Cách chia nhỏ vấn đề` | `HC-OPTIONS` | Options Recovery | `P-OPTIONS`, `P-POLICY` | `T-OPTIONS` | Toàn bộ 8 layer, examples, Coachee recognizes/adjusts/confirms, no interrogation, fallback | `planned` |
| `5 — Will` và `Way Forward — Cam kết hành động` | `HC-PROCESS-WILL` | Six-Step Engine; Records | `P-STATE`, `P-RECORDS`, `P-POLICY` | `T-STATE`, `T-RECORDS` | Action/start/evidence, thang `1–10`, explicit Yes bật `will_confirmed`; save consent qua UI | `planned` |
| `6 — Review > Tổng kết sau phiên` | `HC-PROCESS-REVIEW` | Six-Step Engine; Records | `P-STATE`, `P-RECORDS` | `T-STATE`, `T-RECORDS` | Mọi review question, optional record, re-confirm riêng từng candidate, không batch | `planned` |
| `Theo dõi sau phiên` | `HC-CHECKIN` | Check-in and Notifications | `P-CHECKIN`, `P-RECORDS` | `T-CHECKIN` | Phase 1 contract fixes 14-day cadence, one neutral reminder/catch-up and quiet-hours/permission behavior; scheduler and UI remain planned | `verified` |
| `Kết thúc phiên` | `HC-PROCESS-REVIEW` | Six-Step Engine | `P-STATE`, `P-CHECKIN` | `T-STATE`, `T-CHECKIN` | Step 7 treated as Review substep, four questions, final Yes/No gate | `planned` |
| `Quy tắc câu hỏi chốt` | `HC-PROCESS` | Six-Step Engine | `P-STATE`, `P-RECORDS` | `T-STATE`, `T-RECORDS` | Exactly one Yes/No ở cả sáu bước; No không failure; no auto advance/close | `planned` |
| `Coaching Session State Machine` | `HC-PROCESS` | Six-Step Engine | `P-STATE`, `P-DATA` | `T-STATE`, `T-DATA` | Phase 1 ordered transition and lifecycle contracts cover gates, rollback, pause/resume and early close; session service/persistence remains planned | `verified` |
| `UX Flows > Onboarding` | `HC-UX` | Web UX | `P-UX`, `P-RECORDS` | `T-UX`, `T-RECORDS` | Tất cả 8 steps, six baseline scores và confirmation | `planned` |
| `UX Flows > Home` | `HC-UX` | Web UX | `P-UX` | `T-UX` | Bốn câu hỏi Home và sáu components/actions | `planned` |
| `UX Flows > Coaching Session` | `HC-UX` | Web UX; State Machine | `P-UX`, `P-STATE`, `P-RECORDS` | `T-UX`, `T-STATE`, `T-RECORDS` | Text-only, six steps, one question, useful/skip/stop, per-record candidate UI, Review Yes before close | `planned` |
| `UX Flows > Scheduled Check-in` | `HC-CHECKIN` | Check-in and Notifications | `P-CHECKIN` | `T-CHECKIN` | Neutral notification, open/snooze, all questions/actions, no blame/streak shame | `planned` |
| `UX Flows > Voice` | `HC-VOICE` | Voice | `P-GOV`, `P-PRODUCT` | `T-GOV` | Deferred; guard không tạo STT/TTS/microphone/audio/voice paths hoặc tests trong MVP | `planned` |
| `UX Flows > Privacy Center` | `HC-PRIVACY` | Privacy and Egress | `P-PRIVACY`, `P-UX` | `T-PRIVACY`, `T-UX` | Browse provenance/use, retention 90/30 ngày, unencrypted warning, export, move-to-Trash, transcript/all-data soft delete, per-item restore, separate confirmed permanent purge và egress history | `planned` |
| `Information Architecture` | `HC-UX` | Web UX | `P-UX` | `T-UX` | Tất cả routes Today/Coach/Goals/Journey/Insights/Settings children | `planned` |
| `Technical Architecture` | `HC-PRODUCT` | System Context; Planned Layout | `P-PRODUCT`, `P-RUNTIME`, `P-DATA`, `P-CHECKIN` | `T-GOV`, `T-RUNTIME` | Toàn bộ Mermaid components/dependencies, không voice branch | `planned` |
| `Standalone web product, shared engine` | `HC-PRODUCT` | Integration Boundary | `P-RUNTIME`, `P-PRODUCT` | `T-RUNTIME`, `T-GOV` | Mọi reuse/non-reuse rule, transport patterns, no file memory SoT, no core tool | `planned` |
| `Coach Application Layer` | `HC-PRODUCT` | Application Services | `P-API`, application services | `T-API`, service unit tests | Toàn bộ ownership và UI→service→runtime boundary | `planned` |
| `Prompt and Cache Strategy` | `HC-COMPANION` | Prompt and Cache | `P-PROMPT`, `P-RUNTIME` | `T-PROMPT`, `T-RUNTIME` | Mọi stable element, byte stability, context injection, no system message mid-history | `planned` |
| `Structured Model Output` | `HC-COMPANION` | Prompt and Cache | `P-PROMPT`, `P-RECORDS` | `T-PROMPT`, `T-RECORDS` | Singular `question: string`, toàn bộ JSON fields và candidate confirmation | `planned` |
| `Question-only Validator` | `HC-COMPANION` | Prompt and Cache | `P-PROMPT` | `T-PROMPT` | Phase 1 runtime contract/harness validates singular question output, semantic validation, bounded regeneration and fail-closed result; production policy module remains planned | `verified` |
| `Data Model` relationship diagram | `HC-DATA` | Domain Model | `P-DATA`, `P-PRIVACY` | `T-DATA`, `T-PRIVACY` | Relationships; six-step gate, UI consent, candidate timing, normative memory provenance và `trash_entry` schemas | `planned` |
| `coachee_profile` | `HC-DATA-PROFILE` | Domain Model | `P-DATA` | `T-DATA` | Mọi field được liệt kê | `planned` |
| `career_snapshot` | `HC-DATA-SNAPSHOT` | Domain Model | `P-DATA` | `T-DATA` | Mọi field và append-only invariant | `planned` |
| `goal` | `HC-DATA-GOAL` | Domain Model | `P-DATA`, `P-GOAL` | `T-DATA`, `T-GOAL` | Phase 1 resolves abandoned lifecycle and distinct separately-confirmed draft reuse; full domain schema/repository remains planned | `verified` |
| `commitment` | `HC-DATA-COMMITMENT` | Domain Model | `P-DATA`, `P-RECORDS` | `T-DATA`, `T-RECORDS` | Mọi field được liệt kê | `planned` |
| `evidence` | `HC-DATA-EVIDENCE` | Domain Model | `P-DATA` | `T-DATA` | Mọi field được liệt kê | `planned` |
| `check_in` | `HC-DATA-CHECKIN` | Domain Model | `P-DATA`, `P-CHECKIN` | `T-DATA`, `T-CHECKIN` | Mọi field được liệt kê | `planned` |
| `coaching_session` | `HC-DATA-SESSION` | Domain Model | `P-DATA`, `P-STATE` | `T-DATA`, `T-STATE` | Mọi field được liệt kê | `planned` |
| `insight` | `HC-DATA-INSIGHT` | Domain Model | `P-DATA`, `P-RECORDS` | `T-DATA`, `T-RECORDS` | Mọi field được liệt kê | `planned` |
| `memory_item` | `HC-DATA-MEMORY` | Domain Model; Memory | `P-DATA`, `P-PRIVACY` | `T-DATA`, `T-PRIVACY` | Mọi field; confirmed memory có `expires_at = NULL`, không automatic expiry và tồn tại tới khi Coachee tự xóa; normalized `memory_provenance` đa nguồn; pending memory candidate vẫn retention 90 ngày; independent soft delete/restore và Trash 30 ngày | `planned` |
| `Memory Policy` | `HC-MEMORY` | Domain Model; Privacy | `P-DATA`, `P-PRIVACY`, `P-RUNTIME` | `T-DATA`, `T-PRIVACY`, `T-RUNTIME` | Ba lớp, SQLite truth, approved values/preferences/insights, transcript move-to-Trash, context exclusion và restore | `planned` |
| `Safety > Role Boundaries` | `HC-SAFETY` | Safety Architecture | `P-SAFETY`, `P-POLICY` | `T-SAFETY`, `T-POLICY` | Toàn bộ vai trò không phải và no substitute decision-maker | `planned` |
| `Safety > Safety States` | `HC-SAFETY` | Safety Architecture | `P-SAFETY`, `P-STATE` | `T-SAFETY`, `T-STATE` | Phase 1 contract covers urgent interruption, direct guidance, no normal continuation and no silent de-escalation; thresholds/content/release evidence remain externally gated | `implemented` |
| `Safety > Prohibited Behaviors` | `HC-SAFETY` | Safety Architecture | `P-SAFETY`, `P-POLICY` | `T-SAFETY`, `T-POLICY` | Mọi điều cấm dependency/label/guilt/dark pattern/directive/diagnosis/consent/disclosure | `planned` |
| `Safety > Privacy Controls` | `HC-PRIVACY` | Privacy and Egress | `P-PRIVACY`, `P-DATA`, `P-DEPLOY` | `T-PRIVACY`, `T-DATA`, `T-DEPLOY` | Profile ACL, explicit no-encryption boundary/warnings, backup caveat, retention 90/30 ngày, text-only/no audio, manifest, export, atomic soft delete, context exclusion, restore, confirmed permanent purge, no API key | `planned` |
| `Non-functional Requirements` | `HC-NFR` | Tất cả architecture sections | tất cả production bundles | tất cả verification bundles | NF-01 đến NF-10 nguyên văn và target | `planned` |
| `Evaluation Strategy` | `HC-EVAL` | Evaluation and Verification | policy/state/goal/options/safety bundles | mọi eval bundle | `68` scenarios, `7` rubrics, deterministic harness/scoring and proposal-category coverage | `verified` |
| `Acceptance Criteria` | `HC-AC` | Evaluation and Verification | xem bảng AC bên dưới | xem bảng AC bên dưới | All `58` checklist items are allocated and corpus coverage is verified; product execution remains later-phase work | `implemented` |
| `Success Metrics` | `HC-METRICS` | Evaluation and Verification | planned metrics projection service/UI | planned metric contract/e2e tests | Không optimize messages/time; toàn bộ 7 metrics | `planned` |
| `Delivery Roadmap` và `Phase 0`–`Phase 6` | `HC-ROADMAP` | Delivery and Deployment | bundles theo phase | bundles theo phase | Estimate, commercial-polish exclusion and phase ordering remain planned; Phase 1 contract/eval work is evidenced separately above | `planned` |
| `Architecture Decision > Recommended` | `HC-ADR` | Overview; Integration Boundary | `P-PRODUCT`, `P-RUNTIME` | `T-GOV`, `T-RUNTIME` | Standalone web app + Hermes backend + application layer | `planned` |
| `Alternatives Considered` | `HC-ADR` | Integration Boundary | `P-GOV` | `T-GOV` | Toàn bộ alternatives, benefits, costs và decisions | `planned` |
| `Assumptions to Validate` | `HC-ASSUMPTION` | Evaluation; Blockers | bundles liên quan | evals liên quan | Tất cả six assumptions, không chuyển thành fact trước validation | `blocked` |
| `Decision Log` | `HC-DECISION` | Requirement Ownership; Blockers | `P-GOV` và bundle liên quan | `T-GOV` và test bundle liên quan | Tất cả accepted/rejected/superseded decisions; proposal approved 2026-08-11, code vẫn gated bởi plan approval | `planned` |
| `References` | `HC-REFERENCE` | References; Integration Boundary | `P-GOV`, `P-RUNTIME` | `T-GOV`, existing regression suites | ICF sources và mọi file/folder Hermes tham chiếu | `planned` |
| `Next Steps` | `HC-GOV` | Delivery and Deployment | `P-GOV` | `T-GOV` | Create trace-linked implementation plan, review/approve plan, code only after separate plan approval | `planned` |
| `Unresolved Questions` | `HC-BLOCKER` | Architecture Decision and Blocker Status | `P-GOV` | `T-GOV` | Không còn câu hỏi sản phẩm chưa chốt; retention và MVP no-encryption đã vào Decision Log | `planned` |

## Phase 2 Coaching Engine Evidence

`hermes_coach/requirements_map.yaml.phase_2` is the executable owner for the
Phase 2 slice. `test_requirements_coverage.py` proves its source and AC lists
are exactly equal to all proposal rows allocated to phase `2`, and proves every
listed production/verification file exists. The exact scope is 74 source
blocks, 52 ACs, seven production bundles, seven verification bundles, 19
production files and 22 verification files.

Bằng chứng thực thi ngày 2026-08-22: `301` test pass tại exit gate Phase 2,
branch coverage `91%` trên `hermes_coach`, Ruff pass. Sáu diagnostic
protocol-variance của `ty` đã được sửa ngay trong ngày nên `ty` sạch. Chi tiết
lệnh và giới hạn nằm trong
[báo cáo kiểm chứng Phase 2](../plans/260811-1454-hermes-coach-mvp-implementation/reports/phase-02-verification.md).
Các trạng thái `implemented` trong bảng dưới đây giữ nguyên vì chúng mô tả phạm
vi engine thuần; việc nâng lên `verified` cho từng hàng cần đối chiếu riêng theo
quy tắc hoàn tất số 6 và không được suy ra từ con số tổng.

| Proposal allocation | Architecture destination | Production content/file | Verification content/file | Phase 2 result |
|---|---|---|---|---|
| `SRC-004…025`, `028`, `073…075`; `HC-COMPANION` | Companion, Listening, Question and Feedback Policies | `policies/companion_policy.py`, `listening_policy.py`, `question_policy.py`, `feedback_policy.py`; `prompt/system_prompt.py`, `question_validator.py` | Corresponding policy/validator unit tests and behavior scenarios | `implemented` |
| `SRC-030…039`, `059…061`; `HC-PROCESS`, `HC-GOAL` | Six-Step Engine; Goal Validation | `domain/models.py`, `session_state.py`, `transitions.py`, `goal_rules.py`; `application/coaching_service.py`; `prompt/structured_context.py` | `test_transitions.py`, `test_stage_completion.py`, `test_goal_rules.py`, Goal/transition scenarios | `implemented` |
| `SRC-040…050`; `HC-OPTIONS` | Options Novelty and Stuck Recovery | `domain/options_rules.py`; `policies/question_policy.py` | `test_options_rules.py`, Options scenarios | `implemented` |
| `SRC-051…057`; `HC-PROCESS-WILL`, `HC-PROCESS-REVIEW`, `HC-RECORDS` | Six-Step Engine; Confirmation | `domain/models.py`, `session_state.py`; `application/record_confirmation_service.py` | `test_stage_completion.py`, `test_record_confirmation.py`, `test_record_confirmation_service.py`, Will/Review scenarios | `implemented-process-local`; durable CAS is Phase 3 |
| `SRC-065`, `079`, `080`, `084`, `085`; `HC-UX`, `HC-PRODUCT` | Application Services; Prompt and Structured Output | `application/coaching_service.py`, `record_confirmation_service.py`; `prompt/output_schema.py`, `regeneration.py` | output-schema, regeneration and record-command tests; React/HTTP portions deferred | `engine-implemented` |
| `SRC-083`, `084`; `HC-CHECKIN`, `HC-RECORDS` | Check-in command boundary | `application/record_confirmation_service.py` | `test_record_confirmation.py`; scheduler/notification work deferred | `boundary-implemented` |
| `SRC-087…090`, `092`; `HC-SAFETY` | Safety Architecture | `domain/enums.py`; `policies/safety_policy.py`; `application/safety_service.py` | signed-attestation/tamper/expiry tests, safety scenarios, pending external human gate | `implemented-release-blocked` |
| `SRC-093`, `094`, `096`, `098`, `107`, `108`; `HC-EVAL`, `HC-ADR`, `HC-ROADMAP` | Evaluation; Integration Boundary; Delivery | `prompt/system_prompt.py`, `requirements_map.yaml`; pure no-provider/no-core-fork engine | prompt byte-stability, input/category-driven structural harness, observation-independence and per-structural-field mutation tests, deliberately broken transition/novelty tests and coverage gate | `implemented` |

The source lists above are compact ranges for readability; the canonical exact
list is stored in `requirements_map.yaml.phase_2.required_sources`. `SRC-058`
belongs to later check-in work and is intentionally absent. `AC-50` is present
because Phase 2 owns only its trusted keep/edit/reschedule/cancel UI-command
contract. Proposal roadmap “Phase 1 — Coaching Engine” corresponds to
implementation Phase 2 after the separate contract/evaluation phase.

Statuses in the general allocation tables below refer to end-to-end completion.
An AC that also owns React, SQLite, HTTP, scheduler or provider evidence can
therefore remain `planned` there even when its Phase 2 engine slice is listed as
implemented above.

For evaluation provenance, free-text scenario `expected.must_do` and
`expected.must_not_do` are descriptive golden intent in structural Phase 2 mode.
They are not copied into observed behavior or scored as automatic success;
executable evidence is the real service/rule path plus focused policy tests.
The complete expected object is observation-independence tested, while every
structural field is separately mutation-tested to change the score. Only
applicable, actually observed Phase 2 rubrics are selected.

## Phase 3 Local Data Evidence

`hermes_coach/requirements_map.yaml.phase_3` là owner thực thi của slice Phase 3
và mang `status: completed`; `test_requirements_coverage.py` chứng minh danh
sách source/AC bằng đúng mọi hàng được phân bổ cho phase `3` (36 source, 29 AC)
và mọi file khai báo đều tồn tại. Danh sách file sẽ dài thêm theo từng bước
tests-first, nên nó chưa phải toàn bộ phase.

Cảnh báo phạm vi: mục Trace Scope trong file plan Phase 3 liệt kê ít source hơn
map (thiếu `SRC-028`, `060`, `061`, `070`, `072`, `074`, `093…096`, `107`). Map
là authority; prose cần được đối chiếu lại.

| Proposal allocation | Architecture destination | Production content/file | Verification content/file | Phase 3 result |
|---|---|---|---|---|
| `SRC-076…086`, `SRC-099`; `HC-DATA-*` | Domain Model; SQLite store | `infrastructure/sqlite/migrations/0001_initial_schema.sql` | `test_sqlite_schema.py` — 16 bảng chuẩn tắc, tập cột đúng bằng proposal, enum đóng, FK thực thi, `expires_at IS NULL` cho memory đã xác nhận, provenance null chỉ khi `manual`, một trash entry mở cho mỗi entity, index retention/active-scope | `implemented` |
| `SRC-076…086`, `SRC-099`; `HC-DATA-*` | Migration contract | `infrastructure/sqlite/migration_runner.py`, `migrations/__init__.py` | `test_migrations.py` — nâng cấp từ version 0, rollback cả data lẫn version khi SQL hỏng hoặc postcondition trượt, từ chối hạ cấp, lỗi rõ ràng với file hỏng | `implemented` |
| `SRC-091`; `HC-PRIVACY` | Privacy, Security and Egress | `infrastructure/sqlite/database.py` | `test_database_connection.py` — pragma bắt buộc, WAL kèm fallback, transaction immediate-lock, close idempotent, không có giá trị dạng credential trong file | `implemented-partial`; consent/egress/export vẫn thuộc các bước sau |
| `SRC-054…058`, `SRC-063`, `SRC-068`, `SRC-092`; `HC-RECORDS`, `HC-MEMORY`, `HC-PRIVACY` | Repositories; Trash | `domain/records.py`; `infrastructure/repositories/{base,goal,session_message,candidate,memory,career_snapshot,trash}_repository.py` | `test_active_scope.py` — table-driven trên toàn bộ repository đã đăng ký: soft delete biến mất khỏi cả list lẫn `get` trực tiếp, restore hiện lại, purge vẫn ẩn; lọc expiry/pending/confirmed; snapshot append-only không có method sửa; provenance nhiều nguồn append-only; subclass cố tình bỏ predicate chứng minh chính predicate là thứ loại trừ | `implemented` |
| `SRC-054…059`, `SRC-079`, `SRC-080`, `SRC-084`, `SRC-085`; `HC-RECORDS` | Application Services; Confirmation | `application/durable_confirmation_service.py`; `infrastructure/repositories/confirmation_repository.py`; `migrations/0002_confirmation_internals.sql` | `test_durable_confirmation.py` — intent, command guard, candidate CAS và official write trong một transaction; single-use và replay guard sống sót qua restart; accept/edit tạo goal/insight/commitment/memory, discard không tạo gì; re-confirm thêm revision; audit chỉ chứa id | `implemented` |
| `SRC-026`, `SRC-091`, `SRC-092`; `HC-PRIVACY` | Privacy, Security and Egress | `application/consent_service.py`; `infrastructure/repositories/consent_repository.py` | `test_consent.py` — append-only, bắt buộc control id UI, schema chốt `source='ui'`, chuẩn hoá type/scope, latest wins, `require_granted` đọc lại mỗi lần nên rút consent chặn ngay lần sau | `implemented` |
| `SRC-058`, `SRC-063`, `SRC-068`, `SRC-092`; `HC-PRIVACY`, `HC-MEMORY` | Retention; Trash lifecycle | `application/retention_service.py`; `trash_service.py`; `domain/clock.py`; `migrations/0003_retention_internals.sql` | `test_retention.py`, `test_trash_lifecycle.py` — biên 89/90/91 ngày và 29/30/31 ngày, clock tiêm vào, sweep idempotent, bắt kịp deadline lỡ khi app đóng, rollback khi lỗi; soft delete commit cùng marker, restore từng item và chặn khi mất parent, purge vĩnh viễn cần control UI, xoá dependent theo thứ tự, audit không chứa nội dung | `implemented` |
| `SRC-011`, `SRC-036`, `SRC-070`, `SRC-072`, `SRC-026`, `SRC-091`; `HC-MEMORY`, `HC-PRIVACY` | Context selector; egress audit; export | `application/context_selector.py`; `export_service.py`; `infrastructure/egress_audit.py`; `migrations/0004_egress_audit.sql` | `test_context_selection.py`, `test_egress_and_export.py` — loại expired/Trash/unconfirmed/withdrawn-scope/unrelated trước egress, item ref không chứa nội dung; audit không có cột content, provider retention chưa kiểm chứng hiển thị `unknown` và versioned riêng; export có provenance/status/timestamp/consent và công bố không mã hoá, redact giá trị dạng credential | `implemented` |
| `SRC-061`, `SRC-081`, `SRC-082`; `HC-PROCESS`, `HC-DATA-*`, `HC-CHECKIN` | Restart recovery | `application/session_recovery_service.py`; `infrastructure/repositories/{coaching_session,gate,check_in}_repository.py` | `test_restart_recovery.py` — tiến trình con thật ghi rồi thoát, có ca thoát bằng `os._exit` không đóng sạch; tiến trình cha dựng lại confirmed record, gate history, current stage, provenance và check-in đang chờ; write chưa commit không sống lại, bản ghi đã xoá không quay về | `implemented` |

## Acceptance-Criteria Allocation

Mỗi hàng dưới đây tương ứng đúng một checklist item hiện có trong proposal.

| ID | Nội dung rút gọn | Production | Verification | Status |
|---|---|---|---|---|
| `AC-01` | Onboarding hội thoại + agreement | `P-UX`, `P-RECORDS` | `T-UX`, `T-RECORDS` | `planned` |
| `AC-02` | Six-step bằng text | `P-STATE`, `P-UX` | `T-STATE`, `T-UX` | `planned` |
| `AC-03` | Loopback/no-login + guard không ship voice/STT/TTS paths/tests | `P-PRODUCT`, `P-GOV`, `P-DEPLOY` | `T-GOV`, `T-DEPLOY` | `planned` |
| `AC-04` | Mỗi bước đúng một câu chốt Yes/No | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` | `implemented` |
| `AC-05` | No giữ current step và làm rõ | `P-STATE` | `T-STATE` | `verified` |
| `AC-06` | Sáu bước chỉ qua/đóng với Yes rõ ngay sau closing gate | `P-STATE` | `T-STATE` | `verified` |
| `AC-07` | No/unclear/mâu thuẫn giữ current step; rollback có target riêng | `P-STATE` | `T-STATE` | `verified` |
| `AC-08` | Lưu/hiển thị current_step | `P-STATE`, `P-DATA`, `P-UX` | `T-STATE`, `T-DATA`, `T-UX` | `implemented` |
| `AC-09` | Funnel đúng thứ tự trong step | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` | `planned` |
| `AC-10` | Rollback tới G/R/O/W rồi đi tuần tự; cấm nhảy về origin | `P-STATE` | `T-STATE` | `verified` |
| `AC-11` | Options không qua khi lặp/trùng | `P-OPTIONS`, `P-STATE` | `T-OPTIONS`, `T-STATE` | `implemented` |
| `AC-12` | Coachee sinh solution mới khác bản chất | `P-OPTIONS` | `T-OPTIONS` | `implemented` |
| `AC-13` | Dùng expansion playbook; không Research/Advice mode | `P-OPTIONS`, `P-POLICY` | `T-OPTIONS`, `T-POLICY` | `planned` |
| `AC-14` | No solution kiểm tra Goal trước Options | `P-OPTIONS`, `P-STATE` | `T-OPTIONS`, `T-STATE` | `planned` |
| `AC-15` | Success = clarity/awareness, không count | `P-POLICY`, `P-OPTIONS` | `T-POLICY`, `T-OPTIONS` | `planned` |
| `AC-16` | Im lặng/chia nhỏ; không hỏi dồn | `P-POLICY`, `P-OPTIONS` | `T-POLICY`, `T-OPTIONS` | `planned` |
| `AC-17` | Chia layer đến phần rõ được confirm | `P-OPTIONS`, `P-RECORDS` | `T-OPTIONS`, `T-RECORDS` | `planned` |
| `AC-18` | Không advice/giải pháp thay; không Research/Advice mode | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-19` | Review cần đủ G/R/O/W gates | `P-STATE` | `T-STATE` | `verified` |
| `AC-20` | Goal→Reality cần SMART | `P-GOAL`, `P-STATE` | `T-GOAL`, `T-STATE` | `verified` |
| `AC-21` | Goal cần benefit/loss | `P-GOAL`, `P-STATE` | `T-GOAL`, `T-STATE` | `verified` |
| `AC-22` | Goal ownership/fit/influence | `P-GOAL`, `P-STATE` | `T-GOAL`, `T-STATE` | `verified` |
| `AC-23` | Unready không hỏi goal ngay | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` | `planned` |
| `AC-24` | Hỏi/ghi nhận emotion bằng question-form trước Goal khi cần | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` | `planned` |
| `AC-25` | Empathy + return Pre-Coaching | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` | `planned` |
| `AC-26` | Companion ngang vị thế | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` | `planned` |
| `AC-27` | Niềm tin vào tiềm năng/năng lực | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` | `planned` |
| `AC-28` | Không label bất lực/decide thay | `P-POLICY`, `P-SAFETY` | `T-POLICY`, `T-SAFETY` | `planned` |
| `AC-29` | Barrier là hypothesis | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-30` | Coachee tự nhận diện/tháo barrier | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-31` | Concern/influence không blame/deny | `P-POLICY`, `P-GOAL` | `T-POLICY`, `T-GOAL` | `planned` |
| `AC-32` | Influence → action/responsibility | `P-GOAL`, `P-RECORDS` | `T-GOAL`, `T-RECORDS` | `planned` |
| `AC-33` | Question-only grammar; Safety/UI exception | `P-POLICY`, `P-PROMPT`, `P-SAFETY`, `P-UX` | `T-POLICY`, `T-PROMPT`, `T-SAFETY` | `planned` |
| `AC-34` | Stuck/ask-answer → question | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-35` | Perspective question không deny | `P-POLICY`, `P-OPTIONS` | `T-POLICY`, `T-OPTIONS` | `planned` |
| `AC-36` | KISS/neutral/purpose/step/non-leading | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` | `planned` |
| `AC-37` | Question đúng năng lực/barrier/problem/step | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-38` | Question tạo ownership | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-39` | Dừng judge/fix/prepare-answer | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-40` | Reflect emotion inside one question + verify | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-41` | Acknowledge three-part question-form, no flatter/judge | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-42` | Coachee confirm/correct/disagree acknowledgment | `P-POLICY`, `P-UX` | `T-POLICY`, `T-UX` | `planned` |
| `AC-43` | Understand experience ≠ agree facts/views | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-44` | Accusatory Why → neutral What | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` | `planned` |
| `AC-45` | Feedback question ≠ advice/judgment/demand | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-46` | Feedback Observation→Reflection→Exploration trong một question | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-47` | Lead-in dựa fact/no-label; Coachee interpretation | `P-POLICY` | `T-POLICY` | `planned` |
| `AC-48` | Validator chặn disguised advice | `P-PROMPT` | `T-PROMPT` | `planned` |
| `AC-49` | Per-record confirm + optional individual re-confirm; no batch | `P-RECORDS`, `P-DATA`, `P-UX` | `T-RECORDS`, `T-DATA`, `T-UX` | `planned` |
| `AC-50` | Check-in keep/edit/reschedule/cancel | `P-CHECKIN`, `P-RECORDS` | `T-CHECKIN`, `T-RECORDS` | `implemented` |
| `AC-51` | Review lesson/action/follow-up + explicit Yes close gate | `P-STATE`, `P-RECORDS`, `P-CHECKIN` | `T-STATE`, `T-RECORDS`, `T-CHECKIN` | `planned` |
| `AC-52` | Notification permission + quiet hours | `P-CHECKIN` | `T-CHECKIN` | `verified` |
| `AC-53` | Restart không mất confirmed data | `P-DATA` | `T-DATA` | `planned` |
| `AC-54` | Explicit unencrypted warning + retention 90/30 + view/edit/export/Trash/restore/confirmed purge | `P-PRIVACY`, `P-UX`, `P-DEPLOY` | `T-PRIVACY`, `T-UX`, `T-DEPLOY` | `planned` |
| `AC-55` | Transparent egress categories | `P-PRIVACY` | `T-PRIVACY` | `verified` |
| `AC-56` | Stable system prompt | `P-PROMPT`, `P-RUNTIME` | `T-PROMPT`, `T-RUNTIME` | `verified` |
| `AC-57` | Urgent: labeled Safety System + direct guidance; no normal coaching | `P-SAFETY`, `P-STATE` | `T-SAFETY`, `T-STATE` | `implemented` |
| `AC-58` | Dashboard goal/commitment/evidence/insight | `P-UX`, `P-DATA` | `T-UX`, `T-DATA` | `planned` |

## Blocker Register

Các ID được giữ vĩnh viễn để audit; `resolved` không bị xóa khỏi lịch sử.

| ID | Status | Resolution or remaining decision | Affected families |
|---|---|---|---|
| `BLK-01` | `resolved` | Feedback/reflection/acknowledgment là đúng một câu hỏi; declarative lead-in có căn cứ không được đứng riêng. | `HC-COMPANION`, `AC-24`, `AC-33`, `AC-40`–`AC-47` |
| `BLK-02` | `resolved` | Commitment scale là `1–10`. | `HC-PROCESS-WILL` |
| `BLK-03` | `resolved` | Sáu gate dùng explicit Yes; consent ngoài gate chỉ dùng UI actions, withdrawal chặn request/write mới. | `HC-PROCESS`, `HC-RECORDS` |
| `BLK-04` | `resolved` | Pre-Coaching cần Yes để sang Goal; Review cần Yes để đóng, No/unclear ở lại trừ targeted rollback. | `HC-PROCESS-PRE`, `HC-PROCESS-REVIEW` |
| `BLK-05` | `resolved` | Rollback tới bất kỳ G/R/O/W cần revalidate, invalidate downstream và replay tuần tự. | `HC-PROCESS` |
| `BLK-06` | `resolved` | Goal criteria phải đủ trước closing question; gate service kiểm tra toàn bộ state. | `HC-GOAL` |
| `BLK-07` | `resolved` | Output schema dùng singular `question: string` bắt buộc. | `HC-COMPANION`, `HC-UX` |
| `BLK-08` | `resolved` | Reality/Will cần đủ state và explicit Yes sau closing question. | `HC-PROCESS` |
| `BLK-09` | `resolved` | Đã bổ sung schema value, message, candidate, gate, consent và trash entry. | `HC-DATA` |
| `BLK-10` | `resolved` | `memory_provenance` đa nguồn là schema chuẩn, source fields rời `memory_item`. | `HC-MEMORY` |
| `BLK-11` | `resolved` | Research/Advice mode bị loại; Coach tiếp tục question-only. | `HC-OPTIONS` |
| `BLK-12` | `resolved` | Loopback/no-login, delete/Trash, retention 90/30 ngày và MVP không mã hóa at rest đã chốt; UI warning bắt buộc, API key không nằm trong coaching DB. | `HC-PRIVACY`, `HC-PRODUCT` |
| `BLK-13` | `resolved` | Candidate xác nhận riêng tại điểm phù hợp; có thể re-confirm từng record, không batch. | `HC-RECORDS` |
| `BLK-14` | `resolved` | Voice/STT/TTS deferred; không chọn stack hoặc tạo path/test trong MVP. | `HC-VOICE` |
| `BLK-15` | `resolved` | Safety System được direct guidance trong urgent; operational safety details theo blocker riêng. | `HC-SAFETY` |
| `BLK-16` | `resolved` | Pre-Coaching + GROW + Review là framework duy nhất; rollback không cho phép forward skip khi replay. | `HC-PROCESS` |
| `BLK-17` | `resolved` | Confirmed `memory_item` tồn tại tới khi Coachee tự xóa; `expires_at = NULL`, không automatic expiry; pending memory candidate vẫn retention 90 ngày và Trash vẫn 30 ngày. | `HC-DATA-MEMORY`, `HC-MEMORY`, `HC-PRIVACY` |

## Change Checklist

Mỗi thay đổi Hermes Coach phải trả lời:

- [ ] Source block nào thay đổi?
- [ ] Requirement family và acceptance ID nào bị ảnh hưởng?
- [ ] Architecture section nào đã cập nhật?
- [ ] Production files nào thay đổi?
- [ ] Test/evaluation files nào chứng minh hành vi?
- [ ] Trạng thái traceability có đúng với bằng chứng thực tế không?
- [ ] Có blocker mới hoặc blocker đã được giải quyết tại proposal không?
- [ ] Có source heading, bullet, example, exception, diagram, field hoặc prohibition nào chưa được phân bổ không?

## References

- [Hermes Coach Product Proposal](./hermes-coach-product-proposal.md)
- [Hermes Coach System Architecture](./hermes-coach-system-architecture.md)
- `AGENTS.md`
