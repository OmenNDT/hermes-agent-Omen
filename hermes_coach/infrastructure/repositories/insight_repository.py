"""Insight repository.

Requirement families: `HC-RECORDS`, `HC-DATA-*`; sources `SRC-054…057`.
"""

from __future__ import annotations

from hermes_coach.domain.records import InsightRow
from hermes_coach.infrastructure.repositories.base import Repository, not_in_trash


class InsightRepository(Repository):
    table = "insight"
    entity_type = "insight"
    row_model = InsightRow

    def add(self, insight: InsightRow) -> None:
        self.insert(insight)

    def get(self, insight_id: str) -> InsightRow | None:
        return self.select_one(
            f"entity.id = :insight_id AND {not_in_trash('entity')}",
            {"insight_id": insight_id, **self.trash_params()},
        )

    def list_for_goal(self, goal_id: str) -> tuple[InsightRow, ...]:
        """Confirmed insights linked to one goal; another goal's are unrelated."""
        return tuple(
            self.select(
                "entity.goal_id = :goal_id AND entity.confirmed_at IS NOT NULL "
                f"AND {not_in_trash('entity')}",
                {"goal_id": goal_id, **self.trash_params()},
                order_by="entity.id",
            )
        )

    def list_active(self) -> tuple[InsightRow, ...]:
        return tuple(
            self.select(
                not_in_trash("entity"), self.trash_params(), order_by="entity.id"
            )
        )
