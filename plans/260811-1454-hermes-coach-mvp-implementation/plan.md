---
title: "Hermes Coach MVP Implementation"
description: "Tests-first delivery plan for the approved local-first Hermes Coach web product"
status: in-progress
priority: P1
branch: "main"
tags: [hermes-coach, webapp, local-first, grow, windows]
blockedBy: []
blocks: []
created: "2026-08-11T07:54:59.077Z"
createdBy: "ck:plan"
source: skill
---

# Hermes Coach MVP Implementation

## Outcome and Authority

Deliver a single-user, loopback-only Windows webapp that follows only Pre-Coaching → Goal → Reality → Options → Will → Review and reuses Hermes through a narrow runtime adapter. Scope is **HOLD**: implement the approved proposal without adding voice, Research/Advice mode, multi-user auth, LAN access, billing or a deep Hermes fork.

The canonical authority is [the approved proposal](../../docs/hermes-coach-product-proposal.md). Architecture and traceability are derived aids. Every implementation change must use [the source-to-phase map](./proposal-implementation-map.md) and answer the canonical change checklist. Plan approval authorizes implementation; this draft does not.

## Non-negotiable Invariants

- Exactly one Coach question per turn; statements are allowed only as grounded lead-ins inside that question.
- Every Pre/G/R/O/W/Review step needs an explicit `Yes`; rollback may target G/R/O/W, invalidates downstream gates, then replays sequentially.
- Goal needs SMART + benefit/loss + ownership/fit/influence; Options needs a Coachee-generated materially new solution.
- UI actions are the only evidence for consent and candidate confirmation; records are confirmed individually, never in a batch.
- Coach SQLite is the structured truth; Hermes session DB, file memory and tool palette are not Coach stores.
- System prompt is byte-stable; dynamic state is structured context; output is validated before display or persistence.
- Retention is 90 days for temporary data, Trash is 30 days, durable domain records persist until manual delete; no API key enters Coach DB.
- MVP data/backup is not encrypted at rest and the UI discloses this; server is loopback/no-login/no-LAN.
- Voice/STT/TTS has no package, route, permission, schema, feature directory or dedicated test path.

## Phases

| Phase | Name | Status | Progress | Exit gate |
|---|---|---|---:|---|
| 1 | [Contract and Evaluation](./phase-01-contract-and-evaluation.md) | completed | 6/6 | 50–100 scenarios, runtime/decision contracts and source coverage pass |
| 2 | [Coaching Engine](./phase-02-coaching-engine.md) | completed | 7/7 | Pure six-step/policy/prompt/confirmation tests pass |
| 3 | [Local Data and Privacy](./phase-03-local-data-and-privacy.md) | completed | 7/7 | Real-SQLite migration, retention, Trash, consent and provenance tests pass |
| 4 | [Runtime API and Packaging](./phase-04-runtime-api-and-packaging.md) | in-progress | 5/6 | Validated no-tool runtime works through loopback typed API on Windows |
| 5 | [Standalone Web UX](./phase-05-standalone-web-ux.md) | in-progress | 0/6 | Keyboard-accessible onboarding/session/dashboard/privacy E2E passes |
| 6 | [Check-ins and Notifications](./phase-06-check-ins-and-notifications.md) | pending | 0/6 | Scheduler adapter, quiet hours, snooze/missed recovery and privacy pass |
| 7 | [Hardening and Release](./phase-07-hardening-and-release.md) | pending | 0/7 | AC-01…AC-58, 112-source coverage, recovery and release gates pass |

Phase verification reports: [Phase 1](./reports/phase-01-verification.md), [Phase 2](./reports/phase-02-verification.md), [Phase 3](./reports/phase-03-verification.md).

## Open Follow-ups

- Resolved 2026-08-22: the `OptionTurnEvidence` protocol-variance diagnostics are gone. `OptionTurnEvidence` now declares read-only properties, `TurnActor` is a named alias reused by test helpers, and `ty` reports no diagnostics.
- Resolved 2026-08-22: Phase 3 tests were being silently skipped. `scripts/run_tests_parallel.py` sets `_SKIP_PARTS = {"integration", "e2e", "docker"}` and drops any path containing one of those components, so `tests/hermes_coach/integration/` reported 303 tests instead of 382 and was omitted from every CI slice by `--generate-slices`. The directory is now `tests/hermes_coach/persistence/`, which the filter does not match; these tests need no external service, only real SQLite under `tmp_path`. No flag and no runner change.
- Upstream divergence, all deliberate and each verified not to change Hermes behavior (see the [regression baseline](./reports/phase-04-hermes-regression-baseline.md)):
  - `pyproject.toml` — `pytest-cov==7.1.0` in the `dev` extra; `hermes_coach`/`hermes_coach.*` in `packages.find`; `package-data` for the `.sql` migrations and `requirements_map.yaml`, without which a wheel installs the code and dies on the first database open.
  - `uv.lock` — 119 lines. On rebase re-run `uv lock`; never hand-merge it.
  - `hermes_cli/main.py` — two lines registering the `coach` subcommand, at two independent points. `hermes_cli/subcommands/coach.py` is new and imports the launcher lazily.
  - `scripts/run_tests.sh` — Windows venv probe, `PYTHONUTF8=1`, and a Windows-only `PLATFORM_ENV` block so `env -i` stops stripping `USERPROFILE`/`LOCALAPPDATA`/`TEMP`. All three are strict improvements and no-ops on Linux, so this is the divergence most worth pushing upstream rather than carrying.
