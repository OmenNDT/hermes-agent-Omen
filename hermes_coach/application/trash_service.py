"""Trash lifecycle: soft delete, restore, permanent purge.

Requirement families: `HC-PRIVACY`, `HC-RECORDS`; sources `SRC-058`, `SRC-092`,
`SRC-076…086`.

Deleting is reversible by default. Permanent purge is a separate step that
removes dependents in dependency order and writes payload-free audit evidence.
Every operation is per item — there is no method that deletes or restores a
set, because a bulk undo cannot be reasoned about after the fact.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from hermes_coach.domain.clock import shift
from hermes_coach.domain.records import TrashEntryRow
from hermes_coach.infrastructure.repositories.trash_repository import TrashRepository
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


class PurgeReason(StrEnum):
    USER_CONFIRMED = "user_confirmed"
    RETENTION = "retention"


class RestoreBlocked(RuntimeError):
    """The item cannot be restored or purged in its current state."""


@dataclass(frozen=True)
class PurgePlan:
    """How to erase one entity type completely.

    `dependents` runs first, deepest child first, so a foreign key never blocks
    the parent delete. `detach` clears optional references from records that
    outlive the parent instead of deleting them.
    """

    table: str
    dependents: tuple[str, ...] = ()
    detach: tuple[str, ...] = ()
    parent: tuple[str, str, str] | None = None


# Statements are parameterised on :entity_id throughout.
PURGE_PLANS: dict[str, PurgePlan] = {
    "goal": PurgePlan(
        table="goal",
        dependents=(
            "DELETE FROM evidence WHERE commitment_id IN "
            "(SELECT id FROM commitment WHERE goal_id = :entity_id)",
            "DELETE FROM check_in WHERE commitment_id IN "
            "(SELECT id FROM commitment WHERE goal_id = :entity_id)",
            "DELETE FROM commitment WHERE goal_id = :entity_id",
        ),
        detach=("UPDATE insight SET goal_id = NULL WHERE goal_id = :entity_id",),
    ),
    "commitment": PurgePlan(
        table="commitment",
        dependents=(
            "DELETE FROM evidence WHERE commitment_id = :entity_id",
            "DELETE FROM check_in WHERE commitment_id = :entity_id",
        ),
        parent=("goal", "goal_id", "commitment"),
    ),
    "insight": PurgePlan(table="insight"),
    "memory_item": PurgePlan(
        table="memory_item",
        dependents=("DELETE FROM memory_provenance WHERE memory_item_id = :entity_id",),
    ),
    "session_message": PurgePlan(
        table="session_message",
        detach=(
            "UPDATE candidate_record SET source_message_id = NULL "
            "WHERE source_message_id = :entity_id",
            "UPDATE gate_confirmation SET closing_question_message_id = NULL "
            "WHERE closing_question_message_id = :entity_id",
            "UPDATE gate_confirmation SET response_message_id = NULL "
            "WHERE response_message_id = :entity_id",
            "UPDATE memory_provenance SET source_message_id = NULL "
            "WHERE source_message_id = :entity_id",
        ),
    ),
    "candidate_record": PurgePlan(table="candidate_record"),
}


class TrashService:
    def __init__(
        self, database: CoachDatabase, *, profile_id: str, window=None
    ) -> None:
        from hermes_coach.application.retention_service import TRASH_WINDOW

        self._database = database
        self._profile_id = profile_id
        self._window = window or TRASH_WINDOW

    def soft_delete(self, entity_type: str, entity_id: str, *, now: str) -> str:
        """Mark the entity deleted and schedule its purge, in one transaction."""
        plan = self._plan(entity_type)
        entry = TrashEntryRow(
            id=str(uuid.uuid4()),
            profile_id=self._profile_id,
            entity_type=entity_type,
            entity_id=entity_id,
            deleted_at=now,
            purge_after=shift(now, self._window),
            deletion_source="item",
        )
        with self._database.transaction():
            self._repository().soft_delete(entry)
            self._mark_deleted_column(plan, entity_id, now)
        return entry.id

    def restore(self, entity_type: str, entity_id: str, *, now: str) -> None:
        """Restore one item, refusing if a parent it needs is already gone."""
        plan = self._plan(entity_type)
        with self._database.transaction():
            self._require_open_entry(entity_type, entity_id)
            self._require_surviving_parent(plan, entity_id)
            self._repository().restore(entity_type, entity_id, now)
            self._mark_deleted_column(plan, entity_id, None)

    def purge(
        self,
        entity_type: str,
        entity_id: str,
        *,
        now: str,
        reason: PurgeReason,
        control_id: str | None = None,
    ) -> None:
        """Erase the entity for good.

        A user-initiated purge needs a trusted UI control; the 30-day retention
        sweep does not, because the Coachee already confirmed the deletion when
        the item went to the Trash.
        """
        if reason is PurgeReason.USER_CONFIRMED and not (control_id or "").strip():
            raise ValueError("permanent purge needs a confirmed UI control id")

        plan = self._plan(entity_type)
        connection = self._database.connection
        parameters = {"entity_id": entity_id}

        with self._database.transaction():
            self._require_open_entry(entity_type, entity_id)

            removed = 0
            for statement in plan.detach:
                connection.execute(statement, parameters)
            for statement in plan.dependents:
                removed += connection.execute(statement, parameters).rowcount
            connection.execute(
                f"DELETE FROM {plan.table} WHERE id = :entity_id", parameters
            )

            self._repository().mark_purged(entity_type, entity_id, now)
            connection.execute(
                "INSERT INTO internal_purge_audit "
                "(id, entity_type, entity_id, reason, control_id, "
                "dependents_removed, purged_at) "
                "VALUES (:id, :entity_type, :entity_id, :reason, :control_id, "
                ":dependents_removed, :purged_at)",
                {
                    "id": str(uuid.uuid4()),
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "reason": reason.value,
                    "control_id": control_id,
                    "dependents_removed": removed,
                    "purged_at": now,
                },
            )

    @staticmethod
    def _plan(entity_type: str) -> PurgePlan:
        plan = PURGE_PLANS.get(entity_type)
        if plan is None:
            raise ValueError(f"unsupported entity type for Trash: {entity_type}")
        return plan

    def _require_open_entry(self, entity_type: str, entity_id: str) -> None:
        if self._repository().open_entry(entity_type, entity_id) is None:
            raise RestoreBlocked(
                f"no open Trash entry for {entity_type} {entity_id}"
            )

    def _require_surviving_parent(self, plan: PurgePlan, entity_id: str) -> None:
        if plan.parent is None:
            return
        parent_table, foreign_key, child_table = plan.parent
        row = self._database.connection.execute(
            f"SELECT 1 FROM {child_table} AS child "
            f"JOIN {parent_table} AS parent ON parent.id = child.{foreign_key} "
            "WHERE child.id = :entity_id",
            {"entity_id": entity_id},
        ).fetchone()
        if row is None:
            raise RestoreBlocked(
                f"cannot restore: its {parent_table} no longer exists"
            )

    def _mark_deleted_column(
        self, plan: PurgePlan, entity_id: str, value: str | None
    ) -> None:
        """Set `deleted_at` only where the canonical schema already has it.

        The Trash entry is the deletion marker; this mirrors it for the one
        table that carries the column, and adds no ad-hoc columns elsewhere.
        """
        if plan.table != "session_message":
            return
        self._database.connection.execute(
            "UPDATE session_message SET deleted_at = :value WHERE id = :entity_id",
            {"value": value, "entity_id": entity_id},
        )

    def _repository(self) -> TrashRepository:
        return TrashRepository(self._database.connection)
