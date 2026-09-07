from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import pytest

from hermes_coach.application.safety_service import (
    SafetyReleaseAttestation,
    SafetyReleaseAuthority,
    TrustedSafetyAttestationVerifier,
    route_safety,
    transition_safety_state,
)
from hermes_coach.contracts.evaluation_contract import (
    ExternalGateStatus,
    ExternalValidationGate,
)
from hermes_coach.domain.enums import FunnelStage, SafetyOutputMode, SafetyState
from hermes_coach.contracts.runtime_contract import (
    CandidateRecord,
    CoachingStage,
    GateAnswer,
    RecordKind,
)
from hermes_coach.domain.models import PreCoachingSnapshot
from hermes_coach.domain.session_state import (
    ClosingGateBinding,
    CoachingSessionState,
    SessionGateEvent,
)
from hermes_coach.policies.safety_policy import SafetyBehaviorEvidence, assess_prohibited_behavior


_TRUSTED_ISSUER = "human-safety-board"
_TEST_SIGNING_KEY = b"test-only-external-safety-key"
_GUIDANCE = "Liên hệ dịch vụ khẩn cấp tại địa phương."


class _TrustedTestVerifier(TrustedSafetyAttestationVerifier):
    def verify(self, *, issuer: str, payload: bytes, signature: str) -> bool:
        expected = hmac.new(_TEST_SIGNING_KEY, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)


def _signed_attestation(
    now: datetime,
    *,
    guidance: str = _GUIDANCE,
    issuer: str = _TRUSTED_ISSUER,
    reviewed_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> SafetyReleaseAttestation:
    unsigned = SafetyReleaseAttestation(
        issuer=issuer,
        gate_id="GATE-SAFETY-REVIEW",
        gate_status=ExternalGateStatus.PASSED,
        evidence_uri="review://safety/v1",
        evidence_digest=hashlib.sha256(b"external-review-artifact-v1").hexdigest(),
        guidance_digest=hashlib.sha256(guidance.strip().encode("utf-8")).hexdigest(),
        guidance_version="safety-guidance-v1",
        reviewed_at=reviewed_at or now,
        expires_at=expires_at or now + timedelta(days=30),
        signature="unsigned-test-placeholder",
    )
    signature = hmac.new(
        _TEST_SIGNING_KEY,
        unsigned.signed_payload(),
        hashlib.sha256,
    ).hexdigest()
    return unsigned.model_copy(update={"signature": signature})


def test_normal_sensitive_and_possible_crisis_have_distinct_routes() -> None:
    normal = route_safety(SafetyState.NORMAL)
    sensitive = route_safety(SafetyState.SENSITIVE)
    crisis = route_safety(SafetyState.POSSIBLE_CRISIS)

    assert normal.output_mode is SafetyOutputMode.COACHING_QUESTION
    assert sensitive.permission_required and not sensitive.coaching_interrupted
    assert crisis.coaching_interrupted and crisis.output_mode is SafetyOutputMode.SAFETY_CHECK


def test_urgent_is_fail_closed_without_external_approval_evidence() -> None:
    blocked = route_safety(SafetyState.URGENT)
    forged = route_safety(
        SafetyState.URGENT,
        approved_direct_guidance="Hướng dẫn chưa được duyệt",
        approval_evidence_id="made-up",
    )
    now = datetime.now(UTC)
    unsigned_gate = ExternalValidationGate(
        id="GATE-SAFETY-REVIEW",
        owner="human safety reviewer",
        status=ExternalGateStatus.PASSED,
        blocks=("urgent release",),
        evidence_format="signed review artifact",
        evidence_validity_days=30,
        evidence_uri="review://safety/v1",
        reviewed_at=now,
        expires_at=now + timedelta(days=30),
    )
    authority = SafetyReleaseAuthority(
        trusted_issuer=_TRUSTED_ISSUER,
        verifier=_TrustedTestVerifier(),
    )
    with pytest.raises(PermissionError, match="signed external safety attestation"):
        authority.issue(unsigned_gate, guidance=_GUIDANCE, now=now)  # type: ignore[arg-type]

    attestation = _signed_attestation(now)
    authorization = authority.issue(
        attestation,
        guidance=_GUIDANCE,
        now=now,
    )
    released = route_safety(
        SafetyState.URGENT,
        authorization=authorization,
        authority=authority,
    )

    assert blocked.coaching_interrupted
    assert blocked.output_mode is SafetyOutputMode.BLOCKED
    assert forged.output_mode is SafetyOutputMode.BLOCKED
    assert blocked.direct_guidance is None
    assert released.output_mode is SafetyOutputMode.DIRECT_SAFETY_GUIDANCE
    assert released.labeled_safety_system
    assert not released.normal_coaching_continues


def test_pending_external_safety_evidence_stays_pending_and_cannot_issue_release() -> None:
    now = datetime.now(UTC)
    authority = SafetyReleaseAuthority(
        trusted_issuer=_TRUSTED_ISSUER,
        verifier=_TrustedTestVerifier(),
    )
    pending = ExternalValidationGate(
        id="GATE-SAFETY-REVIEW",
        owner="human safety reviewer",
        status=ExternalGateStatus.PENDING,
        blocks=("urgent release",),
        evidence_format="signed review artifact",
        evidence_validity_days=30,
    )

    assert pending.status is ExternalGateStatus.PENDING
    with pytest.raises(PermissionError, match="signed external safety attestation"):
        authority.issue(pending, guidance=_GUIDANCE, now=now)  # type: ignore[arg-type]


def test_production_default_has_no_attestation_verification_capability() -> None:
    now = datetime.now(UTC)

    with pytest.raises(PermissionError, match="trusted external safety verifier"):
        SafetyReleaseAuthority().issue(
            _signed_attestation(now),
            guidance=_GUIDANCE,
            now=now,
        )


def test_wrong_issuer_future_review_expired_or_guidance_mismatch_fail_closed() -> None:
    now = datetime.now(UTC)
    authority = SafetyReleaseAuthority(
        trusted_issuer=_TRUSTED_ISSUER,
        verifier=_TrustedTestVerifier(),
    )
    invalid = (
        _signed_attestation(now, issuer="untrusted-reviewer"),
        _signed_attestation(now, reviewed_at=now + timedelta(minutes=1)),
        _signed_attestation(
            now,
            reviewed_at=now - timedelta(days=31),
            expires_at=now - timedelta(days=1),
        ),
    )

    for attestation in invalid:
        with pytest.raises(PermissionError, match="current signed external safety approval"):
            authority.issue(attestation, guidance=_GUIDANCE, now=now)
    with pytest.raises(PermissionError, match="current signed external safety approval"):
        authority.issue(_signed_attestation(now), guidance="Tampered guidance", now=now)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("issuer", "different-issuer"),
        ("gate_id", "GATE-DIFFERENT-REVIEW"),
        ("gate_status", ExternalGateStatus.PENDING),
        ("evidence_uri", "review://safety/tampered"),
        ("evidence_digest", "0" * 64),
        ("guidance_digest", "1" * 64),
        ("guidance_version", "safety-guidance-v2"),
        ("reviewed_at", datetime(2026, 1, 1, tzinfo=UTC)),
        ("expires_at", datetime(2099, 1, 1, tzinfo=UTC)),
        ("signature", "tampered-signature"),
    ],
)
def test_every_signed_attestation_binding_rejects_tampering(
    field: str,
    replacement: object,
) -> None:
    now = datetime(2026, 8, 21, tzinfo=UTC)
    authority = SafetyReleaseAuthority(
        trusted_issuer=_TRUSTED_ISSUER,
        verifier=_TrustedTestVerifier(),
    )
    tampered = _signed_attestation(now).model_copy(update={field: replacement})

    with pytest.raises(PermissionError, match="current signed external safety approval"):
        authority.issue(tampered, guidance=_GUIDANCE, now=now)


