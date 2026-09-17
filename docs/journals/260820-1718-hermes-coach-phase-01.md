---
date: 2026-08-20
session: hermes-coach-phase-01
---

# Hermes Coach Phase 1: Contract Boundary Held

## Context

The proposal is canonical. Phase 1 was deliberately limited to contract and evaluation work: no UI, services, voice, research/advice, or deep-core implementation.

## What Happened

The phase closed with 112 SRC, 58 AC, and 33 P/T bundles mapped; 68 evaluation scenarios and 7 rubrics were covered. The final suite reported 48 passing tests, Ruff and ty passed, and measured line coverage was 91%.

Review found three real safety defects before closure: partial SMART state could remain stale, consent could be forged or trusted from an untrusted source, and consent withdrawal had a TOCTOU race. These were fixed. Partial SMART now invalidates rollback/reset state. A trusted UI event grants one-turn opaque authorization bound to manifest, session, turn, scope, and version. `RLock`-protected `provider_call_lease` makes admission through the accepted sink atomic; withdrawal blocks new and retry operations.

## Reflection

The useful part of this phase was forcing the boundaries into executable contracts instead of trusting intent. The uncomfortable part was discovering that apparently complete consent and SMART handling still failed under adversarial state and concurrency. The final bounded reviewer PASS is deserved, but it only covers this bounded contract surface.

## Decisions Made

| Decision | Rationale | Impact |
|---|---|---|
| Keep Phase 1 contract/evaluation-only | Preserve the proposal’s scope and avoid prematurely coupling UI or services to an unproven boundary. | UI/services remain planned for later phases. |
| Invalidate partial SMART state on rollback/reset | Stale assessment is worse than losing incomplete progress; rollback must restore truthful state. | Goal must be revalidated truthfully after rollback/reset. |
| Require trusted, opaque, narrowly bound consent | UI-origin and manifest/session/turn/scope/version binding prevent forged or replayed authorization. | Forged/stale token fails before provider egress. |
| Serialize provider admission and withdrawal with `RLock` | Prevent the TOCTOU race without allowing withdrawal to cancel an already admitted call. | Withdrawal blocks every new or retry operation after the admitted operation completes. |

## Next Steps

Start Phase 2 only from the approved plan and canonical proposal. Future release work owners must obtain and record human safety, provider-retention, provider-capability, native Windows, browser, and real-provider evidence before enabling affected paths. These are release gates, not Phase 1 blockers.

## Unresolved Questions

None for the product contract. Pending external safety/provider/Windows and related runtime evidence remains a release gate for future work, not an unresolved product question.
