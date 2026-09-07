from __future__ import annotations

import re
import unicodedata
from typing import Literal

from hermes_coach.contracts.runtime_contract import CoachingStage, GateAnswer
from hermes_coach.domain.enums import FunnelStage
from hermes_coach.domain.session_state import (
    GROW_STAGES,
    STAGE_ORDER,
    ClosingGateBinding,
    CoachingSessionState,
    SessionTurn,
    SessionGateEvent,
    StageRevision,
    stage_is_complete,
)
from hermes_coach.domain.models import ImmutableModel


class GateTransitionResult(ImmutableModel):
    state: CoachingSessionState
    answer: GateAnswer
    advanced: bool = False
    reason: str


# A gate answer is classified lexically, and deliberately conservatively.
#
# This used to be an exact-match set: a hand-enumerated grid of prefixes,
# pronouns and confirmations, and anything outside the grid was UNCLEAR. The
# grid was built from a handful of eval transcripts, so it accepted "Đồng ý"
# but not "Đúng, tôi xác nhận" — and a Coachee who said the second one watched
# their step refuse to close with no explanation. Verified live: the same gate
# that ignored "Đúng, tôi xác nhận" opened immediately on "Đồng ý".
#
# The shape now is an allowlist of affirmation cores plus a denylist of things
# that make an answer less than unqualified. Both are needed. The allowlist
# alone would take "Đồng ý nếu đổi deadline" as a yes; the denylist alone has
# nothing to affirm.
#
# It stays lexical, and it stays wrong in the safe direction: an answer it
# cannot read is UNCLEAR, which leaves the gate open and the Coach asking
# again. A false YES advances the session on something the Coachee did not
# agree to, and there is no undo for that.

# Split by how much the word can mean on its own.
#
# "đồng ý" and "xác nhận" are confirmations wherever they appear in a sentence.
# "có" is not: it is also the ordinary verb "to have", so "Công việc đó có vẻ
# nhiều" contains the token "có" and means nothing like agreement. Treating the
# two classes alike produced a false YES on plain prose — a gate closing on a
# step the Coachee never agreed to, which is the one error with no undo.
_STRONG_AFFIRMATIONS = (
    "dong y",
    "xac nhan",
    "chinh xac",
    "dung vay",
    "dung roi",
    "san sang",
    "chuan roi",
    "yes",
    "yeah",
    "yep",
)

# These count only when the answer opens with them, where they can only be
# answering the question that was asked.
_WEAK_AFFIRMATIONS = (
    "co",
    "dung",
    "ok",
    "okay",
    "chuan",
    "chot",
    "u",
    "vang",
    "da",
)

# Anything here makes the answer qualified, hesitant, partial or
# self-contradicting, whatever else it contains.
_QUALIFIERS = (
    # Hedges.
    "co le",
    "co ve",
    "co the",
    "co khi",
    "dung ra",
    "dung hon",
    "chac la",
    "hinh nhu",
    "tam thoi",
    "tam thi",
    "chua chac",
    "chua ro",
    "khong chac",
    "maybe",
    "guess",
    "think so",
    "probably",
    "sort of",
    "kind of",
    "i guess",
    # Conditions and reservations.
    "nhung",
    "tuy nhien",
    "neu",
    "mien la",
    "voi dieu kien",
    "tru khi",
    "ngoai tru",
    "con phan",
    "de sau",
    "but",
    "if",
    "except",
    "however",
    # A negation that did not open the answer: "yes no" is not agreement.
    "khong",
    "chua",
    "no",
    "not",
)


def _contains_token_run(haystack: str, needle: str) -> bool:
    """Whole-word containment, so "co" does not match inside "cong viec"."""
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def classify_gate_answer(response: str) -> GateAnswer:
    """YES only for unqualified explicit agreement. Everything else is UNCLEAR.

    NO is deliberately narrow — an answer that *opens* with a refusal — because
    a refusal in the middle of a sentence ("yes no", "đồng ý nhưng không chắc")
    is a Coachee who has not decided, not one who has said no.
    """
    normalized = _normalize(response)

    if normalized in {"no", "khong", "khong dong y"} or normalized.startswith(
        ("no ", "khong ", "no,", "khong,")
    ):
        return GateAnswer.NO

    # A refusal phrase is unambiguous wherever it sits, unlike a bare "không"
    # that might be part of a question the Coachee is quoting back.
    if any(
        _contains_token_run(normalized, phrase)
        for phrase in ("khong dong y", "khong phai vay", "khong dung", "chua dong y")
    ):
        return GateAnswer.NO

    if any(_contains_token_run(normalized, phrase) for phrase in _QUALIFIERS):
        return GateAnswer.UNCLEAR

    if any(_contains_token_run(normalized, phrase) for phrase in _STRONG_AFFIRMATIONS):
        return GateAnswer.YES

    if normalized in _WEAK_AFFIRMATIONS or normalized.startswith(
        tuple(f"{word} " for word in _WEAK_AFFIRMATIONS)
    ):
        return GateAnswer.YES

    return GateAnswer.UNCLEAR


