"""Durable confirmation intents and audit trail.

Requirement families: `HC-RECORDS`, `HC-PRIVACY`; sources `SRC-054…059`,
`SRC-079`, `SRC-080`, `SRC-084`, `SRC-085`.

Both tables are internal machinery holding ids, digests and timestamps. No
record content is written here, so the audit trail stays readable without
exposing what a Coachee said.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from hermes_coach.domain.records import ConfirmationAuditRow


def token_digest(token: str) -> str:
    """Intents are stored hashed; the raw token never touches the database."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredIntent:
    token_digest: str
    local_user_id: str
    session_id: str
    candidate_id: str
    action: str
    edited_payload_digest: str
    issued_at: str
    expires_at: str
    consumed_at: str | None


class ConfirmationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def supersede_live_intents(self, candidate_id: str, now: str) -> None:
        """Retire any unconsumed intent for this candidate.

        Marking it consumed rather than deleting it keeps the single-live-intent
        index honest and leaves the retired token unusable.
        """
        self.connection.execute(
            "UPDATE internal_confirmation_intent SET consumed_at = :now "
            "WHERE candidate_id = :candidate_id AND consumed_at IS NULL",
            {"now": now, "candidate_id": candidate_id},
        )

    def issue(self, intent: StoredIntent) -> None:
        self.connection.execute(
            "INSERT INTO internal_confirmation_intent "
            "(token_digest, local_user_id, session_id, candidate_id, action, "
            "edited_payload_digest, issued_at, expires_at, consumed_at) "
            "VALUES (:token_digest, :local_user_id, :session_id, :candidate_id, "
            ":action, :edited_payload_digest, :issued_at, :expires_at, :consumed_at)",
            intent.__dict__,
        )

    def live_intent(self, digest: str) -> StoredIntent | None:
        row = self.connection.execute(
            "SELECT * FROM internal_confirmation_intent "
            "WHERE token_digest = :digest AND consumed_at IS NULL",
            {"digest": digest},
        ).fetchone()
        return StoredIntent(**dict(row)) if row else None

    def consume(self, digest: str, now: str) -> bool:
        """Compare-and-set: only the first caller to consume wins."""
        cursor = self.connection.execute(
            "UPDATE internal_confirmation_intent SET consumed_at = :now "
            "WHERE token_digest = :digest AND consumed_at IS NULL",
            {"now": now, "digest": digest},
        )
        return cursor.rowcount == 1

    def purge_expired(self, now: str) -> int:
        cursor = self.connection.execute(
            "DELETE FROM internal_confirmation_intent WHERE expires_at <= :now",
            {"now": now},
        )
        return cursor.rowcount

    def next_revision(self, candidate_id: str) -> int:
        row = self.connection.execute(
            "SELECT MAX(revision) AS current FROM internal_confirmation_audit "
            "WHERE candidate_id = :candidate_id",
            {"candidate_id": candidate_id},
        ).fetchone()
        return (row["current"] or 0) + 1

    def record(self, entry: ConfirmationAuditRow) -> None:
        values = entry.model_dump()
        columns = ", ".join(values)
        placeholders = ", ".join(f":{name}" for name in values)
        self.connection.execute(
            f"INSERT INTO internal_confirmation_audit ({columns}) "
            f"VALUES ({placeholders})",
            values,
        )

    def trail(self, candidate_id: str) -> tuple[ConfirmationAuditRow, ...]:
        rows = self.connection.execute(
            "SELECT * FROM internal_confirmation_audit "
            "WHERE candidate_id = :candidate_id ORDER BY revision",
            {"candidate_id": candidate_id},
        ).fetchall()
        return tuple(ConfirmationAuditRow.model_validate(dict(row)) for row in rows)

    def command_was_applied(self, command_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM internal_confirmation_audit WHERE command_id = :command_id",
            {"command_id": command_id},
        ).fetchone()
        return row is not None
