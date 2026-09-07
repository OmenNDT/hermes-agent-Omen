from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from hermes_coach.contracts.egress_contract import (
    EgressConsentAction,
    EgressConsentDecision,
)
from hermes_coach.contracts.lifecycle_contract import (
    AbandonedGoalReuse,
    CheckInRecovery,
    GoalLifecycleStatus,
    RetentionAction,
    RetentionDecision,
    RetentionRecordKind,
    SafetyDecision,
    SafetyLevel,
    SafetyTransition,
    SessionControlAction,
    SessionLifecycleDecision,
)
from hermes_coach.contracts.runtime_contract import CoachingStage


def test_pause_and_resume_preserve_stage_and_gate_history() -> None:
    gates = ("pre:yes", "goal:yes")
    paused = SessionLifecycleDecision(
        action=SessionControlAction.PAUSE,
        current_stage=CoachingStage.REALITY,
        next_stage=CoachingStage.REALITY,
        gate_events_before=gates,
        gate_events_after=gates,
    )
    resumed = SessionLifecycleDecision(
        action=SessionControlAction.RESUME,
        current_stage=CoachingStage.REALITY,
        next_stage=CoachingStage.REALITY,
        gate_events_before=gates,
        gate_events_after=gates,
        readiness_question_count=1,
    )

    assert paused.ended_at is None
    assert resumed.readiness_question_count == 1


def test_early_close_never_synthesizes_records_or_gates() -> None:
    with pytest.raises(ValidationError):
        SessionLifecycleDecision.model_validate(
            {
                "action": "early_close",
                "current_stage": "options",
                "next_stage": "options",
                "gate_events_before": ("pre:yes", "goal:yes", "reality:yes"),
                "gate_events_after": (
                    "pre:yes",
                    "goal:yes",
                    "reality:yes",
                    "options:yes",
                ),
                "ended_at": datetime.now(UTC),
                "synthetic_record_count": 1,
            }
        )


def test_abandoned_goal_reuse_creates_a_distinct_confirmed_draft() -> None:
    reuse = AbandonedGoalReuse(
        original_goal_id="goal-old",
        original_status=GoalLifecycleStatus.ABANDONED,
        new_goal_id="goal-new",
        new_status=GoalLifecycleStatus.DRAFT,
        linked_from_goal_id="goal-old",
        separately_confirmed=True,
    )
    assert reuse.new_goal_id != reuse.original_goal_id


def test_check_in_recovery_sends_at_most_one_reminder_and_one_catch_up() -> None:
    recovery = CheckInRecovery(
        hours_overdue=30,
        notification_permission=True,
        quiet_hours_active=False,
        reminder_count=1,
        catch_up_count=1,
        status="missed",
    )
    assert recovery.default_cadence_days == 14

    with pytest.raises(ValidationError):
        CheckInRecovery(
            hours_overdue=30,
            notification_permission=True,
            quiet_hours_active=False,
            reminder_count=2,
            catch_up_count=1,
            status="missed",
        )


def test_confirmed_memory_persists_until_manual_delete() -> None:
    keep = RetentionDecision(
        record_kind=RetentionRecordKind.CONFIRMED_MEMORY,
        age_days=10_000,
        manually_deleted=False,
        action=RetentionAction.KEEP,
    )
    delete = RetentionDecision(
        record_kind=RetentionRecordKind.CONFIRMED_MEMORY,
        age_days=10_000,
        manually_deleted=True,
        action=RetentionAction.MOVE_TO_TRASH,
    )
    assert keep.action is RetentionAction.KEEP
    assert delete.action is RetentionAction.MOVE_TO_TRASH


def test_pending_candidate_and_trash_use_90_and_30_day_purge_rules() -> None:
    pending = RetentionDecision(
        record_kind=RetentionRecordKind.PENDING_CANDIDATE,
        age_days=90,
        manually_deleted=False,
        action=RetentionAction.PURGE,
    )
    trash = RetentionDecision(
        record_kind=RetentionRecordKind.TRASH_ENTRY,
        age_days=30,
        manually_deleted=True,
        action=RetentionAction.PURGE,
    )
    assert pending.action is trash.action is RetentionAction.PURGE


def test_urgent_safety_interrupts_and_cannot_auto_resume_or_deescalate() -> None:
    decision = SafetyDecision(
        level=SafetyLevel.URGENT,
        session_interrupted=True,
        direct_guidance=True,
        normal_coaching_continues=False,
    )
    assert decision.session_interrupted is True

    with pytest.raises(ValidationError):
        SafetyTransition(
            previous=SafetyLevel.URGENT,
            next=SafetyLevel.NORMAL,
            same_session_resume=True,
            explicit_new_pre_coaching=False,
        )


def test_egress_consent_is_bound_to_ui_action_and_withdrawal_blocks_requests() -> None:
    withdrawal = EgressConsentDecision(
        profile_id="profile-1",
        session_id="session-1",
        scope="model-egress:career-context",
        version="v1",
        action=EgressConsentAction.WITHDRAW,
        ui_event_id="ui-event-1",
        created_at=datetime.now(UTC),
        allows_new_requests=False,
    )
    assert withdrawal.allows_new_requests is False

    with pytest.raises(ValidationError):
        EgressConsentDecision(
            profile_id="profile-1",
            session_id="session-1",
            scope="model-egress:career-context",
            version="v1",
            action=EgressConsentAction.DECLINE,
            ui_event_id="ui-event-2",
            created_at=datetime.now(UTC),
            allows_new_requests=True,
        )
