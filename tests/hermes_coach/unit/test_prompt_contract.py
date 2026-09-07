from __future__ import annotations

import pytest

from hermes_coach.prompt.question_validator import QuestionRejectCode, validate_question


@pytest.mark.parametrize(
    ("question", "reason"),
    [
        (
            "Tôi đề xuất bạn nghỉ việc; điều gì phù hợp nhất?",
            QuestionRejectCode.DISGUISED_ADVICE,
        ),
        (
            "Bạn nên nghỉ việc; điều gì phù hợp nhất?",
            QuestionRejectCode.DISGUISED_ADVICE,
        ),
        (
            "Bạn có thể thử trao đổi với quản lý?",
            QuestionRejectCode.DISGUISED_ADVICE,
        ),
        (
            "Một lựa chọn là trao đổi với quản lý?",
            QuestionRejectCode.DISGUISED_ADVICE,
        ),
        (
            "Sẽ tốt hơn nếu bạn trao đổi với quản lý?",
            QuestionRejectCode.DISGUISED_ADVICE,
        ),
        (
            "Tôi hiểu bạn đang lo; điều gì phù hợp nhất với bạn?",
            QuestionRejectCode.STANDALONE_STATEMENT,
        ),
        (
            "Bạn vừa nhắc “tôi phải làm hết”; tôi hiểu; điều gì phù hợp với bạn?",
            QuestionRejectCode.STANDALONE_STATEMENT,
        ),
    ],
)
def test_advice_or_ungrounded_statement_before_question_is_rejected(
    question: str, reason: QuestionRejectCode
) -> None:
    result = validate_question(question)

    assert not result.valid
    assert reason in result.reason_codes


@pytest.mark.parametrize(
    "question",
    [
        "Điều gì quan trọng với bạn và khi nào bạn sẽ bắt đầu?",
        "Bạn muốn nghỉ việc hay thương lượng; và bạn sẽ làm khi nào?",
        "Bạn nghĩ gì về lựa chọn này và bạn sẽ làm gì tiếp theo?",
    ],
)
def test_one_question_mark_with_multiple_focuses_is_rejected(question: str) -> None:
    result = validate_question(question)

    assert not result.valid
    assert QuestionRejectCode.MULTIPLE_FOCUSES in result.reason_codes


def test_grounded_coachee_quote_can_lead_one_feedback_question() -> None:
    question = (
        "Bạn vừa nhắc lại cụm từ “tôi phải làm hết”; "
        "cụm từ đó có ý nghĩa gì với bạn?"
    )

    grounded = validate_question(
        question,
        grounded_coachee_input="Tôi thấy rằng tôi phải làm hết thì mới yên tâm.",
    )
    ungrounded = validate_question(
        question,
        grounded_coachee_input="Tôi muốn nhờ đồng nghiệp hỗ trợ.",
    )
    missing_evidence = validate_question(question)

    assert grounded.valid
    assert not ungrounded.valid
    assert not missing_evidence.valid
    assert QuestionRejectCode.STANDALONE_STATEMENT in ungrounded.reason_codes
