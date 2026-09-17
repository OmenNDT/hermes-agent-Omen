# Phase 2 Verification — Coaching Engine

Date: 2026-08-22
Status: completed with one open type-check finding
Scope: pure domain/policy/application/prompt engine only; no SQLite, HTTP, React, scheduler or provider adapter.

## Evidence

- Phase 2 trace scope (`hermes_coach/requirements_map.yaml.phase_2`): 74 source blocks, 52 acceptance IDs, 7 production bundles, 7 verification bundles, 19 production files, 22 verification files. `test_requirements_coverage.py` asserts exact equality with the proposal allocation and that every listed file exists.
- Suite grew from 244 (journal `260821-0841`) to 301 tests after the post-journal hardening pass; all pass.
- Branch coverage over `hermes_coach` is 91% (1770 statements, 94 missed; 402 branches, 88 partial).
- Per-module coverage floor is `contracts/lifecycle_contract.py` at 78%; every `domain/`, `policies/` and `prompt/` module is ≥87%, with 100% on `enums`, `goal_rules`, `models`, `companion_policy`, `feedback_policy`, `question_policy`, `safety_policy`, `output_schema`, `regeneration`, `system_prompt`.
- Adversarial regressions from the journal are covered: stage-complete gate precondition, sequential funnel, confirmation-specific Yes/No, unqualified explicit Yes, append-only alternating ledger with exact content and current revision, rollback revision/candidate invalidation, provenance-matched async output, linked per-candidate Options assessment, signed urgent attestation, one-use backend-issued confirmation intent.
- Scenario harness derives actions from input/category rather than copying `expected.must_do` or switching on scenario IDs; observation-independence, per-structural-field mutation and deliberately-broken gate/novelty tests all hold.

## Commands and results

```text
pytest -q tests/hermes_coach/ -p no:randomly
301 passed in 6.62s

pytest -q tests/hermes_coach/ -p no:randomly --cov=hermes_coach --cov-branch --cov-report=term
301 passed in 13.03s; TOTAL 91%

uvx --from ruff==0.15.10 ruff check hermes_coach tests/hermes_coach
All checks passed!

uvx --from ty==0.0.21 --with pydantic==2.13.4 --with pyyaml --with pytest ty check hermes_coach tests/hermes_coach
Found 6 diagnostics
```

Runs used the repository Python 3.11 interpreter with `TZ=UTC PYTHONHASHSEED=0`. `scripts/run_tests.sh` was not usable at the time: no venv existed in this checkout, so it exited with `error: no virtualenv found`. The per-file isolation it enforces is therefore not part of this Phase 2 evidence.

Follow-up 2026-08-22: a venv was provisioned with `uv sync --locked --python 3.11 --extra all --extra dev`. `scripts/run_tests.sh` still refuses to run on Windows — it probes `$candidate/bin/activate` and uses `$VENV/bin/python`, but uv creates the Windows layout `.venv/Scripts/`. Per-file isolation was obtained instead by invoking `scripts/run_tests_parallel.py` directly with the venv interpreter and the same hardened environment, which is the mechanism `run_tests.sh` delegates to.

The repository-level `pytest-asyncio` deprecation warning for unset `asyncio_default_fixture_loop_scope` persists from Phase 1 and does not fail the suite.

## Open finding — protocol variance (resolved 2026-08-22)

Resolved the same day, before Phase 3 work began: `OptionTurnEvidence` now
declares read-only properties instead of mutable attributes, and the actor
literal is a named `TurnActor` alias that the test helpers reuse instead of
widening to `str`. `ty` reports no diagnostics. The original finding is kept
below as the record of what the Phase 2 exit evidence actually looked like.

`ty` reported six `invalid-argument-type` errors, all one root cause:

- `hermes_coach/domain/options_rules.py:60` — `options_are_complete(..., turn_ledger: Sequence[OptionTurnEvidence])`.
- `OptionTurnEvidence` (`options_rules.py:35`) is a `Protocol` declaring mutable attributes (`turn_id: str`, `sequence: int`, `actor: str`, `content: str`), so it is invariant and a frozen `SessionTurn` does not satisfy it structurally.
- Call sites flagged: `hermes_coach/domain/session_state.py:162`, `tests/hermes_coach/evals/pure_engine.py:317`, `tests/hermes_coach/unit/test_options_rules.py:52,64,84,189`.

Runtime behavior is unaffected — `Protocol` attribute mutability is not enforced at runtime and all 301 tests pass. The fix is to declare the protocol members as read-only properties. Do this before Phase 3, which adds repository call sites that would multiply the diagnostics.

## Gates and limitations

`tests/hermes_coach/evals/external-gates.yaml` gates remain pending and unchanged by this phase:

- human safety review — blocks safety thresholds/content and safety-enabled release;
- provider retention — blocks non-`unknown` retention labels and provider-enabled release;
- provider capability — blocks provider-specific adapter approval and provider-enabled release.

Urgent-guidance release stays fail-closed; only signed unit fixtures exercise the release capability. Durable confirmation CAS is process-local here and belongs to Phase 3. Windows/browser/real-provider proof remains later-phase work.

## Tracking result

- Phase 2 exit criteria: 7/7 checked; phase status completed.
- Phases 3–7: pending; 0/32 exit criteria checked.
- Plan total: 13/45 exit criteria checked (28.9%); 2/7 phases completed.
- Plan status: in-progress; product scope unchanged.

## Unresolved questions

- None on product decisions. The `ty` protocol-variance finding is a tracked code follow-up, not a requirements question, and pending external evidence remains a named future gate.