def append_trusted_turn(
    state: CoachingSessionState,
    *,
    turn_id: str,
    sequence: int,
    actor: Literal["coach", "coachee"],
    content: str,
) -> CoachingSessionState:
    if any(turn.turn_id == turn_id for turn in state.turn_ledger):
        raise ValueError("turn ledger IDs must be unique")
    if state.turn_ledger and sequence != state.turn_ledger[-1].sequence + 1:
        raise ValueError("turn ledger append must use the next sequence")
    turn = SessionTurn(
        turn_id=turn_id,
        sequence=sequence,
        actor=actor,
        content=content.strip(),
    )
    return state.model_copy(update={"turn_ledger": state.turn_ledger + (turn,)})


def open_closing_gate(
    state: CoachingSessionState,
    question_turn_id: str,
    *,
    question_sequence: int,
    closing_question: str = "Bạn có xác nhận nội dung bước này là đúng không?",
) -> CoachingSessionState:
    if state.ended:
        raise ValueError("ended session cannot open a gate")
    if not stage_is_complete(state):
        raise ValueError("current stage is incomplete")
    if state.funnel_stage is not FunnelStage.CLARIFY:
        raise ValueError("closing gate requires sequential funnel completion")
    with_question = append_trusted_turn(
        state,
        turn_id=question_turn_id,
        sequence=question_sequence,
        actor="coach",
        content=closing_question,
    )
    binding = ClosingGateBinding(
        stage=with_question.current_step,
        revision=with_question.revision_for(with_question.current_step),
        question_turn_id=question_turn_id,
        question_sequence=question_sequence,
    )
    return with_question.model_copy(
        update={"pending_gate": binding, "funnel_stage": FunnelStage.CLOSE}
    )


def answer_closing_gate(
    state: CoachingSessionState,
    *,
    response_turn_id: str,
    response_sequence: int,
    in_reply_to_turn_id: str,
    exact_response: str,
) -> GateTransitionResult:
    binding = state.pending_gate
    if binding is None:
        return GateTransitionResult(
            state=state, answer=GateAnswer.UNCLEAR, reason="no_open_gate"
        )
    binding_is_current = (
        binding.stage is state.current_step
        and binding.revision == state.revision_for(state.current_step)
    )
    question_is_ledger_tail = bool(
        state.turn_ledger
        and state.turn_ledger[-1].turn_id == binding.question_turn_id
        and state.turn_ledger[-1].sequence == binding.question_sequence
        and state.turn_ledger[-1].actor == "coach"
    )
    try:
        with_response = append_trusted_turn(
            state,
            turn_id=response_turn_id,
            sequence=response_sequence,
            actor="coachee",
            content=exact_response,
        )
    except ValueError:
        with_response = state
    response_is_adjacent = (
        question_is_ledger_tail
        and with_response is not state
        and binding.question_turn_id == in_reply_to_turn_id
        and response_turn_id != binding.question_turn_id
        and response_sequence == binding.question_sequence + 1
    )
    if not binding_is_current or not response_is_adjacent:
        cleared = with_response.model_copy(
            update={"pending_gate": None, "funnel_stage": FunnelStage.CLARIFY}
        )
        return GateTransitionResult(
            state=cleared,
            answer=GateAnswer.UNCLEAR,
            reason="response_not_immediate",
        )
    answer = classify_gate_answer(exact_response)
    can_advance = answer is GateAnswer.YES and stage_is_complete(with_response)
    event = SessionGateEvent(
        stage=binding.stage,
        revision=binding.revision,
        closing_question_turn_id=binding.question_turn_id,
        question_sequence=binding.question_sequence,
        response_turn_id=response_turn_id,
        response_sequence=response_sequence,
        exact_response=exact_response,
        answer=answer,
        valid=can_advance,
    )
    events = state.gate_events + (event,)
    if not can_advance:
        stayed = with_response.model_copy(
            update={"gate_events": events, "pending_gate": None, "funnel_stage": FunnelStage.CLARIFY}
        )
        reason = "gate_no" if answer is GateAnswer.NO else "gate_unclear"
        return GateTransitionResult(state=stayed, answer=answer, reason=reason)
    current_index = STAGE_ORDER.index(state.current_step)
    if state.current_step is CoachingStage.REVIEW:
        ended = with_response.model_copy(
            update={"gate_events": events, "pending_gate": None, "ended": True}
        )
        return GateTransitionResult(
            state=ended, answer=answer, advanced=True, reason="session_closed"
        )
    advanced = with_response.model_copy(
        update={
            "current_step": STAGE_ORDER[current_index + 1],
            "funnel_stage": FunnelStage.OPEN,
            "gate_events": events,
            "pending_gate": None,
        }
    )
    return GateTransitionResult(state=advanced, answer=answer, advanced=True, reason="advanced")


