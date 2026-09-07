from __future__ import annotations

from hermes_coach.domain.models import ImmutableModel
from hermes_coach.policies.companion_policy import PolicyReport


class AcknowledgmentEvidence(ImmutableModel):
    appreciates_sharing: bool
    names_observed_behavior: bool
    asks_coachee_for_value_or_resource: bool
    allows_correction: bool
    flatters_or_judges: bool = False


class FeedbackEvidence(ImmutableModel):
    factual_observation: bool
    grounded_reflection: bool
    exploration_question: bool
    returns_interpretation: bool
    contains_advice: bool = False
    labels_or_diagnoses: bool = False
    demands_change: bool = False


def assess_acknowledgment(evidence: AcknowledgmentEvidence) -> PolicyReport:
    checks = (
        (not evidence.appreciates_sharing, "missing_appreciation"),
        (not evidence.names_observed_behavior, "missing_observed_behavior"),
        (
            not evidence.asks_coachee_for_value_or_resource,
            "missing_value_or_resource_question",
        ),
        (not evidence.allows_correction, "no_correction_right"),
        (evidence.flatters_or_judges, "flattery_or_judgment"),
    )
    violations = tuple(code for failed, code in checks if failed)
    return PolicyReport(compliant=not violations, violations=violations)


def assess_feedback(evidence: FeedbackEvidence) -> PolicyReport:
    checks = (
        (not evidence.factual_observation, "missing_factual_observation"),
        (not evidence.grounded_reflection, "missing_grounded_reflection"),
        (not evidence.exploration_question, "missing_exploration"),
        (not evidence.returns_interpretation, "interpretation_not_returned"),
        (evidence.contains_advice, "advice"),
        (evidence.labels_or_diagnoses, "label_or_diagnosis"),
        (evidence.demands_change, "demand"),
    )
    violations = tuple(code for failed, code in checks if failed)
    return PolicyReport(compliant=not violations, violations=violations)

