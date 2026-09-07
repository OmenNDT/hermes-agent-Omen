"""Durable, single-use candidate confirmation.

Requirement families: `HC-RECORDS`, `HC-DATA-*`; sources `SRC-054…059`,
`SRC-079`, `SRC-080`, `SRC-084`, `SRC-085`.

Phase 2's `RecordConfirmationAuthority` enforces the same rules in memory, which
is enough inside one process but reopens the replay window on restart. This
service moves intent consumption, the command guard, the candidate transition
and the official record write into one `BEGIN IMMEDIATE` transaction. It reuses
Phase 2's command shape and payload digest rather than re-deriving them, so the
two cannot drift.

There is deliberately no method that confirms more than one candidate.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta

from hermes_coach.application.record_confirmation_service import (
    ConfirmationCommand,
    RecordAction,
    edited_payload_digest,
)
from hermes_coach.contracts.lifecycle_contract import CheckInRecovery
from hermes_coach.domain.clock import shift
from hermes_coach.domain.models import ImmutableModel
from hermes_coach.domain.records import (
    CheckInRow,
    CommitmentRow,
    ConfirmationAuditRow,
    GoalRow,
    InsightRow,
    MemoryItemRow,
    MemoryProvenanceRow,
)
from hermes_coach.infrastructure.repositories.check_in_repository import (
    CheckInRepository,
)
from hermes_coach.infrastructure.repositories.commitment_repository import (
    CommitmentRepository,
)
from hermes_coach.infrastructure.repositories.confirmation_repository import (
    ConfirmationRepository,
    StoredIntent,
    token_digest,
)
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.insight_repository import (
    InsightRepository,
)
from hermes_coach.infrastructure.repositories.memory_repository import MemoryRepository
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


DEFAULT_INTENT_TTL = timedelta(minutes=2)

# The candidate status each action leaves behind.
_RESOLVED_STATUS = {
    RecordAction.ACCEPT: "confirmed",
    RecordAction.EDIT: "edited",
    RecordAction.DISCARD: "discarded",
}

_TIMESTAMP_FORMATS = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S")


class ConfirmationRejected(RuntimeError):
    """The command carried no valid, unused, matching authorization."""


class ConfirmationOutcome(ImmutableModel):
    candidate_id: str
    action: str
    revision: int
    official_record_type: str | None = None
    official_record_id: str | None = None


class DurableConfirmationService:
    def __init__(
        self,
        database: CoachDatabase,
        *,
        profile_id: str,
        intent_ttl: timedelta = DEFAULT_INTENT_TTL,
    ) -> None:
        self._database = database
        self._profile_id = profile_id
        self._intent_ttl = intent_ttl

    def issue_intent(
        self,
        *,
        local_user_id: str,
        session_id: str,
        candidate_id: str,
        action: RecordAction,
        edited_value: str | None,
        now: str,
        reconfirm: bool = False,
    ) -> str:
        """Mint a token bound to one user, session, candidate, action and payload."""
        candidate = self._candidate(candidate_id)
        if candidate is None:
            raise ConfirmationRejected(f"unknown candidate {candidate_id}")
        if candidate["session_id"] != session_id:
            raise ConfirmationRejected("candidate belongs to another session")
        if candidate["status"] != "pending" and not reconfirm:
            raise ConfirmationRejected("candidate is already resolved")

        token = secrets.token_urlsafe(32)
        repository = ConfirmationRepository(self._database.connection)
        with self._database.transaction():
            # Re-rendering the confirmation UI must not leave two live tokens.
            repository.supersede_live_intents(candidate_id, now)
            repository.issue(
                StoredIntent(
                    token_digest=token_digest(token),
                    local_user_id=local_user_id,
                    session_id=session_id,
                    candidate_id=candidate_id,
                    action=action.value,
                    edited_payload_digest=edited_payload_digest(edited_value),
                    issued_at=now,
                    expires_at=self._expiry(now),
                    consumed_at=None,
                )
            )
        return token

    def apply(
        self,
        command: ConfirmationCommand,
        *,
        now: str,
        reconfirm: bool = False,
    ) -> ConfirmationOutcome:
        """Consume the intent and write the record in one transaction."""
        connection = self._database.connection
        repository = ConfirmationRepository(connection)

        with self._database.transaction():
            if repository.command_was_applied(command.command_id):
                raise ConfirmationRejected(
                    f"command {command.command_id} was already applied"
                )

            digest = token_digest(command.intent_token)
            intent = repository.live_intent(digest)
            if intent is None:
                raise ConfirmationRejected("no live intent for this token")
            if self._as_datetime(intent.expires_at) <= self._as_datetime(now):
                raise ConfirmationRejected("intent expired")
            if (
                intent.candidate_id != command.candidate_id
                or intent.action != command.action.value
                or intent.edited_payload_digest
                != edited_payload_digest(command.edited_value)
            ):
                raise ConfirmationRejected("command does not match the intent binding")

            candidate = self._candidate(command.candidate_id)
            if candidate is None:
                raise ConfirmationRejected(f"unknown candidate {command.candidate_id}")

            if not self._resolve_candidate(command, now, reconfirm=reconfirm):
                raise ConfirmationRejected("candidate is no longer pending")

            if not repository.consume(digest, now):
                raise ConfirmationRejected("intent was already consumed")

            record_type, record_id = self._write_official_record(
                candidate, command, now
            )

            revision = repository.next_revision(command.candidate_id)
            repository.record(
                ConfirmationAuditRow(
                    id=str(uuid.uuid4()),
                    command_id=command.command_id,
                    candidate_id=command.candidate_id,
                    revision=revision,
                    action=command.action.value,
                    official_record_type=record_type,
                    official_record_id=record_id,
                    created_at=now,
                )
            )

        return ConfirmationOutcome(
            candidate_id=command.candidate_id,
            action=command.action.value,
            revision=revision,
            official_record_type=record_type,
            official_record_id=record_id,
        )

    def audit_trail(self, candidate_id: str) -> tuple[ConfirmationAuditRow, ...]:
        return ConfirmationRepository(self._database.connection).trail(candidate_id)

    def purge_expired_intents(self, now: str) -> int:
        with self._database.transaction():
            return ConfirmationRepository(self._database.connection).purge_expired(now)

    def _candidate(self, candidate_id: str):
        return self._database.connection.execute(
            "SELECT * FROM candidate_record WHERE id = :candidate_id",
            {"candidate_id": candidate_id},
        ).fetchone()

    def _resolve_candidate(
        self, command: ConfirmationCommand, now: str, *, reconfirm: bool
    ) -> bool:
        """Compare-and-set on the candidate row; only one caller can win."""
        status = _RESOLVED_STATUS[command.action]
        if reconfirm:
            cursor = self._database.connection.execute(
                "UPDATE candidate_record SET status = :status, resolved_at = :now "
                "WHERE id = :candidate_id AND status != 'pending'",
                {"status": status, "now": now, "candidate_id": command.candidate_id},
            )
        else:
            cursor = self._database.connection.execute(
                "UPDATE candidate_record SET status = :status, resolved_at = :now "
                "WHERE id = :candidate_id AND status = 'pending'",
                {"status": status, "now": now, "candidate_id": command.candidate_id},
            )
        return cursor.rowcount == 1

    @staticmethod
    def _check_in_due(payload: dict, now: str) -> str:
        """When to come back to this commitment.

        The Coachee's own due date wins whenever the commitment carries one.
        Otherwise the cadence the lifecycle contract fixes at fourteen days —
        read from `CheckInRecovery` rather than written again here, because two
        copies of a number are two numbers waiting to disagree.
        """
        due_at = payload.get("due_at")
        if isinstance(due_at, str) and due_at.strip():
            return due_at
        cadence = CheckInRecovery.model_fields["default_cadence_days"].default
        return shift(now, timedelta(days=cadence))

    def _write_official_record(
        self, candidate, command: ConfirmationCommand, now: str
    ) -> tuple[str | None, str | None]:
        """Discard produces no record; accept and edit produce exactly one."""
        if command.action is RecordAction.DISCARD:
            return None, None

        payload = json.loads(candidate["payload_json"])
        record_id = str(uuid.uuid4())
        session_id = candidate["session_id"]
        connection = self._database.connection

        match candidate["record_type"]:
            case "goal":
                GoalRepository(connection).add(
                    GoalRow(
                        id=record_id,
                        profile_id=self._profile_id,
                        title=self._text(command, payload, "title"),
                        why_it_matters=payload.get("why_it_matters"),
                        desired_outcome=payload.get("desired_outcome"),
                        success_evidence=payload.get("success_evidence"),
                        target_date=payload.get("target_date"),
                        status="active",
                        source_session_id=session_id,
                        confirmed_at=now,
                        created_at=now,
                    )
                )
                return "goal", record_id
            case "insight":
                InsightRepository(connection).add(
                    InsightRow(
                        id=record_id,
                        content=self._text(command, payload, "content"),
                        topic=payload.get("topic"),
                        sensitivity=payload.get("sensitivity"),
                        source_session_id=session_id,
                        goal_id=payload.get("goal_id"),
                        confirmed_at=now,
                    )
                )
                return "insight", record_id
            case "commitment":
                goal_id = payload.get("goal_id")
                if not goal_id:
                    raise ConfirmationRejected("a commitment must name its goal")
                CommitmentRepository(connection).add(
                    CommitmentRow(
                        id=record_id,
                        goal_id=goal_id,
                        action_text=self._text(command, payload, "action_text"),
                        due_at=payload.get("due_at"),
                        evidence_definition=payload.get("evidence_definition"),
                        confidence_score=payload.get("confidence_score"),
                        status="active",
                        source_session_id=session_id,
                        confirmed_at=now,
                    )
                )
                # A commitment nobody ever comes back to is a note, not a
                # commitment. The check-in is what makes it the second kind.
                #
                # `check_in` had a table, a row model, a repository with a
                # Trash-aware `pending()`, a slot in `coach.today` and a screen
                # in the app — and no code anywhere ever inserted a row, so
                # "Không có check-in nào đang chờ" was the only answer the
                # product could give. Confirming a commitment is the one moment
                # that knows a check-in is owed.
                CheckInRepository(connection).schedule(
                    CheckInRow(
                        id=str(uuid.uuid4()),
                        commitment_id=record_id,
                        scheduled_at=self._check_in_due(payload, now),
                    )
                )
                return "commitment", record_id
            case "memory":
                memory = MemoryRepository(connection)
                memory.add(
                    MemoryItemRow(
                        id=record_id,
                        content=self._text(command, payload, "content"),
                        category=payload.get("category"),
                        sensitivity=payload.get("sensitivity"),
                        user_confirmed=True,
                        # Confirmed memory persists until manual deletion.
                        expires_at=None,
                        last_used_at=None,
                    )
                )
                memory.add_provenance(
                    MemoryProvenanceRow(
                        id=str(uuid.uuid4()),
                        memory_item_id=record_id,
                        source_type="session",
                        source_id=session_id,
                        source_session_id=session_id,
                        relation="confirmed_from",
                        created_at=now,
                    )
                )
                return "memory_item", record_id
            case unknown:  # pragma: no cover — the schema closes this set
                raise ConfirmationRejected(f"unsupported record type {unknown}")

    @staticmethod
    def _text(command: ConfirmationCommand, payload: dict, field: str) -> str:
        """An edit replaces the candidate's primary text; accept keeps it."""
        if command.action is RecordAction.EDIT and command.edited_value:
            return command.edited_value
        value = payload.get(field)
        if not value:
            raise ConfirmationRejected(f"candidate payload has no {field}")
        return str(value)

    def _expiry(self, now: str) -> str:
        expires = self._as_datetime(now) + self._intent_ttl
        return expires.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _as_datetime(value: str) -> datetime:
        text = value.replace("Z", "+0000")
        for pattern in _TIMESTAMP_FORMATS:
            try:
                return datetime.strptime(text, pattern)
            except ValueError:
                continue
        raise ValueError(f"unparseable timestamp {value!r}")
