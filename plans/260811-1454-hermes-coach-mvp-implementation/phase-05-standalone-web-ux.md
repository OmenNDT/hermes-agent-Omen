---
phase: 5
title: "Standalone Web UX"
status: in-progress
effort: "2–2.5 weeks"
---

# Phase 5: Standalone Web UX

## Objective

Build a branded, responsive Coach React app for onboarding, the six-step text session, individual record confirmation, goals/journey/insights, dashboard and Privacy Center. It is a standalone product surface using typed Coach RPC; it does not embed or recreate the Hermes dashboard PTY/TUI chat.

## Trace Scope

- Sources: `SRC-010`, `SRC-011`, `SRC-026…SRC-030`, `SRC-034…SRC-040`, `SRC-054…SRC-059`, `SRC-062…SRC-069` except deferred `SRC-067`, `SRC-092`, `SRC-094`, `SRC-095`, `SRC-100`, `SRC-102`, `SRC-108`.
- Production: `P-UX`, browser part of `P-API`, `P-PRODUCT`, `P-RECORDS`, `P-PRIVACY`, `P-METRICS`; `P-GOV` enforces the no-voice boundary.
- Verification: `T-UX`, browser portions of `T-API`, `T-RECORDS`, `T-PRIVACY`, `T-METRICS`, `T-GOV`.
- Acceptance: `AC-01…AC-03`, UI portions of `AC-08`, `AC-24`, `AC-33`, `AC-42`, `AC-49`, `AC-54`, `AC-55`, `AC-57`, `AC-58`.

## Planned Files

| Area | Files |
|---|---|
| App shell | `apps/hermes-coach/package.json`, Vite/TypeScript/Vitest/Tailwind configs, `src/main.tsx`, `src/app/shell.tsx`, `src/app/routes.tsx` |
| Shared state/client | focused nanostores under `src/store/session.ts`, `profile.ts`, `notifications.ts`; `src/lib/coach-api.ts`, `src/lib/format.ts` |
| Features | `src/features/onboarding/`, `today/`, `coach/`, `goals/`, `journey/`, `insights/`, `settings/`, `check-ins/`, `privacy/`; each with a thin `index.tsx` and colocated components/actions/tests |
| Coach session | stage rail, transcript, one-question composer, gate status, rollback/revision indicator, pause/stop controls and `record-confirmation.tsx` |
| Design/accessibility | reuse `@nous-research/ui` primitives and tokens; app-specific responsive layout and visible focus/keyboard semantics |
| Tests | colocated `*.test.tsx`; `tests/hermes_coach/e2e/test_onboarding.py`, `test_dashboard.py`, `test_privacy_center.py`, `test_six_step_text.py` |

Do not create a monolithic page/controller/hook. Shared render state uses feature-owned nanostores; pure side effects live in action modules. No path contains voice, microphone, audio, STT or TTS implementation.

### Progress

| Work-order step | State | Evidence |
|---|---|---|
| 1. Shell, routes, store, client, fake RPC | done | `coach-api.test.ts`, `session.test.ts`, `shell.test.tsx` — 49 tests. Client builds the loopback URL, keeps the token out of every message body, routes concurrent replies by id, attaches session/revision/idempotency to mutations only, reuses the key on retry, and fails pending calls when the socket drops. Store is server-authoritative with no local gate advance. Shell has landmarks, skip link, `aria-current` and a stated degraded mode |
| 2. Onboarding | mostly done | `onboarding.test.tsx`, `connection.test.ts`, `test_rpc_consent.py` — 36 frontend tests plus the consent RPC. Agreement states the equal-companion stance, capacity belief, not-advice/not-therapy and the six steps; the disclosure is a hard gate before any consent control exists; each consent is its own pair of buttons with its own control id, reachable by keyboard, and the UI shows the decision the *server* settled on. Declining egress completes onboarding and says what still works. Per-record confirmation is built: one card per candidate with save/edit/discard, no control that resolves more than one, an edit that survives a refusal, and a refusal reported on its own card. The records step is wired to the live RPC and asks about the first coaching goal only once nothing is left undecided. Only the career-snapshot question flow is missing, and it needs a configured provider |
| 3. Session | not started | |
| 4. Dashboard/goals/journey/insights | not started | |
| 5. Privacy Center | not started | |
| 6. Keyboard/a11y and Playwright E2E | not started | |
| 7. Typecheck, lint, build, no-voice scan | done | `npm run typecheck`, `lint`, `test` and `build` all pass. ESLint follows `web/`'s config plus three product rules — browser storage, `navigator.mediaDevices` and speech constructors are all errors — each verified to fire against a deliberately offending file. The no-voice scan also covers the app from the Python side |

### Consent is collected against the real backend

```text
1. disclosure tu backend -> Dữ liệu Coach lưu trên máy này và không được mã ...
2. local_storage confirm -> {"decision":"granted","granted":true}
3. model_egress decline  -> {"decision":"declined","granted":false}
4. egress state          -> {"granted":false,"decision":"declined","events":1}
```

