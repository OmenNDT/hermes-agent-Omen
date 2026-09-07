from __future__ import annotations

import pytest

from hermes_coach.application.coaching_service import CoachingService
from hermes_coach.contracts.runtime_contract import (
    CandidateRecord,
    CoachOutput,
    CoachingStage,
    RecordKind,
)
from hermes_coach.domain.enums import FunnelStage, SafetyState
from hermes_coach.domain.session_state import CoachingSessionState, SessionTurn
from hermes_coach.prompt.regeneration import ValidatedDelivery
from tests.hermes_coach.unit.test_goal_rules import valid_goal


def completed_state(stage: CoachingStage) -> CoachingSessionState:
    state = CoachingSessionState(session_id="s-1", current_step=stage)
    if stage is CoachingStage.GOAL:
        return state.model_copy(update={"goal": valid_goal()})
    return state


def state_with_current_coachee_turn(
    *,
    session_id: str = "normal",
    stage: CoachingStage = CoachingStage.GOAL,
    turn_id: str = "turn-1",
    content: str = "Tôi muốn làm rõ mục tiêu nghề nghiệp.",
) -> CoachingSessionState:
    return CoachingSessionState(
        session_id=session_id,
        current_step=stage,
        turn_ledger=(
            SessionTurn(
                turn_id=turn_id,
                sequence=0,
                actor="coachee",
                content=content,
            ),
        ),
    )


def valid_output(
    stage: CoachingStage = CoachingStage.GOAL,
    *,
    session_id: str = "normal",
    turn_id: str = "turn-1",
    revision: int = 1,
) -> CoachOutput:
    return CoachOutput(
        question="Điều gì bạn muốn làm rõ thêm ở mục tiêu này?",
        coaching_stage=stage,
        inference_session_id=session_id,
        inference_turn_id=turn_id,
        inference_stage_revision=revision,
    )


def test_service_orchestrates_gate_open_answer_and_close_predicate() -> None:
    service = CoachingService()
    state = completed_state(CoachingStage.GOAL)
    state = service.advance_funnel(state, FunnelStage.DISCOVER)
    state = service.advance_funnel(state, FunnelStage.CLARIFY)

    assert service.can_close_current_step(state)
    opened = service.open_gate(
        state,
        question_turn_id="q-1",
        closing_question="Bạn có xác nhận mục tiêu này là đúng không?",
        question_sequence=10,
    )
    result = service.answer_gate(
        opened,
        response_turn_id="u-1",
        response_sequence=11,
        in_reply_to_turn_id="q-1",
        exact_response="Có",
    )

    assert result.advanced
    assert result.state.current_step is CoachingStage.REALITY


def test_service_wraps_targeted_rollback_and_readiness_reset() -> None:
    service = CoachingService()
    review = completed_state(CoachingStage.REVIEW)

    rolled = service.rollback(review, CoachingStage.GOAL, "Mục tiêu cần xác nhận lại")
    returned = service.return_to_pre_coaching(review, "Coachee chưa sẵn sàng")

    assert rolled.current_step is CoachingStage.GOAL
    assert returned.current_step is CoachingStage.PRE_COACHING


def test_service_validates_before_delivery_and_uses_bounded_regeneration() -> None:
    service = CoachingService()
    calls: list[tuple[str, ...]] = []
    sink: list[CoachOutput] = []
    state = state_with_current_coachee_turn()
    invalid = CoachOutput(
        question="Bạn nên nghỉ việc, đúng không?",
        coaching_stage=CoachingStage.GOAL,
        inference_session_id="normal",
        inference_turn_id="turn-1",
        inference_stage_revision=1,
    )

    delivery = service.validate_output(
        state,
        invalid,
        lambda reasons: calls.append(reasons) or valid_output(),
    )
    service.deliver(state, delivery, sink.append)

    assert calls
    assert sink == [valid_output()]


def test_no_commitment_never_synthesizes_a_will_gate_or_candidate() -> None:
    state = CoachingSessionState(
        session_id="no-commitment",
        current_step=CoachingStage.WILL,
    )

    assert not CoachingService().can_close_current_step(state)
    assert state.candidate_records == ()