- Resolved 2026-08-24: `scripts/run_tests.sh` now works on Windows. Three changes, all no-ops on Linux: the venv probe accepts `Scripts/python.exe` as well as `bin/python`; `PYTHONUTF8=1` joins the environment, being the only encoding variable Python honours on Windows; and a Windows-only `PLATFORM_ENV` block keeps `USERPROFILE`/`LOCALAPPDATA`/`TEMP` and friends, which `env -i` had stripped — without them `Path.expanduser()` raises and ~110 tests fail spuriously. Verified against the ad-hoc baseline: 53 failures either way. See the [regression baseline](./reports/phase-04-hermes-regression-baseline.md).
- Resolved 2026-08-22: the Phase 1 path guard no longer blocks the approved API directory. `api`, `server` and `web` left its forbidden list because the MVP is a loopback API serving a web UI; `auth`, `login`, `pty` and the `0.0.0.0` content check stay. The test is now `test_has_no_login_lan_or_dashboard_pty_surface`.
- The Phase 3 source scope in this plan's prose (`SRC-011`, `SRC-026`, `SRC-036`, `SRC-054…059`, `SRC-063`, `SRC-068`, `SRC-076…086`, `SRC-091`, `SRC-092`, `SRC-099`, `SRC-108`) is narrower than the machine allocation in `requirements_map.yaml`, which assigns 36 sources to phase 3 — it also includes `SRC-028`, `060`, `061`, `070`, `072`, `074`, `093…096`, `107`. The map is the authority and the coverage test enforces it; treat the prose list as an incomplete summary until it is reconciled.

## Dependencies and Sequencing

Phase 1 precedes production code. Phase 2 precedes 3; the canonical memory rule is now resolved: confirmed `memory_item.expires_at = NULL` and memory persists until manual deletion. Phase 3 precedes long-lived runtime/API work. Phase 4 precedes UI integration. Phase 5 precedes notification E2E. Phase 7 may harden completed slices continuously, but cannot release before all earlier exit gates and external safety/provider validations pass.

## Decisions Accepted with Plan Approval

Plan approval accepts the technical semantics documented in Phase 1 for pause/resume, abandoned goals, Options novelty, egress manifests, check-in recovery, startup ownership, backup format and validation-before-display. Any change to a product requirement returns to the proposal before code.

## External Release Gates

- Human safety review of detection thresholds, Vietnamese/regional support content and the non-automatic resume path.
- Current provider documentation review for provider-side retention labels; unknown data must display as unknown.
- Windows 11 validation with a real configured model provider and browser notification permission behavior.

## Verification Commands

Use `uv sync --locked --python 3.11 --extra all --extra dev`, `scripts/run_tests.sh tests/hermes_coach/`, relevant Hermes cache/server/cron regressions, and the package-local TypeScript `typecheck`, `lint`, `test` and `build` commands. Phase 7 records exact outputs and unresolved risks.

`run_tests.sh` works on Windows as of 2026-08-24 and is the runner to use:

```bash
scripts/run_tests.sh tests/hermes_coach/

# Coverage is a separate invocation, not a flag on the runner above: pytest-cov
# cannot see the per-file subprocesses the runner spawns.
PYTHONUTF8=1 TZ=UTC PYTHONHASHSEED=0 .venv/Scripts/python.exe -m pytest \
  tests/hermes_coach/ -q -p no:randomly --cov=hermes_coach --cov-branch --cov-report=term

.venv/Scripts/python.exe -m ruff check hermes_coach tests/hermes_coach
.venv/Scripts/python.exe -m ty check hermes_coach tests/hermes_coach
```

Frontend, from `apps/hermes-coach/`: `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`.

Do not place Coach tests under a directory named `integration`, `e2e` or `docker`: the runner drops those paths from discovery and from CI slice generation, so the tests vanish without failing.
