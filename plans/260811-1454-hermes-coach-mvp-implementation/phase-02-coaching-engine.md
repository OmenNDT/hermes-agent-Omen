---
phase: 2
title: "Coaching Engine"
status: completed
effort: "2–2.5 weeks"
---

# Phase 2: Coaching Engine

## Objective

Implement the six-step engine and Coach behavior as pure, testable domain/application logic. The engine owns stage, revisions, gates, Goal validity, Options novelty, one-question output, candidate staging and basic safety transitions; it does not own SQLite, HTTP, React or provider details.

## Trace Scope

- Sources: `SRC-004…SRC-025`, `SRC-028`, `SRC-030…SRC-057`, `SRC-059…SRC-061`, `SRC-065`, `SRC-073…SRC-075`, `SRC-079`, `SRC-080`, `SRC-083…SRC-085`, `SRC-087…SRC-090`, `SRC-092…SRC-094`, `SRC-096`, `SRC-098`, `SRC-107`, `SRC-108`.
- Production: `P-POLICY`, `P-STATE`, `P-GOAL`, `P-OPTIONS`, `P-RECORDS`, `P-PROMPT`, basic `P-SAFETY`.
- Verification: `T-POLICY`, `T-STATE`, `T-GOAL`, `T-OPTIONS`, `T-RECORDS`, `T-PROMPT`, basic `T-SAFETY`.
- Acceptance: engine/policy portions of `AC-01`, `AC-02`, `AC-04…AC-51`, `AC-56`, `AC-57`; UI, persistence và scheduler portions remain in later phases.

`hermes_coach/requirements_map.yaml.phase_2` is the machine authority for this
scope. Its coverage test requires exact equality with every proposal source and
acceptance criterion allocated to implementation Phase 2. `SRC-058` is not in
this phase; only the UI-command boundary of `AC-50` is implemented here.

Numbering note: proposal roadmap “Phase 1 — Coaching Engine” is implementation
plan Phase 2 because implementation Phase 1 first established contracts and
evaluations. This is a sequencing offset, not a second coaching framework.

## Implemented Files and Content Placement

| Area | Files |
|---|---|
| Domain state | `hermes_coach/domain/session_state.py`, `transitions.py`, `models.py`, `enums.py` |
| Goal/Options | `hermes_coach/domain/goal_rules.py`, `options_rules.py` |
| Companion policy | `hermes_coach/policies/companion_policy.py`, `listening_policy.py`, `question_policy.py`, `feedback_policy.py` |
| Safety policy | `hermes_coach/policies/safety_policy.py`, `hermes_coach/application/safety_service.py` |
| Orchestration | `hermes_coach/application/coaching_service.py`, `record_confirmation_service.py` |
| Prompt contract | `hermes_coach/prompt/system_prompt.py`, `structured_context.py`, `output_schema.py`, `question_validator.py`, `regeneration.py` |
| Unit tests | `tests/hermes_coach/unit/test_{transitions,stage_completion,goal_rules,options_rules,companion_policy,listening_policy,question_policy,feedback_policy,safety_policy,record_confirmation,coaching_service,adversarial_guards}.py` |
| Contract/evals | `tests/hermes_coach/contract/test_output_schema.py`, `test_prompt_byte_stability.py`, eval scenarios/rubrics from Phase 1 |

Models in this phase are immutable DTOs or enums; Phase 3 supplies persistence models/repositories. `coaching_service.py` coordinates narrow services and must not become a policy god-file.

| Proposal content | Production destination | Exact content | Verification destination |
|---|---|---|---|
| Causal thesis, SMART/benefit-loss/ownership/influence (`SRC-004…008`, `030…039`) | `domain/goal_rules.py`, `domain/models.py`, `application/coaching_service.py`, `prompt/structured_context.py` | Independent Goal predicates, success evidence and hard Goal gate | `test_goal_rules.py`, `test_stage_completion.py`, Goal corpus |
| Companion stance, readiness, emotion, barriers, concern/influence, listening, acknowledgment and feedback (`SRC-009…025`, `028`, `073…075`) | `policies/*.py`, `prompt/system_prompt.py`, `prompt/question_validator.py` | Equal companion, capacity belief, hypothesis-only barriers, L1–L4 listening, one-question acknowledgment/feedback and prohibited coaching behavior | Policy unit tests, prompt contract tests, behavior corpus |
| Pre/G/R/O/W/Review and all explicit-Yes/rollback rules (`SRC-030…057`, `059…061`) | `domain/session_state.py`, `domain/transitions.py`, `domain/models.py`, `application/coaching_service.py` | Exact six-stage revision vector, append-only alternating turn ledger with exact content, strict adjacent Yes allowlist, downstream revision invalidation, stale inference rejection, arbitrary GROW rollback and sequential replay | `test_transitions.py`, `test_stage_completion.py`, `test_coaching_service.py`, adversarial tests, transition corpus |
| Options novelty, stuck recovery and decomposition (`SRC-040…050`) | `domain/options_rules.py`, `policies/question_policy.py` | Per-option linked baseline/candidate/provenance/confirmation, modifier/reorder/subset same-mechanism detection, canonical recovery/decomposition order, no solution supply | `test_options_rules.py`, Options corpus |
| Text coaching UX/application boundaries (`SRC-065`, `079`, `080`, `084`, `085`) | `application/coaching_service.py`, `application/record_confirmation_service.py`, `prompt/output_schema.py` | Backend-issued one-record UI intent bound to user/session/action/payload, no natural-language confirmation, one grounded validated question per output; process-local consume only and React/HTTP/durable CAS deferred | `test_record_confirmation.py`, `test_record_confirmation_service.py`, `test_prompt_contract.py`, `test_output_schema.py`, `test_regeneration.py` |
| Four safety states and no-advice/prohibited behavior (`SRC-087…090`, `092`) | `domain/enums.py`, `policies/safety_policy.py`, `application/safety_service.py` | Normal/sensitive/possible-crisis/urgent routing, normal-output interruption, signed attestation bound to issuer/evidence/guidance digest/version/validity, and fail-closed urgent release | `test_safety_policy.py`, safety corpus; external release gate remains pending |
| Evaluation, stable prompt and approved architectural boundary (`SRC-093`, `094`, `096`, `098`, `107`, `108`) | `prompt/system_prompt.py`, `prompt/structured_context.py`, `prompt/regeneration.py`, `requirements_map.yaml` | Byte-stable prompt, deterministic context, bounded fail-closed validation, pure engine with no Hermes-core fork | prompt contracts, `evals/pure_engine.py`, trace coverage test |

