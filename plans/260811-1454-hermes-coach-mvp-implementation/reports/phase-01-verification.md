# Phase 1 Verification — Contract and Evaluation

Date: 2026-08-20  
Status: completed  
Scope: contracts/evaluation only; no Coach UI, voice, research/advice, or deep-core changes.

## Evidence

- Requirements inventory: 112/112 SRC, 58/58 AC, 33 P/T bundles.
- Evaluation inventory: 68 scenarios, 7 rubrics; reproducible harness tests pass.
- Phase 1 tests: 48 passed, including forged-consent and atomic-withdrawal race coverage.
- Contract coverage includes stable prompt, no tools, structured output, validation-before-sink, transition/lifecycle/safety/egress boundaries, and no-voice/deep-fork boundaries.
- Bounded code reviewer verdict: PASS.

## Commands and results

```text
pytest -q tests/hermes_coach
48 passed in 1.78s

uvx --from ruff==0.15.10 ruff check hermes_coach tests/hermes_coach
All checks passed!

uvx --from ty==0.0.21 --with pydantic==2.13.4 --with pyyaml --with pytest ty check hermes_coach tests/hermes_coach
All checks passed!

pytest -q tests/hermes_coach --cov=hermes_coach --cov=tests.hermes_coach.evals.runner --cov=tests.hermes_coach.evals.runtime_harness --cov=tests.hermes_coach.evals.scoring --cov-report=term-missing
48 passed in 4.03s; total line coverage 91% (798 statements, 69 missed)
```

The two pytest runs emit one repository-level `pytest-asyncio` deprecation warning because `asyncio_default_fixture_loop_scope` is unset; it does not fail the Hermes Coach suite.

## Gates and limitations

`tests/hermes_coach/evals/external-gates.yaml` names owner, evidence format, validity/expiry for:

- human safety review — pending; blocks safety thresholds/content and safety-enabled release;
- provider retention — pending; blocks non-`unknown` retention labels and provider-enabled release;
- provider capability — pending; blocks provider-specific adapter approval and provider-enabled release.

These gates do not block generic Phase 1 contracts. Native Windows/browser/real-provider release proof remains later-phase work.

## Tracking result

- Phase 1 exit criteria: 6/6 checked; phase status completed.
- Phases 2–7: pending; 0/39 exit criteria checked.
- Plan total: 6/45 exit criteria checked (13.3%); 1/7 phases completed.
- Plan status: in-progress; product scope unchanged.

## Unresolved questions

- None for the Phase 1 generic contract. Pending external evidence is a named future gate, not an unresolved product decision.
