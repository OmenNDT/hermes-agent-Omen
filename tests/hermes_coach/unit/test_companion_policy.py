from __future__ import annotations

from hermes_coach.policies.companion_policy import (
    BarrierHypothesisEvidence,
    CompanionEvidence,
    InfluenceEvidence,
    evaluate_barrier_hypothesis,
    evaluate_companion,
    evaluate_influence,
)


def test_equal_companion_requires_capacity_belief_ownership_and_no_authority() -> None:
    valid = evaluate_companion(
        CompanionEvidence(
            equal_stance=True,
            capacity_belief=True,
            returns_ownership=True,
        )
    )
    invalid = evaluate_companion(
        CompanionEvidence(
            equal_stance=False,
            capacity_belief=False,
            returns_ownership=False,
            decides_for_coachee=True,
            labels_incapacity=True,
        )
    )

    assert valid.compliant
    assert not invalid.compliant
    assert {"unequal_stance", "missing_capacity_belief", "decision_replacement"} <= set(
        invalid.violations
    )


def test_barrier_is_a_grounded_rejectable_hypothesis_not_a_diagnosis() -> None:
    report = evaluate_barrier_hypothesis(
        BarrierHypothesisEvidence(
            grounded_in_coachee_words=True,
            framed_as_hypothesis=True,
            coachee_can_correct_or_reject=True,
        )
    )

    assert report.compliant
    assert not evaluate_barrier_hypothesis(
        BarrierHypothesisEvidence(
            grounded_in_coachee_words=False,
            framed_as_hypothesis=False,
            coachee_can_correct_or_reject=False,
        )
    ).compliant


def test_concern_and_influence_are_separated_without_blame_or_context_denial() -> None:
    report = evaluate_influence(
        InfluenceEvidence(
            distinguishes_concern_and_influence=True,
            acknowledges_external_context=True,
            avoids_blame=True,
            returns_action_ownership=True,
        )
    )

    assert report.compliant
