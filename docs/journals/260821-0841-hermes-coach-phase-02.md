---
date: 2026-08-21
session: hermes-coach-phase-02
---

# Hermes Coach Phase 2: Green Tests Were Not Enough

## Context

Phase 2 turns the approved coaching behavior into a pure Python engine. The
boundary is intentionally narrow: domain state, policies, prompt validation,
candidate commands and safety routing only; no SQLite, HTTP, React, scheduler
or provider adapter.

## What Happened

The first implementation reached 150 passing tests and 94% statement coverage,
but adversarial QA reproduced paths that violated the proposal: urgent sessions
could continue coaching, descriptive Vietnamese phrases beginning with “Có”
could open a gate, stale revisions could close Review, Options could self-declare
novelty, downstream candidates survived rollback, untrusted confirmation DTOs
could replay, direct advice reached the sink, and the 68-scenario evaluator
indirectly remembered its oracle.

Each reproduction became a regression test. Gates now require a stage-complete
state, sequential funnel, a confirmation-specific Yes/No question, an
unqualified explicit Yes, an append-only alternating ledger containing exact
question/response content and the current stage revision. Rollback increments
target/downstream revisions, invalidates gates/snapshots and removes stale
candidates; asynchronous output must carry matching session/turn/revision
provenance. Options uses linked per-candidate assessment instead of independent
booleans. Safety interrupts validation, staging and delivery; urgent guidance
requires a signed immutable attestation bound to issuer, evidence/guidance
digest, version and validity. Candidate confirmation consumes a short-lived
backend-issued intent bound to local user/session/candidate/action/payload.
Advice, ungrounded statements, judgment, inferred cause and multiple focuses are
rejected before delivery; a reflected phrase requires Coachee grounding evidence.

The scenario harness no longer copies `expected.must_do` or switches on
scenario IDs. It derives actions from input/category, invokes actual service and
rule paths, applies only observable Phase 2 rubrics, mutation-tests observation
independence and every structural scoring field, and proves deliberately broken
gate/novelty implementations fail. It never synthesizes passed external safety
evidence. Free-text golden intent remains human-readable evidence, not an
automatically credited result.

## Verification Snapshot

- `244` tests passed after the second adversarial hardening pass.
- Ruff and ty passed.
- Branch-enabled coverage over `hermes_coach` reported `91%` combined coverage.
- Machine trace scope is exact: `74` Phase 2 source blocks, `52` AC slices,
  seven production bundles, seven verification bundles, `19` production files
  and `22` verification files.

## Decisions Made

| Decision | Rationale | Impact |
|---|---|---|
| Bind gate evidence to adjacent sequence and current revision | Reply-to ID alone is not proof that the answer immediately followed the closing question. | Delayed, stale, reused or same-ID answers fail closed. |
| Keep external safety gates pending while coding a trusted verifier boundary | Phase 2 must model the approved exception without enabling unreviewed urgent copy. | Normal urgent release remains blocked; only signed unit fixtures exercise the release capability. |
| Make candidate confirmation stateful and one-use | A literal `source="ui"` is forgeable and stateless functions cannot prevent replay. | Backend intent, command and candidate are consumed atomically in one process; durable transaction/CAS remains Phase 3. |
| Treat `80/20` and free-text `must_do` as qualitative evidence | Token counting or copying expected prose would manufacture confidence. | Focused policy tests and later provider/human evaluation own language quality. |

## Next Steps

Phase 3 may add SQLite models, repositories, retention, Trash, consent and
provenance without weakening these pure-engine contracts. External safety,
provider-retention, provider-capability and Windows/real-provider evidence stay
release gates for their affected later paths.

## Unresolved Questions

No product decision is unresolved. External release evidence remains pending by
design and must not be represented as completed Phase 2 evidence.