def test_safety_state_never_silently_deescalates_or_auto_resumes() -> None:
    urgent = CoachingSessionState(
        session_id="urgent-session",
        current_step=CoachingStage.WILL,
        safety_state=SafetyState.URGENT,
    )
    with pytest.raises(ValueError, match="new Pre-Coaching"):
        transition_safety_state(urgent, SafetyState.NORMAL)
    with pytest.raises(ValueError, match="distinct"):
        transition_safety_state(
            urgent,
            SafetyState.NORMAL,
            replacement_state=CoachingSessionState(session_id="urgent-session"),
        )

    transition = transition_safety_state(
        urgent,
        SafetyState.NORMAL,
        replacement_state=CoachingSessionState(session_id="new-pre-session"),
    )
    assert transition.replacement_session_id == "new-pre-session"


def test_deescalation_rejects_every_non_fresh_replacement_state() -> None:
    urgent = CoachingSessionState(
        session_id="urgent-session",
        current_step=CoachingStage.WILL,
        safety_state=SafetyState.URGENT,
    )
    baseline = CoachingSessionState(session_id="new-pre-session")
    dirty_states = (
        baseline.model_copy(update={"funnel_stage": FunnelStage.CLOSE}),
        baseline.model_copy(update={"pre_coaching": PreCoachingSnapshot(ready=True)}),
        baseline.model_copy(
            update={
                "gate_events": (
                    SessionGateEvent(
                        stage=CoachingStage.PRE_COACHING,
                        revision=1,
                        closing_question_turn_id="q-1",
                        question_sequence=1,
                        response_turn_id="u-1",
                        response_sequence=2,
                        exact_response="Có",
                        answer=GateAnswer.YES,
                        valid=True,
                    ),
                )
            }
        ),
        baseline.model_copy(
            update={
                "pending_gate": ClosingGateBinding(
                    stage=CoachingStage.PRE_COACHING,
                    revision=1,
                    question_turn_id="q-pending",
                    question_sequence=1,
                )
            }
        ),
        baseline.model_copy(
            update={
                "candidate_records": (
                    CandidateRecord(
                        candidate_id="candidate-1",
                        kind=RecordKind.INSIGHT,
                        value="residual candidate",
                        source_turn_id="turn-1",
                    ),
                )
            }
        ),
        baseline.model_copy(
            update={
                "revisions": tuple(
                    item.model_copy(update={"revision": 2})
                    if item.stage is CoachingStage.PRE_COACHING
                    else item
                    for item in baseline.revisions
                )
            }
        ),
        baseline.model_copy(update={"ended": True}),
    )

    for dirty in dirty_states:
        with pytest.raises(ValueError, match="fresh open Pre-Coaching"):
            transition_safety_state(
                urgent,
                SafetyState.NORMAL,
                replacement_state=dirty,
            )


def test_all_prohibited_coaching_behaviors_fail_policy() -> None:
    report = assess_prohibited_behavior(
        SafetyBehaviorEvidence(
            creates_dependency=True,
            labels_incapacity=True,
            creates_guilt=True,
            uses_dark_pattern=True,
            directs_major_decision=True,
            diagnoses=True,
            writes_without_consent=True,
            discloses_data=True,
        )
    )

    assert not report.compliant
    assert len(report.violations) == 8
