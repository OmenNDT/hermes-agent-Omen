from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RuntimeFailureCode = Literal[
    "consent_error",
    "provider_error",
    "schema_error",
    "policy_error",
    "prompt_changed",
]


class CoachingStage(StrEnum):
    PRE_COACHING = "pre_coaching"
    GOAL = "goal"
    REALITY = "reality"
    OPTIONS = "options"
    WILL = "will"
    REVIEW = "review"


class RecordKind(StrEnum):
    GOAL = "goal"
    INSIGHT = "insight"
    COMMITMENT = "commitment"
    VALUE = "value"
    MESSAGE = "message"
    MEMORY = "memory"


class GateAnswer(StrEnum):
    YES = "yes"
    NO = "no"
    UNCLEAR = "unclear"


class ConsentAction(StrEnum):
    CONFIRM = "confirm"
    DECLINE = "decline"
    WITHDRAW = "withdraw"


class SafetySignal(StrEnum):
    NONE = "none"
    DISTRESS = "distress"
    SELF_HARM = "self_harm"
    IMMEDIATE_DANGER = "immediate_danger"


class GoalSmartStatus(StrEnum):
    UNASSESSED = "unassessed"
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"


class GoalValueStatus(StrEnum):
    UNASSESSED = "unassessed"
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"


class GoalSmartAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    specific: bool = False
    measurable: bool = False
    achievable: bool = False
    relevant: bool = False
    time_bound: bool = False

    @property
    def complete(self) -> bool:
        return all(
            (
                self.specific,
                self.measurable,
                self.achievable,
                self.relevant,
                self.time_bound,
            )
        )


class RuntimeCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supports_tools: Literal[False] = False
    uses_hermes_memory: Literal[False] = False
    uses_context_files: Literal[False] = False
    uses_hermes_session_db: Literal[False] = False
    buffers_before_validation: Literal[True] = True
    structured_output: Literal[True] = True


COACH_RUNTIME_CAPABILITIES = RuntimeCapabilities()


class CandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    kind: RecordKind
    value: str = Field(min_length=1)
    source_turn_id: str = Field(min_length=1)
    status: Literal["candidate"] = "candidate"
    coaching_stage: CoachingStage | None = None
    stage_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def provenance_is_complete_or_absent(self) -> "CandidateRecord":
        if (self.coaching_stage is None) is not (self.stage_revision is None):
            raise ValueError("candidate stage and revision provenance must be supplied together")
        return self


class GateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: CoachingStage
    closing_question_turn_id: str = Field(min_length=1)
    response_turn_id: str = Field(min_length=1)
    exact_response: str = Field(min_length=1)
    answer: GateAnswer


class ConsentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    consent_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    version: str = Field(min_length=1)
    action: ConsentAction
    ui_event_id: str = Field(min_length=1)


class RuntimeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    system_prompt_hash: str
    current_stage: CoachingStage
    user_message: str = Field(min_length=1)
    structured_context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("system_prompt_hash")
    @classmethod
    def validate_prompt_hash(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("system_prompt_hash must be a lowercase SHA-256 digest")
        return value


class CoachOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=2)
    coaching_stage: CoachingStage
    inference_session_id: str | None = Field(default=None, min_length=1)
    inference_turn_id: str | None = Field(default=None, min_length=1)
    inference_stage_revision: int | None = Field(default=None, ge=1)
    candidate_insights: tuple[CandidateRecord, ...] = ()
    candidate_goals: tuple[CandidateRecord, ...] = ()
    candidate_commitments: tuple[CandidateRecord, ...] = ()
    candidate_memories: tuple[CandidateRecord, ...] = ()
    goal_smart_status: GoalSmartStatus = GoalSmartStatus.UNASSESSED
    goal_smart_assessment: GoalSmartAssessment = GoalSmartAssessment()
    goal_value_status: GoalValueStatus = GoalValueStatus.UNASSESSED
    safety_signal: SafetySignal = SafetySignal.NONE
    #: What the Coachee has actually said about the current step, extracted.
    #:
    #: The six-step structure rested entirely on the closing gate — an explicit
    #: yes to a well-formed question — with nothing checking the step had any
    #: content. `stage_is_complete` was written for that job and never wired,
    #: because the snapshots it reads were populated by nothing. This is where
    #: the content finally comes from.
    #:
    #: Free-shaped on purpose: each step needs different pieces, and pinning a
    #: schema per stage here would put six models in the contract before anyone
    #: knows what the model reliably produces. `domain.stage_completeness` owns
    #: which keys matter.
    stage_snapshot: dict[str, Any] = Field(default_factory=dict)

    @field_validator("question")
    @classmethod
    def validate_single_question(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.count("?") != 1 or not normalized.endswith("?"):
            raise ValueError("question must contain exactly one question mark and end with it")
        return normalized

    @model_validator(mode="after")
    def candidate_arrays_match_their_record_kinds(self) -> "CoachOutput":
        provenance = (
            self.inference_session_id,
            self.inference_turn_id,
            self.inference_stage_revision,
        )
        if any(item is not None for item in provenance) and any(
            item is None for item in provenance
        ):
            raise ValueError("inference provenance must be complete or absent")
        expected = {
            "candidate_insights": RecordKind.INSIGHT,
            "candidate_goals": RecordKind.GOAL,
            "candidate_commitments": RecordKind.COMMITMENT,
            "candidate_memories": RecordKind.MEMORY,
        }
        for field_name, record_kind in expected.items():
            if any(item.kind is not record_kind for item in getattr(self, field_name)):
                raise ValueError(f"{field_name} contains a mismatched record kind")
        assessment_complete = self.goal_smart_assessment.complete
        if self.goal_smart_status is GoalSmartStatus.COMPLETE and not assessment_complete:
            raise ValueError("complete Goal status requires all SMART components")
        if self.goal_smart_status is GoalSmartStatus.INCOMPLETE and assessment_complete:
            raise ValueError("incomplete Goal status conflicts with complete SMART components")
        if (
            self.goal_smart_status is GoalSmartStatus.UNASSESSED
            and any(self.goal_smart_assessment.model_dump().values())
        ):
            raise ValueError("unassessed Goal status cannot claim SMART components")
        return self


class UsageAccounting(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ValidatedRuntimeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output: CoachOutput
    attempts: int = Field(ge=1)
    usage: UsageAccounting


class RuntimeFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: RuntimeFailureCode
    retryable: bool
    safe_message: str = Field(min_length=1)
    attempts: int = Field(ge=0)
    usage: UsageAccounting


class PromptStabilityError(RuntimeError):
    """Raised before inference when the cached system-prompt prefix changed."""


def stable_prompt_fingerprint(system_prompt: str) -> str:
    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()


def assert_prompt_stable(expected_hash: str, actual_hash: str) -> None:
    if expected_hash != actual_hash:
        raise PromptStabilityError("Hermes Coach system prompt changed within the session")
