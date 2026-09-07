from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import RLock
from typing import Literal

from pydantic import Field, model_validator

from hermes_coach.contracts.runtime_contract import CandidateRecord, RecordKind
from hermes_coach.domain.models import ImmutableModel
from hermes_coach.domain.session_state import STAGE_ORDER, CoachingSessionState


CONFIRMABLE_KINDS = {
    RecordKind.GOAL,
    RecordKind.INSIGHT,
    RecordKind.COMMITMENT,
    RecordKind.MEMORY,
}
DEFAULT_CONFIRMATION_INTENT_TTL = timedelta(minutes=2)
MAX_CONFIRMATION_INTENT_TTL = timedelta(minutes=5)


class RecordAction(StrEnum):
    ACCEPT = "accept"
    EDIT = "edit"
    DISCARD = "discard"


class CheckInAction(StrEnum):
    KEEP = "keep"
    EDIT = "edit"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"


class ConfirmationCommand(ImmutableModel):
    command_id: str = Field(min_length=1)
    intent_token: str = Field(min_length=32)
    candidate_id: str = Field(min_length=1)
    action: RecordAction
    edited_value: str | None = None

    @model_validator(mode="after")
    def edited_value_matches_action(self) -> "ConfirmationCommand":
        if self.action is RecordAction.EDIT and not (
            self.edited_value and self.edited_value.strip()
        ):
            raise ValueError("edit requires edited_value")
        if self.action is not RecordAction.EDIT and self.edited_value is not None:
            raise ValueError("edited_value is valid only for edit")
        return self


class CheckInChoiceCommand(ImmutableModel):
    command_id: str = Field(min_length=1)
    ui_event_id: str = Field(min_length=1)
    check_in_id: str = Field(min_length=1)
    action: CheckInAction
    edited_commitment: str | None = None
    rescheduled_for: str | None = None

    @model_validator(mode="after")
    def payload_matches_action(self) -> "CheckInChoiceCommand":
        if self.action is CheckInAction.EDIT and not self.edited_commitment:
            raise ValueError("edit requires edited_commitment")
        if self.action is CheckInAction.RESCHEDULE and not self.rescheduled_for:
            raise ValueError("reschedule requires rescheduled_for")
        if self.action is not CheckInAction.EDIT and self.edited_commitment is not None:
            raise ValueError("edited_commitment is valid only for edit")
        if (
            self.action is not CheckInAction.RESCHEDULE
            and self.rescheduled_for is not None
        ):
            raise ValueError("rescheduled_for is valid only for reschedule")
        return self


class RecordConfirmationResult(ImmutableModel):
    candidate_id: str
    kind: RecordKind
    value: str
    status: Literal["confirmed", "discarded"]
    command_id: str


class ConfirmationApplication(ImmutableModel):
    state: CoachingSessionState
    result: RecordConfirmationResult


class ConfirmationIntent(ImmutableModel):
    """Opaque, short-lived challenge returned to the local UI."""

    token: str = Field(min_length=32)
    expires_at: datetime


@dataclass(frozen=True)
class _ConfirmationIntentBinding:
    intent: ConfirmationIntent
    local_user_id: str
    session_id: str
    candidate: CandidateRecord
    action: RecordAction
    edited_payload_digest: str


