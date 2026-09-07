from __future__ import annotations

from hermes_coach.contracts.runtime_contract import SafetySignal
from hermes_coach.domain.enums import SafetyState
from hermes_coach.domain.models import ImmutableModel
from hermes_coach.policies.companion_policy import PolicyReport


# What the model's signal means for the session's safety state.
#
# The two enums are parallel by construction — none/distress/self_harm/
# immediate_danger against normal/sensitive/possible_crisis/urgent — but nothing
# stated the correspondence, so nothing acted on it and every turn's signal was
# discarded.
STATE_FOR_SIGNAL: dict[SafetySignal, SafetyState] = {
    SafetySignal.NONE: SafetyState.NORMAL,
    SafetySignal.DISTRESS: SafetyState.SENSITIVE,
    SafetySignal.SELF_HARM: SafetyState.POSSIBLE_CRISIS,
    SafetySignal.IMMEDIATE_DANGER: SafetyState.URGENT,
}


def escalate(current: SafetyState, signal: SafetySignal) -> SafetyState:
    """The state after this turn. Escalation only, never the reverse.

    A session that has reached possible_crisis does not quietly return to normal
    because the next answer sounded calmer. `transition_safety_state` says the
    same thing from the other side: de-escalating requires a distinct new
    Pre-Coaching session, not a turn. So within one session this only ever
    climbs, and the Coachee is never coached back down through a state they were
    interrupted in.
    """
    ordered = tuple(SafetyState)
    proposed = STATE_FOR_SIGNAL[signal]
    return max(current, proposed, key=ordered.index)


class SafetyBehaviorEvidence(ImmutableModel):
    creates_dependency: bool = False
    labels_incapacity: bool = False
    creates_guilt: bool = False
    uses_dark_pattern: bool = False
    directs_major_decision: bool = False
    diagnoses: bool = False
    writes_without_consent: bool = False
    discloses_data: bool = False


def assess_prohibited_behavior(evidence: SafetyBehaviorEvidence) -> PolicyReport:
    violations = tuple(
        code
        for failed, code in (
            (evidence.creates_dependency, "dependency"),
            (evidence.labels_incapacity, "incapacity_label"),
            (evidence.creates_guilt, "guilt"),
            (evidence.uses_dark_pattern, "dark_pattern"),
            (evidence.directs_major_decision, "major_decision_directive"),
            (evidence.diagnoses, "diagnosis"),
            (evidence.writes_without_consent, "write_without_consent"),
            (evidence.discloses_data, "data_disclosure"),
        )
        if failed
    )
    return PolicyReport(compliant=not violations, violations=violations)

