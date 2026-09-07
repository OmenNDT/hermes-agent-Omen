from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hermes_coach.contracts.runtime_contract import (
    CoachingStage,
    GateAnswer,
    GateEvidence,
    GoalSmartStatus,
    GoalSmartAssessment,
    GoalValueStatus,
)


class TransitionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_stage: CoachingStage
    next_stage: CoachingStage
    rollback_to: CoachingStage | None = None
    return_to_pre_coaching: bool = False
    gate_evidence: GateEvidence | None = None
    session_ended: bool = False
    stage_state_complete: bool = False
    confirmed_stages: tuple[CoachingStage, ...] = ()
    goal_smart_status: GoalSmartStatus = GoalSmartStatus.UNASSESSED
    goal_smart_assessment: GoalSmartAssessment = GoalSmartAssessment()
    goal_value_status: GoalValueStatus = GoalValueStatus.UNASSESSED
    goal_influence_confirmed: bool = False
    options_novelty_confirmed: bool = False
    will_commitment_score: int | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def enforce_ordered_explicit_yes_transitions(self) -> "TransitionDecision":
        ordered = list(CoachingStage)
        grow_stages = {
            CoachingStage.GOAL,
            CoachingStage.REALITY,
            CoachingStage.OPTIONS,
            CoachingStage.WILL,
        }
        if self.return_to_pre_coaching:
            if (
                self.current_stage is CoachingStage.PRE_COACHING
                or self.next_stage is not CoachingStage.PRE_COACHING
                or self.rollback_to is not None
                or self.session_ended
            ):
                raise ValueError("readiness reset must return only to Pre-Coaching")
            if self._contains_progress_state():
                raise ValueError("readiness reset must invalidate all coaching progress state")
            return self
        if self.rollback_to is not None:
            if self.next_stage is not self.rollback_to or self.session_ended:
                raise ValueError("rollback must move to its target without ending the session")
            if ordered.index(self.rollback_to) >= ordered.index(self.current_stage):
                raise ValueError("rollback target must precede the current stage")
            if self.rollback_to not in grow_stages:
                raise ValueError("rollback target must be a G/R/O/W stage")
            target_index = ordered.index(self.rollback_to)
            if set(self.confirmed_stages) != set(ordered[:target_index]):
                raise ValueError("rollback must invalidate target and all downstream gates")
            if self.stage_state_complete or self.gate_evidence is not None:
                raise ValueError("rollback target must restart as incomplete without gate evidence")
            if self.options_novelty_confirmed or self.will_commitment_score is not None:
                raise ValueError("rollback must clear downstream Options and Will state")
            if self.rollback_to is CoachingStage.GOAL and self._contains_goal_state():
                raise ValueError("rollback to Goal must clear all Goal predicates")
            return self

        current_index = ordered.index(self.current_stage)
        allowed_next = self.current_stage
        if current_index + 1 < len(ordered):
            allowed_next = ordered[current_index + 1]
        moves_forward = self.next_stage is not self.current_stage or self.session_ended
        if self.next_stage not in {self.current_stage, allowed_next}:
            raise ValueError("forward transitions cannot skip coaching stages")
        if self.session_ended and self.current_stage is not CoachingStage.REVIEW:
            raise ValueError("only Review may end a coaching session")
        if moves_forward:
            self._validate_forward_state(ordered, current_index)
            self._require_yes_gate()
        elif self.gate_evidence and self.gate_evidence.answer is GateAnswer.YES:
            raise ValueError("a valid Yes gate must advance or end the stage")
        return self

    def _validate_forward_state(
        self,
        ordered: list[CoachingStage],
        current_index: int,
    ) -> None:
        if not self.stage_state_complete:
            raise ValueError("stage state must be complete before its closing gate can advance")
        if not set(ordered[:current_index]) <= set(self.confirmed_stages):
            raise ValueError("all prior stages must be confirmed before advancing")
        if self.current_stage is CoachingStage.GOAL and (
            self.goal_smart_status is not GoalSmartStatus.COMPLETE
            or not self.goal_smart_assessment.complete
            or self.goal_value_status is not GoalValueStatus.CONFIRMED
            or not self.goal_influence_confirmed
        ):
            raise ValueError("Goal must be SMART, valuable and within influence")
        if self.current_stage is CoachingStage.OPTIONS and not self.options_novelty_confirmed:
            raise ValueError("Options requires a materially new Coachee-generated option")
        if self.current_stage is CoachingStage.WILL and (
            self.will_commitment_score is None or not 1 <= self.will_commitment_score <= 10
        ):
            raise ValueError("Will requires a commitment score from 1 to 10")

    def _require_yes_gate(self) -> None:
        gate = self.gate_evidence
        if gate is None or gate.stage is not self.current_stage:
            raise ValueError("forward transition requires gate evidence for current stage")
        if gate.answer is not GateAnswer.YES or not _is_explicit_yes(gate.exact_response):
            raise ValueError("forward transition requires an explicit Yes response")

    def _contains_goal_state(self) -> bool:
        return (
            self.goal_smart_status is not GoalSmartStatus.UNASSESSED
            or any(self.goal_smart_assessment.model_dump().values())
            or self.goal_value_status is not GoalValueStatus.UNASSESSED
            or self.goal_influence_confirmed
        )

    def _contains_progress_state(self) -> bool:
        return bool(
            self.gate_evidence
            or self.stage_state_complete
            or self.confirmed_stages
            or self._contains_goal_state()
            or self.options_novelty_confirmed
            or self.will_commitment_score is not None
        )


def _is_explicit_yes(response: str) -> bool:
    normalized = unicodedata.normalize("NFD", response).strip().casefold()
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.replace("đ", "d")).strip()
    explicit = any(
        normalized == token or normalized.startswith(f"{token} ")
        for token in ("yes", "co", "dong y")
    )
    if not explicit:
        return False
    ambiguous = r"\b(?:no|not|maybe|perhaps|but|however|khong|chua|nhung|neu)\b|\bco\s+le\b"
    return re.search(ambiguous, normalized) is None
