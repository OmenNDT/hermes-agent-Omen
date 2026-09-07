"""Retention sweep.

Requirement families: `HC-PRIVACY`, `HC-MEMORY`, `HC-DATA-*`; sources `SRC-063`,
`SRC-068`, `SRC-076…086`, `SRC-091`.

Temporary data — pending candidates, technical logs and notification history —
is purged at 90 days. Open Trash is purged at 30. Durable structured records
never expire by age; they leave only through the Trash lifecycle.

The transcript used to be on that 90-day clock and no longer is. It was the one
class where the rule did harm: the conclusions drawn from a conversation lived
forever while the conversation itself was deleted from under the person who had
it. It now leaves the same way every durable record does — because the Coachee
deleted it. The lifecycle contract's retention kinds are confirmed memory,
pending candidates and Trash entries; transcript was never among them.

This is a Coach lifecycle service, not a user-visible cron job: it runs at
startup before any context or model call, then periodically. The clock is
injected, the sweep is idempotent, and a restart catches deadlines that passed
while the app was closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from hermes_coach.application.trash_service import PurgeReason, TrashService
from hermes_coach.domain.clock import shift
from hermes_coach.infrastructure.repositories.trash_repository import TrashRepository
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


TEMPORARY_DATA_WINDOW = timedelta(days=90)
TRASH_WINDOW = timedelta(days=30)

# Internal tables with no canonical expiry column: age is measured from
# created_at against the same 90-day window.
_AGE_BASED_TABLES = ("internal_technical_log", "internal_notification_history")


@dataclass
class RetentionOutcome:
    purged: dict[str, int] = field(default_factory=dict)

    @property
    def total_purged(self) -> int:
        return sum(self.purged.values())

    def record(self, table: str, removed: int) -> None:
        if removed:
            self.purged[table] = self.purged.get(table, 0) + removed


class RetentionService:
    def __init__(
        self,
        database: CoachDatabase,
        *,
        temporary_window: timedelta = TEMPORARY_DATA_WINDOW,
    ) -> None:
        # The sweep is profile-wide: a due Trash entry carries its own owner.
        self._database = database
        self._temporary_window = temporary_window

    def run(self, *, now: str) -> RetentionOutcome:
        """Purge everything whose deadline has passed.

        Two atomicity scopes, not one. The temporary-data classes go in a single
        transaction, so that deadline is never half-enforced. Each due Trash
        entity then gets its own transaction, because its dependent rows and its
        audit row must commit together and `TrashService` owns that boundary —
        one giant transaction would also hold a write lock across every purge.

        A crash between the two leaves temporary data gone and some Trash still
        pending, which the next run finishes.
        """
        outcome = RetentionOutcome()
        cutoff = shift(now, -self._temporary_window)

        with self._database.transaction():
            outcome.record(
                "session_message", self._purge_expired_messages(now)
            )
            outcome.record(
                "candidate_record", self._purge_expired_candidates(now, cutoff)
            )
            for table in _AGE_BASED_TABLES:
                outcome.record(table, self._purge_by_age(table, cutoff))

        outcome.record("trash_entry", self._purge_due_trash(now))
        return outcome

    def _purge_expired_messages(self, now: str) -> int:
        """Transcript that still carries a deadline, once it has passed.

        A NULL expiry is durable, exactly as it is everywhere else in this
        schema. This used to read the other way — NULL meant "fall back to
        creation age", written to stop a careless writer creating immortal
        transcript — and that fallback is precisely what would now delete the
        lines the product deliberately keeps. Migration 0006 clears the
        deadlines already written; this stops new ones being enforced.
        """
        cursor = self._database.connection.execute(
            "DELETE FROM session_message "
            "WHERE expires_at IS NOT NULL AND expires_at <= :now",
            {"now": now},
        )
        return cursor.rowcount

    def _purge_expired_candidates(self, now: str, cutoff: str) -> int:
        """Only pending candidates are temporary; a resolved one is history."""
        cursor = self._database.connection.execute(
            "DELETE FROM candidate_record WHERE status = 'pending' AND "
            "((expires_at IS NOT NULL AND expires_at <= :now) "
            "OR (expires_at IS NULL AND created_at <= :cutoff))",
            {"now": now, "cutoff": cutoff},
        )
        return cursor.rowcount

    def _purge_by_age(self, table: str, cutoff: str) -> int:
        cursor = self._database.connection.execute(
            f"DELETE FROM {table} WHERE created_at <= :cutoff", {"cutoff": cutoff}
        )
        return cursor.rowcount

    def _purge_due_trash(self, now: str) -> int:
        """Erase Trash entries whose 30 days elapsed without a restore.

        Each entity is purged through `TrashService`, which owns dependency
        order and writes the payload-free audit evidence.
        """
        due = TrashRepository(self._database.connection).due_for_purge(now)
        for entry in due:
            TrashService(self._database, profile_id=entry.profile_id).purge(
                entry.entity_type,
                entry.entity_id,
                now=now,
                reason=PurgeReason.RETENTION,
            )
        return len(due)
