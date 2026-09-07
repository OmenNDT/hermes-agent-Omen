from __future__ import annotations

from collections.abc import Callable

from hermes_coach.contracts.runtime_contract import CoachOutput, CoachingStage
from hermes_coach.domain.enums import FunnelStage, SafetyState
from hermes_coach.domain.session_state import CoachingSessionState, stage_is_complete
from hermes_coach.domain.transitions import (
    GateTransitionResult,
    answer_closing_gate,
    open_closing_gate,
    return_to_pre_coaching,
    rollback_to,
)
from hermes_coach.policies.question_policy import (
    advance_funnel as advance_funnel_stage,
    is_yes_no_closing_question,
)
from hermes_coach.prompt.regeneration import (
    ValidatedDelivery,
    deliver_validated,
    validate_with_bounded_regeneration,
)


class CoachingService:
    """Thin orchestrator; domain predicates and policies remain in focused modules."""

    def can_close_current_step(self, state: CoachingSessionState) -> bool:
        return stage_is_complete(state)

    def advance_funnel(
        self,
        state: CoachingSessionState,
        requested: FunnelStage,
    ) -> CoachingSessionState:
        self._ensure_coaching_not_interrupted(state)
        next_stage = advance_funnel_stage(state.funnel_stage, requested)
        return state.model_copy(update={"funnel_stage": next_stage})

    def open_gate(
        self,
        state: CoachingSessionState,
        question_turn_id: str,
        closing_question: str,
        question_sequence: int,
    ) -> CoachingSessionState:
        self._ensure_coaching_not_interrupted(state)
        if not is_yes_no_closing_question(closing_question):
            raise ValueError("closing gate requires exactly one Yes/No question")
        return open_closing_gate(
            state,
            question_turn_id,
            question_sequence=question_sequence,
            closing_question=closing_question,
        )

    def answer_gate(
        self,
        state: CoachingSessionState,
        *,
        response_turn_id: str,
        response_sequence: int,
        in_reply_to_turn_id: str,
        exact_response: str,
    ) -> GateTransitionResult:
        self._ensure_coaching_not_interrupted(state)
        return answer_closing_gate(
            state,
            response_turn_id=response_turn_id,
            response_sequence=response_sequence,
            in_reply_to_turn_id=in_reply_to_turn_id,
            exact_response=exact_response,
        )

    def rollback(
        self, state: CoachingSessionState, target: CoachingStage, reason: str
    ) -> CoachingSessionState:
        return rollback_to(state, target, reason=reason)

    def return_to_pre_coaching(
        self, state: CoachingSessionState, reason: str
    ) -> CoachingSessionState:
        return return_to_pre_coaching(state, reason=reason)

    def validate_output(
        self,
        state: CoachingSessionState,
        output: CoachOutput,
        regenerate: Callable[[tuple[str, ...]], CoachOutput],
        *,
        grounded_coachee_input: str | None = None,
    ) -> ValidatedDelivery:
        self._ensure_coaching_not_interrupted(state)
        _, trusted_content = self._require_current_output_provenance(state, output)
        if (
            grounded_coachee_input is not None
            and grounded_coachee_input != trusted_content
        ):
            raise ValueError(
                "grounded coachee input must match the trusted inference turn"
            )

        def regenerate_current(reasons: tuple[str, ...]) -> CoachOutput:
            regenerated = regenerate(reasons)
            self._require_current_output_provenance(state, regenerated)
            return regenerated

        return validate_with_bounded_regeneration(
            output,
            regenerate_current,
            grounded_coachee_input=trusted_content,
        )

    def stage_candidates(
        self, state: CoachingSessionState, output: CoachOutput
    ) -> CoachingSessionState:
        self._ensure_coaching_not_interrupted(state)
        trusted_turn_id, _ = self._require_current_output_provenance(state, output)
        current_revision = state.revision_for(state.current_step)
        candidates = (
            output.candidate_goals
            + output.candidate_insights
            + output.candidate_commitments
            + output.candidate_memories
        )
        existing_ids = {item.candidate_id for item in state.candidate_records}
        if len({item.candidate_id for item in candidates}) != len(candidates):
            raise ValueError("output contains duplicate candidate IDs")
        if existing_ids & {item.candidate_id for item in candidates}:
            raise ValueError("candidate ID already exists in the session")
        if any(candidate.source_turn_id != trusted_turn_id for candidate in candidates):
            raise ValueError("candidate source turn must match the inference turn")
        if any(
            candidate.coaching_stage is not None
            and (
                candidate.coaching_stage is not state.current_step
                or candidate.stage_revision != current_revision
            )
            for candidate in candidates
        ):
            raise ValueError("candidate contains stale output provenance")
        staged = tuple(
            candidate.model_copy(
                update={
                    "coaching_stage": state.current_step,
                    "stage_revision": current_revision,
                }
            )
            for candidate in candidates
        )
        return state.model_copy(
            update={"candidate_records": state.candidate_records + staged}
        )

    def deliver(
        self,
        state: CoachingSessionState,
        delivery: ValidatedDelivery,
        sink: Callable[[CoachOutput], None],
    ) -> None:
        self._ensure_coaching_not_interrupted(state)
        _, trusted_content = self._require_current_output_provenance(
            state, delivery.output
        )
        if delivery.grounded_coachee_input != trusted_content:
            raise ValueError("validated delivery grounding is stale or untrusted")
        deliver_validated(delivery, sink)

    @staticmethod
    def _require_current_output_provenance(
        state: CoachingSessionState,
        output: CoachOutput,
    ) -> tuple[str, str]:
        inference_provenance = (
            output.inference_session_id,
            output.inference_turn_id,
            output.inference_stage_revision,
        )
        if any(item is None for item in inference_provenance):
            raise ValueError("complete inference provenance is required")
        if output.coaching_stage is not state.current_step:
            raise ValueError("output stage must match current coaching step")
        current_revision = state.revision_for(state.current_step)
        if (
            output.inference_session_id != state.session_id
            or output.inference_stage_revision != current_revision
        ):
            raise ValueError("stale output provenance cannot be used")
        if not state.turn_ledger:
            raise ValueError("trusted current coachee ledger turn is required")
        trusted_input = state.turn_ledger[-1]
        if (
            trusted_input.actor != "coachee"
            or trusted_input.turn_id != output.inference_turn_id
        ):
            raise ValueError("trusted current coachee ledger turn is required")
        return trusted_input.turn_id, trusted_input.content

    @staticmethod
    def _ensure_coaching_not_interrupted(state: CoachingSessionState) -> None:
        if state.safety_state in {SafetyState.POSSIBLE_CRISIS, SafetyState.URGENT}:
            raise ValueError("normal coaching is interrupted by the safety state")
