"""Career snapshot repository.

Requirement families: `HC-DATA-*`, `HC-METRICS`; sources `SRC-076…086`.

Snapshots are append-only so change over time stays visible. This repository
exposes no update or delete on purpose: rewriting a past snapshot would erase
the very history it exists to show.
"""

from __future__ import annotations

from hermes_coach.domain.records import CareerSnapshotRow
from hermes_coach.infrastructure.repositories.base import Repository


class CareerSnapshotRepository(Repository):
    table = "career_snapshot"
    entity_type = "career_snapshot"
    row_model = CareerSnapshotRow

    def add(self, snapshot: CareerSnapshotRow) -> None:
        self.insert(snapshot)

    def history(self, profile_id: str) -> tuple[CareerSnapshotRow, ...]:
        """Oldest first — the ordering a trend is read in."""
        return tuple(
            self.select(
                "entity.profile_id = :profile_id",
                {"profile_id": profile_id},
                order_by="entity.captured_at, entity.id",
            )
        )

    def latest(self, profile_id: str) -> CareerSnapshotRow | None:
        history = self.history(profile_id)
        return history[-1] if history else None
