# Proposal → Implementation Map

## Reading Rule

[Hermes Coach Product Proposal](../../docs/hermes-coach-product-proposal.md) is canonical. Each `SRC-*` row below means the **entire content** from that heading until the next heading of equal or higher level: every sentence, bullet, numbered item, example, exception, diagram, table, field, prohibition and note—not merely this map’s short label.

Exact architecture destinations and exact production/verification file lists are defined in [requirements traceability](../../docs/hermes-coach-requirements-traceability.md), sections **Canonical Source Block Allocation**, **Production File Bundles** and **Verification File Bundles**. The `P-*`/`T-*` keys below join to those exact files; each linked phase further specifies the file content, interface, transaction and test work. Implementation must maintain both joins:

`SRC row → requirement family → architecture section → P/T bundle → phase file inventory → code/test evidence`.

Phase key: `1` contract/evaluation, `2` coaching engine, `3` local data/privacy, `4` runtime/API/package, `5` web UX, `6` check-ins/notifications, `7` hardening/release. `→` means ordered ownership; `/` means cross-cutting verification. `Guard` means prove absence, not create a deferred feature.

## Complete Source Allocation (112/112)

| Source | Full-content owner | Phase | Architecture destination | Production | Verification | Gate/status |
|---|---|---|---|---|---|---|
| `SRC-000` | Hermes Coach Product Proposal | 1/7 | Overview; Requirement Ownership | `P-GOV` | `T-GOV` | Plan approval |
| `SRC-001` | Overview | 1→4→5 | Overview; System Context | `P-PRODUCT`, `P-RUNTIME` | `T-GOV`, `T-RUNTIME` | Phase 1 contract |
| `SRC-002` | Source of Truth and Change Control | 1/7 | Requirement Ownership | `P-GOV` | `T-GOV` | Always enforced |
| `SRC-003` | Problem Statement | 1→5→6 | Overview; Evaluation and Verification | `P-PRODUCT`, `P-RECORDS`, `P-CHECKIN` | `T-UX`, `T-CHECKIN` | Eval before UI |
| `SRC-004` | Causal Coaching Thesis | 1→2 | Goal Validation | `P-GOAL`, `P-POLICY` | `T-GOAL`, `T-POLICY` | Phase 2 gate |
| `SRC-005` | Product Principles | 1→2 | Companion Policies | `P-POLICY` | `T-POLICY` | Scenario coverage |
| `SRC-006` | Người đồng hành ngang vị thế | 1→2 | Companion Policies | `P-POLICY` | `T-POLICY` | Scenario coverage |
| `SRC-007` | Nhận diện rào cản vô thức | 1→2 | Companion Policies | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` | Hypothesis only |
| `SRC-008` | Vòng tròn quan tâm/ảnh hưởng | 1→2 | Goal Validation; Companion Policies | `P-POLICY`, `P-GOAL` | `T-GOAL`, `T-POLICY` | No blame/denial |
| `SRC-009` | Niềm tin bắt buộc vào tiềm năng | 1→2 | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` | Prompt invariant |
| `SRC-010` | Chỉ đặt câu hỏi | 1→2→5→7 | Companion Policies; Prompt and Cache | `P-POLICY`, `P-PROMPT`, `P-SAFETY`, `P-UX` | `T-POLICY`, `T-PROMPT`, `T-SAFETY` | Safety exception gate |
| `SRC-011` | Quyền tự chủ | 2→3→5 | Application Services and Confirmation | `P-RECORDS`, `P-UX` | `T-RECORDS`, `T-UX` | UI-only confirmation |
| `SRC-012` | Quay đầu là hỏi | 1→2 | Companion Policies | `P-POLICY` | `T-POLICY` | No advice mode |
| `SRC-013` | Tiêu chí câu hỏi cho Coach | 1→2 | Companion Policies; Prompt and Cache | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` | Rubric pass |
| `SRC-014` | Một câu hỏi đúng phải làm gì | 1→2 | Companion Policies; Evaluation | `P-POLICY` | `T-POLICY` | Rubric pass |
| `SRC-015` | Lắng nghe sâu — 4 cấp độ | 1→2 | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY` | Golden conversations |
| `SRC-016` | L1 — Dừng suy nghĩ của Coach | 1→2 | Companion Policies | `P-POLICY` | `T-POLICY` | Golden conversations |
| `SRC-017` | L2 — Dừng đánh giá | 1→2 | Companion Policies | `P-POLICY` | `T-POLICY` | Golden conversations |
| `SRC-018` | L3 — Tập trung động cơ Coachee | 1→2 | Companion Policies | `P-POLICY` | `T-POLICY` | Golden conversations |
| `SRC-019` | L4 — Lắng nghe từ tâm | 1→2 | Companion Policies | `P-POLICY` | `T-POLICY` | Golden conversations |
| `SRC-020` | Lắng nghe chủ động/phản ánh | 1→2 | Companion Policies | `P-POLICY` | `T-POLICY` | One-question form |
| `SRC-021` | Ghi nhận trong khai vấn | 1→2 | Companion Policies | `P-POLICY` | `T-POLICY` | No praise/judgment |
| `SRC-022` | Cấu trúc ghi nhận | 1→2 | Companion Policies | `P-POLICY` | `T-POLICY` | Three-part question |
| `SRC-023` | Phản hồi trong khai vấn | 1→2 | Companion Policies; Prompt and Cache | `P-POLICY`, `P-PROMPT` | `T-POLICY`, `T-PROMPT` | Validator coverage |
| `SRC-024` | Phản hồi theo từng bước | 1→2 | Six-Step Engine; Companion Policies | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` | Stage-aligned |
| `SRC-025` | Kỹ thuật thay đổi góc nhìn | 1→2 | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-POLICY` | `T-OPTIONS`, `T-POLICY` | No difficulty denial |
| `SRC-026` | Local-first và minh bạch | 1→3→5→7 | Privacy, Security and Egress | `P-PRIVACY`, `P-DATA`, `P-DEPLOY` | `T-PRIVACY`, `T-DEPLOY` | Disclosure/release |
| `SRC-027` | Scope | 1/7 | Overview; Product Boundary | `P-GOV`, `P-PRODUCT` | `T-GOV` | Scope HOLD |
| `SRC-028` | MVP | 1→2→3→4→5→6→7 | Repository layout; all capability sections | `P-PRODUCT`, `P-POLICY`, `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-RECORDS`, `P-DATA`, `P-API`, `P-UX`, `P-CHECKIN`, `P-PRIVACY`, `P-SAFETY`, `P-PROMPT`, `P-RUNTIME`, `P-DEPLOY` | matching 14 capability T bundles | Phase gates |
| `SRC-029` | Out of Scope | 1/7 | Integration Boundary; Product Boundary | `P-GOV`, `P-PRODUCT` | `T-GOV` | Boundary scan |
| `SRC-030` | Coaching Contract | 1→2→5→7 | Web UX; Confirmation; Safety | `P-UX`, `P-RECORDS`, `P-SAFETY` | `T-UX`, `T-RECORDS`, `T-SAFETY` | Safety review |
| `SRC-031` | Six-Step Coaching Process | 1→2 | Six-Step Engine and State Machine | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` | Unique framework |
| `SRC-032` | GROW loop and transition gates | 1→2 | Six-Step Engine and State Machine | `P-STATE` | `T-STATE` | Explicit Yes |
| `SRC-033` | Câu hỏi phễu | 1→2 | Companion Policies; Six-Step Engine | `P-POLICY`, `P-STATE` | `T-POLICY`, `T-STATE` | Ordered funnel |
| `SRC-034` | Pre-Coaching | 1→2→5 | Six-Step Engine; Web UX | `P-STATE`, `P-UX` | `T-STATE`, `T-UX` | Pre gate |
| `SRC-035` | Pre-Coaching — Mục tiêu | 1→2→5 | Six-Step Engine; Web UX | `P-STATE`, `P-UX` | `T-STATE`, `T-UX` | Readiness first |
| `SRC-036` | Thấu hiểu/thỏa thuận chung | 1→2→3 | Six-Step Engine; Confirmation | `P-STATE`, `P-RECORDS` | `T-STATE`, `T-RECORDS` | Agreement evidence |
| `SRC-037` | Pre-Coaching questions | 1→2 | Companion Policies | `P-POLICY` | `T-POLICY` | Scenario coverage |
| `SRC-038` | Chuẩn bị của Coach | 1→2 | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY` | Prompt/eval |
| `SRC-039` | Chuẩn bị tâm thế | 1→2 | Companion Policies | `P-POLICY`, `P-PROMPT` | `T-POLICY` | Prompt/eval |
| `SRC-040` | Lỗi thường gặp | 1→2 | Six-Step Engine; Companion Policies | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` | Counterexamples |
| `SRC-041` | Goal | 1→2 | Goal Validation | `P-GOAL`, `P-STATE` | `T-GOAL`, `T-STATE` | Goal gate |
| `SRC-042` | Goal SMART và đúng Coachee | 1→2 | Goal Validation | `P-GOAL`, `P-STATE` | `T-GOAL`, `T-STATE` | Hard gate |
| `SRC-043` | Tiêu chí Goal hợp lệ | 1→2 | Goal Validation | `P-GOAL`, `P-POLICY` | `T-GOAL` | Full predicate |
| `SRC-044` | Case study mục tiêu thật | 1→2 | Goal Validation; Evaluation | `P-POLICY`, `P-GOAL` | `T-GOAL`, `T-POLICY` | Golden scenario |
| `SRC-045` | Reality | 1→2 | Six-Step Engine | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` | Reality gate |
| `SRC-046` | Khoảng cách Goal–Reality | 1→2 | Six-Step Engine; Companion Policies | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` | Predicate/eval |
| `SRC-047` | Nhận thức sâu sắc | 1→2 | Six-Step Engine; Companion Policies | `P-STATE`, `P-POLICY` | `T-STATE`, `T-POLICY` | One-question eval |
| `SRC-048` | Options | 1→2 | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-STATE` | `T-OPTIONS`, `T-STATE` | Novelty gate |
| `SRC-049` | Think Outside the Box | 1→2 | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-POLICY` | `T-OPTIONS` | Expansion playbook |
| `SRC-050` | Dấu hiệu chạm ngưỡng | 1→2 | Options Novelty and Stuck Recovery | `P-OPTIONS` | `T-OPTIONS` | Phase 1 novelty semantics |
| `SRC-051` | Tiêu chí thành công Options | 1→2 | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-STATE` | `T-OPTIONS`, `T-STATE` | AC-11/12 gate |
| `SRC-052` | Khi chưa có giải pháp | 1→2 | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-POLICY`, `P-STATE` | `T-OPTIONS`, `T-POLICY` | Recheck Goal first |
| `SRC-053` | Chia nhỏ vấn đề | 1→2 | Options Novelty and Stuck Recovery | `P-OPTIONS`, `P-POLICY` | `T-OPTIONS` | Layer confirmation |
| `SRC-054` | Will | 1→2→3 | Six-Step Engine; Confirmation | `P-STATE`, `P-RECORDS`, `P-POLICY` | `T-STATE`, `T-RECORDS` | Will gate |
| `SRC-055` | Way Forward/Cam kết | 1→2→3 | Six-Step Engine; Confirmation | `P-STATE`, `P-RECORDS`, `P-POLICY` | `T-STATE`, `T-RECORDS` | 1–10/evidence |
| `SRC-056` | Review | 1→2→3→5 | Six-Step Engine; Confirmation | `P-STATE`, `P-RECORDS` | `T-STATE`, `T-RECORDS` | Review gate |
| `SRC-057` | Tổng kết sau phiên | 1→2→3→5 | Six-Step Engine; Confirmation | `P-STATE`, `P-RECORDS` | `T-STATE`, `T-RECORDS` | Per-record only |
| `SRC-058` | Theo dõi sau phiên | 1→3→6 | Check-in and Notifications | `P-CHECKIN`, `P-RECORDS` | `T-CHECKIN` | Phase 1 schedule semantics |
| `SRC-059` | Kết thúc phiên | 1→2→6 | Six-Step Engine; Check-in | `P-STATE`, `P-CHECKIN` | `T-STATE`, `T-CHECKIN` | Review Yes first |
| `SRC-060` | Quy tắc câu hỏi chốt | 1→2→3 | Six-Step Engine and State Machine | `P-STATE`, `P-RECORDS` | `T-STATE`, `T-RECORDS` | Exact response binding |
| `SRC-061` | Coaching Session State Machine | 1→2→3 | Six-Step Engine and State Machine | `P-STATE`, `P-DATA` | `T-STATE`, `T-DATA` | Pause/resume semantics |
| `SRC-062` | UX Flows | 1→5 | Web UX | `P-UX` | `T-UX` | Phase 5 gate |
| `SRC-063` | Onboarding UX | 3→5 | Web UX | `P-UX`, `P-RECORDS` | `T-UX`, `T-RECORDS` | Consent/records |
| `SRC-064` | Home UX | 5 | Web UX | `P-UX` | `T-UX` | Dashboard E2E |
| `SRC-065` | Coaching Session UX | 2→4→5 | Web UX; Six-Step Engine | `P-UX`, `P-STATE`, `P-RECORDS` | `T-UX`, `T-STATE`, `T-RECORDS` | Typed API first |
| `SRC-066` | Scheduled Check-in UX | 6 | Check-in and Notifications | `P-CHECKIN` | `T-CHECKIN` | Permission/privacy |
| `SRC-067` | Voice UX | 1/7 Guard | Voice (deferred) | `P-GOV`, `P-PRODUCT` | `T-GOV` | No implementation/test path |
| `SRC-068` | Privacy Center UX | 3→5 | Privacy, Security and Egress | `P-PRIVACY`, `P-UX` | `T-PRIVACY`, `T-UX` | Phase 5 gate |
| `SRC-069` | Information Architecture | 5 | Web UX | `P-UX` | `T-UX` | Route/navigation tests |
| `SRC-070` | Technical Architecture | 1→3→4→5→6 | System Context; Repository Layout | `P-PRODUCT`, `P-RUNTIME`, `P-DATA`, `P-CHECKIN` | `T-GOV`, `T-RUNTIME` | Architecture boundary |
| `SRC-071` | Standalone web/shared engine | 1→4 | Existing Hermes Integration Boundary | `P-RUNTIME`, `P-PRODUCT` | `T-RUNTIME`, `T-GOV` | Narrow adapter |
| `SRC-072` | Coach Application Layer | 3→4 | Application Services and Confirmation | `P-API` | `T-API` | Service-only UI |
| `SRC-073` | Prompt and Cache Strategy | 1→2→4 | Prompt, Cache and Structured Output | `P-PROMPT`, `P-RUNTIME` | `T-PROMPT`, `T-RUNTIME` | Runtime capability |
| `SRC-074` | Structured Model Output | 1→2→3→4 | Prompt, Cache and Structured Output | `P-PROMPT`, `P-RECORDS` | `T-PROMPT`, `T-RECORDS` | Validate before sink |
| `SRC-075` | Question-only Validator | 1→2→4 | Prompt, Cache and Structured Output | `P-PROMPT` | `T-PROMPT` | Schema+semantic pass |
| `SRC-076` | Data Model | 1→3 | Domain Model | `P-DATA` | `T-DATA` | Canonical schema |
| `SRC-077` | coachee_profile | 3 | Domain Model | `P-DATA` | `T-DATA` | Schema test |
| `SRC-078` | career_snapshot | 3 | Domain Model | `P-DATA` | `T-DATA` | Append-only test |
| `SRC-079` | goal | 1→2→3 | Domain Model; Goal Validation | `P-DATA`, `P-GOAL` | `T-DATA`, `T-GOAL` | Abandoned semantics |
| `SRC-080` | commitment | 2→3 | Domain Model; Confirmation | `P-DATA`, `P-RECORDS` | `T-DATA`, `T-RECORDS` | Individual confirm |
| `SRC-081` | evidence | 3 | Domain Model | `P-DATA` | `T-DATA` | Schema/repository |
| `SRC-082` | check_in | 3→6 | Domain Model; Check-in | `P-DATA`, `P-CHECKIN` | `T-DATA`, `T-CHECKIN` | Scheduler consistency |
| `SRC-083` | coaching_session | 2→3 | Domain Model; Six-Step Engine | `P-DATA`, `P-STATE` | `T-DATA`, `T-STATE` | Restart recovery |
| `SRC-084` | insight | 2→3 | Domain Model; Confirmation | `P-DATA`, `P-RECORDS` | `T-DATA`, `T-RECORDS` | Individual confirm |
| `SRC-085` | memory_item | 2→3 | Domain Model; Privacy | `P-DATA`, `P-PRIVACY` | `T-DATA`, `T-PRIVACY` | Confirmed `expires_at = NULL`; manual-delete only |
| `SRC-086` | Memory Policy | 1→3→4→7 | Domain Model; Privacy | `P-DATA`, `P-PRIVACY`, `P-RUNTIME` | `T-DATA`, `T-PRIVACY`, `T-RUNTIME` | Confirmed memory durable; pending candidate 90d; Trash 30d |
| `SRC-087` | Safety | 1→2→7 | Safety Architecture | `P-SAFETY` | `T-SAFETY` | External review |
| `SRC-088` | Safety Role Boundaries | 1→2→7 | Safety Architecture | `P-SAFETY`, `P-POLICY` | `T-SAFETY`, `T-POLICY` | External review |
| `SRC-089` | Safety States | 1→2→7 | Safety Architecture | `P-SAFETY`, `P-STATE` | `T-SAFETY`, `T-STATE` | AC-57 external gate |
| `SRC-090` | Safety Prohibited Behaviors | 1→2→7 | Safety Architecture | `P-SAFETY`, `P-POLICY` | `T-SAFETY`, `T-POLICY` | Counterexamples |
| `SRC-091` | Privacy Controls | 1→3→5→7 | Privacy, Security and Egress | `P-PRIVACY`, `P-DATA` | `T-PRIVACY`, `T-DATA` | Privacy release gate |
| `SRC-092` | Non-functional Requirements | 1→2→3→4→5→6→7 | All architecture sections | `P-PRODUCT`, `P-POLICY`, `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-RECORDS`, `P-DATA`, `P-API`, `P-UX`, `P-CHECKIN`, `P-PRIVACY`, `P-SAFETY`, `P-PROMPT`, `P-RUNTIME`, `P-DEPLOY` | `T-GOV` plus matching 14 capability T bundles | Full release matrix |
| `SRC-093` | Evaluation Strategy | 1→2→3→7 | Evaluation and Verification | `P-POLICY`, `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-SAFETY`, `P-PROMPT`, `P-DATA`, `P-PRIVACY` | `T-POLICY`, `T-STATE`, `T-GOAL`, `T-OPTIONS`, `T-SAFETY`, `T-PROMPT`, `T-DATA`, `T-PRIVACY` | 50–100 scenarios |
| `SRC-094` | Acceptance Criteria | 1→2→3→4→5→6→7 | Evaluation and Verification | `P-POLICY`, `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-RECORDS`, `P-DATA`, `P-API`, `P-UX`, `P-CHECKIN`, `P-PRIVACY`, `P-SAFETY`, `P-PROMPT`, `P-RUNTIME`, `P-PRODUCT` | matching T bundles plus `T-GOV` | AC-01…58 |
| `SRC-095` | Success Metrics | 1→3→5→6→7 | Evaluation and Verification | `P-METRICS` | `T-METRICS` | No engagement scoring |
| `SRC-096` | Delivery Roadmap | 1→2→3→4→5→6→7 | Delivery and Deployment | Bundles by phase | Bundles by phase | No phase before gate |
| `SRC-097` | Roadmap Phase 0 | 1 | Evaluation and Verification; Delivery | `P-GOV`, `P-POLICY`, `P-PROMPT` | `T-GOV`, `T-POLICY`, `T-PROMPT` | Phase 1 exit |
| `SRC-098` | Roadmap Phase 1 | 2 | Six-Step Engine; Prompt | `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-POLICY`, `P-PROMPT` | `T-STATE`, `T-GOAL`, `T-OPTIONS`, `T-POLICY`, `T-PROMPT` | Phase 2 exit |
| `SRC-099` | Roadmap Phase 2 | 3 | Domain Model; Privacy | `P-DATA`, `P-PRIVACY`, `P-RECORDS` | `T-DATA`, `T-PRIVACY`, `T-RECORDS` | Phase 3 exit |
| `SRC-100` | Roadmap Phase 3 | 4→5 | Web UX | `P-UX`, `P-API` | `T-UX`, `T-API` | Runtime before UI |
| `SRC-101` | Roadmap Phase 4 | 6 | Check-in and Notifications | `P-CHECKIN` | `T-CHECKIN` | Phase 6 exit |
| `SRC-102` | Roadmap Phase 5 — Voice | 1/7 Guard | Voice (deferred) | `P-GOV`, `P-PRODUCT` | `T-GOV` | Reopen only by proposal |
| `SRC-103` | Roadmap Phase 6 — Hardening | 7 | Delivery and Deployment | `P-DEPLOY`, `P-PRIVACY`, `P-SAFETY` | `T-DEPLOY`, `T-PRIVACY`, `T-SAFETY` | Release gate |
| `SRC-104` | Architecture Decision | 1→4 | Overview; Integration Boundary | `P-GOV`, `P-PRODUCT`, `P-RUNTIME` | `T-GOV`, `T-RUNTIME` | No deep fork |
| `SRC-105` | Recommended Architecture | 1→4 | Overview; Integration Boundary | `P-PRODUCT`, `P-RUNTIME` | `T-GOV`, `T-RUNTIME` | Narrow adapter proof |
| `SRC-106` | Alternatives Considered | 1→4 | Existing Hermes Integration Boundary | `P-GOV` | `T-GOV` | Reject fork/general UI |
| `SRC-107` | Assumptions to Validate | 1→2→3→4→5→7 | Evaluation; Architecture Blockers | `P-STATE`, `P-POLICY`, `P-PROMPT`, `P-UX`, `P-RECORDS` | `T-STATE`, `T-POLICY`, `T-PROMPT`, `T-UX`, `T-RECORDS` | Evidence, not fact |
| `SRC-108` | Decision Log | 1/2/3/4/5/6/7 | Requirement Ownership; Blockers | `P-GOV`, `P-PRODUCT`, `P-RUNTIME`, `P-STATE`, `P-GOAL`, `P-POLICY`, `P-CHECKIN`, `P-PRIVACY`, `P-SAFETY` | `T-GOV`, `T-RUNTIME`, `T-STATE`, `T-GOAL`, `T-POLICY`, `T-CHECKIN`, `T-PRIVACY`, `T-SAFETY` | Immutable audit history |
| `SRC-109` | References | 1/7 | References; Integration Boundary | `P-GOV`, `P-RUNTIME` | `T-GOV`, existing regressions | Source currency |
| `SRC-110` | Next Steps | 1 | Delivery and Deployment | `P-GOV` | `T-GOV` | Plan before code |
| `SRC-111` | Unresolved Questions | 1→7 | Architecture Decision and Blocker Status | `P-GOV` | `T-GOV` | Product none; technical/external gates explicit |

## Bundle-to-Phase Ownership

| Bundle | Primary phase(s) | Concrete content location |
|---|---|---|
| `P-GOV` / `T-GOV` | 1, 7 | Phase 1 requirements/architecture contracts; Phase 7 evidence/status updates |
| `P-POLICY` / `T-POLICY` | 1, 2, 7 | Phase 1 rubrics; Phase 2 policy modules; Phase 7 provider eval |
| `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-PROMPT` and matching T | 1, 2, 4, 7 | Phase 1 contracts; Phase 2 engine; Phase 4 adapter; Phase 7 regressions |
| `P-RECORDS`, `P-DATA`, `P-PRIVACY` and matching T | 2, 3, 5, 7 | Phase 2 commands; Phase 3 DB/services; Phase 5 controls; Phase 7 recovery |
| `P-RUNTIME`, `P-API`, `P-PRODUCT`, `P-DEPLOY` and matching T | 1, 4, 5, 7 | Runtime spike; backend/package; app build; native Windows release |
| `P-UX` / `T-UX` | 5, 6, 7 | Standalone web features; check-in UI; full E2E |
| `P-CHECKIN` / `T-CHECKIN` | 3, 6, 7 | Canonical records; scheduler/delivery; restart/fault proof |
| `P-SAFETY` / `T-SAFETY` | 1, 2, 5, 7 | External policy gate; state/interruption; labeled UI; approved release evidence |
| `P-METRICS` / `T-METRICS` | 1, 3, 5, 6, 7 | Definitions; aggregation; display; check-in metrics; release audit |

## Change Rule

Every implementation PR must name the affected `SRC-*`, requirement family, architecture section, P/T bundle, phase step and AC; update code and proof together; and leave status `planned` until behavior exists and `verified` until its specified evidence passes. If a proposed code behavior changes a source requirement, stop and update/reapprove the canonical proposal first.