def rollback_to(
    state: CoachingSessionState, target: CoachingStage, *, reason: str
) -> CoachingSessionState:
    if target not in GROW_STAGES:
        raise ValueError("rollback target must be G/R/O/W")
    if not reason.strip():
        raise ValueError("rollback requires a concrete reason")
    if STAGE_ORDER.index(target) >= STAGE_ORDER.index(state.current_step):
        raise ValueError("rollback target must precede the current step")
    target_index = STAGE_ORDER.index(target)
    revised = tuple(
        StageRevision(
            stage=item.stage,
            revision=item.revision + 1
            if STAGE_ORDER.index(item.stage) >= target_index
            else item.revision,
        )
        for item in state.revisions
    )
    invalidated = tuple(
        event.model_copy(update={"valid": False})
        if STAGE_ORDER.index(event.stage) >= target_index
        else event
        for event in state.gate_events
    )
    updates: dict[str, object] = {
        "current_step": target,
        "funnel_stage": FunnelStage.OPEN,
        "revisions": revised,
        "gate_events": invalidated,
        "pending_gate": None,
        "ended": False,
        "candidate_records": tuple(
            candidate
            for candidate in state.candidate_records
            if candidate.coaching_stage is not None
            and STAGE_ORDER.index(candidate.coaching_stage) < target_index
        ),
    }
    updates.update(_cleared_snapshots(target))
    return state.model_copy(update=updates)


def return_to_pre_coaching(
    state: CoachingSessionState, *, reason: str
) -> CoachingSessionState:
    if state.current_step is CoachingStage.PRE_COACHING:
        return state
    if not reason.strip():
        raise ValueError("return to Pre-Coaching requires a concrete readiness reason")
    from hermes_coach.domain.models import (
        OptionsSnapshot,
        PreCoachingSnapshot,
        RealitySnapshot,
        ReviewSnapshot,
        WillSnapshot,
    )

    revised = tuple(
        StageRevision(
            stage=item.stage,
            revision=item.revision + 1,
        )
        for item in state.revisions
    )
    invalidated = tuple(event.model_copy(update={"valid": False}) for event in state.gate_events)
    return state.model_copy(
        update={
            "current_step": CoachingStage.PRE_COACHING,
            "funnel_stage": FunnelStage.OPEN,
            "revisions": revised,
            "gate_events": invalidated,
            "pending_gate": None,
            "pre_coaching": PreCoachingSnapshot(),
            "goal": None,
            "reality": RealitySnapshot(),
            "options": OptionsSnapshot(),
            "will": WillSnapshot(),
            "review": ReviewSnapshot(),
            "candidate_records": (),
            "ended": False,
        }
    )


def _cleared_snapshots(target: CoachingStage) -> dict[str, object]:
    from hermes_coach.domain.models import (
        OptionsSnapshot,
        RealitySnapshot,
        ReviewSnapshot,
        WillSnapshot,
    )

    fields: dict[CoachingStage, tuple[str, object]] = {
        CoachingStage.GOAL: ("goal", None),
        CoachingStage.REALITY: ("reality", RealitySnapshot()),
        CoachingStage.OPTIONS: ("options", OptionsSnapshot()),
        CoachingStage.WILL: ("will", WillSnapshot()),
        CoachingStage.REVIEW: ("review", ReviewSnapshot()),
    }
    start = STAGE_ORDER.index(target)
    return dict(fields[stage] for stage in STAGE_ORDER[start:] if stage in fields)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize(
        "NFD", value.casefold().strip().translate(str.maketrans("đĐ", "dD"))
    )
    no_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", no_marks).strip()
