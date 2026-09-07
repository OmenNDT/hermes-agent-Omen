"""What counts as a yes at a step gate.

Requirement families: `HC-PRODUCT`; sources `SRC-026`, `SRC-104…106`.

`classify_gate_answer` used to be an exact-match set — a hand-enumerated grid
of prefix × pronoun × confirmation, built from a handful of eval transcripts.
Anything outside the grid was UNCLEAR, and UNCLEAR is silent: the step does not
close, the Coach asks again, and the Coachee has no way to know that the words
they chose were the problem.

Found live, not in review. A session confirmed with "Đồng ý" and refused the
same confirmation phrased as "Đúng, tôi xác nhận" — a sentence no reasonable
person would call ambiguous.

The rule now is an affirmation allowlist plus a qualifier denylist. These tests
hold both halves down, because either alone is wrong: the allowlist by itself
takes "Đồng ý nếu đổi deadline" as agreement, and the denylist by itself has
nothing to affirm.
"""

from __future__ import annotations

import pytest

from hermes_coach.contracts.runtime_contract import GateAnswer
from hermes_coach.domain.transitions import classify_gate_answer


@pytest.mark.parametrize(
    "response",
    [
        # The originals, which must keep passing.
        "Yes",
        " yes. ",
        "Có",
        "có!",
        "Đồng ý",
        "Yes, tôi hiểu và đồng ý cách làm việc.",
        "Yes, phần tổng kết này đúng và tôi đồng ý kết thúc.",
        # The ones the old grid dropped on the floor.
        "Đúng, tôi xác nhận.",
        "Đúng rồi",
        "Chính xác",
        "Tôi xác nhận",
        "Vâng, đồng ý",
        "Ừ đúng vậy",
        "Chuẩn rồi bạn",
        "OK",
        "Mình xác nhận",
        "Em đồng ý",
    ],
)
def test_an_unqualified_yes_closes_the_step(response: str) -> None:
    assert classify_gate_answer(response) is GateAnswer.YES


@pytest.mark.parametrize(
    "response",
    ["Không", "No", "Không, mục tiêu vẫn chưa đúng.", "No, phần tổng kết chưa đủ."],
)
def test_a_refusal_that_opens_the_answer_is_a_no(response: str) -> None:
    assert classify_gate_answer(response) is GateAnswer.NO


@pytest.mark.parametrize(
    "response",
    [
        # Hedged.
        "Có lẽ",
        "Yes, nhưng tôi chưa chắc",
        "Yes I guess",
        "Tôi chưa rõ",
        # Conditional.
        "đồng ý tạm thời",
        "Đồng ý nếu đổi deadline",
        "Đồng ý với điều kiện tôi được đổi ngày",
        # Partial: agreement to one part is not agreement to the step.
        "Đồng ý phần mục tiêu, còn phần cam kết để sau",
        # Self-contradicting. A refusal that is not the opening word means the
        # Coachee has not decided, which is not the same as saying no.
        "yes no",
        # No affirmation in it at all, however agreeable it sounds.
        "Tôi nghĩ là công việc này ổn",
    ],
)
def test_anything_less_than_unqualified_leaves_the_gate_open(response: str) -> None:
    assert classify_gate_answer(response) is GateAnswer.UNCLEAR


@pytest.mark.parametrize("response", ["Tôi không đồng ý", "Cái này không đúng"])
def test_a_refusal_phrase_is_a_no_wherever_it_sits(response: str) -> None:
    assert classify_gate_answer(response) is GateAnswer.NO


@pytest.mark.parametrize(
    "response",
    [
        # "có" is also the verb "to have"; "đúng" is also "properly/actually".
        # Read as affirmations wherever they appear, ordinary prose closes a
        # gate — a step confirmed by someone who was still thinking out loud.
        "Công việc đó có vẻ nhiều",
        "Tôi có ba lựa chọn đang cân nhắc",
        "Tôi thấy anh Tuấn có thể giúp",
        "Mục tiêu đúng ra phải rõ hơn",
        "Đúng ra thì tôi nên hỏi lại",
        "Có thể tuần sau tôi mới bắt đầu",
        "Tôi chưa biết mình có làm được không",
        "Cái này ok nhưng cái kia thì chưa",
    ],
)
def test_prose_that_merely_contains_an_affirming_word_is_not_a_yes(
    response: str,
) -> None:
    assert classify_gate_answer(response) is GateAnswer.UNCLEAR
