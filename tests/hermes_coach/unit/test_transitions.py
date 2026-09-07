from __future__ import annotations

import pytest

from hermes_coach.contracts.runtime_contract import CoachingStage, GateAnswer
from hermes_coach.domain.models import (
    GoalSnapshot,
    OptionAssessment,
    OptionIdea,
    OptionsSnapshot,
    PreCoachingSnapshot,
    RealitySnapshot,
    ReviewSnapshot,
    WillSnapshot,
)
from hermes_coach.domain.enums import FunnelStage
from hermes_coach.domain.session_state import CoachingSessionState
from hermes_coach.domain.transitions import (
    append_trusted_turn,
    answer_closing_gate,
    classify_gate_answer,
    open_closing_gate,
    return_to_pre_coaching,
    rollback_to,
)
from tests.hermes_coach.unit.test_goal_rules import valid_goal


OPTIONS_BASELINE = (
    OptionIdea(text="Xin tăng lương", mechanism="đàm phán lương"),
)
OPTIONS_CANDIDATE = OptionIdea(
    text="Xây portfolio để đổi vai trò",
    mechanism="xây portfolio",
    coachee_generated=True,
    material_difference_confirmed=True,
)


def with_options_evidence(state: CoachingSessionState) -> CoachingSessionState:
    if any(turn.turn_id == "options-candidate" for turn in state.turn_ledger):
        return state
    sequence = state.turn_ledger[-1].sequence + 1 if state.turn_ledger else 0
    for turn_id, actor, content in (
        ("options-evoke", "coach", "Bạn còn có thể làm gì khác?"),
        ("options-candidate", "coachee", OPTIONS_CANDIDATE.text),
        ("options-confirm-question", "coach", "Đây có phải một cơ chế khác không?"),
        ("options-confirmation", "coachee", "Đúng, đây là một cơ chế khác."),
    ):
        state = append_trusted_turn(
            state,
            turn_id=turn_id,
            sequence=sequence,
            actor=actor,
            content=content,
        )
        sequence += 1
    return state


@pytest.mark.parametrize(
    "response",
    [
        "Yes",
        " yes. ",
        "Có",
        "có!",
        "Đồng ý",
        "Yes, tôi hiểu và đồng ý cách làm việc.",
        "Yes, phần tổng kết này đúng và tôi đồng ý kết thúc.",
    ],
)
def test_gate_classifier_accepts_only_unqualified_explicit_agreement(response: str) -> None:
    assert classify_gate_answer(response) is GateAnswer.YES


@pytest.mark.parametrize(
    ("response", "answer"),
    [
        ("Không", GateAnswer.NO),
        ("No", GateAnswer.NO),
        ("Không, mục tiêu vẫn chưa đúng.", GateAnswer.NO),
        ("No, phần tổng kết chưa phản ánh bài học chính.", GateAnswer.NO),
        ("Có lẽ", GateAnswer.UNCLEAR),
        ("Yes, nhưng tôi chưa chắc", GateAnswer.UNCLEAR),
        ("yes no", GateAnswer.UNCLEAR),
        ("Yes I guess", GateAnswer.UNCLEAR),
        ("đồng ý tạm thời", GateAnswer.UNCLEAR),
        ("Đồng ý nếu đổi deadline", GateAnswer.UNCLEAR),
        ("Tôi chưa rõ", GateAnswer.UNCLEAR),
    ],
)
def test_gate_classifier_rejects_conditional_or_contradictory_replies(
    response: str, answer: GateAnswer
) -> None:
    assert classify_gate_answer(response) is answer


def completed_state(stage: CoachingStage) -> CoachingSessionState:
    state = CoachingSessionState(session_id="s-1")
    state = state.model_copy(
        update={
            "pre_coaching": PreCoachingSnapshot(
                ready=True,
                coaching_understood=True,
                roles_agreed=True,
                boundaries_agreed=True,
            ),
            "goal": valid_goal(),
            "reality": RealitySnapshot(
                facts="Hai hồ sơ đã gửi",
                present_state="Chưa có phỏng vấn",
                gap="Cần portfolio thể hiện năng lực",
                emotion="Lo lắng",
                barriers=("Portfolio chưa rõ",),
                resources=("Hai case study cũ",),
                prior_attempts=("Đã sửa CV",),
                assumptions_separated=True,
                influence_identified=True,
            ),
            "options": OptionsSnapshot(
                canonical_baseline=OPTIONS_BASELINE,
                assessments=(
                    OptionAssessment(
                        session_id="s-1",
                        stage_revision=1,
                        baseline=OPTIONS_BASELINE,
                        candidate=OPTIONS_CANDIDATE,
                        candidate_source_turn_id="options-candidate",
                        confirmation_turn_id="options-confirmation",
                    ),
                ),
            ),
            "will": WillSnapshot(
                chosen_action="Viết case study đầu tiên",
                starts_at="2026-08-22",
                due_at="2026-08-29",
                completion_evidence="Link case study đã xuất bản",
                commitment_score=8,
            ),
            "review": ReviewSnapshot(
                takeaway="Tập trung vào phần mình ảnh hưởng",
                immediate_application="Viết dàn ý ngày mai",
                follow_up_disposition="Check-in sau 14 ngày",
            ),
            "current_step": stage,
        }
    )
    if stage is CoachingStage.OPTIONS:
        state = with_options_evidence(state)
    return state


