from __future__ import annotations

import pytest

from hermes_coach.prompt.question_validator import QuestionRejectCode, validate_question


@pytest.mark.parametrize(
    ("question", "coachee_input"),
    [
        ("Điều gì đang quan trọng nhất với bạn lúc này?", None),
        (
            "Bạn vừa nhắc lại cụm từ “tôi phải làm hết” ba lần; cụm từ đó có ý nghĩa gì với bạn?",
            "Tôi cứ lặp lại rằng tôi phải làm hết thì mới yên tâm.",
        ),
        (
            "Mình nghe thấy mong muốn chủ động; mình hiểu như vậy có đúng không?",
            "Tôi vừa lo lắng vừa mong muốn chủ động hơn.",
        ),
        ("Bạn có xác nhận bức tranh hiện trạng này để chuyển sang Options không?", None),
    ],
)
def test_valid_question_is_exactly_one_neutral_question(
    question: str, coachee_input: str | None
) -> None:
    assert validate_question(
        question,
        grounded_coachee_input=coachee_input,
    ).valid


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Tôi hiểu. Điều gì đang quan trọng với bạn?", QuestionRejectCode.STANDALONE_STATEMENT),
        ("Bạn muốn gì? Khi nào bạn bắt đầu?", QuestionRejectCode.MULTIPLE_QUESTIONS),
        ("Bạn nên nói chuyện với quản lý, đúng không?", QuestionRejectCode.DISGUISED_ADVICE),
        ("Hãy lập danh sách ba lựa chọn?", QuestionRejectCode.IMPERATIVE),
        ("Bạn đang tự phá hoại mình; vì sao vậy?", QuestionRejectCode.DIAGNOSIS_OR_LABEL),
        ("Tôi biết điều tốt nhất cho bạn là gì?", QuestionRejectCode.AUTHORITY_CLAIM),
    ],
)
def test_semantic_validator_fails_closed(text: str, code: QuestionRejectCode) -> None:
    result = validate_question(text)

    assert not result.valid
    assert code in result.reason_codes


@pytest.mark.parametrize(
    ("question", "coachee_input"),
    [
        (
            "Bạn vừa nhắc ‘nghỉ việc muốn tôi’; điều đó có đúng không?",
            "Tôi muốn nghỉ việc.",
        ),
        (
            "Mình nghe thấy chủ động mong muốn; mình hiểu như vậy có đúng không?",
            "Tôi mong muốn chủ động hơn.",
        ),
        (
            "Bạn vừa nhắc ‘tôi muốn nghỉ việc’; điều đó có đúng không?",
            "Tôi không muốn nghỉ việc.",
        ),
        (
            "Bạn vừa nhắc ‘tôi không muốn nghỉ việc’; điều đó có đúng không?",
            "Tôi muốn nghỉ việc.",
        ),
    ],
)
def test_grounded_reflection_rejects_reordering_or_negation_drift(
    question: str,
    coachee_input: str,
) -> None:
    result = validate_question(question, grounded_coachee_input=coachee_input)

    assert not result.valid
    assert QuestionRejectCode.STANDALONE_STATEMENT in result.reason_codes
