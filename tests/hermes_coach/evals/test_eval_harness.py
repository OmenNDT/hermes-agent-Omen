from __future__ import annotations

from pathlib import Path

import yaml

from hermes_coach.contracts.evaluation_contract import ScenarioCaseType, ScenarioCategory
from hermes_coach.contracts.evaluation_result import ScenarioObservation
from hermes_coach.contracts.runtime_contract import CoachingStage
from tests.hermes_coach.evals.runner import (
    audit_corpus,
    load_external_gates,
    load_rubrics,
    load_scenarios,
    render_report,
    run_evaluation,
)
from tests.hermes_coach.evals.scoring import (
    STRUCTURAL_ONLY_CATEGORIES,
    mandatory_rubric_ids,
    score_scenario,
)


ROOT = Path(__file__).parents[3]
EVAL_ROOT = ROOT / "tests" / "hermes_coach" / "evals"
REQUIREMENTS_MAP = ROOT / "hermes_coach" / "requirements_map.yaml"


def _requirements_map() -> dict:
    return yaml.safe_load(REQUIREMENTS_MAP.read_text(encoding="utf-8"))


def test_versioned_corpus_has_required_size_and_unique_ids() -> None:
    scenarios = load_scenarios(EVAL_ROOT / "scenarios")

    assert 50 <= len(scenarios) <= 100
    assert len({scenario.id for scenario in scenarios}) == len(scenarios)
    assert all(scenario.version >= 1 for scenario in scenarios)


def test_corpus_covers_every_stage_and_acceptance_criterion() -> None:
    scenarios = load_scenarios(EVAL_ROOT / "scenarios")
    requirements = _requirements_map()

    assert {scenario.stage for scenario in scenarios} == set(CoachingStage)
    covered_acceptance = {
        acceptance_id for scenario in scenarios for acceptance_id in scenario.acceptance_ids
    }
    assert covered_acceptance == set(requirements["acceptance_criteria"])


def test_corpus_covers_required_behavior_families() -> None:
    scenarios = load_scenarios(EVAL_ROOT / "scenarios")
    categories = {scenario.category for scenario in scenarios}

    assert {
        "companion",
        "gate",
        "goal_validation",
        "options_novelty",
        "privacy",
        "question_only",
        "rollback",
        "safety",
    } <= categories
    assert {scenario.case_type for scenario in scenarios} == set(ScenarioCaseType)


def test_corpus_covers_every_proposal_evaluation_category() -> None:
    scenarios = load_scenarios(EVAL_ROOT / "scenarios")
    tags = {tag for scenario in scenarios for tag in scenario.tags}

    assert {
        "advice_request",
        "borrowed_goal",
        "career_change",
        "contradiction",
        "crisis",
        "disguised_advice",
        "goal_not_smart",
        "goal_unclear",
        "no_commitment",
        "repeated_delay",
        "sensitive_question",
    } <= tags


def test_rubrics_are_versioned_and_include_all_blocking_policies() -> None:
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")

    assert {
        "RUB-COMPANION",
        "RUB-GOAL",
        "RUB-OPTIONS",
        "RUB-PRIVACY",
        "RUB-QUESTION",
        "RUB-SAFETY",
        "RUB-STAGE",
    } <= {rubric.id for rubric in rubrics}
    assert all(rubric.version >= 1 for rubric in rubrics)
    assert all(any(criterion.blocking for criterion in rubric.criteria) for rubric in rubrics)


def test_phase2_rubric_contract_is_central_total_and_explicitly_structural() -> None:
    scenarios = load_scenarios(EVAL_ROOT / "scenarios")
    by_category = {scenario.category: scenario for scenario in scenarios}

    assert set(by_category) == set(ScenarioCategory)
    assert STRUCTURAL_ONLY_CATEGORIES == {
        ScenarioCategory.PRIVACY,
        ScenarioCategory.MEMORY,
        ScenarioCategory.CHECK_IN,
    }
    assert all(
        mandatory_rubric_ids(by_category[category])
        for category in ScenarioCategory
        if category not in STRUCTURAL_ONLY_CATEGORIES
    )
    assert all(
        mandatory_rubric_ids(by_category[category]) == ()
        for category in STRUCTURAL_ONLY_CATEGORIES
    )
    companion = by_category[ScenarioCategory.COMPANION]
    assert set(mandatory_rubric_ids(companion)) == {
        "RUB-COMPANION",
        "RUB-QUESTION",
    }
    tagged_pre_coaching = by_category[ScenarioCategory.PRE_COACHING].model_copy(
        update={"tags": ("companion",)}
    )
    assert set(mandatory_rubric_ids(tagged_pre_coaching)) == {
        "RUB-COMPANION",
        "RUB-QUESTION",
        "RUB-STAGE",
    }


