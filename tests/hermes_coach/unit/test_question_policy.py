from __future__ import annotations

import pytest

from hermes_coach.contracts.runtime_contract import CoachingStage
from hermes_coach.domain.enums import FunnelStage
from hermes_coach.policies.question_policy import (
    QuestionIntentEvidence,
    advance_funnel,
    assess_question_intent,
    is_yes_no_closing_question,
)


def test_funnel_advances_in_order_inside_one_step() -> None:
    current = FunnelStage.OPEN
    for expected in (FunnelStage.DISCOVER, FunnelStage.CLARIFY, FunnelStage.CLOSE):
        current = advance_funnel(current, expected)
        assert current is expected


def test_funnel_cannot_skip_or_move_backwards() -> None:
    with pytest.raises(ValueError, match="sequential"):
        advance_funnel(FunnelStage.OPEN, FunnelStage.CLARIFY)
    with pytest.raises(ValueError, match="sequential"):
        advance_funnel(FunnelStage.CLARIFY, FunnelStage.OPEN)


def test_good_question_is_neutral_stage_aligned_capacity_and_ownership_evoking() -> None:
    valid = assess_question_intent(
        QuestionIntentEvidence(
            current_step=CoachingStage.REALITY,
            intended_step=CoachingStage.REALITY,
            one_focus=True,
            grounded_in_current_concern=True,
            neutral=True,
            capacity_evoking=True,
            returns_ownership=True,
        )
    )
    invalid = assess_question_intent(
        QuestionIntentEvidence(
            current_step=CoachingStage.REALITY,
            intended_step=CoachingStage.OPTIONS,
            one_focus=False,
            grounded_in_current_concern=False,
            neutral=False,
            capacity_evoking=False,
            returns_ownership=False,
        )
    )

    assert valid.compliant
    assert not invalid.compliant
    assert "wrong_step" in invalid.violations


def test_closing_question_must_be_one_explicit_yes_no_question() -> None:
    assert is_yes_no_closing_question(
        "Bạn có xác nhận phần này đã đủ rõ để chuyển bước không?"
    )
    assert not is_yes_no_closing_question("Điều gì đã đủ rõ với bạn?")
    assert not is_yes_no_closing_question("Bạn có xác nhận không? Khi nào bạn bắt đầu?")
