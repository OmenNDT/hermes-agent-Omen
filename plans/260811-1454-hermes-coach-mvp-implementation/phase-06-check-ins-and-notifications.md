---
phase: 6
title: "Check-ins and Notifications"
status: pending
effort: "1–1.5 weeks"
---

# Phase 6: Check-ins and Notifications

## Objective

Implement proactive but non-coercive commitment check-ins, browser notifications, quiet hours, snooze and missed recovery. Scheduling goes through an adapter/service and confirmed Coach records remain authoritative; no code writes Hermes `cron/jobs.json` directly.

## Trace Scope

- Sources: `SRC-058`, `SRC-059`, `SRC-066`, check-in fields in `SRC-082`, `SRC-092`, `SRC-094`, `SRC-095`, `SRC-101`, `SRC-108`.
- Production: `P-CHECKIN`, check-in parts of `P-RECORDS`, `P-DATA`, `P-API`, `P-UX`, `P-METRICS`, `P-PRIVACY`.
- Verification: `T-CHECKIN`, relevant `T-RECORDS`, `T-DATA`, `T-API`, `T-UX`, `T-METRICS`, `T-PRIVACY`.
- Acceptance: `AC-50…AC-52`, follow-up/notification portions of `AC-51`, `AC-54`, `AC-58`.

## Planned Files

| Area | Files |
|---|---|
| Service | `hermes_coach/application/check_in_service.py`, focused schedule/delivery DTOs under `domain/` |
| Adapter | `hermes_coach/infrastructure/scheduler_adapter.py` using an existing scheduler service/API, never direct store writes |
| API | `hermes_coach/api/routes/check_ins.py`, `notifications.py` |
| Web | `apps/hermes-coach/src/features/check-ins/`, `src/store/notifications.ts`, `src/service-worker.ts` |
| Tests | `tests/hermes_coach/unit/test_check_in_service.py`; integration scheduler tests; E2E check-in and notification-privacy tests; colocated React/service-worker tests |

## Scheduling Semantics Accepted by Plan Approval

- Onboarding proposes 14 days as an editable default. Each confirmed commitment may override schedule, snooze, reschedule or cancel without changing the commitment text implicitly.
- Browser notification is the only MVP delivery channel. Permission is requested contextually, never on initial page load; denial leaves in-app due check-ins working.
- Delivery requires the Coach backend and a browser/service-worker environment that supports notifications. If unavailable or closed, no false guarantee is shown; startup/next-open runs catch-up.
- Phase 1/6 must capability-test foreground, hidden-tab, installed-PWA/background and fully closed-browser states on the target Windows browser. Only proven states are promised in UI; fully closed-browser delivery is not a release claim unless the chosen browser proves it without a cloud push service.
- Quiet hours use the Coachee timezone. A due event inside quiet hours moves to the next allowed instant and records the reason.
- A due check-in may receive one neutral reminder 24 hours later outside quiet hours. After that it becomes `missed`; it does not create repeated jobs, guilt copy, streak loss or escalation pressure.
- Catch-up collapses missed events into one oldest-actionable in-app prompt and schedules the next valid occurrence; it never emits a startup notification storm.
- Cancel is explicit opt-out for that check-in/cadence. Notification permission and coaching/model consent are separate scopes.

## Check-in Conversation Contract

The check-in asks one question per turn about progress/status, supporting/blocking factors, continuing relevance, learning and next choice. The Coachee may keep, edit, reschedule or cancel. Any modified commitment is a new candidate requiring individual confirmation; a check-in response never mutates goal/commitment automatically.

Notification title/body is neutral and contains no goal, career, emotion, blocker or other sensitive content on lock screens. Opening the notification resolves only a local deep link; the server rechecks consent, active status, Trash and expiry before showing details.

## Consistency and Recovery Contract

- Coach SQLite stores canonical check-in state and an adapter job ID/version. Scheduler commands carry idempotency keys.
- Create/update/cancel uses an outbox-style reconciliation record: commit domain intent, call scheduler adapter, then mark synchronized. Startup retries unsynchronized operations idempotently.
- Scheduler callbacks re-read the active commitment/check-in; canceled, completed, Trash, expired or withdrawn-scope records produce no notification.
- Duplicate callbacks are harmless. Completion/cancel and delivery race under a transaction/revision check; stale callback loses.
- Scheduler shutdown is deterministic and profile-scoped. Tests exercise restart, clock/timezone/DST boundaries and native Windows lock behavior where available.

## Tests-first Work Order

1. Add table-driven service tests for default/override cadence, keep/edit/reschedule/cancel, snooze, one reminder, missed state and catch-up collapse.
2. Add timezone/quiet-hour/DST tests with an injected clock and no wall-clock sleeps.
3. Add scheduler adapter contract tests for create/update/cancel/reconcile, idempotency, duplicate callback, partial failure and restart recovery using a temporary Hermes profile.
4. Add privacy tests proving Trash/expired/unconfirmed/withdrawn/canceled items produce no job or notification and notification copy contains no sensitive fixture tokens.
5. Add browser permission/service-worker/deep-link tests for granted, denied, unsupported and browser-closed/degraded states.
6. Add E2E from Review-confirmed follow-up through due notification/open/check-in/record edit and next schedule.
7. Run existing scheduler lifecycle/claim/shutdown/cross-process regressions; do not weaken platform-specific skips without native replacement coverage.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Browser background capability is overpromised | State-by-state Windows browser spike, truthful UI limitation and startup catch-up |
| SQLite and scheduler diverge after crash | Idempotent outbox reconciliation and stale callback revision checks |
| Lock-screen copy leaks sensitive coaching context | Neutral fixed templates plus fixture-token scans and eligibility recheck on open |

## Exit Criteria

- [ ] Confirmed follow-up creates one idempotent schedule through the adapter and survives restart.
- [ ] Keep/edit/reschedule/cancel/snooze/missed/catch-up semantics match this phase and require individual confirmation for record changes.
- [ ] Permission and quiet hours are respected; unsupported/closed environments state limitations and recover on next open.
- [ ] Notification copy is neutral and contains no sensitive coaching content, guilt or streak language.
- [ ] Canceled, Trash, expired, unconfirmed or withdrawn-scope data cannot trigger a check-in or notification.
- [ ] No direct read/write of `cron/jobs.json` exists in Coach code.
