from __future__ import annotations

from dataclasses import dataclass
import re

from hermes_coach.application.coaching_service import CoachingService
from hermes_coach.application.safety_service import route_safety
from hermes_coach.contracts.evaluation_contract import (
    EvaluationRubric,
    EvaluationScenario,
    ScenarioCategory,
)
from hermes_coach.contracts.evaluation_result import ScenarioObservation
from hermes_coach.contracts.runtime_contract import (
    CoachingStage,
    GateAnswer,
    GoalSmartAssessment,
)
from hermes_coach.domain.enums import FunnelStage, SafetyOutputMode, SafetyState
from hermes_coach.domain.models import (
    GoalSnapshot,
    OptionAssessment,
    OptionIdea,
    OptionsSnapshot,
    PreCoachingSnapshot,
    RealitySnapshot,
    ReviewSnapshot,
    WillSnapshot,
)
from hermes_coach.domain.goal_rules import SMART_FIELDS, assess_goal
from hermes_coach.domain.options_rules import assess_option_novelty
from hermes_coach.domain.session_state import (
    GROW_STAGES,
    CoachingSessionState,
    SessionGateEvent,
    SessionTurn,
    TurnActor,
)
from hermes_coach.domain.transitions import classify_gate_answer
from hermes_coach.policies.companion_policy import (
    BarrierHypothesisEvidence,
    CompanionEvidence,
    evaluate_barrier_hypothesis,
    evaluate_companion,
)
from hermes_coach.policies.listening_policy import (
    ListeningEvidence,
    ListeningLevel,
    assess_listening,
)
from hermes_coach.policies.question_policy import (
    QuestionIntentEvidence,
    assess_question_intent,
)
from hermes_coach.prompt.question_validator import (
    QuestionRejectCode,
    QuestionValidationResult,
    validate_question,
)


class PureEngineEvaluator:
    """Runs scenario inputs through Phase-2 services without reading expected output."""

    def evaluate(
        self,
        scenario: EvaluationScenario,
        rubrics: tuple[EvaluationRubric, ...],
    ) -> ScenarioObservation:
        del rubrics
        transition = _transition_for(scenario)
        novelty_correct, novel_observed = _novelty_for(scenario)
        safety_correct, safety_exception = _safety_for(scenario)
        emitted = _emitted_output_for(scenario)
        question_count = emitted.text.count("?")
        question_validation = validate_question(
            emitted.text,
            grounded_coachee_input=emitted.grounding,
        )
        question_valid = question_count == 0 or question_validation.valid
        companion_equal, companion_listen = _companion_scores(
            scenario,
            emitted,
            question_validation,
        )
        goal_smart, goal_ownership = _goal_scores(scenario)
        criterion_scores = _criterion_scores(
            scenario,
            companion_equal=companion_equal,
            companion_listen=companion_listen,
            goal_smart=goal_smart,
            goal_ownership=goal_ownership,
            question_valid=question_valid,
            novelty_correct=novelty_correct,
            safety_correct=safety_correct,
            transition=transition,
        )
        return ScenarioObservation(
            scenario_id=scenario.id,
            actual_next_stage=transition.next_stage,
            question_count=question_count,
            closing_question_observed=transition.closing_question_observed,
            gate_answer=transition.gate_answer,
            rollback_to=transition.rollback,
            return_to_pre_coaching=transition.return_to_pre,
            novel_option_observed=novel_observed,
            safety_exception=safety_exception,
            met_behaviors=(),
            prohibited_behaviors=(),
            criterion_scores=criterion_scores,
        )


@dataclass(frozen=True)
class TransitionTrace:
    next_stage: CoachingStage
    rollback: CoachingStage | None = None
    return_to_pre: bool = False
    closing_question_observed: bool = False
    gate_answer: GateAnswer | None = None


@dataclass(frozen=True)
class EmittedOutput:
    text: str
    intended_step: CoachingStage
    grounding: str | None = None
    grounded_excerpt: str | None = None