The disclosure text is fetched from the backend rather than duplicated in the
browser, so the launcher and the page cannot drift into telling the Coachee
different things. The decision the UI displays is the one the server returned,
not the button that was clicked.

### Lint carries product rules, not just style

`eslint.config.js` extends the same config `web/` uses, then adds three rules
that encode plan invariants a reviewer would otherwise have to catch by eye:

- `localStorage`/`sessionStorage` are errors — Coach records live in
  server-side SQLite, and browser storage is for ephemeral UI preferences only.
  Test files opt out, because they reach for storage precisely to prove the app
  never writes to it.
- `navigator.mediaDevices` and `new MediaRecorder`/`new SpeechRecognition` are
  errors — the no-voice boundary, enforced where the code is written rather than
  only in a path scan afterwards.

Each was verified by linting a file that deliberately violates it and watching
both rules fire.

Two real findings came out of turning lint on, neither cosmetic. `routes.tsx`
mixed a component factory with the route data, which breaks fast refresh; the
factory moved to `placeholder.tsx` and the table became `routes.ts`, which is
what a module with no JSX should have been. And `OnboardingRoute` called
`setState` synchronously inside an effect for the not-connected case; that is
knowable during the first render, so it moved into a lazy `useState` initialiser
and costs one render pass instead of two.

### Confirming records, against the real backend

```text
1. candidates cho xac nhan -> goal, insight, memory
2. accept c0 (goal)        -> OK
3. edit   c1 (insight)     -> OK
4. discard c2 (memory)     -> OK
5. con lai                 -> 0
6. coach.today goals       -> ["Chuyển vai trò"]
7. insight moi nhat        -> Tôi né xung đột khi mệt
```

Three different actions, three correct outcomes: accept creates the record,
edit stores the *edited* text, discard creates nothing. The list empties as each
is resolved.

Wired into onboarding's records step and re-verified through the route's own
path: a pending memory candidate, edited on confirmation, lands as
`user_confirmed=1` with `expires_at=NULL` and its provenance recorded, and the
candidate list empties.

After each resolution the route re-reads session state rather than removing the
card locally. The server decides a candidate is resolved; a local guess could
disagree with it.

Confirmation is two round trips by design. The intent binds the exact action and
the exact edited text, so it cannot be minted when the card renders — only when
the Coachee commits. `resolve-candidate.ts` is the only place that pairing
lives, and its tests assert that both calls carry the same action and the same
value, since a mismatch is what the server refuses.

### Stack decisions

Follows the `web/` workspace conventions rather than inventing any: React 19,
Vite 8, Vitest 4, TypeScript 6, npm workspaces under `apps/*`. `@nous-research/ui`,
`nanostores` and `@testing-library/react` were already in the tree.

Two deviations from the planned file list, both toward less machinery:

- **No MSW.** It intercepts HTTP; the Coach transport is a WebSocket carrying
  JSON-RPC. `src/lib/fake-rpc.ts` is an in-process fake socket instead — simpler
  and closer to the thing under test. It replies on a microtask, so a client
  that assumed a synchronous answer would pass against it and deadlock against
  the real server.
- **No router dependency.** Eight destinations, one local user, no deep links or
  SEO. `routes.tsx` is a data table with hash routing, so a test can assert what
  routes exist — and that none is a terminal, tool palette or voice surface —
  without rendering.

### Verified against the running backend

The unit tests prove the client builds a given envelope; they cannot prove the
server accepts it. Driving `CoachApi` itself against a live `python -m
hermes_coach`:

```text
CONNECT: CoachApi's own URL passed the real loopback guard
ERROR routed: true unknown_method | no such method: coach.today
```

With the RPC surface now registered, the same client drives a real flow against
a live backend:

```text
1. connect            -> OK
2. coach.today        -> {"goals":0,"encrypted":false}
3. session.start      -> {"session_id":"session-1","stage":"pre_coaching"}
4. session.state      -> {"stage":"pre_coaching","revision":1,"steps":[]}
5. coach.turn         -> provider_not_configured
```

Read, mutate, and a mutation moving the revision from 0 to 1 that the next read
reflects. Step 5 is the correct answer on a machine with no provider wired: a
typed reason the UI can act on, not a crash and not `unknown_method`.

Record confirmation closes the loop, again against a live backend:

```text
1. mint intent   -> hmaPhwNvtn...
2. confirm       -> {"official_record_type":"goal","official_record_id":"ef92ca6f-…"}
3. replay intent -> confirmation_rejected
4. coach.today   -> [{"title":"Chuyển vai trò","status":"active"}]
```

A candidate becomes an official goal that Home then shows, and the spent intent
is refused. Confirmation is registered without the RPC mutating envelope on
purpose: `DurableConfirmationService` already binds a single-use intent to
user/session/candidate/action/payload, guards the command id, and
compare-and-sets the candidate row, all in one transaction. Wrapping it would
nest a second transaction and layer a weaker replay check over a stronger one.

