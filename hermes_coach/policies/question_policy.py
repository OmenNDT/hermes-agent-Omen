from __future__ import annotations

import re
import unicodedata

from hermes_coach.contracts.runtime_contract import CoachingStage
from hermes_coach.domain.enums import FunnelStage
from hermes_coach.domain.models import ImmutableModel
from hermes_coach.policies.companion_policy import PolicyReport
from hermes_coach.prompt.question_validator import validate_question


class QuestionIntentEvidence(ImmutableModel):
    current_step: CoachingStage
    intended_step: CoachingStage
    one_focus: bool
    grounded_in_current_concern: bool
    neutral: bool
    capacity_evoking: bool
    returns_ownership: bool
    denies_difficulty: bool = False
    accusatory_why: bool = False


def advance_funnel(current: FunnelStage, requested: FunnelStage) -> FunnelStage:
    ordered = tuple(FunnelStage)
    if ordered.index(requested) != ordered.index(current) + 1:
        raise ValueError("funnel progression must be sequential inside the current step")
    return requested


def assess_question_intent(evidence: QuestionIntentEvidence) -> PolicyReport:
    checks = (
        (evidence.current_step is not evidence.intended_step, "wrong_step"),
        (not evidence.one_focus, "multiple_focuses"),
        (not evidence.grounded_in_current_concern, "not_current_concern"),
        (not evidence.neutral, "not_neutral"),
        (not evidence.capacity_evoking, "does_not_evoke_capacity"),
        (not evidence.returns_ownership, "ownership_not_returned"),
        (evidence.denies_difficulty, "denies_difficulty"),
        (evidence.accusatory_why, "accusatory_why"),
    )
    violations = tuple(code for failed, code in checks if failed)
    return PolicyReport(compliant=not violations, violations=violations)


def is_yes_no_closing_question(question: str) -> bool:
    if not validate_question(question).valid:
        return False
    decomposed = unicodedata.normalize(
        "NFD", question.casefold().translate(str.maketrans("đĐ", "dD"))
    )
    normalized = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    has_confirmation = bool(
        re.search(
            r"\b(xac nhan|dong y|chot|san sang|co dung|co phu hop|agree|confirm|ready|correct)\b",
            normalized,
        )
    )
    # Both poles, deliberately. "chứ?" and "A, hay B?" are excluded on purpose
    # and stay excluded — the first end-to-end run met both, and the temptation
    # was to widen this until they passed.
    #
    # "…sẵn sàng chứ?" is a leading question: it presumes the yes it is asking
    # for. "A, hay B?" is a choice question, which "Đồng ý" does not answer. A
    # step closes on a question that genuinely offered the Coachee the chance to
    # say no, or it does not close. Widening this to smooth over a phrasing the
    # model chose would trade the one safeguard that makes confirmation mean
    # anything for a shorter conversation.
    #
    # The prompt is what has to change, and the silence is what has to end —
    # `unmatched_yes` now tells the Coachee their words were fine and no
    # question was open. Neither of those costs anything here.
    has_no_pole = bool(re.search(r"\b(khong|chua|no|not)\b", normalized))
    return has_confirmation and has_no_pole