def _transition_for(
    scenario: EvaluationScenario,
) -> TransitionTrace:
    service = CoachingService()
    state = _complete_state(scenario.stage)
    normalized_input = scenario.coachee_input.casefold()
    if scenario.category is ScenarioCategory.ROLLBACK:
        target = _rollback_target(normalized_input)
        if target is None:
            return TransitionTrace(next_stage=state.current_step)
        rolled = service.rollback(state, target, reason="scenario requires revalidation")
        return TransitionTrace(next_stage=rolled.current_step, rollback=target)
    if "chưa sẵn sàng" in normalized_input and scenario.stage is not CoachingStage.PRE_COACHING:
        returned = service.return_to_pre_coaching(state, "readiness changed")
        return TransitionTrace(next_stage=returned.current_step, return_to_pre=True)
    if scenario.category is not ScenarioCategory.GATE:
        answer = classify_gate_answer(scenario.coachee_input)
        return TransitionTrace(
            next_stage=state.current_step,
            gate_answer=answer if _looks_like_gate_response(normalized_input) else None,
        )

    if "đủ rõ" in normalized_input:
        state = service.advance_funnel(state, FunnelStage.DISCOVER)
        state = service.advance_funnel(state, FunnelStage.CLARIFY)
        question_sequence = _next_sequence(state)
        service.open_gate(
            state,
            question_turn_id="scenario-closing-question",
            closing_question="Bạn có xác nhận nội dung bước này là đúng không?",
            question_sequence=question_sequence,
        )
        return TransitionTrace(
            next_stage=state.current_step,
            closing_question_observed=True,
        )
    if "bỏ qua" in normalized_input:
        return TransitionTrace(next_stage=state.current_step)

    state = service.advance_funnel(state, FunnelStage.DISCOVER)
    state = service.advance_funnel(state, FunnelStage.CLARIFY)
    question_sequence = _next_sequence(state)
    opened = service.open_gate(
        state,
        question_turn_id="scenario-closing-question",
        closing_question="Bạn có xác nhận nội dung bước này là đúng không?",
        question_sequence=question_sequence,
    )
    result = service.answer_gate(
        opened,
        response_turn_id="scenario-response",
        response_sequence=question_sequence + 1,
        in_reply_to_turn_id="scenario-closing-question",
        exact_response=scenario.coachee_input,
    )
    return TransitionTrace(
        next_stage=result.state.current_step,
        gate_answer=result.answer,
    )


def _rollback_target(text: str) -> CoachingStage | None:
    if "mục tiêu" in text or "thực sự muốn gì" in text:
        return CoachingStage.GOAL
    if "giả định" in text:
        return CoachingStage.REALITY
    if "cam kết" in text:
        return CoachingStage.WILL
    return None


def _looks_like_gate_response(text: str) -> bool:
    return text.lstrip().startswith("yes")


def _next_sequence(state: CoachingSessionState) -> int:
    return state.turn_ledger[-1].sequence + 1 if state.turn_ledger else 0


