---
phase: 1
title: "Contract and Evaluation"
status: completed
effort: "1.5–2 weeks"
---

# Phase 1: Contract and Evaluation

## Objective

Turn the approved proposal into executable contracts before product code or large UI work. This phase resolves technical ambiguities without redefining product requirements and creates 50–100 versioned scenarios covering the complete six-step behavior, policy, privacy and safety surface.

## Trace Scope

- Primary: `SRC-000…SRC-061`, `SRC-070…SRC-075`, `SRC-087…SRC-094`, `SRC-096…SRC-111`.
- Bundles: all `P-*` are declared; first deliverables are `P-GOV`, contract portions of `P-POLICY`, `P-PROMPT`, `P-RUNTIME`, `P-SAFETY`; verification uses `T-GOV`, `T-POLICY`, `T-PROMPT`, `T-RUNTIME`, `T-SAFETY`.
- Acceptance baselines: fixtures cover `AC-01…AC-58`; later phases make them executable end to end.

## Planned Files

| File | Responsibility |
|---|---|
| `hermes_coach/requirements_map.yaml` | Machine-readable SRC/family/bundle/AC ownership; generated neither from headings nor code at runtime |
| `hermes_coach/contracts/runtime_contract.py` | Provider-neutral request/result and no-tool/stable-prompt invariants |
| `hermes_coach/contracts/egress_contract.py` | Egress category, purpose, provider/model, consent scope and disclosure DTOs |
| `hermes_coach/contracts/evaluation_contract.py` | Scenario/rubric result schemas and version fields |
| `tests/hermes_coach/contract/test_requirements_coverage.py` | Fail on missing/duplicate SRC, AC, P/T bundle or stale proposal fingerprint |
| `tests/hermes_coach/contract/test_architecture_boundaries.py` | Forbid Coach core tools, Hermes DB ownership, LAN/login, Research/Advice and voice paths |
| `tests/hermes_coach/contract/test_runtime_capability.py` | Spike exact prompt ownership, portable structured output, no tools and validation-before-sink |
| `tests/hermes_coach/evals/runner.py` | Deterministic scenario loader, provider harness and result report; no product state writes |
| `tests/hermes_coach/evals/rubrics/*.yaml` | Question-only, companion, stage, Goal, Options, safety and privacy rubrics |
| `tests/hermes_coach/evals/scenarios/*.yaml` | 50–100 positive, counterexample, rollback, ambiguity, request-for-advice and crisis scenarios |

Keep each implementation module focused and preferably below 200 lines; split scenario loaders, scoring and report formatting when necessary.

## Technical Semantics Accepted by Approving This Plan

1. **Pause/resume:** pause changes no gate and leaves `ended_at` empty; resume reconstructs `current_step` from session stage plus gate events and asks one readiness/current-step question. Early close sets `ended_at`, never synthesizes missing gates, candidates or commitments.
2. **Abandoned goal:** `draft`, `active` or `paused` may become `abandoned`; abandoned has no outgoing transition. Reuse creates a separately confirmed new draft linked in audit metadata, not silent reactivation.
3. **Options novelty:** baseline is the first distinct option set expressed in the current Options revision. Normalize exact wording, classify actor/causal mechanism/resource, reject exact or same-mechanism repeats, and ask the Coachee to articulate the material difference when ambiguous. A model similarity score alone never opens the gate.
4. **Check-in:** default cadence is 14 days and editable; browser notification is the only delivery channel. One neutral reminder may occur after 24 hours outside quiet hours, then the item is `missed`; startup/next-open presents one catch-up without a notification storm. Permission denial disables browser delivery, not in-app due items; cancel is the explicit opt-out.
5. **Egress:** manifest fields are category, item IDs, purpose, provider/model, required/optional, consent scope/version, provider-retention label/source/version and timestamp. First use or broader scope requires UI consent; optional categories are editable. Unknown provider retention is displayed as `unknown`, never inferred.
6. **Safety:** deterministic/user-triggered signals and model signals may escalate but never silently de-escalate. `urgent` interrupts the current session and cannot auto-resume; an explicit UI choice starts a new Pre-Coaching session. Exact thresholds and regional direct-support content remain externally reviewed release artifacts.
7. **Startup/backup:** one `hermes coach` owner starts the loopback backend, selects an available port, issues an ephemeral token and optionally opens the browser. Backup is an unencrypted ZIP with `manifest.json`, SQLite Backup API snapshot, attachments, schema version and checksums; restore validates into a temporary profile, runs migrations/retention, then atomically swaps after confirmation.
8. **Runtime output:** no raw token is streamed or persisted. The adapter obtains a complete structured response, parses schema, runs semantic/safety validation, regenerates with a bounded retry, and only then emits an accepted DTO. Repeated failure produces neutral Product UI error data.

### Resolved canonical memory rule

Confirmed `memory_item` persists until the Coachee manually deletes it. Its `expires_at` is nullable and always `NULL` in MVP; the retention service never purges confirmed memory by age. Pending candidate records of type `memory` remain temporary and purge after 90 days. A manually deleted memory uses the normal 30-day Trash lifecycle.

If exact caller-owned stable prompt and provider-portable structured output cannot be proven through public runtime APIs, Phase 1 produces a generic Hermes seam ADR and maintainer approval gate. It must not add Coach branching to `run_agent.py`, core tools or the global prompt.

## Tests-first Work Order

1. Add failing coverage tests for all 112 SRC rows, 58 AC rows and declared P/T bundles; make `requirements_map.yaml` satisfy them.
2. Add forbidden-boundary tests for core tools, `state.db`, direct `jobs.json`, dashboard PTY chat, LAN/login, voice and Research/Advice surfaces.
3. Define scenario schema and rubrics; seed at least 50 scenarios, including every proposal evaluation category and every blocked/edge transition.
4. Build a fake-provider harness and failing runtime contract tests: byte-stable prompt, `enabled_toolsets=[]`, no memory/context/session DB, singular `question`, no sink before validation, bounded regeneration and usage accounting.
5. Run a small matrix on each supported provider intended for MVP; record schema reliability and fail closed for unsupported capability.
6. Add decision fixtures for pause/resume, abandoned, novelty, check-in recovery, egress and safety. Update derived architecture/traceability only after plan approval and only if semantics do not alter product intent.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Derived architecture silently overrides proposal | Contract fingerprint plus SRC/AC/bundle join; product changes return to proposal |
| Evals overfit examples | Separate golden/counterexample/holdout sets and require human review of sampled outputs |
| Provider capability differs | Capability matrix and fail-closed adapter gate; no prompt-only JSON assumption |

## External Validation Gates

- A qualified human reviews safety detection examples, escalation thresholds, Vietnamese/regional support resources, expiry metadata and resume wording. No placeholder hotline is allowed.
- Provider retention labels require current authoritative provider documentation. Missing facts remain `unknown`.
- User approval of this plan is required before any file listed above is implemented.

## Exit Criteria

- [x] `requirements_map.yaml` contract proves exactly 112 unique SRC IDs, `AC-01…AC-58`, all families and all P/T bundles.
- [x] 50–100 versioned scenarios load and produce reproducible rubric reports.
- [x] Runtime spike proves or explicitly gates stable prompt, no tools, structured output and validation-before-display/persistence.
- [x] Technical semantics above have executable fixtures and do not contradict proposal text.
- [x] Safety/provider external gates have named owner, evidence format and expiry; unresolved evidence blocks only affected implementation/release.
- [x] No Coach production UI, voice path, deep fork or unapproved product behavior is introduced.
