"""Trash repository — the canonical deletion marker.

Requirement families: `HC-PRIVACY`, `HC-RECORDS`; sources `SRC-058`, `SRC-092`,
`SRC-076…086`.

Soft delete writes an open `trash_entry`; nothing else marks an entity deleted,
which is why no repository needed an ad-hoc deletion column. The caller owns the
transaction, so the marker and any status change commit together or not at all.
"""

from __future__ import annotations

from hermes_coach.domain.records import TrashEntryRow
from hermes_coach.infrastructure.repositories.base import Repository


class TrashRepository(Repository):
    table = "trash_entry"
    entity_type = "trash_entry"
    row_model = TrashEntryRow

    def soft_delete(self, entry: TrashEntryRow) -> str:
        """Open a Trash entry. The partial unique index refuses a second one."""
        self.insert(entry)
        return entry.id

    def open_entry(self, entity_type: str, entity_id: str) -> TrashEntryRow | None:
        return self.select_one(
            "entity.entity_type = :entity_type AND entity.entity_id = :entity_id "
            "AND entity.restored_at IS NULL AND entity.purged_at IS NULL",
            {"entity_type": entity_type, "entity_id": entity_id},
        )

    def open_entries(self) -> tuple[TrashEntryRow, ...]:
        """Everything currently in the Trash, soonest to be purged first.

        The Privacy Center needs this to show the Coachee what deletion actually
        did: an item they can still get back, and the date after which they
        cannot. Without it, "deleted" is a claim they have to take on trust.
        """
        return tuple(
            self.select(
                "entity.restored_at IS NULL AND entity.purged_at IS NULL",
                {},
                order_by="entity.purge_after, entity.id",
            )
        )

    def restore(self, entity_type: str, entity_id: str, restored_at: str) -> None:
        """Restore cancels the pending purge and makes the entity active again."""
        self.connection.execute(
            "UPDATE trash_entry SET restored_at = :restored_at "
            "WHERE entity_type = :entity_type AND entity_id = :entity_id "
            "AND restored_at IS NULL AND purged_at IS NULL",
            {
                "restored_at": restored_at,
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )

    def mark_purged(self, entity_type: str, entity_id: str, purged_at: str) -> None:
        """Record that the payload was permanently deleted.

        The entry stays un-restored so the entity remains hidden; the audit
        evidence it leaves behind carries no deleted content.
        """
        self.connection.execute(
            "UPDATE trash_entry SET purged_at = :purged_at "
            "WHERE entity_type = :entity_type AND entity_id = :entity_id "
            "AND restored_at IS NULL AND purged_at IS NULL",
            {
                "purged_at": purged_at,
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )

    def due_for_purge(self, now: str) -> tuple[TrashEntryRow, ...]:
        return tuple(
            self.select(
                "entity.restored_at IS NULL AND entity.purged_at IS NULL "
                "AND entity.purge_after <= :now",
                {"now": now},
                order_by="entity.purge_after, entity.id",
            )
        )
