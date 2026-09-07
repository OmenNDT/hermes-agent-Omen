from __future__ import annotations

from pathlib import Path

import pytest

from hermes_coach.contracts.evaluation_contract import ScenarioCategory
from hermes_coach.contracts.runtime_contract import CoachingStage, GateAnswer
from hermes_coach.domain.enums import NoveltyStatus
from hermes_coach.domain.goal_rules import GoalAssessmentReport
from hermes_coach.domain.options_rules import NoveltyAssessment
from hermes_coach.policies.companion_policy import PolicyReport
from hermes_coach.policies.listening_policy import ListeningAssessment, ListeningLevel
from tests.hermes_coach.evals.pure_engine import PureEngineEvaluator
from tests.hermes_coach.evals.runner import load_rubrics, load_scenarios, run_evaluation
from tests.hermes_coach.evals.scoring import score_scenario


EVAL_ROOT = Path(__file__).parent


def test_all_scenarios_execute_structural_phase2_harness_without_oracle() -> None:
    scenarios = load_scenarios(EVAL_ROOT / "scenarios")
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")

    report = run_evaluation(
        scenarios,
        rubrics,
        PureEngineEvaluator(),
        require_free_text_behaviors=False,
    )

    assert report.scenario_count == len(scenarios)
    assert report.failed_count == 0
    assert report.passed_count == len(scenarios)


def test_evaluator_does_not_echo_expected_transition() -> None:
    scenario = next(
        item for item in load_scenarios(EVAL_ROOT / "scenarios") if item.id == "SCN-020"
    )
    changed_oracle = scenario.model_copy(
        update={
            "expected": scenario.expected.model_copy(
                update={"next_stage": CoachingStage.REALITY}
            )
        }
    )
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    observation = PureEngineEvaluator().evaluate(changed_oracle, rubrics)

    assert observation.actual_next_stage is CoachingStage.GOAL
    assert not score_scenario(
        changed_oracle,
        rubrics,
        observation,
        require_free_text_behaviors=False,
    ).passed


def test_evaluator_observation_is_independent_of_every_expected_field() -> None:
    scenarios = load_scenarios(EVAL_ROOT / "scenarios")
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    evaluator = PureEngineEvaluator()

    for scenario in scenarios:
        changed = scenario.model_copy(
            update={
                "expected": scenario.expected.model_copy(
                    update={
                        "next_stage": CoachingStage.REVIEW,
                        "question_only": not scenario.expected.question_only,
                        "closing_question": not scenario.expected.closing_question,
                        "gate_answer": GateAnswer.NO,
                        "rollback_to": CoachingStage.GOAL,
                        "return_to_pre_coaching": not scenario.expected.return_to_pre_coaching,
                        "novel_option_required": not scenario.expected.novel_option_required,
                        "safety_exception": not scenario.expected.safety_exception,
                        "must_do": ("mutated oracle",),
                        "must_not_do": ("mutated prohibition",),
                    }
                )
            }
        )

        assert evaluator.evaluate(changed, rubrics) == evaluator.evaluate(scenario, rubrics)


def test_every_structural_expectation_independently_changes_the_verdict() -> None:
    scenarios = {
        item.id: item for item in load_scenarios(EVAL_ROOT / "scenarios")
    }
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    evaluator = PureEngineEvaluator()
    mutations = (
        ("SCN-020", {"actual_next_stage": CoachingStage.REVIEW}),
        ("SCN-020", {"question_count": 0}),
        ("SCN-004", {"closing_question_observed": False}),
        ("SCN-006", {"gate_answer": GateAnswer.NO}),
        ("SCN-010", {"rollback_to": None}),
        ("SCN-025", {"return_to_pre_coaching": False}),
        ("SCN-012", {"novel_option_observed": False}),
        ("SCN-057", {"safety_exception": False}),
    )

    for scenario_id, update in mutations:
        scenario = scenarios[scenario_id]
        observation = evaluator.evaluate(scenario, rubrics)
        baseline = score_scenario(
            scenario,
            rubrics,
            observation,
            require_free_text_behaviors=False,
        )
        mutated = score_scenario(
            scenario,
            rubrics,
            observation.model_copy(update=update),
            require_free_text_behaviors=False,
        )

        assert baseline.passed, scenario_id
        assert not mutated.passed, (scenario_id, update)


def test_broken_gate_classifier_makes_the_corpus_fail(monkeypatch) -> None:
    scenarios = load_scenarios(EVAL_ROOT / "scenarios")
    scenario = next(
        item
        for item in scenarios
        if item.stage is CoachingStage.PRE_COACHING
        and item.coachee_input.casefold().startswith("yes")
    )
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    monkeypatch.setattr(
        "hermes_coach.domain.transitions.classify_gate_answer",
        lambda _response: GateAnswer.UNCLEAR,
    )

    observation = PureEngineEvaluator().evaluate(scenario, rubrics)

    assert not score_scenario(
        scenario,
        rubrics,
        observation,
        require_free_text_behaviors=False,
    ).passed


