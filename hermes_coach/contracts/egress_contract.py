from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from enum import StrEnum
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EgressCategory(StrEnum):
    CURRENT_TURN = "current_turn"
    SELECTED_PROFILE = "selected_profile"
    SELECTED_MEMORY = "selected_memory"
    COACHING_STATE = "coaching_state"
    CANDIDATE_RECORD = "candidate_record"


class ProviderRetentionStatus(StrEnum):
    DOCUMENTED = "documented"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class EgressRequirement(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"


class EgressConsentAction(StrEnum):
    CONFIRM = "confirm"
    DECLINE = "decline"
    WITHDRAW = "withdraw"


class EgressConsentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1)
    session_id: str | None = None
    consent_type: Literal["model_egress"] = "model_egress"
    scope: str = Field(min_length=1)
    version: str = Field(min_length=1)
    action: EgressConsentAction
    ui_event_id: str = Field(min_length=1)
    source: Literal["ui"] = "ui"
    created_at: datetime
    allows_new_requests: bool

    @model_validator(mode="after")
    def bind_permission_to_ui_action(self) -> "EgressConsentDecision":
        should_allow = self.action is EgressConsentAction.CONFIRM
        if self.allows_new_requests is not should_allow:
            raise ValueError("decline or withdrawal blocks new requests in its scope")
        return self


class EgressAuthorization(BaseModel):
    """Opaque one-turn authorization issued from a trusted UI consent event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_token: str = Field(min_length=32)
    ui_event_id: str = Field(min_length=1)
    manifest_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    version: str = Field(min_length=1)


class EgressConsentAuthority:
    """Trusted boundary between UI consent events and provider authorization.

    A decision DTO alone is never sufficient for model egress. The UI boundary
    must first record it here, and this authority issues a one-turn opaque token.
    """

    def __init__(self) -> None:
        self._events: dict[str, EgressConsentDecision] = {}
        self._latest_by_scope: dict[tuple[str, str, str], str] = {}
        self._authorizations: dict[str, EgressAuthorization] = {}
        self._lock = RLock()

    def record_ui_decision(self, decision: EgressConsentDecision) -> None:
        with self._lock:
            if decision.ui_event_id in self._events:
                raise ValueError("ui_event_id must be unique")
            key = (decision.profile_id, decision.scope, decision.version)
            self._events[decision.ui_event_id] = decision
            self._latest_by_scope[key] = decision.ui_event_id

    def issue_authorization(
        self,
        *,
        profile_id: str,
        ui_event_id: str,
        manifest_id: str,
        session_id: str,
        turn_id: str,
        scope: str,
        version: str,
    ) -> EgressAuthorization:
        with self._lock:
            decision = self._events.get(ui_event_id)
            key = (profile_id, scope, version)
            if not (
                decision
                and self._latest_by_scope.get(key) == ui_event_id
                and decision.profile_id == profile_id
                and decision.scope == scope
                and decision.version == version
                and decision.action is EgressConsentAction.CONFIRM
                and decision.allows_new_requests
                and (decision.session_id is None or decision.session_id == session_id)
            ):
                raise PermissionError("no active trusted UI consent for this egress scope")

            authorization = EgressAuthorization(
                authorization_token=secrets.token_urlsafe(32),
                ui_event_id=ui_event_id,
                manifest_id=manifest_id,
                session_id=session_id,
                turn_id=turn_id,
                scope=scope,
                version=version,
            )
            self._authorizations[authorization.authorization_token] = authorization
            return authorization

    def permits(
        self,
        authorization: EgressAuthorization,
        *,
        profile_id: str,
        manifest_id: str,
        session_id: str,
        turn_id: str,
        scope: str,
        version: str,
    ) -> bool:
        with self._lock:
            return self._permits_unlocked(
                authorization,
                profile_id=profile_id,
                manifest_id=manifest_id,
                session_id=session_id,
                turn_id=turn_id,
                scope=scope,
                version=version,
            )

    @contextmanager
    def provider_call_lease(
        self,
        authorization: EgressAuthorization,
        *,
        profile_id: str,
        manifest_id: str,
        session_id: str,
        turn_id: str,
        scope: str,
        version: str,
    ) -> Iterator[bool]:
        """Atomically admit one provider attempt and its accepted-result sink."""

        with self._lock:
            yield self._permits_unlocked(
                authorization,
                profile_id=profile_id,
                manifest_id=manifest_id,
                session_id=session_id,
                turn_id=turn_id,
                scope=scope,
                version=version,
            )

    def _permits_unlocked(
        self,
        authorization: EgressAuthorization,
        *,
        profile_id: str,
        manifest_id: str,
        session_id: str,
        turn_id: str,
        scope: str,
        version: str,
    ) -> bool:
        issued = self._authorizations.get(authorization.authorization_token)
        decision = self._events.get(authorization.ui_event_id)
        key = (profile_id, scope, version)
        return bool(
            issued == authorization
            and decision
            and self._latest_by_scope.get(key) == authorization.ui_event_id
            and decision.action is EgressConsentAction.CONFIRM
            and decision.allows_new_requests
            and authorization.manifest_id == manifest_id
            and authorization.session_id == session_id
            and authorization.turn_id == turn_id
            and authorization.scope == scope
            and authorization.version == version
        )


class EgressItemRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    local_id: str = Field(min_length=1)
    category: EgressCategory
    requirement: EgressRequirement


class ProviderRetentionDisclosure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ProviderRetentionStatus
    label: str = Field(min_length=1)
    source_url: str | None = None
    source_checked_at: datetime | None = None
    version: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_source_for_documented_policy(self) -> "ProviderRetentionDisclosure":
        if self.status is ProviderRetentionStatus.DOCUMENTED and not self.source_url:
            raise ValueError("documented provider retention requires source_url")
        return self


class EgressManifest(BaseModel):
    """Audit metadata only; transmitted coaching data is never copied here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    created_at: datetime
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    requirement: EgressRequirement
    categories: tuple[EgressCategory, ...] = Field(min_length=1)
    item_refs: tuple[EgressItemRef, ...] = Field(min_length=1)
    consent_scope: str = Field(min_length=1)
    consent_version: str = Field(min_length=1)
    provider_retention: ProviderRetentionDisclosure
