from __future__ import annotations

import pytest
from pydantic import ValidationError

from hermes_coach.contracts.runtime_contract import CoachingStage, GateAnswer
from hermes_coach.domain.models import (
    PreCoachingSnapshot,
    RealitySnapshot,
    ReviewSnapshot,
    WillSnapshot,
)
from hermes_coach.domain.session_state import (
    CoachingSessionState,
    SessionGateEvent,
    SessionTurn,
    stage_is_complete,
)


def completed_state(stage: CoachingStage) -> CoachingSessionState:
    snapshots: dict[str, object] = {"current_step": stage}
    if stage is CoachingStage.REALITY:
        snapshots["reality"] = RealitySnapshot(
            facts="Hai hồ sơ đã gửi",
            present_state="Chưa có phỏng vấn",
            gap="Cần portfolio thể hiện năng lực",
            emotion="Lo lắng",
            barriers=("Portfolio chưa rõ",),
            resources=("Hai case study cũ",),
            prior_attempts=("Đã sửa CV",),
            assumptions_separated=True,
            influence_identified=True,
        )
    elif stage is CoachingStage.WILL:
        snapshots["will"] = WillSnapshot(
            chosen_action="Viết case study đầu tiên",
            starts_at="2026-08-22",
            due_at="2026-08-29",
            completion_evidence="Link case study đã xuất bản",
            commitment_score=8,
        )
    elif stage is CoachingStage.REVIEW:
        snapshots["review"] = ReviewSnapshot(
            takeaway="Tập trung vào phần mình ảnh hưởng",
            immediate_application="Viết dàn ý ngày mai",
            follow_up_disposition="Check-in sau 14 ngày",
        )
    return CoachingSessionState(session_id="complete").model_copy(update=snapshots)


def state_with_gate_evidence(
    stages: tuple[CoachingStage, ...] = (CoachingStage.GOAL,),
) -> CoachingSessionState:
    turns: list[SessionTurn] = []
    events: list[SessionGateEvent] = []
    for index, stage in enumerate(stages):
        question = SessionTurn(
            turn_id=f"q-{stage.value}",
            sequence=index * 2,
            actor="coach",
            content="Bạn có xác nhận nội dung bước này là đúng không?",
        )
        response = SessionTurn(
            turn_id=f"u-{stage.value}",
            sequence=index * 2 + 1,
            actor="coachee",
            content="Có",
        )
        turns.extend((question, response))
        events.append(
            SessionGateEvent(
                stage=stage,
                revision=1,
                closing_question_turn_id=question.turn_id,
                question_sequence=question.sequence,
                response_turn_id=response.turn_id,
                response_sequence=response.sequence,
                exact_response=response.content,
                answer=GateAnswer.YES,
                valid=True,
            )
        )
    return CoachingSessionState(
        session_id="gate-evidence",
        turn_ledger=tuple(turns),
        gate_events=tuple(events),
    )


def test_pre_coaching_requires_emotion_exploration_when_emotion_is_relevant() -> None:
    state = CoachingSessionState(
        session_id="s",
        pre_coaching=PreCoachingSnapshot(
            ready=True,
            coaching_understood=True,
            roles_agreed=True,
            boundaries_agreed=True,
            emotion_relevant=True,
            emotion_explored=False,
        ),
    )

    assert not stage_is_complete(state)
    assert stage_is_complete(
        state.model_copy(
            update={
                "pre_coaching": state.pre_coaching.model_copy(
                    update={"emotion_explored": True}
                )
            }
        )
    )


@pytest.mark.parametrize(
    "update",
    [
        {"facts": ""},
        {"present_state": ""},
        {"gap": ""},
        {"emotion": ""},
        {"barriers": ()},
        {"resources": ()},
        {"prior_attempts": ()},
        {"assumptions_separated": False},
        {"influence_identified": False},
    ],
)
def test_reality_requires_every_fact_emotion_gap_resource_and_influence_predicate(
    update: dict[str, object],
) -> None:
    complete = completed_state(CoachingStage.REALITY).reality
    state = completed_state(CoachingStage.REALITY).model_copy(
        update={"reality": complete.model_copy(update=update)}
    )

    assert not stage_is_complete(state)


@pytest.mark.parametrize(
    "update",
    [
        {"chosen_action": ""},
        {"starts_at": ""},
        {"due_at": ""},
        {"completion_evidence": ""},
        {"commitment_score": None},
    ],
)
def test_will_requires_action_timing_evidence_and_score_1_to_10(
    update: dict[str, object],
) -> None:
    complete = completed_state(CoachingStage.WILL).will
    state = completed_state(CoachingStage.WILL).model_copy(
        update={"will": complete.model_copy(update=update)}
    )

    assert not stage_is_complete(state)