@pytest.mark.parametrize(
    "safety_state", [SafetyState.POSSIBLE_CRISIS, SafetyState.URGENT]
)
def test_interrupted_safety_state_blocks_normal_output_and_candidate_staging(
    safety_state: SafetyState,
) -> None:
    service = CoachingService()
    normal = state_with_current_coachee_turn()
    interrupted = normal.model_copy(update={"safety_state": safety_state})
    output = CoachOutput(
        question="Điều gì bạn muốn làm rõ thêm ở mục tiêu này?",
        coaching_stage=CoachingStage.GOAL,
        inference_session_id="normal",
        inference_turn_id="turn-1",
        inference_stage_revision=1,
        candidate_goals=(
            CandidateRecord(
                candidate_id="goal-1",
                kind=RecordKind.GOAL,
                value="Xuất bản portfolio",
                source_turn_id="turn-1",
            ),
        ),
    )
    delivery = service.validate_output(normal, output, lambda _: output)
    sink: list[CoachOutput] = []

    with pytest.raises(ValueError, match="interrupted"):
        service.validate_output(interrupted, output, lambda _: output)
    with pytest.raises(ValueError, match="interrupted"):
        service.deliver(interrupted, delivery, sink.append)
    with pytest.raises(ValueError, match="interrupted"):
        service.stage_candidates(interrupted, output)

    assert sink == []


def test_candidate_staging_rejects_stale_async_provenance_instead_of_relabeling() -> (
    None
):
    state = state_with_current_coachee_turn(session_id="revised", turn_id="old-turn")
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
    stale_output = CoachOutput(
        question="Điều gì bạn muốn làm rõ thêm ở mục tiêu này?",
        coaching_stage=CoachingStage.GOAL,
        inference_session_id="revised",
        inference_turn_id="old-turn",
        inference_stage_revision=1,
        candidate_goals=(
            CandidateRecord(
                candidate_id="stale-goal",
                kind=RecordKind.GOAL,
                value="Mục tiêu từ revision cũ",
                source_turn_id="old-turn",
                coaching_stage=CoachingStage.GOAL,
                stage_revision=1,
            ),
        ),
    )

    with pytest.raises(ValueError, match="stale output provenance"):
        CoachingService().stage_candidates(revised, stale_output)


@pytest.mark.parametrize(
    ("provenance", "candidate_turn_id", "message"),
    [
        ((None, None, None), "turn-2", "inference provenance is required"),
        (("other-session", "turn-2", 1), "turn-2", "stale output provenance"),
        (("session-1", "turn-2", 2), "turn-2", "stale output provenance"),
        (("session-1", "turn-2", 1), "different-turn", "source turn"),
    ],
)
def test_candidate_staging_requires_current_output_and_source_turn_provenance(
    provenance: tuple[str | None, str | None, int | None],
    candidate_turn_id: str,
    message: str,
) -> None:
    session_id, turn_id, revision = provenance
    output = CoachOutput(
        question="Điều gì bạn muốn làm rõ thêm ở mục tiêu này?",
        coaching_stage=CoachingStage.GOAL,
        inference_session_id=session_id,
        inference_turn_id=turn_id,
        inference_stage_revision=revision,
        candidate_goals=(
            CandidateRecord(
                candidate_id="goal-2",
                kind=RecordKind.GOAL,
                value="Xuất bản portfolio",
                source_turn_id=candidate_turn_id,
            ),
        ),
    )

    with pytest.raises(ValueError, match=message):
        CoachingService().stage_candidates(
            state_with_current_coachee_turn(
                session_id="session-1",
                turn_id="turn-2",
            ),
            output,
        )


def test_candidate_staging_binds_current_verified_inference_provenance() -> None:
    state = state_with_current_coachee_turn(
        session_id="session-current",
        stage=CoachingStage.REVIEW,
        turn_id="turn-current",
    )
    output = CoachOutput(
        question="Điều gì bạn muốn mang theo sau phiên này?",
        coaching_stage=CoachingStage.REVIEW,
        inference_session_id="session-current",
        inference_turn_id="turn-current",
        inference_stage_revision=1,
        candidate_insights=(
            CandidateRecord(
                candidate_id="insight-current",
                kind=RecordKind.INSIGHT,
                value="Tập trung vào phần mình ảnh hưởng",
                source_turn_id="turn-current",
            ),
        ),
    )

    staged = CoachingService().stage_candidates(state, output)

    assert staged.candidate_records[0].coaching_stage is CoachingStage.REVIEW
    assert staged.candidate_records[0].stage_revision == 1


