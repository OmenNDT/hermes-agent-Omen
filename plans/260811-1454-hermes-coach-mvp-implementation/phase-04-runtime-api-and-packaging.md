---
phase: 4
title: "Runtime API and Packaging"
status: in-progress
effort: "1.5–2 weeks"
---

# Phase 4: Runtime API and Packaging

## Objective

Expose the validated Coach engine through a Coach-specific loopback FastAPI/JSON-RPC service and a narrow Hermes runtime adapter. The UI sees typed Coach DTOs only; it never sees `AIAgent`, Hermes message/tool shapes, unvalidated model text or the process-global TUI dispatcher.

## Trace Scope

- Sources: `SRC-001`, `SRC-026…SRC-029`, `SRC-070…SRC-075`, `SRC-086`, `SRC-092`, `SRC-096`, `SRC-100`, `SRC-104…SRC-109`.
- Production: `P-RUNTIME`, `P-API`, `P-PRODUCT`, prompt/egress parts of `P-PROMPT`, `P-PRIVACY`, startup parts of `P-DEPLOY`.
- Verification: `T-RUNTIME`, `T-API`, `T-GOV`, `T-PROMPT`, `T-PRIVACY`, startup parts of `T-DEPLOY`.
- Acceptance: `AC-03`, `AC-55`, `AC-56`, transport/runtime portions of `AC-01`, `AC-02`, `AC-33`, `AC-48`, `AC-57`.

## Planned Files

| Area | Files |
|---|---|
| Bootstrap/config | `hermes_coach/bootstrap.py`, `config.py`, `__main__.py`; `skills/hermes-coach/SKILL.md` as a versioned Coach-only prompt asset |
| Runtime | `hermes_coach/infrastructure/hermes_runtime_adapter.py`, optional generic adapter protocol in an existing edge module only after Phase 1 ADR approval |
| API | `hermes_coach/api/app.py`, `rpc.py`, `security.py`, focused Phase 3 route modules for onboarding, sessions, goals, commitments, privacy and metrics; Phase 6 owns check-in/notification routes without Phase 4 stubs |
| CLI/package | `hermes_cli/coach_cmd.py` plus minimal `hermes_cli/main.py` edge registration for `hermes coach`, `pyproject.toml` package discovery/data, lockfile only if dependencies change |
| Shared client | `apps/shared/src/coach-rpc-types.ts` only if types are framework-agnostic; otherwise `apps/hermes-coach/src/lib/coach-api.ts` in Phase 5 |
| Tests | `tests/hermes_coach/runtime/test_hermes_runtime_adapter.py`; contract tests for API/RPC/prompt/no-core-tool; loopback, Host/Origin/peer/token and Windows startup tests |

Do not name a Coach test directory `integration`, `e2e` or `docker`: the canonical runner drops those paths from discovery and from CI slice generation, so the tests disappear without failing. Phase 3 hit this and renamed to `persistence/`.

No Coach branch is added to `model_tools.py`, `toolsets.py`, global system prompt or `tui_gateway.server` method registry. Generic helper extraction must have a non-Coach contract test and remain byte-compatible for existing Hermes users.

### Progress