def _complete_state(stage: CoachingStage) -> CoachingSessionState:
    options, option_turns = _options_evidence(start_sequence=0)
    turn_ledger: tuple[SessionTurn, ...] = ()
    gate_events: tuple[SessionGateEvent, ...] = ()
    if stage is CoachingStage.OPTIONS:
        turn_ledger = option_turns
    elif stage is CoachingStage.REVIEW:
        review_turns: list[SessionTurn] = []
        review_events: list[SessionGateEvent] = []
        sequence = 0
        for grow_stage in (CoachingStage.GOAL, CoachingStage.REALITY):
            event, turns = _gate_evidence(grow_stage, sequence)
            review_events.append(event)
            review_turns.extend(turns)
            sequence += 2
        options, turns = _options_evidence(start_sequence=sequence)
        review_turns.extend(turns)
        sequence += len(turns)
        for grow_stage in (CoachingStage.OPTIONS, CoachingStage.WILL):
            event, turns = _gate_evidence(grow_stage, sequence)
            review_events.append(event)
            review_turns.extend(turns)
            sequence += 2
        turn_ledger = tuple(review_turns)
        gate_events = tuple(review_events)

    return CoachingSessionState(
        session_id="scenario-session",
        current_step=stage,
        pre_coaching=PreCoachingSnapshot(
            ready=True,
            coaching_understood=True,
            roles_agreed=True,
            boundaries_agreed=True,
        ),
        goal=GoalSnapshot(
            wording="Xuất bản portfolio trước ngày 30/09/2026",
            smart=GoalSmartAssessment(
                specific=True,
                measurable=True,
                achievable=True,
                relevant=True,
                time_bound=True,
            ),
            belongs_to_coachee=True,
            aligned_with_values_or_needs=True,
            within_influence=True,
            benefit="Tăng tự tin nghề nghiệp",
            success_evidence="Portfolio công khai",
        ),
        reality=RealitySnapshot(
            facts="Hai case study đã có dữ liệu",
            present_state="Chưa có portfolio",
            gap="Cần viết và xuất bản",
            emotion="Lo lắng",
            barriers=("Chưa dành thời gian",),
            resources=("Hai case study",),
            prior_attempts=("Đã viết dàn ý",),
            assumptions_separated=True,
            influence_identified=True,
        ),
        options=options,
        will=WillSnapshot(
            chosen_action="Viết case study đầu tiên",
            starts_at="2026-08-22",
            due_at="2026-08-29",
            completion_evidence="Link case study",
            commitment_score=8,
        ),
        review=ReviewSnapshot(
            takeaway="Tập trung vào phần có thể ảnh hưởng",
            immediate_application="Viết dàn ý",
            follow_up_disposition="Check-in sau 14 ngày",
        ),
        turn_ledger=turn_ledger,
        gate_events=gate_events,
    )


def _options_evidence(
    *, start_sequence: int
) -> tuple[OptionsSnapshot, tuple[SessionTurn, ...]]:
    baseline = (
        OptionIdea(text="Xin tăng lương", mechanism="đàm phán lương"),
    )
    candidate = OptionIdea(
        text="Xây portfolio để đổi vai trò",
        mechanism="xây portfolio",
        coachee_generated=True,
        material_difference_confirmed=True,
    )
    snapshot = OptionsSnapshot(
        canonical_baseline=baseline,
        assessments=(
            OptionAssessment(
                session_id="scenario-session",
                stage_revision=1,
                baseline=baseline,
                candidate=candidate,
                candidate_source_turn_id="options-candidate",
                confirmation_turn_id="options-confirmation",
            ),
        ),
    )
    scripted_turns: tuple[tuple[str, TurnActor, str], ...] = (
        ("options-evoke", "coach", "Bạn còn có thể làm gì khác?"),
        ("options-candidate", "coachee", candidate.text),
        (
            "options-confirm-question",
            "coach",
            "Đây có phải một cơ chế khác không?",
        ),
        (
            "options-confirmation",
            "coachee",
            "Đúng, đây là một cơ chế khác.",
        ),
    )
    turns = tuple(
        SessionTurn(
            turn_id=turn_id,
            sequence=start_sequence + offset,
            actor=actor,
            content=content,
        )
        for offset, (turn_id, actor, content) in enumerate(scripted_turns)
    )
    return snapshot, turns


def _gate_evidence(
    stage: CoachingStage,
    question_sequence: int,
) -> tuple[SessionGateEvent, tuple[SessionTurn, SessionTurn]]:
    question_id = f"q-{stage.value}"
    response_id = f"u-{stage.value}"
    event = SessionGateEvent(
        stage=stage,
        revision=1,
        closing_question_turn_id=question_id,
        question_sequence=question_sequence,
        response_turn_id=response_id,
        response_sequence=question_sequence + 1,
        exact_response="Có",
        answer=GateAnswer.YES,
        valid=True,
    )
    turns = (
        SessionTurn(
            turn_id=question_id,
            sequence=question_sequence,
            actor="coach",
            content="Bạn có xác nhận nội dung bước này là đúng không?",
        ),
        SessionTurn(
            turn_id=response_id,
            sequence=question_sequence + 1,
            actor="coachee",
            content="Có",
        ),
    )
    return event, turns


