"""Commitment repository.

Requirement families: `HC-RECORDS`, `HC-DATA-GOAL`; sources `SRC-054…057`.

A commitment always hangs off a goal: the schema enforces the foreign key, so a
confirmation that cannot name its goal fails rather than creating an orphan.
"""

from __future__ import annotations

from hermes_coach.domain.records import CommitmentRow
from hermes_coach.infrastructure.repositories.base import Repository, not_in_trash


class CommitmentRepository(Repository):
    table = "commitment"
    entity_type = "commitment"
    row_model = CommitmentRow

    def add(self, commitment: CommitmentRow) -> None:
        self.insert(commitment)

    def get(self, commitment_id: str) -> CommitmentRow | None:
        return self.select_one(
            f"entity.id = :commitment_id AND {not_in_trash('entity')}",
            {"commitment_id": commitment_id, **self.trash_params()},
        )

    def list_for_goal(self, goal_id: str) -> tuple[CommitmentRow, ...]:
        return tuple(
            self.select(
                f"entity.goal_id = :goal_id AND {not_in_trash('entity')}",
                {"goal_id": goal_id, **self.trash_params()},
                order_by="entity.due_at, entity.id",
            )
        )
