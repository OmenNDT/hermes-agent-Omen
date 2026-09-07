from __future__ import annotations

from hermes_coach.contracts.evaluation_contract import (
    EvaluationRubric,
    EvaluationScenario,
    ScenarioCategory,
)
from hermes_coach.contracts.evaluation_result import (
    RubricScore,
    ScenarioEvaluationResult,
    ScenarioObservation,
)


STRUCTURAL_ONLY_CATEGORIES = frozenset(
    {
        ScenarioCategory.PRIVACY,
        ScenarioCategory.MEMORY,
        ScenarioCategory.CHECK_IN,
    }
)

_CATEGORY_RUBRICS: dict[ScenarioCategory, tuple[str, ...]] = {
    ScenarioCategory.PRE_COACHING: ("RUB-STAGE",),
    ScenarioCategory.COMPANION: ("RUB-COMPANION", "RUB-QUESTION"),
    ScenarioCategory.QUESTION_ONLY: ("RUB-QUESTION",),
    ScenarioCategory.GATE: ("RUB-STAGE",),
    ScenarioCategory.GOAL_VALIDATION: ("RUB-GOAL", "RUB-STAGE"),
    ScenarioCategory.REALITY: ("RUB-STAGE",),
    ScenarioCategory.OPTIONS_NOVELTY: ("RUB-OPTIONS",),
    ScenarioCategory.WILL: ("RUB-STAGE",),
    ScenarioCategory.REVIEW: ("RUB-STAGE",),
    ScenarioCategory.ROLLBACK: ("RUB-STAGE",),
    ScenarioCategory.PRIVACY: (),
    ScenarioCategory.SAFETY: ("RUB-SAFETY",),
    ScenarioCategory.MEMORY: (),
    ScenarioCategory.CHECK_IN: (),
}

_TAG_RUBRICS: dict[str, tuple[str, ...]] = {
    "companion": ("RUB-COMPANION", "RUB-QUESTION"),
    "question_only": ("RUB-QUESTION",),
    "goal_validation": ("RUB-GOAL", "RUB-STAGE"),
    "options_novelty": ("RUB-OPTIONS",),
    "gate": ("RUB-STAGE",),
    "rollback": ("RUB-STAGE",),
    "safety": ("RUB-SAFETY",),
}


def mandatory_rubric_ids(scenario: EvaluationScenario) -> tuple[str, ...]:
    """Return scorer-owned Phase-2 rubrics for a scenario."""
    if scenario.category in STRUCTURAL_ONLY_CATEGORIES:
        return ()

    required = list(_CATEGORY_RUBRICS[scenario.category])
    for tag in scenario.tags:
        required.extend(_TAG_RUBRICS.get(tag, ()))
    return tuple(dict.fromkeys(required))


def score_scenario(
    scenario: EvaluationScenario,
    rubrics: tuple[EvaluationRubric, ...],
    observation: ScenarioObservation,
    *,
    require_free_text_behaviors: bool = True,
) -> ScenarioEvaluationResult:
    structural_failures = _structural_failures(
        scenario,
        observation,
        require_free_text_behaviors=require_free_text_behaviors,
    )
    required_ids = mandatory_rubric_ids(scenario)
    rubrics_by_id = {rubric.id: rubric for rubric in rubrics}
    missing_ids = tuple(
        rubric_id for rubric_id in required_ids if rubric_id not in rubrics_by_id
    )
    structural_failures.extend(
        f"missing_required_rubric:{rubric_id}" for rubric_id in missing_ids
    )
    selected_rubrics = tuple(
        rubrics_by_id[rubric_id]
        for rubric_id in required_ids
        if rubric_id in rubrics_by_id
    )
    rubric_scores = tuple(
        _score_rubric(rubric, observation) for rubric in selected_rubrics
    )
    passed = not structural_failures and all(score.passed for score in rubric_scores)
    return ScenarioEvaluationResult(
        scenario_id=scenario.id,
        structural_failures=tuple(structural_failures),
        rubric_scores=rubric_scores,
        passed=passed,
    )


def _structural_failures(
    scenario: EvaluationScenario,
    observation: ScenarioObservation,
    *,
    require_free_text_behaviors: bool,
) -> list[str]:
    expected = scenario.expected
    failures: list[str] = []
    if observation.scenario_id != scenario.id:
        failures.append("scenario_id")
    if observation.actual_next_stage is not expected.next_stage:
        failures.append("next_stage")
    if expected.question_only and observation.question_count != 1:
        failures.append("question_count")
    if observation.closing_question_observed is not expected.closing_question:
        failures.append("closing_question")
    if observation.gate_answer is not expected.gate_answer:
        failures.append("gate_answer")
    if observation.rollback_to is not expected.rollback_to:
        failures.append("rollback_to")
    if observation.return_to_pre_coaching is not expected.return_to_pre_coaching:
        failures.append("return_to_pre_coaching")
    if expected.novel_option_required and not observation.novel_option_observed:
        failures.append("novel_option")
    if observation.safety_exception is not expected.safety_exception:
        failures.append("safety_exception")
    if require_free_text_behaviors and not set(expected.must_do) <= set(
        observation.met_behaviors
    ):
        failures.append("must_do")
    if require_free_text_behaviors and set(expected.must_not_do) & set(
        observation.prohibited_behaviors
    ):
        failures.append("must_not_do")
    return failures


def _score_rubric(
    rubric: EvaluationRubric,
    observation: ScenarioObservation,
) -> RubricScore:
    score = sum(
        criterion.weight * observation.criterion_scores.get(criterion.id, 0.0)
        for criterion in rubric.criteria
    )
    blocking = tuple(
        criterion.id
        for criterion in rubric.criteria
        if criterion.blocking and observation.criterion_scores.get(criterion.id, 0.0) < 1.0
    )
    return RubricScore(
        rubric_id=rubric.id,
        score=score,
        blocking_failures=blocking,
        passed=score >= rubric.minimum_score and not blocking,
    )
