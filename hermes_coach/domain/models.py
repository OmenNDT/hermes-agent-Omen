from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hermes_coach.contracts.runtime_contract import GoalSmartAssessment


class ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreCoachingSnapshot(ImmutableModel):
    ready: bool = False
    coaching_understood: bool = False
    roles_agreed: bool = False
    boundaries_agreed: bool = False
    emotion_relevant: bool = False
    emotion_explored: bool = False

    @property
    def complete(self) -> bool:
        emotion_ready = not self.emotion_relevant or self.emotion_explored
        return all(
            (
                self.ready,
                self.coaching_understood,
                self.roles_agreed,
                self.boundaries_agreed,
                emotion_ready,
            )
        )


class GoalSnapshot(ImmutableModel):
    wording: str = Field(min_length=1)
    smart: GoalSmartAssessment = GoalSmartAssessment()
    belongs_to_coachee: bool = False
    aligned_with_values_or_needs: bool = False
    within_influence: bool = False
    benefit: str | None = None
    loss_avoided: str | None = None
    success_evidence: str | None = None


class RealitySnapshot(ImmutableModel):
    facts: str = ""
    present_state: str = ""
    gap: str = ""
    emotion: str = ""
    barriers: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    prior_attempts: tuple[str, ...] = ()
    assumptions_separated: bool = False
    influence_identified: bool = False

    @property
    def complete(self) -> bool:
        return bool(
            self.facts.strip()
            and self.present_state.strip()
            and self.gap.strip()
            and self.emotion.strip()
            and self.barriers
            and self.resources
            and self.prior_attempts
            and self.assumptions_separated
            and self.influence_identified
        )


class OptionIdea(ImmutableModel):
    text: str = Field(min_length=1)
    mechanism: str = Field(min_length=1)
    coachee_generated: bool = False
    material_difference_confirmed: bool = False

    @field_validator("text", "mechanism")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("option text and mechanism must not be blank")
        return normalized


class OptionAssessment(ImmutableModel):
    session_id: str = Field(min_length=1)
    stage_revision: int = Field(ge=1)
    baseline: tuple[OptionIdea, ...] = Field(min_length=1)
    candidate: OptionIdea
    candidate_source_turn_id: str = Field(min_length=1)
    confirmation_turn_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_turns_are_distinct(self) -> "OptionAssessment":
        if self.candidate_source_turn_id == self.confirmation_turn_id:
            raise ValueError("candidate and confirmation evidence require separate turns")
        return self


class OptionsSnapshot(ImmutableModel):
    canonical_baseline: tuple[OptionIdea, ...] = ()
    assessments: tuple[OptionAssessment, ...] = ()

    @property
    def complete(self) -> bool:
        # Completion requires the owning session aggregate's current revision and
        # trusted turn ledger. A detached snapshot must always fail closed.
        return False


class WillSnapshot(ImmutableModel):
    chosen_action: str = ""
    starts_at: str = ""
    due_at: str = ""
    completion_evidence: str = ""
    commitment_score: int | None = Field(default=None, ge=1, le=10)

    @property
    def complete(self) -> bool:
        return bool(
            self.chosen_action.strip()
            and self.starts_at.strip()
            and self.due_at.strip()
            and self.completion_evidence.strip()
            and self.commitment_score is not None
        )


class ReviewSnapshot(ImmutableModel):
    takeaway: str = ""
    immediate_application: str = ""
    follow_up_disposition: str = ""

    @property
    def complete(self) -> bool:
        return bool(
            self.takeaway.strip()
            and self.immediate_application.strip()
            and self.follow_up_disposition.strip()
        )
