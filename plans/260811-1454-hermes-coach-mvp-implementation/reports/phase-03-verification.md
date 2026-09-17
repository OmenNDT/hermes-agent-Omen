# Phase 3 Verification — Local Data and Privacy

Date: 2026-08-22
Status: completed
Scope: Coach-owned SQLite store, repositories, confirmation atomicity, consent, retention, Trash, context/egress/export and restart recovery. No HTTP, React, scheduler or provider adapter.

## Evidence

- All seven tests-first work-order steps landed; 7/7 exit criteria checked.
- Suite grew from 382 at the Phase 2 gate to **552 tests across 35 files**, all passing under per-file process isolation.
- Branch coverage over `hermes_coach` is **93%** (2836 statements, 128 missed; 528 branches, 101 partial).
- 61 production Python modules and 4 immutable migrations.
- Every persistence test runs against a real SQLite file under a temporary Coach profile. There is no repository-only mock in the phase.

## Commands and results

```text
scripts/run_tests_parallel.py tests/hermes_coach/
35 files, 552 tests passed, 0 failed in 6.3s (56 workers)

pytest -q tests/hermes_coach/ -p no:randomly --cov=hermes_coach --cov-branch
552 passed; TOTAL 93%

ruff check hermes_coach tests/hermes_coach
All checks passed!

ty check hermes_coach tests/hermes_coach
All checks passed!
```

Run with the project venv on Windows (`.venv/Scripts/python.exe`) and `TZ=UTC LANG=C.UTF-8 PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1`. `scripts/run_tests.sh` remains unusable here — it assumes the POSIX `bin/` venv layout — so the runner it delegates to is invoked directly. See the plan's Open Follow-ups.

## What the phase established

| Area | Guarantee | Where it is enforced |
|---|---|---|
| Schema | 16 canonical tables with exactly their proposal fields, closed enum CHECKs, foreign keys enforced at runtime | `0001_initial_schema.sql` |
| Migrations | DDL, postcondition and version advance in one `BEGIN IMMEDIATE`; refusal to downgrade a database from a newer build | `migration_runner.py` |
| Connection | Caller-owned transactions under an immediate write lock; WAL with a tested fallback for filesystems that refuse or silently ignore it | `database.py` |
| Active scope | One `not_in_trash` / `not_expired` definition, applied by every repository read and proven by a deliberately leaky subclass | `repositories/base.py` |
| Confirmation | Intent check, command replay guard, candidate compare-and-set and the official write in one transaction, surviving restart | `durable_confirmation_service.py` |
| Consent | Append-only, UI-control-only, normalized type/scope, latest event wins, re-read on every check | `consent_service.py` |
| Retention | 90/30-day deadlines on an injected clock, idempotent, catching deadlines missed while closed | `retention_service.py` |
| Trash | Soft delete atomic with its marker, per-item restore with a parent check, purge in dependency order with payload-free audit | `trash_service.py` |
| Egress | Audit schema with no content column; unverified provider retention displays as unknown and is versioned separately | `egress_audit.py` |
| Recovery | Committed state rebuilt from rows after a genuine process restart, including one that never closed cleanly | `session_recovery_service.py` |

## Decisions worth carrying forward

| Decision | Rationale |
|---|---|
| No separate `schema.sql`; a fresh database runs every migration | Two hand-synced definitions are how a new install and an upgraded install drift apart |
| Test directory is `persistence/`, not `integration/` | The canonical runner drops any path containing an `integration` component from discovery and CI slice generation — the tests were silently absent until renamed |
| A NULL `expires_at` falls back to creation age | Treating a missing expiry as "durable" would let a forgetful writer create immortal transcript, which is a privacy failure, not a safe default |
| Purging a goal detaches its insights rather than deleting them | An insight is structured truth of its own; cascading would delete data the Coachee never asked to remove |
| Retention uses two atomicity scopes | Temporary-data classes share one transaction; each Trash entity gets its own so its dependents and audit commit together without holding a write lock across every purge |
| Intents are stored as SHA-256 digests | A database copy of a live token would let anyone who can read the file replay a confirmation |
| Recovery hands back state and stops | The proposal requires an explicit non-automatic resume path |

## Gates and limitations

External gates in `tests/hermes_coach/evals/external-gates.yaml` are unchanged and still pending: human safety review, provider retention, provider capability. None is affected by this phase, and none may be represented as satisfied.

Not implemented here, by design: HTTP API, React UI, scheduler and notification delivery, provider adapter, backup (Phase 7). Exit criterion 5 covers context and egress; the UI, check-in and notification surfaces arrive in Phases 5–6 and reuse these same repository scopes rather than re-deriving them.

`pyproject.toml` and `uv.lock` diverge from upstream Hermes by one dependency (`pytest-cov==7.1.0`), added so coverage runs from the project venv.

## Tracking result

- Phase 3 exit criteria: 7/7 checked; phase status completed.
- Phases 4–7: pending; 0/25 exit criteria checked.
- Plan total: 20/45 exit criteria checked (44.4%); 3/7 phases completed.
- Plan status: in-progress; product scope unchanged.

## Unresolved questions

- The Phase 3 source scope in the plan's prose is narrower than the machine allocation in `requirements_map.yaml` (24 listed vs 36 allocated). The map is the authority and its coverage test enforces it, but the prose should be reconciled before Phase 7 audits coverage.
- `scripts/run_tests.sh` still cannot run on Windows. Fixing it touches shared upstream tooling and has not been authorized.