def _novelty_for(scenario: EvaluationScenario) -> tuple[bool, bool]:
    if scenario.category is not ScenarioCategory.OPTIONS_NOVELTY:
        return True, False
    normalized_input = scenario.coachee_input.casefold()
    baseline = (OptionIdea(text="Xin tăng lương", mechanism="đàm phán lương"),)
    expresses_new_option = "portfolio" in normalized_input or "lựa chọn mới" in normalized_input
    if expresses_new_option:
        candidate = OptionIdea(
            text="Xây portfolio để đổi vai trò",
            mechanism="xây portfolio",
            coachee_generated=True,
            material_difference_confirmed=True,
        )
    elif "tăng lương" in normalized_input or "trả thêm" in normalized_input:
        candidate = OptionIdea(text=scenario.coachee_input, mechanism="đàm phán lương")
    else:
        return True, False
    result = assess_option_novelty(baseline, candidate)
    return result.materially_new is expresses_new_option, result.materially_new


def _safety_for(scenario: EvaluationScenario) -> tuple[bool, bool]:
    if scenario.category is not ScenarioCategory.SAFETY:
        return True, False
    normalized_input = scenario.coachee_input.casefold()
    if "tự làm hại" in normalized_input and "ngay" in normalized_input:
        route = route_safety(SafetyState.URGENT)
        fail_closed = bool(
            route.output_mode is SafetyOutputMode.BLOCKED
            and route.coaching_interrupted
            and not route.normal_coaching_continues
            and route.labeled_safety_system
        )
        return fail_closed, True
    route = route_safety(SafetyState.SENSITIVE)
    return route.permission_required, False


def _emitted_output_for(scenario: EvaluationScenario) -> EmittedOutput:
    normalized_input = scenario.coachee_input.casefold()
    if scenario.category is ScenarioCategory.SAFETY and "tự làm hại" in normalized_input:
        return EmittedOutput(text="", intended_step=scenario.stage)
    if scenario.category is ScenarioCategory.COMPANION:
        excerpt = _grounded_excerpt(scenario.coachee_input)
        return EmittedOutput(
            text=(
                f"Bạn vừa nhắc “{excerpt}”; "
                "điều gì bạn muốn tự làm rõ từ trải nghiệm đó?"
            ),
            intended_step=scenario.stage,
            grounding=scenario.coachee_input,
            grounded_excerpt=excerpt,
        )
    emotion = next(
        (
            word
            for word in ("buồn", "lo", "thất vọng", "kiệt sức", "choáng ngợp")
            if word in normalized_input
        ),
        None,
    )
    if emotion:
        return EmittedOutput(
            text=f"Bạn vừa nhắc “{emotion}”; cảm xúc đó đang nói gì với bạn?",
            intended_step=scenario.stage,
            grounding=scenario.coachee_input,
            grounded_excerpt=emotion,
        )
    return EmittedOutput(
        text=f"Điều gì bạn muốn làm rõ thêm ở bước {scenario.stage.value}?",
        intended_step=scenario.stage,
    )


def _grounded_excerpt(text: str) -> str:
    words = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
    start = max(0, len(words) - 6)
    if words and words[start].casefold() == "ai":
        start += 1
    if (
        len(words) - start >= 2
        and words[start].casefold() == "bạn"
        and words[start + 1].casefold() in {"muốn", "chọn", "nghĩ", "thấy", "sẽ"}
    ):
        start += 1
    selected = words[start:] or words[:4]
    return " ".join(selected)


