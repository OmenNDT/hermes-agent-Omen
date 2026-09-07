from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hermes_coach.contracts.runtime_contract import CoachingStage


class SessionControlAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    EARLY_CLOSE = "early_close"


class SessionLifecycleDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: SessionControlAction
    current_stage: CoachingStage
    next_stage: CoachingStage
    gate_events_before: tuple[str, ...] = ()
    gate_events_after: tuple[str, ...] = ()
    ended_at: datetime | None = None
    readiness_question_count: int = Field(default=0, ge=0, le=1)
    synthetic_record_count: Literal[0] = 0

    @model_validator(mode="after")
    def preserve_session_truth(self) -> "SessionLifecycleDecision":
        if self.next_stage is not self.current_stage:
            raise ValueError("pause, resume and early close preserve the current stage")
        if self.gate_events_after != self.gate_events_before:
            raise ValueError("session control cannot synthesize or remove gate events")
        if self.action is SessionControlAction.EARLY_CLOSE:
            if self.ended_at is None or self.readiness_question_count:
                raise ValueError("early close requires ended_at and no readiness question")
        elif self.ended_at is not None:
            raise ValueError("pause and resume leave ended_at empty")
        if self.action is SessionControlAction.RESUME and self.readiness_question_count != 1:
            raise ValueError("resume asks exactly one readiness/current-stage question")
        if self.action is SessionControlAction.PAUSE and self.readiness_question_count:
            raise ValueError("pause does not synthesize a readiness question")
        return self


class GoalLifecycleStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ABANDONED = "abandoned"


class AbandonedGoalReuse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original_goal_id: str = Field(min_length=1)
    original_status: GoalLifecycleStatus
    new_goal_id: str = Field(min_length=1)
    new_status: GoalLifecycleStatus
    linked_from_goal_id: str = Field(min_length=1)
    separately_confirmed: bool

    @model_validator(mode="after")
    def require_a_new_linked_confirmed_draft(self) -> "AbandonedGoalReuse":
        if self.original_status is not GoalLifecycleStatus.ABANDONED:
            raise ValueError("reuse contract applies only to abandoned goals")
        if self.new_status is not GoalLifecycleStatus.DRAFT:
            raise ValueError("reuse creates a new draft, never reactivates the old goal")
        if self.new_goal_id == self.original_goal_id:
            raise ValueError("abandoned goal has no outgoing transition")
        if self.linked_from_goal_id != self.original_goal_id or not self.separately_confirmed:
            raise ValueError("new draft must be linked and separately confirmed")
        return self


class CheckInRecovery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    default_cadence_days: Literal[14] = 14
    hours_overdue: int = Field(ge=0)
    notification_permission: bool
    quiet_hours_active: bool
    reminder_count: int = Field(ge=0, le=1)
    catch_up_count: int = Field(ge=0, le=1)
    status: Literal["due", "missed"]

    @model_validator(mode="after")
    def enforce_neutral_recovery_limits(self) -> "CheckInRecovery":
        delivery_allowed = self.notification_permission and not self.quiet_hours_active
        if self.reminder_count and (self.hours_overdue < 24 or not delivery_allowed):
            raise ValueError("reminder requires 24h overdue, permission and non-quiet hours")
        if self.hours_overdue >= 24 and self.status != "missed":
            raise ValueError("item becomes missed after the one-reminder window")
        return self


class RetentionRecordKind(StrEnum):
    CONFIRMED_MEMORY = "confirmed_memory"
    PENDING_CANDIDATE = "pending_candidate"
    TRASH_ENTRY = "trash_entry"


class RetentionAction(StrEnum):
    KEEP = "keep"
    MOVE_TO_TRASH = "move_to_trash"
    PURGE = "purge"


class RetentionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_kind: RetentionRecordKind
    age_days: int = Field(ge=0)
    manually_deleted: bool
    action: RetentionAction

    @model_validator(mode="after")
    def enforce_retention_policy(self) -> "RetentionDecision":
        if self.record_kind is RetentionRecordKind.CONFIRMED_MEMORY:
            expected = RetentionAction.MOVE_TO_TRASH if self.manually_deleted else RetentionAction.KEEP
        elif self.record_kind is RetentionRecordKind.PENDING_CANDIDATE:
            expected = RetentionAction.PURGE if self.age_days >= 90 else RetentionAction.KEEP
        else:
            expected = RetentionAction.PURGE if self.age_days >= 30 else RetentionAction.KEEP
        if self.action is not expected:
            raise ValueError(f"retention action must be {expected.value}")
        return self


class SafetyLevel(StrEnum):
    NORMAL = "normal"
    DISTRESS = "distress"
    URGENT = "urgent"


class SafetyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    level: SafetyLevel
    session_interrupted: bool
    direct_guidance: bool
    normal_coaching_continues: bool

    @model_validator(mode="after")
    def urgent_state_interrupts_normal_coaching(self) -> "SafetyDecision":
        if self.level is SafetyLevel.URGENT and (
            not self.session_interrupted
            or not self.direct_guidance
            or self.normal_coaching_continues
        ):
            raise ValueError("urgent safety requires interruption and direct guidance")
        return self


class SafetyTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    previous: SafetyLevel
    next: SafetyLevel
    same_session_resume: bool = False
    explicit_new_pre_coaching: bool = False

    @model_validator(mode="after")
    def never_silently_deescalate(self) -> "SafetyTransition":
        levels = list(SafetyLevel)
        deescalates = levels.index(self.next) < levels.index(self.previous)
        if deescalates and (self.same_session_resume or not self.explicit_new_pre_coaching):
            raise ValueError("safety de-escalation requires a new explicit Pre-Coaching session")
        if self.previous is SafetyLevel.URGENT and self.same_session_resume:
            raise ValueError("urgent session cannot auto-resume")
        return self

