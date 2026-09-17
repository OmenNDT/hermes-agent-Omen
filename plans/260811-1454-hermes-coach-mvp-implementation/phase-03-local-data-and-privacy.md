---
phase: 3
title: "Local Data and Privacy"
status: completed
effort: "2 weeks"
---

# Phase 3: Local Data and Privacy

## Objective

Create a Coach-owned SQLite source of truth with versioned migrations, transactional repositories, explicit consent/provenance, 90-day temporary-data retention, 30-day Trash, export and privacy-safe context selection. This database is separate from Hermes `state.db` and contains no provider credential.

## Trace Scope

- Sources: `SRC-011`, `SRC-026`, `SRC-036`, `SRC-054…SRC-059`, `SRC-063`, `SRC-068`, `SRC-076…SRC-086`, `SRC-091`, `SRC-092`, `SRC-099`, `SRC-108`.
- Production: `P-DATA`, `P-RECORDS`, `P-PRIVACY`, data parts of `P-GOAL`, `P-STATE`, `P-CHECKIN`, `P-METRICS`.
- Verification: `T-DATA`, `T-RECORDS`, `T-PRIVACY`, repository portions of `T-GOAL`, `T-STATE`, `T-CHECKIN`, `T-METRICS`.
- Acceptance: `AC-49`, `AC-53…AC-55`, plus persistence for `AC-08`, `AC-32`, `AC-50`, `AC-51`, `AC-58`.

## Planned Files

| Area | Files |
|---|---|
| SQLite | `hermes_coach/infrastructure/sqlite/database.py`, `migration_runner.py`, `migrations/0001_initial_schema.sql` and later immutable versioned migrations |
| Domain | `hermes_coach/domain/records.py` for persisted product records, `models.py`/`enums.py` for live session state, internal persistence DTOs under `domain/` only when not product entities |
| Repositories | focused modules under `hermes_coach/infrastructure/repositories/` for profile, value, snapshot, goal, commitment, evidence, check-in, session/message/gate, candidate, insight, memory/provenance, consent, Trash and audit |
| Services | `record_confirmation_service.py`, `privacy_service.py`, `retention_service.py`, `trash_service.py`, `context_selector.py`, `metrics_service.py` |
| Egress/export | `hermes_coach/infrastructure/egress_audit.py`, `hermes_coach/application/export_service.py` |
| Tests | `tests/hermes_coach/persistence/test_{sqlite_schema,migrations,restart_recovery,record_persistence,memory_provenance,egress_manifest,trash_lifecycle}.py`; focused unit tests for retention/context/consent/confirmation/metrics |

Repositories return domain records and own SQL; services own transactions spanning repositories. No service reaches raw `sqlite3.Connection` except through a transaction interface.

Deviation from the original file list: there is no separate `schema.sql`. A fresh
database is built by running every migration, so a new install and an upgraded
install cannot drift apart — one source of truth instead of two that must be
kept identical by hand. This is an implementation detail; no product requirement
changed.

Test directory is `persistence/`, not `integration/`. The canonical runner drops
any path containing an `integration` component (`_SKIP_PARTS`), reserving that
name for suites needing real external services in dedicated CI jobs. These tests
need none — real SQLite under `tmp_path` only — so under the original name they
were silently absent from both default runs and CI slice generation. The rename
is the whole fix: no flag, no runner change.

### Progress

| Work-order step | State | Evidence |
|---|---|---|
| 1. Fresh schema | done | `test_sqlite_schema.py` — 16 canonical tables, exact column sets, closed enums, FK enforcement, retention indexes |
| 2. Migrations and connection | done | `test_migrations.py`, `test_database_connection.py` — version-0 upgrade, rollback on bad SQL/postcondition, refusal to downgrade, corrupt-file error, WAL fallback, immediate-lock transactions |
| 3. Repository active scopes | done | `test_active_scope.py` — table-driven over every registered repository: soft-deleted rows leave both lists and direct `get`, restore brings them back, purge keeps them hidden; expiry, pending-only and confirmed-only filters; append-only snapshots and multi-source provenance; a deliberately leaky subclass proves the predicate is what excludes |
| 4. Candidate/consent atomicity | done | `test_durable_confirmation.py`, `test_consent.py` — intent check, command guard, candidate CAS and official write in one transaction; single-use intent and command replay both survive restart; accept/edit materialize goal/insight/commitment/memory, discard writes nothing; re-confirmation adds a revision; audit holds ids only; consent is UI-only, append-only, latest-wins, normalized, and re-read on every check |
| 5. Retention and Trash clocks | done | `test_retention.py`, `test_trash_lifecycle.py` — day 89/90/91 and 29/30/31 boundaries, injected clock, idempotent sweep, restart catch-up, rollback on failure; soft delete atomic with its marker, per-item restore with parent check, purge needs a confirmed UI control, dependents removed in order, insights detached not deleted, payload-free audit |
| 6. Context, egress and export | done | `test_context_selection.py`, `test_egress_and_export.py` — selector drops expired, Trash, unconfirmed, withdrawn-scope and unrelated records and names every selected item in content-free refs; audit stores categories/item ids/provider/model/purpose/consent/decision with no payload column; unverified provider retention displays as unknown and is versioned separately; export carries provenance, status, timestamps, consent history and the unencrypted disclosure, redacts credential-shaped values |
| 7. Restart recovery | done | `test_restart_recovery.py` — a genuine child interpreter writes and exits, one of them via `os._exit` without ever closing; the parent rebuilds confirmed records, gate history, current stage, provenance and pending check-ins, sees no uncommitted write, and finds deletions still made |