class RecordConfirmationAuthority:
    """Issues and consumes trusted, per-record confirmation intents.

    Phase 2 exactly-once is process-local only: one authority instance protects
    its in-memory intent, command, and candidate registries with one lock. A
    restart or another process does not share those registries. Phase 3 must put
    intent verification/consumption, command and candidate CAS, and the official
    record write in one durable transaction; this pure service intentionally
    does not add SQLite or claim crash-safe exactly-once delivery.
    """

    def __init__(
        self,
        *,
        intent_ttl: timedelta = DEFAULT_CONFIRMATION_INTENT_TTL,
    ) -> None:
        if not timedelta(0) < intent_ttl <= MAX_CONFIRMATION_INTENT_TTL:
            raise ValueError("intent_ttl must be positive and at most five minutes")
        self._intent_ttl = intent_ttl
        self._intents: dict[str, _ConfirmationIntentBinding] = {}
        self._issued_intent_tokens: set[str] = set()
        self._used_command_keys: set[tuple[str, str, str]] = set()
        self._resolved_candidate_keys: set[tuple[str, str, str]] = set()
        self._lock = RLock()

    def issue_intent(
        self,
        *,
        local_user_id: str,
        state: CoachingSessionState,
        candidate_id: str,
        action: RecordAction,
        edited_value: str | None = None,
        now: datetime | None = None,
    ) -> ConfirmationIntent:
        with self._lock:
            _require_non_blank(local_user_id, "local_user_id")
            _require_non_blank(candidate_id, "candidate_id")
            try:
                normalized_action = RecordAction(action)
            except ValueError as exc:
                raise ValueError("unsupported record confirmation action") from exc
            _validate_edited_value(normalized_action, edited_value)

            current = _current_time(now)
            self._prune_expired_intents_unlocked(current)
            candidate_key = (local_user_id, state.session_id, candidate_id)
            if candidate_key in self._resolved_candidate_keys:
                raise ValueError("candidate has already been resolved")
            candidate = _current_pending_candidate(state, candidate_id)

            token = secrets.token_urlsafe(32)
            while token in self._issued_intent_tokens:
                token = secrets.token_urlsafe(32)
            intent = ConfirmationIntent(
                token=token,
                expires_at=current + self._intent_ttl,
            )
            self._intents[token] = _ConfirmationIntentBinding(
                intent=intent,
                local_user_id=local_user_id,
                session_id=state.session_id,
                candidate=candidate,
                action=normalized_action,
                edited_payload_digest=edited_payload_digest(edited_value),
            )
            self._issued_intent_tokens.add(token)
            return intent

    def apply(
        self,
        state: CoachingSessionState,
        command: ConfirmationCommand,
        *,
        local_user_id: str,
        now: datetime | None = None,
    ) -> ConfirmationApplication:
        with self._lock:
            _require_non_blank(local_user_id, "local_user_id")
            current = _current_time(now)
            binding = self._intents.get(command.intent_token)
            if binding is None:
                raise PermissionError(
                    "confirmation requires an unused backend-issued intent"
                )
            if binding.intent.expires_at <= current:
                del self._intents[command.intent_token]
                raise PermissionError("confirmation intent has expired")

            payload_digest = edited_payload_digest(command.edited_value)
            binding_matches = (
                binding.local_user_id == local_user_id
                and binding.session_id == state.session_id
                and binding.candidate.candidate_id == command.candidate_id
                and binding.action is command.action
                and secrets.compare_digest(
                    binding.edited_payload_digest,
                    payload_digest,
                )
            )
            if not binding_matches:
                raise PermissionError(
                    "confirmation command does not match its issued intent"
                )

            command_key = (local_user_id, state.session_id, command.command_id)
            candidate_key = (local_user_id, state.session_id, command.candidate_id)
            if command_key in self._used_command_keys:
                raise ValueError("command_id has already been used")
            if candidate_key in self._resolved_candidate_keys:
                raise ValueError("candidate has already been resolved")
            candidate = _current_pending_candidate(state, command.candidate_id)
            if candidate != binding.candidate:
                raise ValueError(
                    "pending candidate/revision changed after intent issuance"
                )

            result = _build_confirmation_result(candidate, command)
            remaining = tuple(
                item
                for item in state.candidate_records
                if item.candidate_id != candidate.candidate_id
            )
            application = ConfirmationApplication(
                state=state.model_copy(update={"candidate_records": remaining}),
                result=result,
            )
            del self._intents[command.intent_token]
            self._used_command_keys.add(command_key)
            self._resolved_candidate_keys.add(candidate_key)
            return application

    def _prune_expired_intents_unlocked(self, now: datetime) -> None:
        expired = tuple(
            token
            for token, binding in self._intents.items()
            if binding.intent.expires_at <= now
        )
        for token in expired:
            del self._intents[token]


def _current_pending_candidate(
    state: CoachingSessionState,
    candidate_id: str,
) -> CandidateRecord:
    matches = tuple(
        candidate
        for candidate in state.candidate_records
        if candidate.candidate_id == candidate_id
    )
    if len(matches) != 1:
        raise ValueError("command must target one pending session candidate")
    candidate = matches[0]
    if candidate.kind not in CONFIRMABLE_KINDS:
        raise ValueError("record kind is not confirmable by the coaching flow")
    if candidate.coaching_stage is None or candidate.stage_revision is None:
        raise ValueError("candidate lacks stage/revision provenance")
    if candidate.stage_revision != state.revision_for(candidate.coaching_stage):
        raise ValueError("candidate belongs to a stale stage revision")
    if STAGE_ORDER.index(candidate.coaching_stage) > STAGE_ORDER.index(
        state.current_step
    ):
        raise ValueError("candidate belongs to a future coaching stage")
    return candidate


def _current_time(now: datetime | None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(UTC)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _validate_edited_value(
    action: RecordAction,
    edited_value: str | None,
) -> None:
    if action is RecordAction.EDIT and not (edited_value and edited_value.strip()):
        raise ValueError("edit requires edited_value")
    if action is not RecordAction.EDIT and edited_value is not None:
        raise ValueError("edited_value is valid only for edit")


def edited_payload_digest(edited_value: str | None) -> str:
    """Bind an edited payload to its intent.

    Public so the durable Phase 3 service computes the same digest instead of
    re-deriving it and drifting.
    """
    canonical_payload = json.dumps(
        {"edited_value": edited_value},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _build_confirmation_result(
    candidate: CandidateRecord, command: ConfirmationCommand
) -> RecordConfirmationResult:
    if candidate.candidate_id != command.candidate_id:
        raise ValueError("command must target exactly the supplied candidate")
    if candidate.kind not in CONFIRMABLE_KINDS:
        raise ValueError("record kind is not confirmable by the coaching flow")
    status = "discarded" if command.action is RecordAction.DISCARD else "confirmed"
    value = command.edited_value.strip() if command.edited_value else candidate.value
    return RecordConfirmationResult(
        candidate_id=candidate.candidate_id,
        kind=candidate.kind,
        value=value,
        status=status,
        command_id=command.command_id,
    )
