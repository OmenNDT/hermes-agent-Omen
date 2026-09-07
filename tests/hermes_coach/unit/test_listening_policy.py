from __future__ import annotations

from hermes_coach.policies.listening_policy import ListeningEvidence, ListeningLevel, assess_listening


def test_deep_listening_stops_preparing_judging_and_fixing_before_reflection() -> None:
    report = assess_listening(
        ListeningEvidence(
            stopped_preparing_answer=True,
            stopped_judging=True,
            centered_coachee_motive=True,
            stopped_fixing_or_rescuing=True,
            reflected_emotion=True,
            returned_interpretation=True,
        )
    )

    assert report.level is ListeningLevel.L4
    assert report.active_reflection_ready


def test_understanding_experience_does_not_claim_all_facts_are_true() -> None:
    report = assess_listening(
        ListeningEvidence(
            stopped_preparing_answer=True,
            stopped_judging=True,
            centered_coachee_motive=True,
            stopped_fixing_or_rescuing=True,
            reflected_emotion=True,
            returned_interpretation=True,
            claims_factual_agreement=True,
        )
    )

    assert not report.active_reflection_ready
    assert "claims_factual_agreement" in report.violations

