"""Append-only consent evidence.

Requirement families: `HC-PRIVACY`; sources `SRC-026`, `SRC-091`, `SRC-092`.

There is no update or delete here on purpose: consent history is evidence, and
a withdrawal is a new event rather than the erasure of an earlier grant.
"""

from __future__ import annotations

from hermes_coach.domain.records import ConsentEventRow
from hermes_coach.infrastructure.repositories.base import Repository


class ConsentRepository(Repository):
    table = "consent_event"
    entity_type = "consent_event"
    row_model = ConsentEventRow

    def append(self, event: ConsentEventRow) -> None:
        self.insert(event)

    def history(
        self, profile_id: str, consent_type: str, scope_json: str
    ) -> tuple[ConsentEventRow, ...]:
        """Oldest first. `consent_type` and `scope_json` arrive normalized."""
        return tuple(
            self.select(
                "entity.profile_id = :profile_id "
                "AND entity.consent_type = :consent_type "
                "AND entity.scope_json = :scope_json",
                {
                    "profile_id": profile_id,
                    "consent_type": consent_type,
                    "scope_json": scope_json,
                },
                order_by="entity.created_at, entity.id",
            )
        )

    def all_for_profile(self, profile_id: str) -> tuple[ConsentEventRow, ...]:
        """Every event for the profile, for export and audit review."""
        return tuple(
            self.select(
                "entity.profile_id = :profile_id",
                {"profile_id": profile_id},
                order_by="entity.created_at, entity.id",
            )
        )

    def latest(
        self, profile_id: str, consent_type: str, scope_json: str
    ) -> ConsentEventRow | None:
        events = self.history(profile_id, consent_type, scope_json)
        return events[-1] if events else None
