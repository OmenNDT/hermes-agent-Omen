from __future__ import annotations

from hermes_coach.policies.feedback_policy import (
    AcknowledgmentEvidence,
    FeedbackEvidence,
    assess_acknowledgment,
    assess_feedback,
)


def test_acknowledgment_is_appreciation_observed_behavior_then_value_question() -> None:
    report = assess_acknowledgment(
        AcknowledgmentEvidence(
            appreciates_sharing=True,
            names_observed_behavior=True,
            asks_coachee_for_value_or_resource=True,
            allows_correction=True,
        )
    )

    assert report.compliant


def test_feedback_requires_observation_reflection_exploration_without_advice() -> None:
    valid = assess_feedback(
        FeedbackEvidence(
            factual_observation=True,
            grounded_reflection=True,
            exploration_question=True,
            returns_interpretation=True,
        )
    )
    advice = assess_feedback(
        FeedbackEvidence(
            factual_observation=True,
            grounded_reflection=True,
            exploration_question=True,
            returns_interpretation=False,
            contains_advice=True,
        )
    )

    assert valid.compliant
    assert not advice.compliant
    assert "advice" in advice.violations