@pytest.mark.parametrize("boundary", ["validate", "stage", "deliver"])
@pytest.mark.parametrize("ledger_kind", ["missing", "coach", "not_current"])
def test_every_output_boundary_requires_a_trusted_current_coachee_ledger_turn(
    boundary: str,
    ledger_kind: str,
) -> None:
    output = valid_output()
    if ledger_kind == "missing":
        state = CoachingSessionState(
            session_id="normal", current_step=CoachingStage.GOAL
        )
    elif ledger_kind == "coach":
        state = CoachingSessionState(
            session_id="normal",
            current_step=CoachingStage.GOAL,
            turn_ledger=(
                SessionTurn(
                    turn_id="turn-1",
                    sequence=0,
                    actor="coach",
                    content="Bạn muốn tập trung vào điều gì?",
                ),
            ),
        )
    else:
        original = state_with_current_coachee_turn()
        state = original.model_copy(
            update={
                "turn_ledger": original.turn_ledger
                + (
                    SessionTurn(
                        turn_id="turn-2",
                        sequence=1,
                        actor="coach",
                        content="Bạn muốn làm rõ điều gì?",
                    ),
                    SessionTurn(
                        turn_id="turn-3",
                        sequence=2,
                        actor="coachee",
                        content="Tôi muốn làm rõ tiêu chí thành công.",
                    ),
                )
            }
        )
    service = CoachingService()

    with pytest.raises(ValueError, match="trusted current coachee ledger turn"):
        if boundary == "validate":
            service.validate_output(state, output, lambda _: output)
        elif boundary == "stage":
            service.stage_candidates(state, output)
        else:
            service.deliver(
                state,
                ValidatedDelivery(output=output, attempts=1),
                lambda _: None,
            )


@pytest.mark.parametrize(
    "output",
    [
        CoachOutput(
            question="Điều gì bạn muốn làm rõ thêm ở mục tiêu này?",
            coaching_stage=CoachingStage.GOAL,
        ),
        valid_output(session_id="another-session"),
        valid_output(revision=2),
        valid_output(stage=CoachingStage.REALITY),
    ],
)
def test_validation_requires_complete_current_session_stage_revision_provenance(
    output: CoachOutput,
) -> None:
    state = state_with_current_coachee_turn()

    with pytest.raises(ValueError, match="provenance|stage"):
        CoachingService().validate_output(state, output, lambda _: output)


def test_regenerated_output_must_preserve_current_inference_provenance() -> None:
    state = state_with_current_coachee_turn()
    invalid = valid_output().model_copy(
        update={"question": "Bạn nên nghỉ việc, đúng không?"}
    )
    stale_regeneration = valid_output(turn_id="fabricated-turn")

    with pytest.raises(ValueError, match="trusted current coachee ledger turn"):
        CoachingService().validate_output(
            state,
            invalid,
            lambda _: stale_regeneration,
        )


def test_validation_grounding_must_equal_the_trusted_inference_turn_content() -> None:
    state = state_with_current_coachee_turn(content="Tôi muốn tự chọn hướng đi.")

    with pytest.raises(ValueError, match="grounded coachee input"):
        CoachingService().validate_output(
            state,
            valid_output(),
            lambda _: valid_output(),
            grounded_coachee_input="Nội dung không có trong ledger",
        )


def test_delivery_rechecks_provenance_after_state_moves_or_revises() -> None:
    service = CoachingService()
    state = state_with_current_coachee_turn()
    output = valid_output()
    delivery = service.validate_output(state, output, lambda _: output)
    moved = state.model_copy(update={"current_step": CoachingStage.REALITY})
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
    sink: list[CoachOutput] = []

    with pytest.raises(ValueError, match="stage"):
        service.deliver(moved, delivery, sink.append)
    with pytest.raises(ValueError, match="stale output provenance"):
        service.deliver(revised, delivery, sink.append)

    assert sink == []
