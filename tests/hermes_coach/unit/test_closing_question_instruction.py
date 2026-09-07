"""The closing question: what the prompt asks for, and what the gate accepts.

Requirement families: `HC-PROCESS`; sources `SRC-030…057`.

Three places have to agree on the shape of a closing question — the system
prompt the model reads, the default in `domain.transitions.open_closing_gate`,
and `policies.question_policy.is_yes_no_closing_question`, which is what
actually decides whether a step can close. They drifted once: the prompt asked
for "một câu chốt Có/Không" without saying the words must carry both poles, so
the model produced "Bạn cảm thấy sẵn sàng … chứ?", the predicate refused it, and
no step ever closed. Nothing failed, nothing logged; the product simply never
got past Pre-Coaching.

These tests pin the three together so that cannot happen quietly again.
"""

from __future__ import annotations

import pytest

from hermes_coach.policies.question_policy import is_yes_no_closing_question
from hermes_coach.prompt.system_prompt import (
    CLOSING_QUESTION_EXAMPLE,
    COACH_SYSTEM_PROMPT,
)


def test_the_example_the_prompt_gives_is_one_the_gate_accepts() -> None:
    """The instruction has to be followable.

    A prompt that showed the model a form the predicate rejects would be worse
    than no instruction at all.
    """
    assert is_yes_no_closing_question(CLOSING_QUESTION_EXAMPLE)


def test_the_prompt_shows_that_example_verbatim() -> None:
    assert CLOSING_QUESTION_EXAMPLE in COACH_SYSTEM_PROMPT


def test_the_prompt_asks_for_both_poles_rather_than_just_a_yes_no_question() -> None:
    """The words "Có/Không" alone were not enough, which is the whole point."""
    assert "cả hai cực" in COACH_SYSTEM_PROMPT


def test_the_domain_default_is_the_same_sentence() -> None:
    """`open_closing_gate` writes this question into the ledger itself."""
    import inspect

    from hermes_coach.domain.transitions import open_closing_gate

    default = inspect.signature(open_closing_gate).parameters["closing_question"].default
    assert default == CLOSING_QUESTION_EXAMPLE


@pytest.mark.parametrize(
    "question",
    [
        # Every one of these was actually produced by the Coach model during a
        # live Pre-Coaching step, and every one of them left the step open.
        "Bạn cảm thấy sẵn sàng để khám phá hướng đi nghề nghiệp của mình ngay bây giờ chứ?",
        "Bạn sẵn sàng bắt đầu định hình mục tiêu cụ thể cho hướng đi nghề nghiệp của mình trong 6 tháng tới?",
    ],
)
def test_a_leading_question_does_not_close_a_step(question: str) -> None:
    """These are decent coaching questions and still not gates.

    Each one presumes the yes it is asking for. A step must not close on a
    question that made "không" the harder answer to give.
    """
    assert not is_yes_no_closing_question(question)


@pytest.mark.parametrize(
    "question",
    [
        "Bạn có xác nhận đã sẵn sàng chuyển sang bước Goal không?",
        "Bạn có sẵn sàng bắt đầu làm rõ mục tiêu cụ thể cho 6 tháng tới không?",
        "Bạn có xác nhận phần này đã đủ rõ để chuyển bước không?",
    ],
)
def test_both_poles_in_the_wording_closes_a_step(question: str) -> None:
    assert is_yes_no_closing_question(question)


@pytest.mark.parametrize(
    "question",
    [
        # Produced live during the first end-to-end run. Both are refused, and
        # both should be: the Coachee said "Đồng ý" to each and the step stayed
        # open, because neither question gave them a real way to say no.
        "Bạn có xác nhận rằng bạn đã sẵn sàng và muốn tiếp tục với một mục tiêu"
        " chạy bộ cụ thể, hay có điều gì khác bạn muốn làm rõ trước khi chúng ta"
        " chốt bước này?",
        "Phiên coaching hôm nay đã hoàn tất, bạn sẵn sàng kết thúc phiên này chứ?",
    ],
)
def test_a_choice_or_leading_question_still_does_not_close_a_step(
    question: str,
) -> None:
    """The temptation after that run was to widen the predicate until these
    passed. That would trade the one safeguard making confirmation mean
    something — that the Coachee could have said no — for a smoother demo."""
    assert not is_yes_no_closing_question(question)


def test_the_prompt_names_the_choice_form_the_model_actually_produced() -> None:
    """An instruction that does not name the mistake does not prevent it."""
    assert "A, hay B?" in COACH_SYSTEM_PROMPT
