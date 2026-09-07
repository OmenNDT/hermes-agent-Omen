from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from pydantic import ValidationError

from hermes_coach.application.record_confirmation_service import (
    ConfirmationApplication,
    ConfirmationCommand,
    RecordAction,
    RecordConfirmationAuthority,
)
from hermes_coach.contracts.runtime_contract import (
    CandidateRecord,
    CoachingStage,
    RecordKind,
)
from hermes_coach.domain.session_state import CoachingSessionState


NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
LOCAL_USER_ID = "local-user-1"


def pending_state(session_id: str = "session-1") -> CoachingSessionState:
    return CoachingSessionState(
        session_id=session_id,
        current_step=CoachingStage.REVIEW,
        candidate_records=(
            CandidateRecord(
                candidate_id="candidate-1",
                kind=RecordKind.INSIGHT,
                value="Tôi đang tập trung vào phần ngoài phạm vi ảnh hưởng",
                source_turn_id="turn-1",
                coaching_stage=CoachingStage.REVIEW,
                stage_revision=1,
            ),
            CandidateRecord(
                candidate_id="candidate-2",
                kind=RecordKind.COMMITMENT,
                value="Viết dàn ý vào sáng mai",
                source_turn_id="turn-2",
                coaching_stage=CoachingStage.REVIEW,
                stage_revision=1,
            ),
        ),
    )


def issue_command(
    authority: RecordConfirmationAuthority,
    state: CoachingSessionState,
    *,
    command_id: str = "command-1",
    candidate_id: str = "candidate-1",
    action: RecordAction = RecordAction.ACCEPT,
    edited_value: str | None = None,
) -> ConfirmationCommand:
    intent = authority.issue_intent(
        local_user_id=LOCAL_USER_ID,
        state=state,
        candidate_id=candidate_id,
        action=action,
        edited_value=edited_value,
        now=NOW,
    )
    return ConfirmationCommand(
        command_id=command_id,
        intent_token=intent.token,
        candidate_id=candidate_id,
        action=action,
        edited_value=edited_value,
    )


def test_authority_issues_only_an_opaque_short_lived_intent() -> None:
    authority = RecordConfirmationAuthority(intent_ttl=timedelta(seconds=30))
    intent = authority.issue_intent(
        local_user_id=LOCAL_USER_ID,
        state=pending_state(),
        candidate_id="candidate-1",
        action=RecordAction.ACCEPT,
        now=NOW,
    )

    assert set(intent.model_dump()) == {"token", "expires_at"}
    assert len(intent.token) >= 32
    assert all(
        bound_value not in intent.token
        for bound_value in (LOCAL_USER_ID, "session-1", "candidate-1", "accept")
    )
    assert intent.expires_at == NOW + timedelta(seconds=30)


def test_confirmation_has_no_arbitrary_ui_event_or_self_claimed_ui_source() -> None:
    authority = RecordConfirmationAuthority()

    assert not hasattr(authority, "record_ui_event")
    with pytest.raises(ValidationError):
        ConfirmationCommand.model_validate({
            "command_id": "command-1",
            "intent_token": "x" * 32,
            "candidate_id": "candidate-1",
            "action": "accept",
            "ui_event_id": "arbitrary-string",
            "source": "ui",
        })


def test_accept_and_exact_edited_payload_apply_one_pending_candidate() -> None:
    state = pending_state()

    accept_authority = RecordConfirmationAuthority()
    accepted = accept_authority.apply(
        state,
        issue_command(accept_authority, state),
        local_user_id=LOCAL_USER_ID,
        now=NOW + timedelta(seconds=1),
    )

    edit_authority = RecordConfirmationAuthority()
    raw_edit = "  Tôi sẽ tập trung vào phần mình ảnh hưởng  "
    edited = edit_authority.apply(
        state,
        issue_command(
            edit_authority,
            state,
            action=RecordAction.EDIT,
            edited_value=raw_edit,
        ),
        local_user_id=LOCAL_USER_ID,
        now=NOW + timedelta(seconds=1),
    )

    assert accepted.result.status == "confirmed"
    assert tuple(item.candidate_id for item in accepted.state.candidate_records) == (
        "candidate-2",
    )
    assert edited.result.value == raw_edit.strip()


def test_forged_intent_token_is_rejected() -> None:
    authority = RecordConfirmationAuthority()
    command = ConfirmationCommand(
        command_id="command-1",
        intent_token="x" * 32,
        candidate_id="candidate-1",
        action=RecordAction.ACCEPT,
    )

    with pytest.raises(PermissionError, match="backend-issued"):
        authority.apply(
            pending_state(),
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW,
        )


def test_intent_is_bound_to_the_trusted_local_user() -> None:
    state = pending_state()
    authority = RecordConfirmationAuthority()
    command = issue_command(authority, state)

    with pytest.raises(PermissionError, match="does not match"):
        authority.apply(
            state,
            command,
            local_user_id="different-local-user",
            now=NOW + timedelta(seconds=1),
        )

    assert (
        authority.apply(
            state,
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        ).result.candidate_id
        == "candidate-1"
    )


def test_intent_cannot_cross_sessions_even_when_candidate_id_matches() -> None:
    state = pending_state()
    authority = RecordConfirmationAuthority()
    command = issue_command(authority, state)

    with pytest.raises(PermissionError, match="does not match"):
        authority.apply(
            pending_state(session_id="session-2"),
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        )

    assert (
        authority.apply(
            state,
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        ).result.candidate_id
        == "candidate-1"
    )