Evidence and residual risks: [Phase 3 verification report](./reports/phase-03-verification.md).

## Schema and Migration Contract

- Implement every canonical field, enum and relationship for profile, snapshot, value, goal, commitment, evidence, check-in, session, message, candidate, gate, consent, insight, memory/provenance and Trash. Confirmed memory always uses `expires_at = NULL`, is excluded from age-based retention and persists until manual deletion; no sentinel date is permitted. Pending memory candidates still purge after 90 days.
- Internal tables may hold schema version, session state snapshots, egress/audit metadata, technical logs and notification history; they must not redefine canonical product entities and must map to source/bundle IDs.
- Use `sqlite3` with `isolation_level=None`, row factory, `foreign_keys=ON`, `busy_timeout`, WAL with tested fallback, `synchronous=FULL` for critical writes and `secure_delete=ON` as best-effort hygiene—not encryption.
- Each immutable migration uses `BEGIN IMMEDIATE`, checks current version, applies DDL/backfill/indexes, validates postconditions and updates version in the same transaction. Failure rolls back both data and version.
- Migration tests open real legacy fixtures through production code, cover every previous version, rerun safely and test malformed/corrupt recovery without silent data loss.

## Transaction Contracts

### Confirmation and consent

- Accept/edit candidate creates the official record and resolves that one candidate atomically; discard creates no official record. Store the resulting official ID in internal confirmation audit metadata.
- No batch-confirm command or repository method exists. Re-confirm creates a new record revision/audit event rather than mutating provenance invisibly.
- `consent_event` is append-only and only application commands carrying a trusted UI control ID may create it. Effective consent is the latest event for normalized type/scope; withdrawal is checked fresh before every scoped write or model egress.

### Trash and retention

- An open `trash_entry` is the canonical deletion marker. Soft delete creates it atomically and changes an entity status/`deleted_at` only where that field already exists in the canonical schema; it does not add ad-hoc deletion columns. All active repository queries share an exclusion scope; context, egress, check-ins and notifications perform a second eligibility check.
- Restore is per item, verifies surviving dependencies, marks `restored_at` and cancels pending purge. Permanent purge requires a distinct confirmed UI command, deletes children/payload in dependency order and stores payload-free audit evidence.
- Startup retention runs before context/model calls and then periodically with an injected clock. It permanently purges only pending candidates, session messages/transcripts, technical logs and notification history at 90 days and open Trash at 30 days. Durable structured records never auto-expire.
- Retention is a Coach lifecycle service, not a user cron job. Cleanup is idempotent and restart catches missed deadlines.

### Context, egress and export

- Context selector takes active goal/session/purpose and returns the minimum eligible confirmed items plus provenance. It rejects expired, Trash, unconfirmed, withdrawn-scope and unrelated records before egress.
- Egress audit stores categories, item IDs, provider/model, purpose, consent evidence and decision—not full payload or secrets. Provider-retention display metadata is separate and versioned.
- JSON/Markdown export is user-initiated and includes provenance/status/timestamps while excluding API keys and internal secrets. Backup is deferred to Phase 7.

## Tests-first Work Order

1. Build failing fresh-schema tests from every canonical field/enum/FK/unique/index rule; implement `schema.sql` and version 1.
2. Add legacy/migration/failure-injection/concurrent-write/WAL-fallback tests; implement migration runner and deterministic close/shutdown.
3. Add repository contract tests proving active scopes always exclude Trash/expired/unconfirmed data and preserve append-only snapshot/provenance semantics.
4. Add atomic candidate accept/edit/discard/re-confirm and UI-only consent/withdrawal tests.
5. Add clock-boundary retention and Trash tests immediately before/at/after 90/30 days, startup catch-up, restore, dependent purge and failure rollback.
6. Add context/egress/export tests, including withdrawn consent, unknown provider retention, no full payload in audit and no credential in DB/export.
7. Add real-process restart recovery tests for confirmed records, gates, current stage and pending schedules.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| One query leaks Trash/expired/unconfirmed data | Shared active-scope repositories plus independent context/egress eligibility guard |
| Migration partially advances | `BEGIN IMMEDIATE`, postcondition check, version update in same transaction and legacy fixtures |
| Schema convenience contradicts canonical fields | Requirements contract blocks migration; internal tables cannot redefine product entities |

## Privacy Disclosure Requirements

The service exposes one versioned disclosure saying Coach DB, attachments and backups are not encrypted; Windows ACL is not encryption; authorized local users/processes can read them; permanent purge of active data does not erase old backups. UI surfaces it in Phase 5 and backup flow in Phase 7.

## Exit Criteria

- [x] Fresh DB and every migration path pass with foreign keys, atomic versioning and tested failure recovery.
- [x] Restart preserves all confirmed records, gate history, current stage and provenance.
- [x] Candidate/consent paths are individual, UI-evidenced and atomic; withdrawal blocks the next scoped request/write.
- [x] Temporary data and Trash purge exactly at 90/30 days; durable records do not auto-expire.
- [x] Deleted/expired/unconfirmed data cannot appear in active UI queries, context, egress, check-ins or notifications. UI, check-in and notification surfaces arrive in Phases 5–6 and reuse these same repository scopes.
- [x] Export/egress audits are transparent and secret-free; database scan finds no API key.
- [x] Tests use real SQLite under a temporary Coach profile, not repository-only mocks.
