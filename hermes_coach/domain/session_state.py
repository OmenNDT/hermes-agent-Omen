from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from hermes_coach.contracts.runtime_contract import (
    CandidateRecord,
    CoachingStage,
    GateAnswer,
)
from hermes_coach.domain.enums import FunnelStage, SafetyState
from hermes_coach.domain.goal_rules import assess_goal
from hermes_coach.domain.models import (
    GoalSnapshot,
    ImmutableModel,
    OptionsSnapshot,
    PreCoachingSnapshot,
    RealitySnapshot,
    ReviewSnapshot,
    WillSnapshot,
)


STAGE_ORDER = tuple(CoachingStage)
GROW_STAGES = (
    CoachingStage.GOAL,
    CoachingStage.REALITY,
    CoachingStage.OPTIONS,
    CoachingStage.WILL,
)


class StageRevision(ImmutableModel):
    stage: CoachingStage
    revision: int = Field(ge=1)


TurnActor = Literal["coach", "coachee"]
"""The only two participants a ledger turn may be attributed to."""


class SessionTurn(ImmutableModel):
    turn_id: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    actor: TurnActor
    content: str = Field(min_length=1)


class ClosingGateBinding(ImmutableModel):
    stage: CoachingStage
    revision: int = Field(ge=1)
    question_turn_id: str = Field(min_length=1)
    question_sequence: int = Field(ge=0)


class SessionGateEvent(ImmutableModel):
    stage: CoachingStage
    revision: int = Field(ge=1)
    closing_question_turn_id: str = Field(min_length=1)
    question_sequence: int = Field(ge=0)
    response_turn_id: str = Field(min_length=1)
    response_sequence: int = Field(ge=0)
    exact_response: str = Field(min_length=1)
    answer: GateAnswer
    valid: bool


class CoachingSessionState(ImmutableModel):
    session_id: str = Field(min_length=1)
    current_step: CoachingStage = CoachingStage.PRE_COACHING
    funnel_stage: FunnelStage = FunnelStage.OPEN
    revisions: tuple[StageRevision, ...] = tuple(
        StageRevision(stage=stage, revision=1) for stage in STAGE_ORDER
    )
    turn_ledger: tuple[SessionTurn, ...] = ()
    gate_events: tuple[SessionGateEvent, ...] = ()
    pending_gate: ClosingGateBinding | None = None
    pre_coaching: PreCoachingSnapshot = PreCoachingSnapshot()
    goal: GoalSnapshot | None = None
    reality: RealitySnapshot = RealitySnapshot()
    options: OptionsSnapshot = OptionsSnapshot()
    will: WillSnapshot = WillSnapshot()
    review: ReviewSnapshot = ReviewSnapshot()
    candidate_records: tuple[CandidateRecord, ...] = ()
    safety_state: SafetyState = SafetyState.NORMAL
    ended: bool = False

    @model_validator(mode="after")
    def aggregate_vectors_are_exact(self) -> "CoachingSessionState":
        revision_stages = tuple(item.stage for item in self.revisions)
        if revision_stages != STAGE_ORDER:
            raise ValueError(
                "revision vector must contain each of the six coaching stages exactly once "
                "in canonical order"
            )
        turn_ids = tuple(item.turn_id for item in self.turn_ledger)
        if len(set(turn_ids)) != len(turn_ids):
            raise ValueError("turn ledger IDs must be unique")
        if any(
            current.sequence != previous.sequence + 1
            for previous, current in zip(self.turn_ledger, self.turn_ledger[1:])
        ):
            raise ValueError("turn ledger sequences must be contiguous")
        if any(
            current.actor == previous.actor
            for previous, current in zip(self.turn_ledger, self.turn_ledger[1:])
        ):
            raise ValueError("turn ledger actors must alternate")
        return self

    def revision_for(self, stage: CoachingStage) -> int:
        return next(item.revision for item in self.revisions if item.stage is stage)

    @property
    def confirmed_steps(self) -> tuple[CoachingStage, ...]:
        # Local imports avoid the session_state <-> transitions dependency cycle.
        from hermes_coach.domain.transitions import classify_gate_answer
        from hermes_coach.policies.question_policy import is_yes_no_closing_question

        ledger_turns = {
            turn.turn_id: (index, turn) for index, turn in enumerate(self.turn_ledger)
        }
        confirmed: set[CoachingStage] = set()
        for event in self.gate_events:
            question_entry = ledger_turns.get(event.closing_question_turn_id)
            response_entry = ledger_turns.get(event.response_turn_id)
            if question_entry is None or response_entry is None:
                continue
            question_index, question = question_entry
            response_index, response = response_entry
            evidence_is_valid = (
                event.valid
                and event.answer is GateAnswer.YES
                and event.revision == self.revision_for(event.stage)
                and question.sequence == event.question_sequence
                and response.sequence == event.response_sequence
                and response_index == question_index + 1
                and response.sequence == question.sequence + 1
                and question.actor == "coach"
                and response.actor == "coachee"
                and response.content == event.exact_response
                and is_yes_no_closing_question(question.content)
                and classify_gate_answer(response.content) is GateAnswer.YES
            )
            if evidence_is_valid:
                confirmed.add(event.stage)
        return tuple(stage for stage in STAGE_ORDER if stage in confirmed)


def stage_is_complete(state: CoachingSessionState) -> bool:
    stage = state.current_step
    if stage is CoachingStage.PRE_COACHING:
        return state.pre_coaching.complete
    if stage is CoachingStage.GOAL:
        return state.goal is not None and assess_goal(state.goal).complete
    if stage is CoachingStage.REALITY:
        return state.reality.complete
    if stage is CoachingStage.OPTIONS:
        from hermes_coach.domain.options_rules import options_are_complete

        return options_are_complete(
            state.options,
            session_id=state.session_id,
            stage_revision=state.revision_for(CoachingStage.OPTIONS),
            turn_ledger=state.turn_ledger,
        )
    if stage is CoachingStage.WILL:
        return state.will.complete
    prior_grow_confirmed = set(GROW_STAGES) <= set(state.confirmed_steps)
    return state.review.complete and prior_grow_confirmed