def confirm_current_stage(state: CoachingSessionState, index: int) -> CoachingSessionState:
    if state.current_step is CoachingStage.OPTIONS:
        state = with_options_evidence(state)
    question_id = f"q-{index}"
    question_sequence = (
        state.turn_ledger[-1].sequence + 1 if state.turn_ledger else index * 2
    )
    state = state.model_copy(update={"funnel_stage": FunnelStage.CLARIFY})
    opened = open_closing_gate(
        state, question_id, question_sequence=question_sequence
    )
    result = answer_closing_gate(
        opened,
        response_turn_id=f"u-{index}",
        response_sequence=question_sequence + 1,
        in_reply_to_turn_id=question_id,
        exact_response="Có",
    )
    assert result.advanced
    return result.state


def state_at_stage(stage: CoachingStage) -> CoachingSessionState:
    state = completed_state(CoachingStage.PRE_COACHING)
    while state.current_step is not stage:
        state = confirm_current_stage(state, len(state.gate_events) + 20)
    if stage is CoachingStage.OPTIONS:
        state = with_options_evidence(state)
    return state


def test_all_six_steps_require_complete_state_and_explicit_yes_in_order() -> None:
    state = completed_state(CoachingStage.PRE_COACHING)
    for index, expected in enumerate(
        (
            CoachingStage.GOAL,
            CoachingStage.REALITY,
            CoachingStage.OPTIONS,
            CoachingStage.WILL,
            CoachingStage.REVIEW,
        )
    ):
        state = confirm_current_stage(state, index)
        assert state.current_step is expected

    state = confirm_current_stage(state, 5)
    assert state.ended
    assert len([event for event in state.gate_events if event.valid]) == 6
    assert state.turn_ledger[-2].content.endswith("không?")
    assert state.turn_ledger[-1].content == "Có"


@pytest.mark.parametrize("stage", tuple(CoachingStage))
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("Không", GateAnswer.NO),
        ("Tôi chưa rõ", GateAnswer.UNCLEAR),
        ("Yes, nhưng tôi muốn đổi nội dung", GateAnswer.UNCLEAR),
    ],
)
def test_every_step_stays_on_no_unclear_or_conditional_response(
    stage: CoachingStage, response: str, expected: GateAnswer
) -> None:
    state = state_at_stage(stage)
    state = state.model_copy(update={"funnel_stage": FunnelStage.CLARIFY})
    question_sequence = (
        state.turn_ledger[-1].sequence + 1 if state.turn_ledger else 10
    )
    opened = open_closing_gate(
        state, "closing-question", question_sequence=question_sequence
    )

    result = answer_closing_gate(
        opened,
        response_turn_id="response",
        response_sequence=question_sequence + 1,
        in_reply_to_turn_id="closing-question",
        exact_response=response,
    )

    assert result.answer is expected
    assert not result.advanced
    assert result.state.current_step is stage


def test_no_unclear_or_non_immediate_response_stays_in_current_revision() -> None:
    original = completed_state(CoachingStage.PRE_COACHING)
    original = original.model_copy(update={"funnel_stage": FunnelStage.CLARIFY})
    opened = open_closing_gate(original, "q-1", question_sequence=10)

    no_result = answer_closing_gate(
        opened,
        response_turn_id="u-1",
        response_sequence=11,
        in_reply_to_turn_id="q-1",
        exact_response="Không",
    )
    unclear = answer_closing_gate(
        open_closing_gate(original, "q-2", question_sequence=20),
        response_turn_id="u-2",
        response_sequence=21,
        in_reply_to_turn_id="q-2",
        exact_response="Có lẽ",
    )
    stale = answer_closing_gate(
        open_closing_gate(original, "q-3", question_sequence=30),
        response_turn_id="u-3",
        response_sequence=31,
        in_reply_to_turn_id="some-other-turn",
        exact_response="Có",
    )

    assert not no_result.advanced and no_result.state.current_step is CoachingStage.PRE_COACHING
    assert not unclear.advanced and unclear.answer is GateAnswer.UNCLEAR
    assert not stale.advanced and stale.reason == "response_not_immediate"


