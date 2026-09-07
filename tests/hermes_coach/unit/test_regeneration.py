from __future__ import annotations

import pytest

from hermes_coach.contracts.runtime_contract import CoachOutput, CoachingStage
from hermes_coach.prompt.regeneration import (
    OutputRejected,
    deliver_validated,
    validate_with_bounded_regeneration,
)


def output(question: str) -> CoachOutput:
    return CoachOutput(question=question, coaching_stage=CoachingStage.GOAL)


def test_invalid_output_is_regenerated_before_sink() -> None:
    reasons_seen: list[tuple[str, ...]] = []
    delivery = validate_with_bounded_regeneration(
        output("Bạn nên nói với quản lý, đúng không?"),
        lambda reasons: reasons_seen.append(reasons) or output("Điều gì bạn muốn làm rõ?"),
    )
    delivered: list[CoachOutput] = []
    deliver_validated(delivery, delivered.append)

    assert reasons_seen
    assert [item.question for item in delivered] == ["Điều gì bạn muốn làm rõ?"]


def test_invalid_output_never_reaches_sink_after_bounded_attempts() -> None:
    sink: list[CoachOutput] = []
    with pytest.raises(OutputRejected):
        delivery = validate_with_bounded_regeneration(
            output("Hãy làm việc này?"), lambda _: output("Bạn nên làm việc đó, đúng không?")
        )
        deliver_validated(delivery, sink.append)

    assert sink == []


def test_grounded_reflection_evidence_survives_the_delivery_boundary() -> None:
    coachee_input = "Tôi thấy rằng tôi phải làm hết thì mới yên tâm."
    reflected = output(
        "Bạn vừa nhắc ‘tôi phải làm hết’; cụm từ đó có ý nghĩa gì với bạn?"
    )
    delivery = validate_with_bounded_regeneration(
        reflected,
        lambda _reasons: reflected,
        grounded_coachee_input=coachee_input,
    )
    sink: list[CoachOutput] = []

    deliver_validated(delivery, sink.append)

    assert sink == [reflected]
    assert delivery.grounded_coachee_input == coachee_input


def test_delivery_rejects_reflection_that_no_longer_matches_retained_grounding() -> None:
    coachee_input = "Tôi muốn nghỉ việc."
    reflected = output(
        "Bạn vừa nhắc ‘tôi muốn nghỉ việc’; cụm từ đó có ý nghĩa gì với bạn?"
    )
    delivery = validate_with_bounded_regeneration(
        reflected,
        lambda _reasons: reflected,
        grounded_coachee_input=coachee_input,
    )
    reordered = output(
        "Bạn vừa nhắc ‘nghỉ việc muốn tôi’; cụm từ đó có ý nghĩa gì với bạn?"
    )
    tampered_delivery = delivery.model_copy(update={"output": reordered})
    sink: list[CoachOutput] = []

    with pytest.raises(OutputRejected, match="semantic_question_rejected"):
        deliver_validated(tampered_delivery, sink.append)

    assert sink == []
