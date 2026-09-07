from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hermes_coach.contracts.runtime_contract import CoachingStage, GateAnswer


class ScenarioCategory(StrEnum):
    PRE_COACHING = "pre_coaching"
    COMPANION = "companion"
    QUESTION_ONLY = "question_only"
    GATE = "gate"
    GOAL_VALIDATION = "goal_validation"
    REALITY = "reality"
    OPTIONS_NOVELTY = "options_novelty"
    WILL = "will"
    REVIEW = "review"
    ROLLBACK = "rollback"
    PRIVACY = "privacy"
    SAFETY = "safety"
    MEMORY = "memory"
    CHECK_IN = "check_in"


class ScenarioCaseType(StrEnum):
    POSITIVE = "positive"
    COUNTEREXAMPLE = "counterexample"
    EDGE = "edge"


class ExternalGateStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    EXPIRED = "expired"


class ExternalValidationGate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^GATE-[A-Z0-9-]+$")
    owner: str = Field(min_length=1)
    status: ExternalGateStatus
    blocks: tuple[str, ...] = Field(min_length=1)
    evidence_format: str = Field(min_length=1)
    evidence_validity_days: int = Field(gt=0)
    evidence_uri: str | None = None
    reviewed_at: datetime | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def passed_gate_requires_current_evidence(self) -> "ExternalValidationGate":
        evidence = (self.evidence_uri, self.reviewed_at, self.expires_at)
        if self.status is ExternalGateStatus.PASSED and any(item is None for item in evidence):
            raise ValueError("passed external gate requires URI, review time and expiry")
        if self.status is not ExternalGateStatus.PASSED and any(
            item is not None for item in evidence
        ):
            raise ValueError("pending or expired gate cannot claim current evidence")
        return self


class ScenarioExpected(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    next_stage: CoachingStage
    question_only: bool = True
    closing_question: bool = False
    gate_answer: GateAnswer | None = None
    rollback_to: CoachingStage | None = None
    return_to_pre_coaching: bool = False
    novel_option_required: bool = False
    safety_exception: bool = False
    must_do: tuple[str, ...] = ()
    must_not_do: tuple[str, ...] = ()

    @model_validator(mode="after")
    def rollback_targets_the_declared_next_stage(self) -> "ScenarioExpected":
        if self.rollback_to is not None and self.next_stage is not self.rollback_to:
            raise ValueError("rollback_to must equal next_stage")
        if self.return_to_pre_coaching and (
            self.next_stage is not CoachingStage.PRE_COACHING or self.rollback_to is not None
        ):
            raise ValueError("readiness reset must target Pre-Coaching without rollback")
        if self.safety_exception and self.question_only:
            raise ValueError("safety exceptions must explicitly relax question_only")
        return self


class EvaluationScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^SCN-\d{3}$")
    version: int = Field(ge=1)
    title: str = Field(min_length=1)
    category: ScenarioCategory
    case_type: ScenarioCaseType
    stage: CoachingStage
    coachee_input: str = Field(min_length=1)
    expected: ScenarioExpected
    source_ids: tuple[str, ...] = Field(min_length=1)
    acceptance_ids: tuple[str, ...] = Field(min_length=1)
    tags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_requirement_ids(self) -> "EvaluationScenario":
        if any(not item.startswith("SRC-") for item in self.source_ids):
            raise ValueError("source_ids must contain SRC-* identifiers")
        if any(not item.startswith("AC-") for item in self.acceptance_ids):
            raise ValueError("acceptance_ids must contain AC-* identifiers")
        return self


class RubricCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^CRIT-[A-Z0-9-]+$")
    description: str = Field(min_length=1)
    weight: float = Field(gt=0, le=1)
    blocking: bool = False


class EvaluationRubric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^RUB-[A-Z0-9-]+$")
    version: int = Field(ge=1)
    name: str = Field(min_length=1)
    minimum_score: float = Field(ge=0, le=1)
    source_ids: tuple[str, ...] = Field(min_length=1)
    criteria: tuple[RubricCriterion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "EvaluationRubric":
        if abs(sum(item.weight for item in self.criteria) - 1.0) > 1e-9:
            raise ValueError("rubric criterion weights must sum to 1")
        return self


class CorpusAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_count: int = Field(ge=0)
    rubric_count: int = Field(ge=0)
    covered_source_ids: tuple[str, ...]
    covered_acceptance_ids: tuple[str, ...]
    errors: tuple[str, ...] = ()