def test_yes_cannot_open_an_incomplete_step() -> None:
    state = CoachingSessionState(session_id="s-1")

    with pytest.raises(ValueError, match="incomplete"):
        open_closing_gate(state, "q-1", question_sequence=1)


def test_closing_gate_requires_sequential_funnel_completion() -> None:
    state = completed_state(CoachingStage.GOAL)

    with pytest.raises(ValueError, match="funnel"):
        open_closing_gate(state, "q-1", question_sequence=1)


def test_gate_requires_the_immediately_adjacent_distinct_response_turn() -> None:
    state = completed_state(CoachingStage.GOAL).model_copy(
        update={"funnel_stage": FunnelStage.CLARIFY}
    )
    opened = open_closing_gate(state, "q-1", question_sequence=10)

    delayed = answer_closing_gate(
        opened,
        response_turn_id="u-1",
        response_sequence=15,
        in_reply_to_turn_id="q-1",
        exact_response="Có",
    )
    same_id = answer_closing_gate(
        opened,
        response_turn_id="q-1",
        response_sequence=11,
        in_reply_to_turn_id="q-1",
        exact_response="Có",
    )

    assert delayed.reason == "response_not_immediate"
    assert same_id.reason == "response_not_immediate"


def test_gate_adjacency_comes_from_the_aggregate_turn_ledger() -> None:
    state = completed_state(CoachingStage.GOAL).model_copy(
        update={"funnel_stage": FunnelStage.CLARIFY}
    )
    opened = open_closing_gate(state, "q-1", question_sequence=10)
    interrupted = append_trusted_turn(
        opened,
        turn_id="intervening-turn",
        sequence=11,
        actor="coachee",
        content="Một lượt xen giữa",
    )

    forged_adjacent = answer_closing_gate(
        interrupted,
        response_turn_id="u-1",
        response_sequence=11,
        in_reply_to_turn_id="q-1",
        exact_response="Có",
    )

    assert tuple(turn.turn_id for turn in opened.turn_ledger) == ("q-1",)
    assert forged_adjacent.reason == "response_not_immediate"
    assert not forged_adjacent.advanced
    assert forged_adjacent.state.current_step is CoachingStage.GOAL


def test_arbitrary_rollback_invalidates_target_and_downstream_then_replays_sequentially() -> None:
    state = completed_state(CoachingStage.PRE_COACHING)
    for index in range(4):
        state = confirm_current_stage(state, index)
    assert state.current_step is CoachingStage.WILL

    rolled = rollback_to(state, CoachingStage.GOAL, reason="Mục tiêu không còn phù hợp")

    assert rolled.current_step is CoachingStage.GOAL
    assert {
        item.stage: item.revision for item in rolled.revisions
    } == {
        CoachingStage.PRE_COACHING: 1,
        CoachingStage.GOAL: 2,
        CoachingStage.REALITY: 2,
        CoachingStage.OPTIONS: 2,
        CoachingStage.WILL: 2,
        CoachingStage.REVIEW: 2,
    }
    assert rolled.confirmed_steps == (CoachingStage.PRE_COACHING,)
    assert all(
        not event.valid
        for event in rolled.gate_events
        if event.stage in {
            CoachingStage.GOAL,
            CoachingStage.REALITY,
            CoachingStage.OPTIONS,
            CoachingStage.WILL,
        }
    )
    rolled = rolled.model_copy(update={"goal": valid_goal()})
    replayed = confirm_current_stage(rolled, 9)
    assert replayed.current_step is CoachingStage.REALITY


@pytest.mark.parametrize("target", [CoachingStage.PRE_COACHING, CoachingStage.REVIEW])
def test_targeted_rollback_is_limited_to_grow(target: CoachingStage) -> None:
    with pytest.raises(ValueError, match="G/R/O/W"):
        rollback_to(completed_state(CoachingStage.WILL), target, reason="test")


def test_unready_or_distressed_coachee_returns_to_fresh_pre_coaching_revision() -> None:
    state = completed_state(CoachingStage.PRE_COACHING)
    state = confirm_current_stage(state, 1)
    assert state.current_step is CoachingStage.GOAL

    returned = return_to_pre_coaching(state, reason="Coachee chưa sẵn sàng")

    assert returned.current_step is CoachingStage.PRE_COACHING
    assert all(item.revision == 2 for item in returned.revisions)
    assert returned.confirmed_steps == ()
    assert returned.goal is None
