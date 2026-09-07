from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

from pydantic import Field

from hermes_coach.contracts.evaluation_contract import ExternalGateStatus
from hermes_coach.domain.enums import SafetyOutputMode, SafetyState
from hermes_coach.domain.models import ImmutableModel
from hermes_coach.domain.session_state import CoachingSessionState


_SAFETY_REVIEW_GATE_ID = "GATE-SAFETY-REVIEW"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class SafetyRoute(ImmutableModel):
    state: SafetyState
    output_mode: SafetyOutputMode
    coaching_interrupted: bool
    normal_coaching_continues: bool
    permission_required: bool = False
    labeled_safety_system: bool = False
    direct_guidance: str | None = None
    approval_evidence_id: str | None = Field(default=None, min_length=1)


class SafetyStateTransition(ImmutableModel):
    previous: SafetyState
    next: SafetyState
    replacement_session_id: str | None = None


class SafetyReleaseAttestation(ImmutableModel):
    """Immutable claims signed by an external safety-review issuer."""

    issuer: str = Field(min_length=1)
    gate_id: str = Field(pattern=r"^GATE-[A-Z0-9-]+$")
    gate_status: ExternalGateStatus
    evidence_uri: str = Field(min_length=1)
    evidence_digest: str = Field(pattern=_SHA256_PATTERN)
    guidance_digest: str = Field(pattern=_SHA256_PATTERN)
    guidance_version: str = Field(min_length=1)
    reviewed_at: datetime
    expires_at: datetime
    signature: str = Field(min_length=1)

    def signed_payload(self) -> bytes:
        claims = self.model_dump(exclude={"signature"}, mode="json")
        return json.dumps(
            claims,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")


class TrustedSafetyAttestationVerifier(Protocol):
    """Verification-only trust boundary supplied by application composition."""

    def verify(self, *, issuer: str, payload: bytes, signature: str) -> bool: ...


class SafetyReleaseAuthorization(ImmutableModel):
    token: str = Field(min_length=32)
    issuer: str = Field(min_length=1)
    gate_id: str = Field(min_length=1)
    gate_status: ExternalGateStatus
    guidance: str = Field(min_length=1)
    guidance_digest: str = Field(pattern=_SHA256_PATTERN)
    guidance_version: str = Field(min_length=1)
    evidence_uri: str = Field(min_length=1)
    evidence_digest: str = Field(pattern=_SHA256_PATTERN)
    reviewed_at: datetime
    expires_at: datetime
    attestation_signature: str = Field(min_length=1)


class SafetyReleaseAuthority:
    """Issues release capabilities only from current external human evidence."""

    def __init__(
        self,
        *,
        trusted_issuer: str | None = None,
        verifier: TrustedSafetyAttestationVerifier | None = None,
    ) -> None:
        self._trusted_issuer = trusted_issuer.strip() if trusted_issuer else None
        self._verifier = verifier
        self._issued: dict[str, SafetyReleaseAuthorization] = {}
        self._lock = RLock()

    def issue(
        self,
        attestation: SafetyReleaseAttestation,
        *,
        guidance: str,
        now: datetime | None = None,
    ) -> SafetyReleaseAuthorization:
        with self._lock:
            current = now or datetime.now(UTC)
            if type(attestation) is not SafetyReleaseAttestation:
                raise PermissionError("signed external safety attestation is required")
            if self._trusted_issuer is None or self._verifier is None:
                raise PermissionError("trusted external safety verifier is required")

            normalized_guidance = guidance.strip()
            approved = (
                attestation.issuer == self._trusted_issuer
                and attestation.gate_id == _SAFETY_REVIEW_GATE_ID
                and attestation.gate_status is ExternalGateStatus.PASSED
                and bool(normalized_guidance)
                and _is_aware(current)
                and _is_aware(attestation.reviewed_at)
                and _is_aware(attestation.expires_at)
                and attestation.reviewed_at <= current < attestation.expires_at
                and attestation.reviewed_at < attestation.expires_at
                and _sha256(normalized_guidance) == attestation.guidance_digest
            )
            verified = False
            if approved:
                try:
                    verified = bool(
                        self._verifier.verify(
                            issuer=attestation.issuer,
                            payload=attestation.signed_payload(),
                            signature=attestation.signature,
                        )
                    )
                except Exception:
                    verified = False
            if not verified:
                raise PermissionError("current signed external safety approval is required")

            authorization = SafetyReleaseAuthorization(
                token=secrets.token_urlsafe(32),
                issuer=attestation.issuer,
                gate_id=attestation.gate_id,
                gate_status=attestation.gate_status,
                guidance=normalized_guidance,
                guidance_digest=attestation.guidance_digest,
                guidance_version=attestation.guidance_version,
                evidence_uri=attestation.evidence_uri,
                evidence_digest=attestation.evidence_digest,
                reviewed_at=attestation.reviewed_at,
                expires_at=attestation.expires_at,
                attestation_signature=attestation.signature,
            )
            self._issued[authorization.token] = authorization
            return authorization

    def permits(
        self,
        authorization: SafetyReleaseAuthorization,
        *,
        now: datetime | None = None,
    ) -> bool:
        with self._lock:
            current = now or datetime.now(UTC)
            return bool(
                self._issued.get(authorization.token) == authorization
                and authorization.expires_at > current
            )


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# What the Safety System says when it replaces the Coach.
#
# PROVISIONAL. Phase 7 lists "human safety review of detection thresholds,
# Vietnamese/regional support content and the non-automatic resume path" as an
# external release gate, and this copy has not been through it. It is written to
# be safe to ship *before* that review rather than to be the final text: no
# diagnosis, no clinical claim, no invented hotline number, nothing that reads
# as advice. It says what the product just did and that a person is needed.
#
# Shipping nothing was the alternative, and it is worse: interrupting coaching
# without a word leaves someone in difficulty facing a screen that simply
# stopped answering.
SAFETY_CHECK_MESSAGE = (
    "Mình dừng phần coaching ở đây. Điều bạn vừa nói nghe như một chuyện cần "
    "được quan tâm ngay, và một phiên coaching không phải là chỗ cho nó. "
    "Ngay lúc này bạn có đang an toàn không?"
)

BLOCKED_MESSAGE = (
    "Mình dừng phần coaching ở đây. Điều bạn vừa nói cần một con người ở bên "
    "bạn, không phải một ứng dụng. Hãy liên hệ ngay với người bạn tin tưởng, "
    "hoặc dịch vụ khẩn cấp tại nơi bạn đang ở. Những gì bạn đã lưu vẫn còn "
    "nguyên."
)


def safety_system_message(route: SafetyRoute) -> str | None:
    """The text to show in place of a coaching question, if any.

    `None` means the Coach's own question stands: routing did not interrupt.
    """
    if route.normal_coaching_continues:
        return None
    if route.output_mode is SafetyOutputMode.DIRECT_SAFETY_GUIDANCE:
        # Only ever text an external reviewer signed; never anything generated.
        return route.direct_guidance
    if route.output_mode is SafetyOutputMode.SAFETY_CHECK:
        return SAFETY_CHECK_MESSAGE
    return BLOCKED_MESSAGE


def route_safety(
    state: SafetyState,
    *,
    authorization: SafetyReleaseAuthorization | None = None,
    authority: SafetyReleaseAuthority | None = None,
    approved_direct_guidance: str | None = None,
    approval_evidence_id: str | None = None,
) -> SafetyRoute:
    if state is SafetyState.NORMAL:
        return SafetyRoute(
            state=state,
            output_mode=SafetyOutputMode.COACHING_QUESTION,
            coaching_interrupted=False,
            normal_coaching_continues=True,
        )
    if state is SafetyState.SENSITIVE:
        return SafetyRoute(
            state=state,
            output_mode=SafetyOutputMode.PERMISSION_QUESTION,
            coaching_interrupted=False,
            normal_coaching_continues=True,
            permission_required=True,
        )
    if state is SafetyState.POSSIBLE_CRISIS:
        return SafetyRoute(
            state=state,
            output_mode=SafetyOutputMode.SAFETY_CHECK,
            coaching_interrupted=True,
            normal_coaching_continues=False,
            labeled_safety_system=True,
        )
    if not authorization or not authority or not authority.permits(authorization):
        return SafetyRoute(
            state=state,
            output_mode=SafetyOutputMode.BLOCKED,
            coaching_interrupted=True,
            normal_coaching_continues=False,
            labeled_safety_system=True,
        )
    return SafetyRoute(
        state=state,
        output_mode=SafetyOutputMode.DIRECT_SAFETY_GUIDANCE,
        coaching_interrupted=True,
        normal_coaching_continues=False,
        labeled_safety_system=True,
        direct_guidance=authorization.guidance,
        approval_evidence_id=authorization.evidence_uri,
    )


def transition_safety_state(
    previous_state: CoachingSessionState,
    next_state: SafetyState,
    *,
    replacement_state: CoachingSessionState | None = None,
) -> SafetyStateTransition:
    ordered = tuple(SafetyState)
    previous = previous_state.safety_state
    deescalates = ordered.index(next_state) < ordered.index(previous)
    if deescalates:
        valid_replacement = False
        if replacement_state and replacement_state.session_id != previous_state.session_id:
            fresh_replacement = CoachingSessionState(
                session_id=replacement_state.session_id,
                safety_state=next_state,
            )
            valid_replacement = replacement_state == fresh_replacement
        if not valid_replacement:
            raise ValueError(
                "safety de-escalation requires a distinct new Pre-Coaching session "
                "in fresh open Pre-Coaching state"
            )
    return SafetyStateTransition(
        previous=previous,
        next=next_state,
        replacement_session_id=(
            replacement_state.session_id if deescalates and replacement_state else None
        ),
    )
