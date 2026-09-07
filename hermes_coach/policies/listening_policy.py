from __future__ import annotations

from enum import IntEnum

from hermes_coach.domain.models import ImmutableModel


class ListeningLevel(IntEnum):
    BELOW_L1 = 0
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4


class ListeningEvidence(ImmutableModel):
    stopped_preparing_answer: bool = False
    stopped_judging: bool = False
    centered_coachee_motive: bool = False
    stopped_fixing_or_rescuing: bool = False
    reflected_emotion: bool = False
    returned_interpretation: bool = False
    claims_factual_agreement: bool = False
    pity_or_praise: bool = False


class ListeningAssessment(ImmutableModel):
    level: ListeningLevel
    active_reflection_ready: bool
    violations: tuple[str, ...] = ()


def assess_listening(evidence: ListeningEvidence) -> ListeningAssessment:
    level = ListeningLevel.BELOW_L1
    if evidence.stopped_preparing_answer:
        level = ListeningLevel.L1
        if evidence.stopped_judging:
            level = ListeningLevel.L2
            if evidence.centered_coachee_motive:
                level = ListeningLevel.L3
                if evidence.stopped_fixing_or_rescuing:
                    level = ListeningLevel.L4
    violations = tuple(
        code
        for failed, code in (
            (evidence.claims_factual_agreement, "claims_factual_agreement"),
            (evidence.pity_or_praise, "pity_or_praise"),
        )
        if failed
    )
    reflection_ready = bool(
        level is ListeningLevel.L4
        and evidence.reflected_emotion
        and evidence.returned_interpretation
        and not violations
    )
    return ListeningAssessment(
        level=level,
        active_reflection_ready=reflection_ready,
        violations=violations,
    )