## UX Flow Contracts

### First run and onboarding

1. Explain the equal companion role, capacity belief, coaching/not-advice/not-therapy boundaries, responsibilities and six-step agreement.
2. Show the explicit unencrypted local/backup disclosure. Collect local-storage and model-egress consent only through `Xác nhận`/`Từ chối`; expose `Rút consent` later.
3. Ask one conversational question at a time for career snapshot, values, strengths, constraints and 1–3-year vision; never jump to Goal while readiness/emotion is unresolved.
4. Configure challenge level, editable 14-day check-in default, quiet hours and baseline self-ratings.
5. Present each candidate profile/value/goal record separately for edit/accept/discard. End by asking whether to create the first coaching goal.

### Session

- Display one accepted Coach question per turn and one composer. Product UI labels, errors, disclosures and cards are visibly distinct from Coach/Safety System voices.
- Persist/show `current_step`, revision and six gate states. Step advancement is rendered only after server-confirmed Yes event; No/unclear remains at the step. Rollback shows invalidated downstream gates and sequential replay.
- Provide pause, stop and “question useful” controls without fabricating a response or gate. Stop can close early without commitment.
- Candidate cards appear individually when suitable; each has edit, accept and discard. Review may reopen one record at a time; no “confirm all” control or implicit chat confirmation exists.
- `urgent` immediately replaces normal coaching controls with a clearly labeled Safety System surface; only externally approved content is rendered and normal six-step actions are disabled.

### Home and information architecture

Home answers: destination, commitments, today’s attention and learning. It shows active goal, next commitment, due check-in, career pulse and recent confirmed insight plus “Bắt đầu phiên coaching”. Goals, Journey, Insights and Settings/Privacy use confirmed active records only. Metrics are self-reflection/product quality indicators, never human-worth scoring, streak pressure or engagement optimization.

### Privacy Center

- Show/edit effective consent and provide withdrawal controls.
- Show data by category with provenance/`last_used_at`, export JSON/Markdown and individual/session/goal/all-data soft-delete actions.
- Show Trash entries with purge date, per-item restore and separately confirmed permanent purge/purge-all.
- Repeat exact no-at-rest-encryption and old-backup caveats. Provider retention displays authoritative label/source/version or `unknown`.
- Never expose provider API keys, raw rejected outputs or full egress payloads.

## Interaction and Accessibility Requirements

- All core flows are keyboard operable with logical focus, focus restoration after dialogs, semantic headings/landmarks, labeled controls and non-color-only state.
- Responsive layouts support practical desktop and narrow browser widths; no mouse-only drag gate.
- Errors preserve draft input and offer neutral retry. Offline/provider-declined mode keeps local dashboard/privacy/data functions available and clearly marks coaching generation unavailable.
- Browser storage contains only ephemeral UI preferences/session token; Coach records stay server-side SQLite.

## Tests-first Work Order

1. Add route/shell/store/client contract tests and MSW/fake RPC fixtures before components.
2. Implement onboarding tests for agreement, emotion/readiness, consent buttons, disclosure, one-question progression and individual record confirmation.
3. Implement session tests for stage/gates, Yes/No/unclear, rollback/replay, pause/stop, candidate timing and Product UI vs Coach voice.
4. Implement dashboard/goals/journey/insights tests using confirmed/Trash/expired fixtures and metric definition assertions.
5. Implement Privacy Center tests for consent withdrawal, export, soft delete, restore, permanent purge confirmation, no-encryption disclosure and provider-retention unknown state.
6. Add keyboard/focus/accessibility tests and Playwright E2E against the real loopback API/temp profile.
7. Run typecheck, lint, unit tests, build and the no-voice architecture boundary scan.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Client state advances ahead of server gate/revision | Server-authoritative DTOs and optimistic revision rejection; never compute gate locally |
| Standalone UX drifts into a second general Hermes chat | Coach RPC/types only; no PTY, tool activity, slash palette or general transcript reuse |
| Accessibility regresses under custom session UI | Keyboard/focus/a11y tests in each feature plus E2E core-flow audit |

## Exit Criteria

- [ ] Onboarding and the complete six-step text flow are usable with keyboard and one question per turn.
- [ ] UI never advances a gate locally, never batch-confirms records and visibly distinguishes Coach, Product UI and Safety System.
- [ ] Dashboard reflects active confirmed goal, commitment, evidence and insight while excluding Trash/expired/unconfirmed data.
- [ ] Privacy Center supports disclosure, consent/withdrawal, view/edit/export, Trash/restore and separately confirmed permanent purge.
- [ ] Local functions degrade safely without provider/egress consent; secrets/raw rejected output never reach browser persistence.
- [ ] App is independent of dashboard PTY/TUI and ships no voice-related surface or permission.
