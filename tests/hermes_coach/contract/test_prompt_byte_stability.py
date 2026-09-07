from __future__ import annotations

from hermes_coach.contracts.runtime_contract import stable_prompt_fingerprint
from hermes_coach.domain.session_state import CoachingSessionState
from hermes_coach.prompt.structured_context import structured_context_json
from hermes_coach.prompt.system_prompt import COACH_SYSTEM_PROMPT, coach_system_prompt


def test_system_prompt_is_byte_stable_and_contains_load_bearing_invariants() -> None:
    first = coach_system_prompt()
    second = coach_system_prompt()

    assert first == second == COACH_SYSTEM_PROMPT
    assert stable_prompt_fingerprint(first) == stable_prompt_fingerprint(second)
    for invariant in (
        "Người đồng hành",
        "ngang vị thế",
        "tiềm năng",
        "Pre-Coaching → Goal → Reality → Options → Will → Review",
        "đúng một câu hỏi",
        "Yes",
        "rollback",
        "Safety System",
    ):
        assert invariant in first


def test_dynamic_state_changes_structured_context_not_system_prompt() -> None:
    state = CoachingSessionState(session_id="session-1")
    before_prompt = coach_system_prompt()
    before_context = structured_context_json(state)
    changed = state.model_copy(update={"session_id": "session-2"})

    assert structured_context_json(changed) != before_context
    assert coach_system_prompt() == before_prompt
