from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from hermes_coach.contracts.runtime_contract import CoachOutput
from hermes_coach.domain.models import ImmutableModel
from hermes_coach.prompt.question_validator import validate_question


class RegenerationCode(StrEnum):
    SEMANTIC_QUESTION_REJECTED = "semantic_question_rejected"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"


class OutputRejected(RuntimeError):
    """Raised before any output sink when validation remains invalid."""


class ValidatedDelivery(ImmutableModel):
    output: CoachOutput
    attempts: int
    grounded_coachee_input: str | None = None


def validate_with_bounded_regeneration(
    initial: CoachOutput,
    regenerate: Callable[[tuple[str, ...]], CoachOutput],
    *,
    max_regenerations: int = 2,
    grounded_coachee_input: str | None = None,
) -> ValidatedDelivery:
    output = initial
    for attempt in range(max_regenerations + 1):
        result = validate_question(
            output.question,
            grounded_coachee_input=grounded_coachee_input,
        )
        if result.valid:
            return ValidatedDelivery(
                output=output,
                attempts=attempt + 1,
                grounded_coachee_input=grounded_coachee_input,
            )
        if attempt < max_regenerations:
            output = regenerate(tuple(code.value for code in result.reason_codes))
    raise OutputRejected(RegenerationCode.ATTEMPTS_EXHAUSTED.value)


def deliver_validated(delivery: ValidatedDelivery, sink: Callable[[CoachOutput], None]) -> None:
    if not validate_question(
        delivery.output.question,
        grounded_coachee_input=delivery.grounded_coachee_input,
    ).valid:
        raise OutputRejected(RegenerationCode.SEMANTIC_QUESTION_REJECTED.value)
    sink(delivery.output)
