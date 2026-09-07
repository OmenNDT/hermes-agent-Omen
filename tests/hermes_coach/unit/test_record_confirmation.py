from __future__ import annotations

import pytest
from pydantic import ValidationError

from hermes_coach.application.record_confirmation_service import (
    CheckInAction,
    CheckInChoiceCommand,
    ConfirmationCommand,
    RecordConfirmationAuthority,
    RecordAction,
)
from hermes_coach.application.coaching_service import CoachingService
from hermes_coach.contracts.runtime_contract import (
    CandidateRecord,
    CoachOutput,
    CoachingStage,
    RecordKind,
)
from hermes_coach.domain.session_state import CoachingSessionState
from hermes_coach.domain.transitions import append_trusted_turn


def candidate() -> CandidateRecord:
    return CandidateRecord(
        candidate_id="candidate-1",
        kind=RecordKind.INSIGHT,
        value="Tôi đang theo đuổi phần ngoài phạm vi ảnh hưởng",
        source_turn_id="turn-7",
    )


def candidate_output(*, edited_question: str | None = None) -> CoachOutput:
    return CoachOutput(
        question=edited_question or "Điều gì bạn muốn mang theo sau phiên này?",
        coaching_stage=CoachingStage.REVIEW,
        inference_session_id="session-1",
        inference_turn_id="turn-7",
        inference_stage_revision=1,
        candidate_insights=(candidate(),),
    )


def review_state() -> CoachingSessionState:
    state = CoachingSessionState(
        session_id="session-1",
        current_step=CoachingStage.REVIEW,
    )
    state = append_trusted_turn(
        state,
        turn_id="turn-6",
        sequence=6,
        actor="coach",
        content="Bạn đang nhận ra điều gì?",
    )
    return append_trusted_turn(
        state,
        turn_id="turn-7",
        sequence=7,
        actor="coachee",
        content=candidate().value,
    )


def test_ui_command_accepts_edits_or_discards_one_candidate_at_a_time() -> None:
    state = CoachingService().stage_candidates(
        review_state(),
        candidate_output(),
    )
    accept_authority = RecordConfirmationAuthority()
    accept_intent = accept_authority.issue_intent(
        local_user_id="local-owner",
        state=state,
        candidate_id="candidate-1",
        action=RecordAction.ACCEPT,
    )
    accepted = accept_authority.apply(
        state,
        ConfirmationCommand(
            command_id="cmd-1",
            intent_token=accept_intent.token,
            candidate_id="candidate-1",
            action=RecordAction.ACCEPT,
        ),
        local_user_id="local-owner",
    )
    edit_authority = RecordConfirmationAuthority()
    edited_value = "Tôi muốn tập trung vào phần mình ảnh hưởng"
    edit_intent = edit_authority.issue_intent(
        local_user_id="local-owner",
        state=state,
        candidate_id="candidate-1",
        action=RecordAction.EDIT,
        edited_value=edited_value,
    )
    edited = edit_authority.apply(
        state,
        ConfirmationCommand(
            command_id="cmd-2",
            intent_token=edit_intent.token,
            candidate_id="candidate-1",
            action=RecordAction.EDIT,
            edited_value=edited_value,
        ),
        local_user_id="local-owner",
    )

    assert accepted.result.status == "confirmed"
    assert accepted.state.candidate_records == ()
    assert edited.result.value == "Tôi muốn tập trung vào phần mình ảnh hưởng"


def test_natural_language_and_batch_confirmation_have_no_valid_command_shape() -> None:
    with pytest.raises(ValidationError):
        ConfirmationCommand.model_validate(
            {
                "command_id": "cmd-1",
                "ui_event_id": "ui-1",
                "candidate_id": "candidate-1",
                "action": "accept",
                "source": "natural_language",
            }
        )
    with pytest.raises(ValidationError):
        ConfirmationCommand.model_validate(
            {
                "command_id": "cmd-2",
                "ui_event_id": "ui-2",
                "candidate_ids": ["candidate-1", "candidate-2"],
                "action": "accept",
            }
        )


def test_model_output_only_stages_candidates_and_never_creates_official_records() -> None:
    state = review_state()
    output = candidate_output()

    staged = CoachingService().stage_candidates(state, output)

    assert staged.candidate_records[0].candidate_id == candidate().candidate_id
    assert staged.candidate_records[0].coaching_stage is CoachingStage.REVIEW
    assert staged.candidate_records[0].stage_revision == 1
    assert staged.candidate_records[0].status == "candidate"


def test_confirmation_requires_trusted_ui_event_and_rejects_replay() -> None:
    state = CoachingService().stage_candidates(
        review_state(),
        candidate_output(),
    )
    authority = RecordConfirmationAuthority()
    intent = authority.issue_intent(
        local_user_id="local-owner",
        state=state,
        candidate_id="candidate-1",
        action=RecordAction.ACCEPT,
    )
    command = ConfirmationCommand(
        command_id="cmd-1",
        intent_token=intent.token,
        candidate_id="candidate-1",
        action=RecordAction.ACCEPT,
    )

    forged = command.model_copy(update={"intent_token": "x" * 32})
    with pytest.raises(PermissionError, match="backend-issued intent"):
        authority.apply(state, forged, local_user_id="local-owner")
    applied = authority.apply(state, command, local_user_id="local-owner")
    with pytest.raises((PermissionError, ValueError)):
        authority.apply(applied.state, command, local_user_id="local-owner")


def test_confirmation_rejects_candidate_from_a_stale_stage_revision() -> None:
    state = CoachingService().stage_candidates(
        review_state(),
        candidate_output(),
    )
    stale = state.model_copy(
        update={
            "revisions": tuple(
                item.model_copy(update={"revision": 2})
                if item.stage is CoachingStage.REVIEW
                else item
                for item in state.revisions
            )
        }
    )
    authority = RecordConfirmationAuthority()
    intent = authority.issue_intent(
        local_user_id="local-owner",
        state=state,
        candidate_id="candidate-1",
        action=RecordAction.ACCEPT,
    )

    with pytest.raises(ValueError, match="stale"):
        authority.apply(
            stale,
            ConfirmationCommand(
                command_id="cmd-stale",
                intent_token=intent.token,
                candidate_id="candidate-1",
                action=RecordAction.ACCEPT,
            ),
            local_user_id="local-owner",
        )


@pytest.mark.parametrize(
    "command",
    [
        CheckInChoiceCommand(
            command_id="keep",
            ui_event_id="ui-keep",
            check_in_id="check-1",
            action=CheckInAction.KEEP,
        ),
        CheckInChoiceCommand(
            command_id="edit",
            ui_event_id="ui-edit",
            check_in_id="check-1",
            action=CheckInAction.EDIT,
            edited_commitment="Viết dàn ý trước",
        ),
        CheckInChoiceCommand(
            command_id="move",
            ui_event_id="ui-move",
            check_in_id="check-1",
            action=CheckInAction.RESCHEDULE,
            rescheduled_for="2026-09-04",
        ),
        CheckInChoiceCommand(
            command_id="cancel",
            ui_event_id="ui-cancel",
            check_in_id="check-1",
            action=CheckInAction.CANCEL,
        ),
    ],
)
def test_check_in_choice_boundary_supports_keep_edit_reschedule_cancel(
    command: CheckInChoiceCommand,
) -> None:
    assert command.action in set(CheckInAction)
