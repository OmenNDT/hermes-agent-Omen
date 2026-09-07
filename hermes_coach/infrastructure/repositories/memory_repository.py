"""Approved-memory repository with append-only provenance.

Requirement families: `HC-MEMORY`, `HC-DATA-*`; sources `SRC-063`, `SRC-068`,
`SRC-076…086`.

Only confirmed memory is approved for reuse. Confirmed memory has no automatic
expiry and is excluded from age-based retention; it leaves only through the
Trash lifecycle. Provenance is append-only and one memory may cite several
sources.
"""

from __future__ import annotations

from hermes_coach.domain.records import MemoryItemRow, MemoryProvenanceRow
from hermes_coach.infrastructure.repositories.base import (
    Repository,
    not_expired,
    not_in_trash,
)


class MemoryRepository(Repository):
    table = "memory_item"
    entity_type = "memory_item"
    row_model = MemoryItemRow

    def add(self, memory: MemoryItemRow) -> None:
        self.insert(memory)

    def get(self, memory_id: str, *, now: str | None = None) -> MemoryItemRow | None:
        return self.select_one(
            f"entity.id = :memory_id AND entity.user_confirmed = 1 "
            f"AND {not_expired('entity')} AND {not_in_trash('entity')}",
            {"memory_id": memory_id, "now": now or "", **self.trash_params()},
        )

    def list_active(self, *, now: str | None = None) -> tuple[MemoryItemRow, ...]:
        return tuple(
            self.select(
                f"entity.user_confirmed = 1 AND {not_expired('entity')} "
                f"AND {not_in_trash('entity')}",
                {"now": now or "", **self.trash_params()},
                order_by="entity.id",
            )
        )

    def add_provenance(self, provenance: MemoryProvenanceRow) -> None:
        values = provenance.model_dump()
        columns = ", ".join(values)
        placeholders = ", ".join(f":{name}" for name in values)
        self.connection.execute(
            f"INSERT INTO memory_provenance ({columns}) VALUES ({placeholders})",
            values,
        )

    def provenance_for(self, memory_id: str) -> tuple[MemoryProvenanceRow, ...]:
        rows = self.connection.execute(
            "SELECT * FROM memory_provenance WHERE memory_item_id = :memory_id "
            "ORDER BY created_at, id",
            {"memory_id": memory_id},
        ).fetchall()
        return tuple(MemoryProvenanceRow.model_validate(dict(row)) for row in rows)
