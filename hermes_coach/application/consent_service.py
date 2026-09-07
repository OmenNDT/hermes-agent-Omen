"""Consent evidence and enforcement.

Requirement families: `HC-PRIVACY`; sources `SRC-026`, `SRC-091`, `SRC-092`.

Only a trusted UI control writes consent — a conversational "yes" is not
evidence, which is why every write needs a `control_id` and the schema pins
`source` to `ui`. Effective consent is the latest event for a normalized
type/scope, and it is read fresh on every check so a withdrawal takes effect on
the very next scoped write or model egress.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum

from hermes_coach.domain.records import ConsentEventRow
from hermes_coach.infrastructure.repositories.consent_repository import (
    ConsentRepository,
)
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


EVIDENCE_VERSION = 1


class UiConsentAction(StrEnum):
    CONFIRM = "confirm"
    DECLINE = "decline"
    WITHDRAW = "withdraw"


class ConsentDecision(StrEnum):
    GRANTED = "granted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


# The decision a UI control means. Keeping the mapping here stops a caller from
# recording "withdraw" evidence against a "granted" decision.
_DECISION_FOR_ACTION = {
    UiConsentAction.CONFIRM: ConsentDecision.GRANTED,
    UiConsentAction.DECLINE: ConsentDecision.DECLINED,
    UiConsentAction.WITHDRAW: ConsentDecision.WITHDRAWN,
}


class ConsentWithdrawn(PermissionError):
    """The scoped action has no standing consent."""


def normalize_type(consent_type: str) -> str:
    return consent_type.strip().casefold()


def normalize_scope(scope: Mapping[str, object] | None) -> str:
    """Canonical JSON so key order and spacing cannot split one scope in two."""
    return json.dumps(scope or {}, sort_keys=True, separators=(",", ":"))


class ConsentService:
    def __init__(self, database: CoachDatabase, *, profile_id: str) -> None:
        self._database = database
        self._profile_id = profile_id

    def record(
        self,
        *,
        event_id: str,
        consent_type: str,
        scope: Mapping[str, object] | None,
        ui_action: UiConsentAction,
        control_id: str,
        now: str,
        session_id: str | None = None,
    ) -> None:
        if not control_id.strip():
            raise ValueError("consent needs a trusted UI control id")
        event = ConsentEventRow(
            id=event_id,
            profile_id=self._profile_id,
            session_id=session_id,
            consent_type=normalize_type(consent_type),
            decision=_DECISION_FOR_ACTION[ui_action].value,
            scope_json=normalize_scope(scope),
            source="ui",
            ui_action=ui_action.value,
            control_id=control_id,
            evidence_version=EVIDENCE_VERSION,
            created_at=now,
        )
        with self._database.transaction():
            self._repository().append(event)

    def effective(
        self, consent_type: str, scope: Mapping[str, object] | None
    ) -> ConsentDecision | None:
        latest = self._repository().latest(
            self._profile_id, normalize_type(consent_type), normalize_scope(scope)
        )
        return ConsentDecision(latest.decision) if latest else None

    def is_granted(self, consent_type: str, scope: Mapping[str, object] | None) -> bool:
        return self.effective(consent_type, scope) is ConsentDecision.GRANTED

    def require_granted(
        self, consent_type: str, scope: Mapping[str, object] | None
    ) -> None:
        """Read fresh — a decision cached from an earlier pass can be stale."""
        if not self.is_granted(consent_type, scope):
            raise ConsentWithdrawn(
                f"no standing consent for {normalize_type(consent_type)}"
            )

    def history(
        self, consent_type: str, scope: Mapping[str, object] | None
    ) -> tuple[ConsentEventRow, ...]:
        return self._repository().history(
            self._profile_id, normalize_type(consent_type), normalize_scope(scope)
        )

    def _repository(self) -> ConsentRepository:
        return ConsentRepository(self._database.connection)
