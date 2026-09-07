from __future__ import annotations

from pathlib import Path
import json
from typing import Protocol

import yaml

from hermes_coach.contracts.evaluation_contract import (
    CorpusAuditReport,
    EvaluationRubric,
    EvaluationScenario,
    ExternalValidationGate,
)
from hermes_coach.contracts.evaluation_result import (
    EvaluationRunReport,
    ScenarioObservation,
)
from tests.hermes_coach.evals.scoring import score_scenario


class ScenarioEvaluator(Protocol):
    def evaluate(
        self,
        scenario: EvaluationScenario,
        rubrics: tuple[EvaluationRubric, ...],
    ) -> ScenarioObservation: ...


def _yaml_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.yaml") if path.is_file())


def load_scenarios(directory: Path) -> tuple[EvaluationScenario, ...]:
    scenarios: list[EvaluationScenario] = []
    for path in _yaml_files(directory):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for item in document.get("scenarios", []):
            scenarios.append(EvaluationScenario.model_validate(item))
    return tuple(scenarios)


def load_rubrics(directory: Path) -> tuple[EvaluationRubric, ...]:
    rubrics: list[EvaluationRubric] = []
    for path in _yaml_files(directory):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rubrics.append(EvaluationRubric.model_validate(document))
    return tuple(rubrics)


def load_external_gates(path: Path) -> tuple[ExternalValidationGate, ...]:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return tuple(
        ExternalValidationGate.model_validate(item) for item in document.get("gates", [])
    )


def run_evaluation(
    scenarios: tuple[EvaluationScenario, ...],
    rubrics: tuple[EvaluationRubric, ...],
    evaluator: ScenarioEvaluator,
    *,
    require_free_text_behaviors: bool = True,
) -> EvaluationRunReport:
    results = tuple(
        score_scenario(
            scenario,
            rubrics,
            evaluator.evaluate(scenario, rubrics),
            require_free_text_behaviors=require_free_text_behaviors,
        )
        for scenario in sorted(scenarios, key=lambda item: item.id)
    )
    passed = sum(result.passed for result in results)
    return EvaluationRunReport(
        version=1,
        scenario_count=len(results),
        passed_count=passed,
        failed_count=len(results) - passed,
        results=results,
    )


def render_report(report: EvaluationRunReport) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def audit_corpus(
    scenario_dir: Path,
    rubric_dir: Path,
    requirements_map_path: Path,
) -> CorpusAuditReport:
    scenarios = load_scenarios(scenario_dir)
    rubrics = load_rubrics(rubric_dir)
    requirements = yaml.safe_load(requirements_map_path.read_text(encoding="utf-8"))
    source_catalog = set(requirements["sources"])
    acceptance_catalog = set(requirements["acceptance_criteria"])
    covered_sources = {item for scenario in scenarios for item in scenario.source_ids}
    covered_acceptance = {
        item for scenario in scenarios for item in scenario.acceptance_ids
    }
    scenario_ids = [scenario.id for scenario in scenarios]
    rubric_ids = [rubric.id for rubric in rubrics]
    errors: list[str] = []

    if not 50 <= len(scenarios) <= 100:
        errors.append("scenario count must be between 50 and 100")
    if len(set(scenario_ids)) != len(scenario_ids):
        errors.append("scenario IDs must be unique")
    if len(set(rubric_ids)) != len(rubric_ids):
        errors.append("rubric IDs must be unique")
    unknown_sources = covered_sources - source_catalog
    unknown_acceptance = covered_acceptance - acceptance_catalog
    if unknown_sources:
        errors.append(f"unknown source IDs: {sorted(unknown_sources)}")
    if unknown_acceptance:
        errors.append(f"unknown acceptance IDs: {sorted(unknown_acceptance)}")
    if covered_acceptance != acceptance_catalog:
        missing = sorted(acceptance_catalog - covered_acceptance)
        errors.append(f"acceptance IDs without scenario coverage: {missing}")
    required_scenario_sources = set(requirements["phase_1"]["scenario_sources"])
    if not required_scenario_sources <= covered_sources:
        missing = sorted(required_scenario_sources - covered_sources)
        errors.append(f"Phase 1 source IDs without scenario coverage: {missing}")

    return CorpusAuditReport(
        scenario_count=len(scenarios),
        rubric_count=len(rubrics),
        covered_source_ids=tuple(sorted(covered_sources)),
        covered_acceptance_ids=tuple(sorted(covered_acceptance)),
        errors=tuple(errors),
    )
