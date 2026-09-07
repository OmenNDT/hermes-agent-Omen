"""Session transcript repository.

Requirement families: `HC-DATA-*`, `HC-MEMORY`, `HC-PRIVACY`; sources
`SRC-076…086`.

Transcript is kept until the Coachee deletes it. Rows are written with a NULL
expiry, which is this schema's word for durable, and leave through the Trash
lifecycle like every other record they own.

It was temporary data on a 90-day clock until 31/08/2026. That rule deleted a
Coachee's own words out from under them while the conclusions drawn from those
words lived on: the record said "you decided X" and the only thing that could
ever show why was gone.

The expiry filter stays in the active reads regardless. A row that does carry a
deadline — legacy data, or something a future caller deliberately stamps — must
still drop out of reads the moment it passes, before any sweep gets to it.
"""

from __future__ import annotations

from hermes_coach.domain.records import SessionMessageRow
from hermes_coach.infrastructure.repositories.base import (
    Repository,
    not_expired,
    not_in_trash,
)


class SessionMessageRepository(Repository):
    table = "session_message"
    entity_type = "session_message"
    row_model = SessionMessageRow

    def add(self, message: SessionMessageRow) -> None:
        self.insert(message)

    def next_sequence(self, session_id: str) -> int:
        """The next free slot, counting purged rows as used.

        MAX+1 rather than a count: retention deletes expired transcript, and
        reusing a freed number would collide with the unique sequence index and
        make the ledger look reordered.
        """
        row = self.connection.execute(
            "SELECT MAX(sequence_no) AS highest FROM session_message "
            "WHERE session_id = :session_id",
            {"session_id": session_id},
        ).fetchone()
        highest = row["highest"]
        return 0 if highest is None else highest + 1

    def get(self, message_id: str, *, now: str | None = None) -> SessionMessageRow | None:
        return self.select_one(
            f"entity.id = :message_id AND entity.deleted_at IS NULL "
            f"AND {not_expired('entity')} AND {not_in_trash('entity')}",
            {"message_id": message_id, "now": now or "", **self.trash_params()},
        )

    def list_active(
        self, session_id: str, *, now: str | None = None
    ) -> tuple[SessionMessageRow, ...]:
        return tuple(
            self.select(
                "entity.session_id = :session_id AND entity.deleted_at IS NULL "
                f"AND {not_expired('entity')} AND {not_in_trash('entity')}",
                {
                    "session_id": session_id,
                    "now": now or "",
                    **self.trash_params(),
                },
                order_by="entity.sequence_no",
            )
        )
