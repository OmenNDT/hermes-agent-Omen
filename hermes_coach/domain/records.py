"""Persisted product records.

Requirement families: `HC-DATA-*`, `HC-RECORDS`, `HC-MEMORY`, `HC-PRIVACY`.

These mirror the canonical tables one-for-one. They are separate from the
coaching snapshots in `models.py`: those describe the live state of a session,
these describe rows that outlive it. Field sets are exact — a storage
convenience must not grow a canonical product entity.

Timestamps are ISO-8601 UTC strings, matching the schema's text columns.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from hermes_coach.domain.models import ImmutableModel


GoalStatus = Literal["draft", "active", "paused", "achieved", "abandoned"]
MessageRole = Literal["coach", "coachee", "product_ui", "safety_system"]
CandidateType = Literal["goal", "insight", "commitment", "memory"]
CandidateStatus = Literal["pending", "confirmed", "edited", "discarded"]
ProvenanceSource = Literal["session", "message", "goal", "insight", "manual"]
ProvenanceRelation = Literal["derived_from", "confirmed_from", "manually_entered"]
DeletionSource = Literal["item", "session", "goal", "transcript", "all_data"]
ConsentDecisionName = Literal["granted", "declined", "withdrawn"]
UiActionName = Literal["confirm", "decline", "withdraw"]
ConfirmationActionName = Literal["accept", "edit", "discard"]
GateResultName = Literal["yes", "no", "unclear", "invalidated"]
CoachingStageName = Literal[
    "pre_coaching", "goal", "reality", "options", "will", "review"
]
SafetyStateName = Literal["normal", "sensitive", "possible_crisis", "urgent"]


class GoalRow(ImmutableModel):
    id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    why_it_matters: str | None = None
    desired_outcome: str | None = None
    success_evidence: str | None = None
    target_date: str | None = None
    status: GoalStatus
    priority: int | None = None
    source_session_id: str | None = None
    confirmed_at: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str | None = None


class SessionMessageRow(ImmutableModel):
    id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    sequence_no: int = Field(ge=0)
    role: MessageRole
    content: str = Field(min_length=1)
    modality: Literal["text"] = "text"
    coaching_stage: CoachingStageName | None = None
    question_kind: str | None = None
    safety_state: SafetyStateName | None = None
    created_at: str = Field(min_length=1)
    expires_at: str | None = None
    deleted_at: str | None = None


class CandidateRecordRow(ImmutableModel):
    id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    record_type: CandidateType
    payload_json: str
    source_message_id: str | None = None
    status: CandidateStatus
    created_at: str = Field(min_length=1)
    expires_at: str | None = None
    resolved_at: str | None = None


class MemoryItemRow(ImmutableModel):
    id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    category: str | None = None
    sensitivity: str | None = None
    user_confirmed: bool = False
    # Always NULL once confirmed: approved memory persists until manual deletion.
    expires_at: str | None = None
    last_used_at: str | None = None


class MemoryProvenanceRow(ImmutableModel):
    id: str = Field(min_length=1)
    memory_item_id: str = Field(min_length=1)
    source_type: ProvenanceSource
    source_id: str | None = None
    source_session_id: str | None = None
    source_message_id: str | None = None
    relation: ProvenanceRelation
    created_at: str = Field(min_length=1)


class CareerSnapshotRow(ImmutableModel):
    id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    current_role: str | None = None
    industry: str | None = None
    experience_summary: str | None = None
    strengths: str | None = None
    constraints: str | None = None
    career_vision: str | None = None
    clarity_score: int | None = None
    satisfaction_score: int | None = None
    energy_score: int | None = None
    confidence_score: int | None = None
    balance_score: int | None = None
    follow_through_score: int | None = None
    captured_at: str = Field(min_length=1)


class CoachingSessionRow(ImmutableModel):
    id: str = Field(min_length=1)
    started_at: str = Field(min_length=1)
    ended_at: str | None = None
    intention: str | None = None
    success_definition: str | None = None
    coaching_stage: CoachingStageName
    coachee_takeaway: str | None = None
    summary: str | None = None
    safety_state: SafetyStateName | None = None


class GateConfirmationRow(ImmutableModel):
    """One gate event. Append-only: a rollback adds `invalidated`, never edits."""

    id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    step: CoachingStageName
    revision: int = Field(ge=1)
    result: GateResultName
    closing_question_message_id: str | None = None
    response_message_id: str | None = None
    confirmed_at: str | None = None
    invalidated_at: str | None = None
    invalidated_by_step: CoachingStageName | None = None


class CheckInRow(ImmutableModel):
    id: str = Field(min_length=1)
    commitment_id: str = Field(min_length=1)
    scheduled_at: str = Field(min_length=1)
    completed_at: str | None = None
    result: str | None = None
    blockers: str | None = None
    still_relevant: bool | None = None
    rescheduled_to: str | None = None
    review: str | None = None


class InsightRow(ImmutableModel):
    id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    topic: str | None = None
    sensitivity: str | None = None
    source_session_id: str | None = None
    goal_id: str | None = None
    confirmed_at: str | None = None


class CommitmentRow(ImmutableModel):
    id: str = Field(min_length=1)
    goal_id: str = Field(min_length=1)
    action_text: str = Field(min_length=1)
    due_at: str | None = None
    evidence_definition: str | None = None
    confidence_score: int | None = Field(default=None, ge=1, le=10)
    status: str = Field(min_length=1)
    source_session_id: str | None = None
    confirmed_at: str | None = None


class ConsentEventRow(ImmutableModel):
    id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    session_id: str | None = None
    consent_type: str = Field(min_length=1)
    decision: ConsentDecisionName
    scope_json: str
    source: Literal["ui"] = "ui"
    ui_action: UiActionName
    control_id: str = Field(min_length=1)
    evidence_version: int = Field(ge=1)
    created_at: str = Field(min_length=1)


class ConfirmationAuditRow(ImmutableModel):
    """Internal audit metadata. Holds ids only — never record content."""

    id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    action: ConfirmationActionName
    official_record_type: str | None = None
    official_record_id: str | None = None
    created_at: str = Field(min_length=1)


class TrashEntryRow(ImmutableModel):
    id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    deleted_at: str = Field(min_length=1)
    purge_after: str = Field(min_length=1)
    restored_at: str | None = None
    purged_at: str | None = None
    deletion_source: DeletionSource