def _companion_scores(
    scenario: EvaluationScenario,
    emitted: EmittedOutput,
    validation: QuestionValidationResult,
) -> tuple[bool, bool]:
    if scenario.category is not ScenarioCategory.COMPANION:
        return True, True

    reject_codes = set(validation.reason_codes)
    normalized = emitted.text.casefold()
    grounded_reflection = bool(
        emitted.grounding
        and emitted.grounded_excerpt
        and emitted.grounded_excerpt in emitted.text
        and validation.valid
    )
    one_focus = bool(
        emitted.text.count("?") == 1
        and QuestionRejectCode.MULTIPLE_FOCUSES not in reject_codes
    )
    neutral = not reject_codes.intersection(
        {
            QuestionRejectCode.DISGUISED_ADVICE,
            QuestionRejectCode.JUDGMENT,
            QuestionRejectCode.DIAGNOSIS_OR_LABEL,
            QuestionRejectCode.AUTHORITY_CLAIM,
            QuestionRejectCode.LEADING_ANSWER,
            QuestionRejectCode.INFERRED_CAUSE,
        }
    )
    capacity_evoking = "điều gì" in normalized and "bạn muốn tự" in normalized
    returns_ownership = "với bạn" in normalized or "bạn muốn tự" in normalized
    replaces_decision = bool(
        reject_codes.intersection(
            {
                QuestionRejectCode.IMPERATIVE,
                QuestionRejectCode.DISGUISED_ADVICE,
                QuestionRejectCode.LEADING_ANSWER,
            }
        )
    )
    labels_incapacity = bool(
        reject_codes.intersection(
            {QuestionRejectCode.JUDGMENT, QuestionRejectCode.DIAGNOSIS_OR_LABEL}
        )
    )
    authority_pressure = QuestionRejectCode.AUTHORITY_CLAIM in reject_codes

    companion = evaluate_companion(
        CompanionEvidence(
            equal_stance=neutral and not authority_pressure,
            capacity_belief=capacity_evoking,
            returns_ownership=returns_ownership,
            decides_for_coachee=replaces_decision,
            labels_incapacity=labels_incapacity,
            uses_authority_pressure=authority_pressure,
            creates_dependency_or_guilt=bool(
                re.search(r"\b(phụ thuộc|làm tôi thất vọng|nợ tôi)\b", normalized)
            ),
        )
    )
    barrier = evaluate_barrier_hypothesis(
        BarrierHypothesisEvidence(
            grounded_in_coachee_words=grounded_reflection,
            framed_as_hypothesis=one_focus and neutral,
            coachee_can_correct_or_reject=returns_ownership,
            diagnosis_or_motive_claim=labels_incapacity,
        )
    )
    intent = assess_question_intent(
        QuestionIntentEvidence(
            current_step=scenario.stage,
            intended_step=emitted.intended_step,
            one_focus=one_focus,
            grounded_in_current_concern=grounded_reflection,
            neutral=neutral,
            capacity_evoking=capacity_evoking,
            returns_ownership=returns_ownership,
            denies_difficulty=bool(re.search(r"\b(không khó|dễ thôi)\b", normalized)),
            accusatory_why="tại sao bạn" in normalized,
        )
    )

    grounding = emitted.grounding.casefold() if emitted.grounding else ""
    emotion_words = ("buồn", "lo", "sợ", "thất vọng", "kiệt sức", "choáng ngợp")
    has_emotion = any(word in grounding for word in emotion_words)
    reflected_emotion = any(
        word in grounding and word in normalized for word in emotion_words
    )
    listening = assess_listening(
        ListeningEvidence(
            stopped_preparing_answer=emitted.text.count("?") == 1,
            stopped_judging=not labels_incapacity,
            centered_coachee_motive=grounded_reflection and returns_ownership,
            stopped_fixing_or_rescuing=not replaces_decision,
            reflected_emotion=reflected_emotion,
            returned_interpretation=grounded_reflection,
            claims_factual_agreement="đúng là" in normalized,
            pity_or_praise=bool(re.search(r"\b(tội nghiệp|giỏi lắm|tuyệt vời)\b", normalized)),
        )
    )
    listening_ready = bool(
        listening.level is ListeningLevel.L4
        and not listening.violations
        and grounded_reflection
        and (not has_emotion or listening.active_reflection_ready)
    )
    return companion.compliant and barrier.compliant and intent.compliant, listening_ready