def test_broken_novelty_assessor_makes_the_corpus_fail(monkeypatch) -> None:
    scenario = next(
        item
        for item in load_scenarios(EVAL_ROOT / "scenarios")
        if "portfolio" in item.coachee_input.casefold()
    )
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    monkeypatch.setattr(
        "tests.hermes_coach.evals.pure_engine.assess_option_novelty",
        lambda _baseline, _candidate: NoveltyAssessment(
            status=NoveltyStatus.SAME_MECHANISM,
            materially_new=False,
        ),
    )

    observation = PureEngineEvaluator().evaluate(scenario, rubrics)

    assert not score_scenario(
        scenario,
        rubrics,
        observation,
        require_free_text_behaviors=False,
    ).passed


def test_companion_scenarios_score_companion_and_question_policies() -> None:
    scenario = next(
        item
        for item in load_scenarios(EVAL_ROOT / "scenarios")
        if item.category is ScenarioCategory.COMPANION
    )
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    observation = PureEngineEvaluator().evaluate(scenario, rubrics)
    result = score_scenario(
        scenario,
        rubrics,
        observation,
        require_free_text_behaviors=False,
    )

    assert result.passed
    assert {score.rubric_id for score in result.rubric_scores} == {
        "RUB-COMPANION",
        "RUB-QUESTION",
    }
    assert observation.criterion_scores["CRIT-COMPANION-EQUAL"] == 1.0
    assert observation.criterion_scores["CRIT-COMPANION-LISTEN"] == 1.0


@pytest.mark.parametrize(
    ("policy_name", "broken_result"),
    [
        (
            "evaluate_companion",
            PolicyReport(compliant=False, violations=("mutation",)),
        ),
        (
            "evaluate_barrier_hypothesis",
            PolicyReport(compliant=False, violations=("mutation",)),
        ),
        (
            "assess_question_intent",
            PolicyReport(compliant=False, violations=("mutation",)),
        ),
        (
            "assess_listening",
            ListeningAssessment(
                level=ListeningLevel.BELOW_L1,
                active_reflection_ready=False,
                violations=("mutation",),
            ),
        ),
    ],
)
def test_broken_companion_policy_makes_a_companion_scenario_fail(
    monkeypatch,
    policy_name: str,
    broken_result: object,
) -> None:
    scenario = next(
        item
        for item in load_scenarios(EVAL_ROOT / "scenarios")
        if item.category is ScenarioCategory.COMPANION
    )
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    monkeypatch.setattr(
        f"tests.hermes_coach.evals.pure_engine.{policy_name}",
        lambda _evidence: broken_result,
    )

    observation = PureEngineEvaluator().evaluate(scenario, rubrics)

    assert not score_scenario(
        scenario,
        rubrics,
        observation,
        require_free_text_behaviors=False,
    ).passed


def test_companion_evidence_is_derived_from_emitted_output_grounding(monkeypatch) -> None:
    scenario = next(
        item
        for item in load_scenarios(EVAL_ROOT / "scenarios")
        if item.category is ScenarioCategory.COMPANION
    )
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    monkeypatch.setattr(
        "tests.hermes_coach.evals.pure_engine._grounded_excerpt",
        lambda _text: "evidence absent from coachee input",
    )

    observation = PureEngineEvaluator().evaluate(scenario, rubrics)

    assert observation.criterion_scores["CRIT-COMPANION-LISTEN"] == 0.0
    assert not score_scenario(
        scenario,
        rubrics,
        observation,
        require_free_text_behaviors=False,
    ).passed


def test_broken_goal_assessor_makes_a_goal_scenario_fail(monkeypatch) -> None:
    scenario = next(
        item
        for item in load_scenarios(EVAL_ROOT / "scenarios")
        if "goal_not_smart" in item.tags
    )
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    monkeypatch.setattr(
        "tests.hermes_coach.evals.pure_engine.assess_goal",
        lambda _goal: GoalAssessmentReport(complete=True, missing=()),
    )

    observation = PureEngineEvaluator().evaluate(scenario, rubrics)

    assert not score_scenario(
        scenario,
        rubrics,
        observation,
        require_free_text_behaviors=False,
    ).passed


def test_options_gate_uses_current_aggregate_completion_api(monkeypatch) -> None:
    scenario = next(
        item
        for item in load_scenarios(EVAL_ROOT / "scenarios")
        if item.category is ScenarioCategory.GATE
    ).model_copy(
        update={"stage": CoachingStage.OPTIONS, "coachee_input": "Yes"}
    )
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")

    baseline = PureEngineEvaluator().evaluate(scenario, rubrics)
    completion_results = iter((True, False))
    monkeypatch.setattr(
        "hermes_coach.domain.options_rules.options_are_complete",
        lambda *_args, **_kwargs: next(completion_results),
    )
    mutated = PureEngineEvaluator().evaluate(scenario, rubrics)

    assert baseline.gate_answer is GateAnswer.YES
    assert baseline.actual_next_stage is CoachingStage.WILL
    assert mutated.gate_answer is GateAnswer.YES
    assert mutated.actual_next_stage is CoachingStage.OPTIONS
