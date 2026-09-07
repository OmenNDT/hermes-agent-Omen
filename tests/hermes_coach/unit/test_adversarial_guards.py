from __future__ import annotations

import pytest
from pydantic import ValidationError

from hermes_coach.application.coaching_service import CoachingService
from hermes_coach.application.record_confirmation_service import ConfirmationCommand, RecordAction
from hermes_coach.application.safety_service import route_safety
from hermes_coach.contracts.runtime_contract import (
    CandidateRecord,
    CoachingStage,
    GateAnswer,
    RecordKind,
)
from hermes_coach.domain.enums import FunnelStage, SafetyOutputMode, SafetyState
from hermes_coach.domain.session_state import CoachingSessionState, StageRevision, stage_is_complete
from hermes_coach.domain.transitions import classify_gate_answer, rollback_to
from hermes_coach.policies.question_policy import is_yes_no_closing_question
from hermes_coach.prompt.question_validator import validate_question
from tests.hermes_coach.unit.test_transitions import completed_state, state_at_stage


def test_urgent_state_cannot_open_or_answer_a_normal_coaching_gate() -> None:
    service = CoachingService()
    urgent = completed_state(CoachingStage.GOAL).model_copy(
        update={
            "safety_state": SafetyState.URGENT,
            "funnel_stage": FunnelStage.CLARIFY,
        }
    )

    with pytest.raises(ValueError, match="interrupted"):
        service.open_gate(
            urgent,
            question_turn_id="q-urgent",
            closing_question="Bạn có xác nhận mục tiêu này là đúng không?",
            question_sequence=1,
        )


def test_arbitrary_or_blank_urgent_guidance_evidence_stays_fail_closed() -> None:
    forged = route_safety(
        SafetyState.URGENT,
        approved_direct_guidance="   ",
        approval_evidence_id="made-up",
    )

    assert forged.output_mode is SafetyOutputMode.BLOCKED
    assert forged.direct_guidance is None


@pytest.mark.parametrize(
    "response",
    [
        "Có một lựa chọn khác",
        "Có vấn đề",
        "Có, tôi không đồng ý với phần thời hạn",
    ],
)
def test_descriptive_or_contradictory_co_prefix_is_not_explicit_yes(response: str) -> None:
    assert classify_gate_answer(response) is GateAnswer.UNCLEAR


def test_polite_unqualified_agreement_is_explicit_yes() -> None:
    assert classify_gate_answer("Dạ, tôi đồng ý") is GateAnswer.YES


def test_generic_co_khong_question_is_not_a_closing_confirmation() -> None:
    assert not is_yes_no_closing_question("Có điều gì bạn không muốn chạm tới hôm nay?")


@pytest.mark.parametrize(
    "question",
    [
        "Tôi đề nghị bạn nghỉ việc; bạn thấy sao?",
        "Theo tôi, nghỉ việc là lựa chọn tốt nhất; bạn đồng ý không?",
        "Bạn hãy nghỉ việc; bạn thấy quyết định này thế nào?",
        "Bạn muốn nghỉ việc hay thương lượng; và bạn sẽ làm khi nào?",
        "Bạn đã thất bại vì thiếu kỷ luật: điều gì khiến bạn tiếp tục như vậy?",
    ],
)
def test_advice_judgment_or_multiple_focus_never_passes_question_validator(
    question: str,
) -> None:
    assert not validate_question(question).valid


def _replace_options_assessment(
    state: CoachingSessionState, **updates: object
) -> CoachingSessionState:
    assessment = state.options.assessments[0].model_copy(update=updates)
    options = state.options.model_copy(update={"assessments": (assessment,)})
    return state.model_copy(update={"options": options})


def _replace_turn_content(
    state: CoachingSessionState, turn_id: str, content: str
) -> CoachingSessionState:
    ledger = tuple(
        turn.model_copy(update={"content": content}) if turn.turn_id == turn_id else turn
        for turn in state.turn_ledger
    )
    return state.model_copy(update={"turn_ledger": ledger})


def test_options_snapshot_cannot_complete_without_aggregate_ledger() -> None:
    state = completed_state(CoachingStage.OPTIONS)
    detached = state.model_copy(update={"turn_ledger": ()})

    assert not detached.options.complete
    assert not stage_is_complete(detached)


@pytest.mark.parametrize(
    "updates",
    [
        {"session_id": "fabricated-session"},
        {"stage_revision": 2},
        {"candidate_source_turn_id": "fabricated-turn"},
        {"candidate_source_turn_id": "options-evoke"},
    ],
)
def test_options_rejects_cross_session_stale_fabricated_or_coach_source(
    updates: dict[str, object],
) -> None:
    state = _replace_options_assessment(
        completed_state(CoachingStage.OPTIONS), **updates
    )

    assert not stage_is_complete(state)


def test_options_rejects_negated_candidate_even_when_flags_are_true() -> None:
    state = _replace_turn_content(
        completed_state(CoachingStage.OPTIONS),
        "options-candidate",
        "Tôi không muốn xây portfolio để đổi vai trò",
    )

    assert not stage_is_complete(state)


def test_options_rejects_same_mechanism_against_canonical_baseline() -> None:
    state = completed_state(CoachingStage.OPTIONS)
    candidate = state.options.assessments[0].candidate.model_copy(
        update={
            "text": "Đề nghị điều chỉnh lương bằng cách tiếp tục đàm phán lương",
            "mechanism": "tiếp tục đàm phán lương",
        }
    )
    state = _replace_options_assessment(state, candidate=candidate)
    state = _replace_turn_content(
        state,
        "options-candidate",
        "Đề nghị điều chỉnh lương bằng cách tiếp tục đàm phán lương",
    )

    assert not stage_is_complete(state)


def test_stale_gate_revisions_do_not_satisfy_review_prerequisites() -> None:
    state = state_at_stage(CoachingStage.REVIEW)
    stale_revisions = tuple(
        StageRevision(
            stage=item.stage,
            revision=item.revision + 1
            if item.stage in {
                CoachingStage.GOAL,
                CoachingStage.REALITY,
                CoachingStage.OPTIONS,
                CoachingStage.WILL,
            }
            else item.revision,
        )
        for item in state.revisions
    )

    assert not stage_is_complete(state.model_copy(update={"revisions": stale_revisions}))


def test_rollback_discards_unbound_or_downstream_candidates() -> None:
    state = state_at_stage(CoachingStage.REVIEW)
    state = state.model_copy(
        update={
            "candidate_records": (
                CandidateRecord(
                    candidate_id="commitment-1",
                    kind=RecordKind.COMMITMENT,
                    value="Viết case study",
                    source_turn_id="turn-will",
                    coaching_stage=CoachingStage.WILL,
                    stage_revision=state.revision_for(CoachingStage.WILL),
                ),
            )
        }
    )
    rolled = rollback_to(state, CoachingStage.GOAL, reason="Mục tiêu cần làm rõ")

    assert rolled.candidate_records == ()


def test_ui_source_must_be_explicit_on_confirmation_command() -> None:
    with pytest.raises(ValidationError):
        ConfirmationCommand.model_validate(
            {
                "command_id": "cmd-1",
                "ui_event_id": "ui-1",
                "candidate_id": "cand-1",
                "action": RecordAction.ACCEPT,
            }
        )
