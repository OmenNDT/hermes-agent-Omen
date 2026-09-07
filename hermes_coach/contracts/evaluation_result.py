from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from hermes_coach.contracts.runtime_contract import CoachingStage, GateAnswer


class ScenarioObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(pattern=r"^SCN-\d{3}$")
    actual_next_stage: CoachingStage
    question_count: int = Field(ge=0)
    closing_question_observed: bool = False
    gate_answer: GateAnswer | None = None
    rollback_to: CoachingStage | None = None
    return_to_pre_coaching: bool = False
    novel_option_observed: bool = False
    safety_exception: bool = False
    met_behaviors: tuple[str, ...] = ()
    prohibited_behaviors: tuple[str, ...] = ()
    criterion_scores: dict[str, float] = Field(default_factory=dict)


class RubricScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rubric_id: str
    score: float = Field(ge=0, le=1)
    blocking_failures: tuple[str, ...] = ()
    passed: bool


class ScenarioEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    structural_failures: tuple[str, ...] = ()
    rubric_scores: tuple[RubricScore, ...]
    passed: bool


class EvaluationRunReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    scenario_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    results: tuple[ScenarioEvaluationResult, ...]