| Work-order step | State | Evidence |
|---|---|---|
| 1. Runtime, fake provider | done | `test_hermes_runtime_adapter.py` — no toolsets, no Hermes memory/context files/session id, post-construction tool list asserted empty and fail-closed if not; one agent per session with byte-stable prompt; prompt version/hash checked before any provider call; strict role alternation with no synthetic user turn on retry; bounded regeneration; schema and policy failures typed; provider text and secrets absent from errors; nothing reaches a sink before validation |
| 2. RPC contract snapshots and surface | done | `test_coach_app.py`, `test_rpc_mutations.py`, `test_rpc_envelope.py` — allowlist registry, echoed ids, stable error codes, internal detail never leaked; mutating commands carry session/revision/idempotency key, a stale view is refused, a retry replays its first result without reapplying, a refused or raising command moves neither revision nor memory. `test_rpc_methods.py` registers the surface — `coach.today`, `coach.session.start`, `coach.session.state`, `coach.turn` — with reads going through the shared active scope and `coach.turn` degrading to `provider_not_configured` when no provider is wired. `test_rpc_candidate_confirm.py` adds the two-step confirmation — mint an intent, then consume it — with no plural form at any layer |
| 3. Loopback WebSocket security | done | `test_loopback_security.py`, `test_coach_app.py`, `test_rpc_cancellation.py` — peer, Host, Origin and token checked independently and refused before the socket opens; guard refuses any non-loopback bind; rejection never quotes the token; requests dispatch concurrently so a cancel can arrive, cancellation targets one turn, and a disconnect cancels in-flight work leaving no task behind |
| 4. Persist-before-emit transactions | done | `test_coaching_turn.py`, `test_coach_turn_rpc.py` — consent checked before any model call, the provider call runs with no write lock held, transcript and candidates and the revision bump and the idempotency record all commit in one transaction, and the reply goes out only after it commits; a rejected turn, a withdrawn consent and a failed write each leave nothing behind |
| 5. `hermes coach` startup, packaging and profile lock | done | `test_bootstrap.py`, `test_launcher.py` — profile under the Hermes home but separate from its state, OS-level lock that a second process is refused and a crash releases, migrations and retention complete before the handshake, per-process token never written to disk, free-port selection, Windows Selector loop, and no LAN/login/voice flag. Packaging added to `packages.find` with `package-data` for migrations and the requirements map, verified by building a wheel (69 modules, 5 migrations, 1 yaml); `hermes coach` registered as a CLI subcommand with a lazy import. Verified by running both `python -m hermes_coach` and `hermes coach` for real and connecting to the port |
| 6. Existing Hermes regressions | done | [baseline report](./reports/phase-04-hermes-regression-baseline.md) — 799 Hermes test files run; every failure is a pre-existing Windows incompatibility, proven independent of the Coach work by disabling the one dependency added (identical counts) and by the absence of any reference between the two |
| 7. Skill snapshot | done | `test_skill_snapshot.py` — the prompt has one definition site and is an AST-verified literal, no Coach module touches skill machinery, no skill directory exists, the prompt forbids Research/Advice and declares a single framework, and the adapter sends only that constant with context files, memory and toolsets all off. Byte stability is not duplicated from `test_prompt_byte_stability.py`, and no hash literal is pinned |

| 8. Live Anthropic provider | done | `test_coach_provider.py` — Haiku over the Messages API, the system prompt carried in the `system` field so its cached prefix stays byte-identical across turns, no tools offered and an empty tool list reported, strict role alternation, bounded output, a missing credential reported at wiring time rather than mid-turn, and no credential in the agent's `repr`. It lives in `hermes_cli` because the architecture guard forbids Coach importing `agent.*`, and is injected through the adapter's existing `agent_factory` seam. Verified against the running backend: `coach.turn` returned one Haiku-generated Vietnamese question, opened at `pre_coaching` rather than jumping to Goal, on the first attempt, and the transcript row was committed before the reply went out |

| 9. Serving the built UI | done | `test_static_ui.py` — the page and its bundle come from the backend's own port, which is not a preference: the page reads `window.location.port` to find the socket, so a UI on a second port hands the browser the wrong one. Loopback peer, Host and Origin are checked exactly as the WebSocket checks them; the token is not, because a browser cannot attach one to the asset requests `index.html` triggers and the page carries no Coachee data. A traversal path outside the build is refused, an unknown path 404s rather than falling back to the page, and a backend with no build still serves RPC. Verified live: `GET /` 200 from a loopback origin and 403 from a foreign one, the WebSocket upgrade 101 and 403 the same way |

## Two Defects the Live Turn Found

