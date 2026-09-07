from __future__ import annotations

from hermes_coach.domain.models import ImmutableModel


class CompanionEvidence(ImmutableModel):
    equal_stance: bool
    capacity_belief: bool
    returns_ownership: bool
    decides_for_coachee: bool = False
    labels_incapacity: bool = False
    uses_authority_pressure: bool = False
    creates_dependency_or_guilt: bool = False


class BarrierHypothesisEvidence(ImmutableModel):
    grounded_in_coachee_words: bool
    framed_as_hypothesis: bool
    coachee_can_correct_or_reject: bool
    diagnosis_or_motive_claim: bool = False


class InfluenceEvidence(ImmutableModel):
    distinguishes_concern_and_influence: bool
    acknowledges_external_context: bool
    avoids_blame: bool
    returns_action_ownership: bool


class PolicyReport(ImmutableModel):
    compliant: bool
    violations: tuple[str, ...] = ()


def evaluate_companion(evidence: CompanionEvidence) -> PolicyReport:
    checks = (
        (not evidence.equal_stance, "unequal_stance"),
        (not evidence.capacity_belief, "missing_capacity_belief"),
        (not evidence.returns_ownership, "ownership_not_returned"),
        (evidence.decides_for_coachee, "decision_replacement"),
        (evidence.labels_incapacity, "incapacity_label"),
        (evidence.uses_authority_pressure, "authority_pressure"),
        (evidence.creates_dependency_or_guilt, "dependency_or_guilt"),
    )
    violations = tuple(code for failed, code in checks if failed)
    return PolicyReport(compliant=not violations, violations=violations)


def evaluate_barrier_hypothesis(evidence: BarrierHypothesisEvidence) -> PolicyReport:
    checks = (
        (not evidence.grounded_in_coachee_words, "not_grounded"),
        (not evidence.framed_as_hypothesis, "presented_as_conclusion"),
        (not evidence.coachee_can_correct_or_reject, "no_correction_right"),
        (evidence.diagnosis_or_motive_claim, "diagnosis_or_motive_claim"),
    )
    violations = tuple(code for failed, code in checks if failed)
    return PolicyReport(compliant=not violations, violations=violations)


def evaluate_influence(evidence: InfluenceEvidence) -> PolicyReport:
    checks = (
        (
            not evidence.distinguishes_concern_and_influence,
            "concern_influence_not_distinguished",
        ),
        (not evidence.acknowledges_external_context, "external_context_denied"),
        (not evidence.avoids_blame, "blame"),
        (not evidence.returns_action_ownership, "action_ownership_not_returned"),
    )
    violations = tuple(code for failed, code in checks if failed)
    return PolicyReport(compliant=not violations, violations=violations)