def test_scorer_rejects_missing_mandatory_rubrics() -> None:
    scenario = next(
        item
        for item in load_scenarios(EVAL_ROOT / "scenarios")
        if item.category is ScenarioCategory.COMPANION
    )
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    observation = _PassingEvaluator().evaluate(scenario, rubrics)

    without_companion = tuple(
        rubric for rubric in rubrics if rubric.id != "RUB-COMPANION"
    )
    incomplete = score_scenario(scenario, without_companion, observation)
    empty = score_scenario(scenario, (), observation)

    assert not incomplete.passed
    assert "missing_required_rubric:RUB-COMPANION" in incomplete.structural_failures
    assert not empty.passed
    assert {
        "missing_required_rubric:RUB-COMPANION",
        "missing_required_rubric:RUB-QUESTION",
    } <= set(empty.structural_failures)


def test_observation_contract_has_no_evaluator_selected_rubrics() -> None:
    assert "applicable_rubric_ids" not in ScenarioObservation.model_fields


def test_static_corpus_audit_resolves_all_requirement_references() -> None:
    report = audit_corpus(
        scenario_dir=EVAL_ROOT / "scenarios",
        rubric_dir=EVAL_ROOT / "rubrics",
        requirements_map_path=REQUIREMENTS_MAP,
    )

    assert report.scenario_count >= 50
    assert report.rubric_count >= 7
    assert report.errors == ()
    requirements = _requirements_map()
    assert set(requirements["phase_1"]["scenario_sources"]) <= set(
        report.covered_source_ids
    )


def test_external_release_gates_name_owner_evidence_and_expiry_policy() -> None:
    path = EVAL_ROOT / "external-gates.yaml"
    gates = load_external_gates(path)

    assert {gate.id for gate in gates} == {
        "GATE-PROVIDER-CAPABILITY",
        "GATE-PROVIDER-RETENTION",
        "GATE-SAFETY-REVIEW",
    }
    assert all(gate.owner and gate.blocks for gate in gates)
    assert all(gate.evidence_format and gate.evidence_validity_days > 0 for gate in gates)
    assert all(gate.status.value == "pending" for gate in gates)
    assert "placeholder hotline" not in path.read_text(encoding="utf-8").lower()


class _PassingEvaluator:
    def evaluate(self, scenario, rubrics):
        criteria = {
            criterion.id: 1.0 for rubric in rubrics for criterion in rubric.criteria
        }
        return ScenarioObservation(
            scenario_id=scenario.id,
            actual_next_stage=scenario.expected.next_stage,
            question_count=1 if scenario.expected.question_only else 0,
            closing_question_observed=scenario.expected.closing_question,
            gate_answer=scenario.expected.gate_answer,
            rollback_to=scenario.expected.rollback_to,
            return_to_pre_coaching=scenario.expected.return_to_pre_coaching,
            novel_option_observed=scenario.expected.novel_option_required,
            safety_exception=scenario.expected.safety_exception,
            met_behaviors=scenario.expected.must_do,
            criterion_scores=criteria,
        )


def test_scenarios_execute_score_and_render_reproducibly() -> None:
    scenarios = load_scenarios(EVAL_ROOT / "scenarios")
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")

    first = run_evaluation(scenarios, rubrics, _PassingEvaluator())
    second = run_evaluation(scenarios, rubrics, _PassingEvaluator())

    assert first.scenario_count == len(scenarios)
    assert first.passed_count == len(scenarios)
    assert first.failed_count == 0
    assert render_report(first) == render_report(second)


def test_blocking_rubric_failure_fails_the_scenario() -> None:
    scenario = load_scenarios(EVAL_ROOT / "scenarios")[0]
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    observation = _PassingEvaluator().evaluate(scenario, rubrics)
    required_rubrics = set(mandatory_rubric_ids(scenario))
    blocking_id = next(
        criterion.id
        for rubric in rubrics
        if rubric.id in required_rubrics
        for criterion in rubric.criteria
        if criterion.blocking
    )
    scores = dict(observation.criterion_scores)
    scores[blocking_id] = 0.0
    failed = observation.model_copy(update={"criterion_scores": scores})

    report = run_evaluation((scenario,), rubrics, lambda_evaluator(failed))

    assert report.failed_count == 1
    assert any(score.blocking_failures for score in report.results[0].rubric_scores)


def test_free_text_behavior_mode_enforces_must_do_and_must_not_do() -> None:
    scenario = next(
        item
        for item in load_scenarios(EVAL_ROOT / "scenarios")
        if item.expected.must_do and item.expected.must_not_do
    )
    rubrics = load_rubrics(EVAL_ROOT / "rubrics")
    passing = _PassingEvaluator().evaluate(scenario, rubrics)

    missing_required = score_scenario(
        scenario,
        rubrics,
        passing.model_copy(update={"met_behaviors": ()}),
    )
    emitted_prohibited = score_scenario(
        scenario,
        rubrics,
        passing.model_copy(
            update={"prohibited_behaviors": (scenario.expected.must_not_do[0],)}
        ),
    )

    assert not missing_required.passed
    assert "must_do" in missing_required.structural_failures
    assert not emitted_prohibited.passed
    assert "must_not_do" in emitted_prohibited.structural_failures


def lambda_evaluator(observation):
    class _Evaluator:
        def evaluate(self, _scenario, _rubrics):
            return observation

    return _Evaluator()
