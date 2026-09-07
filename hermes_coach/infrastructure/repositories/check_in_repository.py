"""Check-in repository.

Requirement families: `HC-CHECKIN`, `HC-DATA-*`; sources `SRC-083`, `SRC-084`.

Scheduling and delivery belong to Phase 6. What this owns is the row, so a
restart can see which check-ins are still outstanding.
"""

from __future__ import annotations

from hermes_coach.domain.records import CheckInRow
from hermes_coach.infrastructure.repositories.base import Repository, not_in_trash


class CheckInRepository(Repository):
    table = "check_in"
    entity_type = "check_in"
    row_model = CheckInRow

    def schedule(self, check_in: CheckInRow) -> None:
        self.insert(check_in)

    def get(self, check_in_id: str) -> CheckInRow | None:
        return self.select_one(
            f"entity.id = :check_in_id AND {not_in_trash('entity')}",
            {"check_in_id": check_in_id, **self.trash_params()},
        )

    def pending(self) -> tuple[CheckInRow, ...]:
        """Outstanding check-ins: scheduled, not completed, not deleted.

        A deleted commitment's check-in must not resurface, so the Trash
        exclusion applies to the parent as well as to the check-in itself.
        """
        return tuple(
            self.select(
                "entity.completed_at IS NULL "
                f"AND {not_in_trash('entity')} "
                "AND NOT EXISTS (SELECT 1 FROM trash_entry AS parent_trash "
                "WHERE parent_trash.entity_type = 'commitment' "
                "AND parent_trash.entity_id = entity.commitment_id "
                "AND parent_trash.restored_at IS NULL)",
                self.trash_params(),
                order_by="entity.scheduled_at, entity.id",
            )
        )