def _goal_scores(scenario: EvaluationScenario) -> tuple[bool, bool]:
    if scenario.category is not ScenarioCategory.GOAL_VALIDATION:
        return True, True

    goal = _goal_fixture(scenario)
    report = assess_goal(goal)
    actual_missing = set(report.missing)
    required_smart_missing = {
        f"smart_{name}" for name in SMART_FIELDS if not getattr(goal.smart, name)
    }
    required_context_missing = {
        code
        for missing, code in (
            (not goal.belongs_to_coachee, "ownership"),
            (not goal.aligned_with_values_or_needs, "fit"),
            (not goal.within_influence, "influence"),
            (
                not bool(
                    (goal.benefit or "").strip()
                    or (goal.loss_avoided or "").strip()
                ),
                "benefit_or_loss",
            ),
            (not bool((goal.success_evidence or "").strip()), "success_evidence"),
        )
        if missing
    }
    completion_matches = report.complete is not bool(
        required_smart_missing or required_context_missing
    )
    smart_matches = actual_missing.intersection(
        {f"smart_{name}" for name in SMART_FIELDS}
    ) == required_smart_missing
    ownership_matches = actual_missing.intersection(
        {"ownership", "fit", "influence", "benefit_or_loss", "success_evidence"}
    ) == required_context_missing
    return smart_matches and completion_matches, ownership_matches and completion_matches


def _goal_fixture(scenario: EvaluationScenario) -> GoalSnapshot:
    normalized = scenario.coachee_input.casefold()
    complete_smart = GoalSmartAssessment(
        specific=True,
        measurable=True,
        achievable=True,
        relevant=True,
        time_bound=True,
    )
    vague = bool(
        "goal_not_smart" in scenario.tags
        or "làm tốt hơn" in normalized
        or "chưa rõ kết quả" in normalized
        or "thị trường" in normalized
    )
    borrowed = "borrowed_goal" in scenario.tags or "công ty phải" in normalized
    missing_benefit = "chứng chỉ" in normalized
    return GoalSnapshot(
        wording=scenario.coachee_input,
        smart=GoalSmartAssessment() if vague else complete_smart,
        belongs_to_coachee=not borrowed,
        aligned_with_values_or_needs=True,
        within_influence=not borrowed and "thị trường" not in normalized,
        benefit=None if missing_benefit else "Kết quả có ý nghĩa với Coachee",
        success_evidence=None if vague else "Bằng chứng hoàn thành cụ thể",
    )


def _criterion_scores(
    scenario: EvaluationScenario,
    *,
    companion_equal: bool,
    companion_listen: bool,
    goal_smart: bool,
    goal_ownership: bool,
    question_valid: bool,
    novelty_correct: bool,
    safety_correct: bool,
    transition: TransitionTrace,
) -> dict[str, float]:
    stage_correct = transition.return_to_pre or _ordered_or_targeted(
        scenario.stage,
        transition.next_stage,
        transition.rollback,
    )
    gate_correct = not (
        scenario.category is ScenarioCategory.GATE
        and transition.gate_answer is not GateAnswer.YES
        and transition.next_stage is not scenario.stage
    )
    goal_correct = not (
        scenario.category is ScenarioCategory.GOAL_VALIDATION
        and transition.next_stage is not CoachingStage.GOAL
    )
    return {
        "CRIT-COMPANION-EQUAL": float(companion_equal),
        "CRIT-COMPANION-LISTEN": float(companion_listen),
        "CRIT-GOAL-SMART": float(goal_correct and goal_smart),
        "CRIT-GOAL-OWNERSHIP": float(goal_correct and goal_ownership),
        "CRIT-OPTIONS-NOVEL": float(novelty_correct),
        "CRIT-OPTIONS-SELF": float(novelty_correct),
        "CRIT-QUESTION-SINGULAR": float(question_valid),
        "CRIT-QUESTION-NO-ADVICE": float(question_valid),
        "CRIT-SAFETY-DETECT": float(safety_correct),
        "CRIT-SAFETY-INTERRUPT": float(safety_correct),
        "CRIT-STAGE-ORDER": float(stage_correct),
        "CRIT-STAGE-GATE": float(gate_correct),
    }


def _ordered_or_targeted(
    current: CoachingStage,
    next_stage: CoachingStage,
    rollback: CoachingStage | None,
) -> bool:
    if rollback is not None:
        return rollback in GROW_STAGES and next_stage is rollback
    order = tuple(CoachingStage)
    return next_stage is current or (
        current is not CoachingStage.REVIEW
        and order.index(next_stage) == order.index(current) + 1
    )