## State and Interface Contracts

### Six-step transition service

- `Pre-Coaching → Goal → Reality → Options → Will → Review`; no framework dispatcher and no forward skip.
- State includes `current_step`, revision and gate events. Gate classifier runs only for the response immediately following the closing-question message ID.
- Normalize only unqualified explicit agreement such as `Yes`, `Có`, `Đồng ý` to `yes`; conditional, contradictory or unclear replies remain non-yes.
- A step service may request rollback only with a concrete target in G/R/O/W. Rollback creates a new target revision and invalidates target/downstream gate events; replay begins at target.
- `No` is normal data, not failure. It preserves the current revision and asks what is unclear or unsuitable.

### Step completion predicates

| Step | Required before closing question and explicit Yes |
|---|---|
| Pre-Coaching | readiness, emotion when relevant, agreement, roles/responsibility and session boundary |
| Goal | ownership/fit/influence, benefit or loss, all SMART dimensions and success evidence |
| Reality | facts, present state, gap, emotion, barriers, resources and relevant prior attempts |
| Options | baseline captured and at least one Coachee-generated materially new option |
| Will | chosen action, start/due timing, completion evidence and commitment score `1–10` |
| Review | takeaway, immediate application, follow-up/check-in disposition and valid prior G/R/O/W gates |

### Question-only contract

- Stable prompt contains companion identity, belief in Coachee capacity, equal stance, six-step/gate rules, output contract and safety boundary.
- Output schema has one required non-null `question: string`, stage, candidate arrays, Goal statuses and safety signal; no `questions[]`.
- Validator rejects standalone statements, multiple questions, imperatives, disguised advice, judgment, diagnosis, authority claims and leading answers.
- Reflection/acknowledgment/feedback may use a factual declarative lead-in only inside the same question and must return interpretation to the Coachee.
- One turn has one focus. Funnel progression is open → 5W/1H → clarify → Yes/No within the same step, not four questions in one message.

### Stuck/novelty behavior

The order is recheck Goal/Reality, change angle/question, ask further, evoke memory, allow silence, decompose, then explore resources. Coach never supplies an option. Repeated wording/mechanism remains blocked; ambiguous difference is clarified by one question and Coachee ownership, not an evaluator assertion.

### Candidate and safety behavior

- Goal/insight/commitment/memory outputs are candidates only. Accept/edit/discard is one-record-at-a-time through an application command; natural-language chat cannot confirm them.
- `normal` follows six steps; `sensitive` asks permission; `possible_crisis` pauses coaching for a safety check; `urgent` targets interruption, emits labeled Safety System output and bypasses question-only only for externally approved direct guidance.
- Until the external Phase 1 safety gate is met, `urgent` content is fail-closed and cannot be released; no ordinary advice mode is added.

## Tests-first Work Order

1. Write table-driven transition/gate tests for every legal/illegal edge, every step Yes/No/unclear/conditional response and arbitrary rollback with sequential replay.
2. Write Goal predicate tests for each missing SMART dimension, borrowed goal, no benefit/loss, no influence and valid combinations.
3. Write Options baseline/duplicate/same-mechanism/ambiguous/new-mechanism tests and stuck-playbook ordering tests.
4. Write policy golden/counterexample tests for readiness, emotion, equal stance, capacity belief, barrier hypotheses, concern/influence, listening levels, acknowledgment, feedback and perspective change.
5. Write singular-schema and semantic-validator tests; then implement bounded regeneration reason codes without any output sink.
6. Write one-record candidate command tests and safety transition/interruption-intent tests.
7. Run all Phase 1 scenarios against the pure engine/fake runtime; classify failures by policy, transition, schema or evaluator instead of loosening gates.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Model/policy output appears compliant but is disguised advice | Two-layer validator, counterexamples and fail-closed regeneration |
| Novelty evaluator creates false confidence | Coachee articulates material difference; model score alone never opens gate |
| `coaching_service.py` becomes a god-file | Policies, predicates, transition and confirmation commands remain focused modules with table-driven interfaces |

## Exit Criteria

- [x] All six step gates require their predicate plus explicit Yes; No/unclear stays and rollback invalidates/replays correctly.
- [x] Goal never reaches Reality without complete SMART, value/loss, ownership/fit/influence.
- [x] Options never passes repeated/same-mechanism ideas and passes only a Coachee-owned material difference.
- [x] 100% accepted Coach outputs contain exactly one valid question; invalid output never reaches a display/persistence callback.
- [x] Companion, listening, acknowledgment and feedback scenarios meet the complete proposal rubric.
- [x] Candidate confirmation is per-record UI-command-only; no batch/natural-language path exists.
- [x] Safety states interrupt normal coaching correctly; urgent release remains blocked until approved content/detection evidence exists.

Evidence and residual findings: [Phase 2 verification report](./reports/phase-02-verification.md).