def test_intent_cannot_be_retargeted_to_another_candidate() -> None:
    state = pending_state()
    authority = RecordConfirmationAuthority()
    command = issue_command(authority, state)
    retargeted = command.model_copy(update={"candidate_id": "candidate-2"})

    with pytest.raises(PermissionError, match="does not match"):
        authority.apply(
            state,
            retargeted,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        )

    assert (
        authority.apply(
            state,
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        ).result.candidate_id
        == "candidate-1"
    )


def test_intent_cannot_change_the_exact_action() -> None:
    state = pending_state()
    authority = RecordConfirmationAuthority()
    command = issue_command(authority, state)
    changed_action = command.model_copy(update={"action": RecordAction.DISCARD})

    with pytest.raises(PermissionError, match="does not match"):
        authority.apply(
            state,
            changed_action,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        )

    assert (
        authority.apply(
            state,
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        ).result.status
        == "confirmed"
    )


def test_intent_cannot_change_even_whitespace_in_the_edited_payload() -> None:
    state = pending_state()
    authority = RecordConfirmationAuthority()
    command = issue_command(
        authority,
        state,
        action=RecordAction.EDIT,
        edited_value="Nội dung đã sửa",
    )
    changed_payload = command.model_copy(update={"edited_value": " Nội dung đã sửa "})

    with pytest.raises(PermissionError, match="does not match"):
        authority.apply(
            state,
            changed_payload,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        )

    assert (
        authority.apply(
            state,
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        ).result.value
        == "Nội dung đã sửa"
    )


def test_expired_intent_fails_closed_at_the_expiry_boundary() -> None:
    state = pending_state()
    authority = RecordConfirmationAuthority(intent_ttl=timedelta(seconds=30))
    command = issue_command(authority, state)

    with pytest.raises(PermissionError, match="expired"):
        authority.apply(
            state,
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=30),
        )

    with pytest.raises(PermissionError, match="backend-issued"):
        authority.apply(
            state,
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=31),
        )


def test_apply_requires_the_same_current_pending_candidate_and_revision() -> None:
    state = pending_state()
    authority = RecordConfirmationAuthority()
    command = issue_command(authority, state)
    stale = state.model_copy(
        update={
            "revisions": tuple(
                revision.model_copy(update={"revision": 2})
                if revision.stage is CoachingStage.REVIEW
                else revision
                for revision in state.revisions
            )
        }
    )

    with pytest.raises(ValueError, match="stale"):
        authority.apply(
            stale,
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        )

    missing = state.model_copy(update={"candidate_records": ()})
    with pytest.raises(ValueError, match="pending"):
        authority.apply(
            missing,
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        )

    current_revision_with_changed_candidate = stale.model_copy(
        update={
            "candidate_records": (
                state.candidate_records[0].model_copy(
                    update={"value": "Nội dung đã đổi", "stage_revision": 2}
                ),
                state.candidate_records[1],
            )
        }
    )
    with pytest.raises(ValueError, match="changed"):
        authority.apply(
            current_revision_with_changed_candidate,
            command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        )


def test_success_consumes_intent_command_and_candidate_once() -> None:
    state = pending_state()
    authority = RecordConfirmationAuthority()
    first_command = issue_command(authority, state, command_id="same-command")
    applied = authority.apply(
        state,
        first_command,
        local_user_id=LOCAL_USER_ID,
        now=NOW + timedelta(seconds=1),
    )

    with pytest.raises(PermissionError, match="backend-issued"):
        authority.apply(
            state,
            first_command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="resolved"):
        authority.issue_intent(
            local_user_id=LOCAL_USER_ID,
            state=state,
            candidate_id="candidate-1",
            action=RecordAction.ACCEPT,
            now=NOW + timedelta(seconds=1),
        )

    second_command = issue_command(
        authority,
        applied.state,
        command_id="same-command",
        candidate_id="candidate-2",
    )
    with pytest.raises(ValueError, match="command_id"):
        authority.apply(
            applied.state,
            second_command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        )

    fresh_command = second_command.model_copy(update={"command_id": "command-2"})
    assert (
        authority.apply(
            applied.state,
            fresh_command,
            local_user_id=LOCAL_USER_ID,
            now=NOW + timedelta(seconds=1),
        ).result.candidate_id
        == "candidate-2"
    )


def test_concurrent_replay_has_exactly_one_success() -> None:
    state = pending_state()
    authority = RecordConfirmationAuthority()
    command = issue_command(authority, state)
    start = Barrier(2)

    def race_apply() -> ConfirmationApplication | Exception:
        start.wait()
        try:
            return authority.apply(
                state,
                command,
                local_user_id=LOCAL_USER_ID,
                now=NOW + timedelta(seconds=1),
            )
        except Exception as exc:  # noqa: BLE001 - the losing replay is the assertion
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(lambda _: race_apply(), range(2)))

    assert sum(isinstance(item, ConfirmationApplication) for item in outcomes) == 1
    assert sum(isinstance(item, PermissionError) for item in outcomes) == 1


@pytest.mark.parametrize(
    "intent_ttl",
    [timedelta(0), timedelta(seconds=-1), timedelta(minutes=6)],
)
def test_intent_ttl_must_be_positive_and_short(intent_ttl: timedelta) -> None:
    with pytest.raises(ValueError, match="intent_ttl"):
        RecordConfirmationAuthority(intent_ttl=intent_ttl)