def test_review_requires_takeaway_application_follow_up_and_valid_grow_gates() -> None:
    state = completed_state(CoachingStage.REVIEW)
    assert not stage_is_complete(state)
    evidence = state_with_gate_evidence((
        CoachingStage.GOAL,
        CoachingStage.REALITY,
        CoachingStage.OPTIONS,
        CoachingStage.WILL,
    ))

    assert stage_is_complete(
        state.model_copy(
            update={
                "turn_ledger": evidence.turn_ledger,
                "gate_events": evidence.gate_events,
            }
        )
    )


def test_confirmed_steps_reconstructs_a_valid_gate_from_trusted_ledger_turns() -> None:
    state = state_with_gate_evidence()

    assert state.confirmed_steps == (CoachingStage.GOAL,)


def test_fabricated_valid_gate_event_without_ledger_turns_cannot_confirm_a_step() -> (
    None
):
    state = state_with_gate_evidence().model_copy(update={"turn_ledger": ()})

    assert state.confirmed_steps == ()


def test_gate_event_requires_actual_adjacent_coach_then_coachee_turns() -> None:
    state = state_with_gate_evidence()
    question, response = state.turn_ledger
    non_adjacent = (
        question,
        SessionTurn(
            turn_id="u-intervening",
            sequence=11,
            actor="coachee",
            content="Tôi muốn bổ sung một ý",
        ),
        SessionTurn(
            turn_id="q-follow-up",
            sequence=12,
            actor="coach",
            content="Bạn muốn bổ sung điều gì?",
        ),
        response.model_copy(update={"sequence": 13}),
    )
    non_adjacent_event = state.gate_events[0].model_copy(
        update={"response_sequence": 13}
    )
    swapped_actors = (
        question.model_copy(update={"actor": "coachee"}),
        response.model_copy(update={"actor": "coach"}),
    )

    assert (
        state.model_copy(
            update={
                "turn_ledger": non_adjacent,
                "gate_events": (non_adjacent_event,),
            }
        ).confirmed_steps
        == ()
    )
    assert (
        state.model_copy(update={"turn_ledger": swapped_actors}).confirmed_steps == ()
    )


def test_gate_event_requires_exact_ledger_response_and_reclassified_yes() -> None:
    state = state_with_gate_evidence()
    question, response = state.turn_ledger
    mismatched_event = state.gate_events[0].model_copy(update={"exact_response": "Yes"})
    forged_yes_event = state.gate_events[0].model_copy(
        update={"exact_response": "Không"}
    )
    no_response = response.model_copy(update={"content": "Không"})

    assert (
        state.model_copy(update={"gate_events": (mismatched_event,)}).confirmed_steps
        == ()
    )
    assert (
        state.model_copy(
            update={
                "turn_ledger": (question, no_response),
                "gate_events": (forged_yes_event,),
            }
        ).confirmed_steps
        == ()
    )


def test_gate_event_requires_a_valid_closing_question_from_the_ledger() -> None:
    state = state_with_gate_evidence()
    question, response = state.turn_ledger
    open_question = question.model_copy(
        update={"content": "Bạn muốn khám phá thêm điều gì?"}
    )

    assert (
        state.model_copy(
            update={"turn_ledger": (open_question, response)}
        ).confirmed_steps
        == ()
    )


def test_gate_event_revision_must_match_the_current_stage_revision() -> None:
    state = state_with_gate_evidence()
    revised = state.model_copy(
        update={
            "revisions": tuple(
                item.model_copy(update={"revision": 2})
                if item.stage is CoachingStage.GOAL
                else item
                for item in state.revisions
            )
        }
    )

    assert revised.confirmed_steps == ()


@pytest.mark.parametrize("malformation", ["missing", "duplicate", "reordered"])
def test_session_revision_vector_contains_each_of_the_six_stages_exactly_once(
    malformation: str,
) -> None:
    revisions = CoachingSessionState(session_id="valid").revisions
    if malformation == "missing":
        malformed = revisions[:-1]
    elif malformation == "duplicate":
        malformed = revisions[:-1] + (revisions[0],)
    else:
        malformed = tuple(reversed(revisions))

    with pytest.raises(ValidationError, match="revision vector"):
        CoachingSessionState(session_id="invalid", revisions=malformed)
