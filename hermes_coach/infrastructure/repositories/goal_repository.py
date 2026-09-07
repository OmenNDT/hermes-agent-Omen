"""Goal repository.

Requirement families: `HC-DATA-GOAL`, `HC-RECORDS`; sources `SRC-054…057`,
`SRC-076…086`.
"""

from __future__ import annotations

from hermes_coach.domain.records import GoalRow
from hermes_coach.infrastructure.repositories.base import Repository, not_in_trash


# draft is a candidate shape, not structured truth; achieved and abandoned are
# closed. Only live goals belong in an active list.
LIVE_STATUSES = ("active", "paused")


class GoalRepository(Repository):
    table = "goal"
    entity_type = "goal"
    row_model = GoalRow

    def add(self, goal: GoalRow) -> None:
        self.insert(goal)

    def get(self, goal_id: str) -> GoalRow | None:
        return self.select_one(
            f"entity.id = :goal_id AND {not_in_trash('entity')}",
            {"goal_id": goal_id, **self.trash_params()},
        )

    def list_active(self, profile_id: str) -> tuple[GoalRow, ...]:
        placeholders = ", ".join(f":status_{index}" for index in range(len(LIVE_STATUSES)))
        params = {
            "profile_id": profile_id,
            **{f"status_{index}": status for index, status in enumerate(LIVE_STATUSES)},
            **self.trash_params(),
        }
        return tuple(
            self.select(
                "entity.profile_id = :profile_id "
                f"AND entity.status IN ({placeholders}) "
                "AND entity.confirmed_at IS NOT NULL "
                f"AND {not_in_trash('entity')}",
                params,
                order_by="entity.created_at, entity.id",
            )
        )