Neither was reachable with a fake provider, which is why the run happened.

1. **The model was never shown the output contract.** `CoachOutput` sets
   `extra="forbid"` and names its field `coaching_stage`; Haiku, told only "output
   phải theo schema", answered `{"stage", "question", "rationale"}` — wrong field
   name plus a forbidden key. The contract is now stated on every turn, in the turn
   message rather than the system prompt, which is fingerprinted and must stay
   byte-stable.

2. **`RuntimeRejected` escaped `_turn` unmapped**, so every distinct provider
   outcome collapsed into one `internal_error` the UI could not act on. It now
   carries through as its own typed code and safe message.

A third problem made both of these far harder to find than they should have been:
the dispatcher discards internal detail so it cannot leak to the client, but it
was not writing that detail anywhere else either. An `internal_error` left no
trace in any log. The traceback now goes to a server-side logger the launcher
configures — uvicorn installs handlers only for its own loggers, so without that
step the log had no listener.

## Capability and Guard Findings

**Phase 1 capability gate: passed.** `AIAgent.__init__` in `run_agent.py` already
exposes `enabled_toolsets`, `ephemeral_system_prompt`, `skip_memory` and
`skip_context_files` as public parameters. The adapter needs no Coach branch in
Hermes core and no generic-seam ADR. Implementation may continue.

**Guard narrowed, 2026-08-22.** `test_phase_one_has_no_login_lan_server_or_dashboard_pty_surface`
forbade any `hermes_coach/` path containing `api`, `auth`, `login`, `pty`,
`server` or `web`, so the approved loopback API directory could not exist —
verified by creating it and watching the test fail, not predicted. `api`,
`server` and `web` left the list because the approved MVP *is* a loopback API
serving a web UI, so those terms never described an invariant. What the guard
exists for is unchanged and still enforced: no login/account model (`auth`,
`login`), no terminal surface (`pty`), and no non-loopback bind (`0.0.0.0`). The
test is renamed `test_has_no_login_lan_or_dashboard_pty_surface` to match what it
now checks. Decision taken under the standing instruction to keep a single-user
system as simple as possible.

## Runtime Adapter Contract

`CoachRuntimeAdapter.generate(request)` receives a stable prompt version, validated structured context, provider selection and turn text; it returns either an accepted Coach output DTO or a typed neutral error.

- Resolve configured provider through the existing public resolver and instantiate `AIAgent` behind the adapter.
- Explicitly set `enabled_toolsets=[]`, `skip_memory=True`, `skip_context_files=True`, no Hermes session DB and no tool-capable environment; assert the post-construction tool list is empty, including kanban/environment injection cases.
- Build the system prompt once per Coach session and prove byte equality on every turn and after restart; dynamic stage/goal/memory enters the current request context, never a new system history message.
- Reuse the existing skill-loading mechanism only for the bundled, versioned `hermes-coach` policy asset. Resolve/hash it before session creation and freeze it into the prompt version; disable arbitrary user/global skills and slash-message injection so no second framework, advice behavior or mid-session prompt mutation can enter Coach. The skill is derived from the proposal and cannot become a competing source of truth.
- Reuse Hermes session execution as one long-lived `AIAgent` per active Coach session while Coach SQLite remains durable truth. On restart, rebuild the same prompt/tool/skill snapshot and ordered history from Coach repositories so the provider sees a byte-identical cache prefix without introducing Hermes SessionDB as a second store.
- Preserve strict role alternation; do not inject synthetic users mid-loop. Regeneration is a new validated attempt tied to the same turn/usage record, not hidden history mutation.
- Buffer provider output. Parse `output_schema`, run question/policy/safety validator, then commit accepted session message/candidates and emit the RPC event in one application transaction boundary. Raw/rejected content is neither streamed nor persisted.
- A repeated validation/provider failure returns Product UI error code, retryability and correlation ID without leaking prompts, secrets or raw unsafe content.

