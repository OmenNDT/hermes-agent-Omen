---
phase: 7
title: "Hardening and Release"
status: pending
effort: "1.5–2 weeks"
---

# Phase 7: Hardening and Release

## Objective

Harden crash/restart, backup/restore, offline/provider failure, egress audit, safety interruption and native Windows packaging; then prove all 112 source blocks and `AC-01…AC-58` through contract, unit, integration, evaluation and E2E evidence. This is a local MVP release gate, not commercial polish.

## Trace Scope

- Sources: all `SRC-000…SRC-111`, with primary hardening ownership for `SRC-026`, `SRC-067` as a no-voice boundary, `SRC-086…SRC-103`, `SRC-107…SRC-111`.
- Production: all P bundles; primary `P-DEPLOY`, `P-PRIVACY`, `P-SAFETY`, `P-RUNTIME`, `P-GOV`.
- Verification: all T bundles and relevant existing Hermes regression suites.
- Acceptance: release evidence for every `AC-01…AC-58`; blocked AC-11/12/57 cannot be marked verified until novelty/safety gates pass.

## Planned Files

| Area | Files |
|---|---|
| Backup/recovery | `hermes_coach/application/backup_service.py`, `restore_service.py`, focused manifest/checksum DTOs, crash journal/reconciliation helpers only where needed |
| Deployment | Coach package-data/build config, `scripts/` launcher/package helpers if required, `docs/hermes-coach-deployment-guide.md`, update derived architecture/traceability statuses with evidence |
| Release evidence | `tests/hermes_coach/e2e/`, `integration/`, `contract/`, `evals/reports/` plus `plans/260811-1454-hermes-coach-mvp-implementation/verification-report.md` generated from commands, not hand-waved |
| Windows | startup/profile-lock/port/notification/backup smoke scripts or pytest fixtures that execute on native Windows |

Do not add outbound telemetry. Technical logs are local, payload-minimized and subject to the approved 90-day retention. Avoid adding a new dependency unless the existing pinned stack cannot satisfy a verified requirement.

## Backup and Restore Contract

- Before backup, show/confirm the explicit unencrypted-backup warning. Use SQLite Backup API for a consistent snapshot; include attachment files, `manifest.json` with format/schema/app versions, timestamps, profile ID, file sizes and SHA-256 checksums. Exclude provider keys, ephemeral tokens and technical secrets.
- Write to a temporary file, fsync/close, then atomic rename. Never overwrite the only known-good backup without a separate confirmation.
- Restore verifies ZIP paths, checksums, manifest compatibility and free space into a temporary profile; reject traversal, duplicate paths, unknown mandatory entries and corrupt DB.
- Run migrations, integrity/FK checks and retention/Trash cleanup before preview or context use. Warn that backup may contain previously purged data. After user confirmation, stop services, atomically swap profiles and retain a recoverable pre-restore copy until post-start validation succeeds.
- A failed restore leaves the active profile untouched. A failed post-swap startup rolls back to the pre-restore copy and records payload-free diagnostics.

## Hardening Matrix

| Risk | Required proof |
|---|---|
| Crash/restart | Kill/restart during accepted turn, candidate confirmation, Trash transaction, scheduler sync, backup and restore; no partial official record or duplicate job |
| Offline/provider failure | Local dashboard/privacy/export remain usable; coaching shows neutral retry/degraded state; no invalid candidate/gate is written |
| Prompt/cache | Byte-stability and role-alternation across long sessions, rollback, regeneration, compression boundary and restart; existing Hermes cache suites stay green |
| Security | Loopback-only bind, Host/Origin/peer/token, ZIP traversal, log/DB/export secret scans, CORS and no dashboard admin/API exposure |
| Privacy | 90/30 boundaries, old-backup caveat, consent withdrawal, egress minimization, Trash exclusion, permanent purge and local log retention |
| Safety | Correct escalation/interruption, labeled Safety System, approved direct content, no normal flow in urgent and no automatic resume |
| Windows | Native Windows 11 launch, profile ACL behavior disclosure, Selector loop, file locks, Unicode paths, browser notification and clean shutdown |

## External Release Gates

1. **Safety:** named human reviewer approves detection cases/thresholds, Vietnamese/regional resources with authoritative source and review expiry, direct-support wording and resume path. Automated model scores alone are insufficient.
2. **Provider metadata:** each displayed provider-retention claim has a current authoritative source/date; otherwise UI shows `unknown`.
3. **Real provider:** at least one configured MVP provider passes structured-output, validation-before-display, cache and failure-accounting tests without tools.
4. **Windows/browser:** real Windows 11 and supported browser confirm loopback launch, permissions, quiet hours/degraded notification behavior and backup/restore.

## Tests-first Work Order

1. Write failing backup/restore security, corruption, migration, retention and rollback tests; implement services to pass them.
2. Add process-level fault injection and restart/reconciliation tests across DB, RPC, scheduler and backup boundaries.
3. Execute all Phase 1 evaluation scenarios on the target provider(s); manually review safety and a statistically meaningful sample of question-only/novelty results.
4. Run complete Python/TypeScript/E2E suites plus existing Hermes state, prompt-cache, alternation, server/auth/WS and cron regressions.
5. Generate an acceptance report with one row per AC and links to test/eval evidence, plus a source coverage report with exactly 112 SRC rows and no undefined bundle.
6. Run native Windows packaging/install/start/upgrade/uninstall-smoke without deleting the Coach profile; document recovery, backup and data-location behavior.
7. Update derived architecture/traceability from `planned`/`blocked` to `implemented`/`verified` only where evidence exists. Never mark canonical proposal requirements complete from file existence alone.

## Verification Commands

```powershell
uv sync --locked --python 3.11 --extra all --extra dev
bash scripts/run_tests.sh tests/hermes_coach/
bash scripts/run_tests.sh tests/run_agent/test_anthropic_prompt_cache_policy.py tests/run_agent/test_message_sequence_repair.py tests/test_tui_gateway_ws.py tests/hermes_cli/test_serve_command.py tests/hermes_cli/test_web_server_host_header.py tests/cron/
cd apps/hermes-coach; npm ci; npm run typecheck; npm run lint; npm test; npm run build
cd ../shared; npm run typecheck
```

Use the repository-supported shell/venv on Windows; record substitutions and exact versions in the verification report. Integration/E2E exclusions must be run explicitly.

## Release Exit Criteria

- [ ] Exactly 112/112 source blocks, 58/58 ACs and every P/T bundle have bidirectional evidence; no placeholder or unjustified `verified` status remains.
- [ ] All external gates above are signed/date-stamped and current.
- [ ] Full Coach suites and scoped Hermes regressions pass on native Windows and target browser/provider.
- [ ] Backup/restore, crash recovery, offline/degraded mode, retention/Trash, egress audit and scheduler reconciliation pass fault injection.
- [ ] Security/privacy scans find no credential, non-loopback listener, sensitive notification, raw rejected output, stale Trash context or unsafe backup path.
- [ ] No voice/STT/TTS path, dependency, permission, schema, feature module or dedicated voice test ships; the governance boundary check remains green.
- [ ] Remaining risks and out-of-scope commercial polish are documented; implementation is not called complete merely because the token/time budget ended.