If the existing runtime cannot provide a caller-owned stable prompt or portable structured result without conflicting Hermes identity, implementation stops at the Phase 1 gate. The only acceptable remedy is an approved generic runtime seam with cache/alternation regression coverage—not a Coach-specific core fork.

## API and Security Contract

- Coach service owns a separate FastAPI app and `/api/coach/ws` typed JSON-RPC endpoint. Reuse `@hermes/shared` client/URL patterns, not `/api/ws` TUI dispatch or `/api/pty`.
- Bind only `127.0.0.1`/`::1`; reject `0.0.0.0`, LAN and public host configuration. No login/account model exists.
- Use an ephemeral random token plus loopback peer, Host and Origin validation. CORS allows only actual loopback origins. Never place provider credentials in URL, Coach DB, logs or browser storage.
- On Windows use the proven Selector event-loop startup behavior. Startup handshake returns port/token/profile/schema status only after migrations and retention catch-up complete.
- RPC methods call application services and use versioned request/result DTOs, optimistic revision checks and idempotency keys for mutating commands. Cancellation targets one Coach session/turn.
- Egress consent guard runs immediately before adapter call. Declined/withdrawn consent yields local degraded UI data and performs no model request.

## Startup and Packaging Contract

`hermes coach` owns one backend process, an independent Coach profile under the Hermes home/profile convention, port selection and optional browser open. A per-profile lock prevents two writers. Dev mode may serve Vite separately; release mode serves only built Coach assets and Coach APIs, not dashboard admin APIs.

Package discovery includes `hermes_coach`; frontend assets are declared package data after Phase 5 build. The launcher reports unencrypted-storage disclosure before first profile initialization and never enables voice or LAN flags.

## Tests-first Work Order

1. Write runtime fake-provider tests for no tools/memory/context/session DB, stable prompt, role alternation, schema portability, bounded regeneration and no sink before validation.
2. Write RPC contract snapshots as behavior relations: IDs/revisions/idempotency/error semantics, not enum-count or version-literal change detectors.
3. Add real loopback WebSocket tests for token, Host, Origin, peer, CORS, cancellation, disconnect cleanup and non-loopback rejection.
4. Add transaction tests proving accepted output persists before event emission and rejected output reaches neither DB nor client.
5. Add `hermes coach` startup/profile-lock/migration/retention/port/Windows Selector tests under a temporary `HERMES_HOME`.
6. Run existing Hermes prompt-cache, message-sequence, serve/auth/WS and runtime regressions to prove the adapter/helper extraction changes no general behavior.
7. Add skill-snapshot tests proving the approved Coach skill is loaded once, hash-stable and incapable of enabling arbitrary skills, tools, Research/Advice or an alternate framework.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Runtime only exposes private/conflicting prompt seam | Phase 1 capability gate and approved generic seam ADR; no Coach core branch |
| Raw/rejected output leaks through streaming/logging | Buffer before schema/policy validation; sink spies and secret/raw-content scans |
| Separate server broadens attack surface | Coach-only app, loopback/token/Host/Origin/peer checks and no dashboard admin routes |

## Exit Criteria

- [x] Supported providers return one validated Coach DTO through the public adapter; unsupported capability fails closed. Both halves are now proven: fail-closed by test, and the provider half by a live Haiku turn through `hermes coach`.
- [x] No model tool, Hermes memory/context file/session DB or TUI dispatcher is reachable from Coach.
- [x] Prompt bytes and message alternation remain stable; rejected raw output is never displayed or persisted.
- [x] Typed RPC mutations are revision-safe/idempotent and cancellation is session-scoped. Cancellation is per turn, which is narrower than the criterion asks.
- [x] Server accepts only loopback with token/Host/Origin/peer checks and starts reliably on native Windows.
- [x] Package/launcher creates an independent Coach profile and contains no login, LAN, voice or dashboard admin surface.
