"""What the Coachee has actually been through.

Requirement families: `HC-PROCESS`, `HC-RECORDS`; sources `SRC-061`,
`SRC-076…086`.

A list of dates would be an activity log, and this product does not need one.
What makes a history worth opening is what each session *left behind* — the
goal it produced, the thing the Coachee realised, the promise they made — so
every entry carries those counts, and a session that produced nothing says so
rather than looking identical to one that produced three records.

The honest edge is the transcript. Session rows are durable; the messages in
them expire on the retention window and are purged. So an old entry can be real
and still have nothing left to read, and the entry says which — a screen that
offered to open an empty transcript would be promising the Coachee their own
words back and then not having them.

That claim has to be earned, though. A session with no messages is usually not
a session whose words expired: it is one where nothing was ever said — opened
and abandoned before the first turn. Telling a Coachee their transcript was
lost when it never existed is a false alarm about their own data, so both
counts travel and only a session that *had* messages and now has none is
described as having lost them.
"""

from __future__ import annotations

from hermes_coach.domain.records import CoachingSessionRow
from hermes_coach.infrastructure.repositories.base import not_expired, not_in_trash
from hermes_coach.infrastructure.repositories.coaching_session_repository import (
    CoachingSessionRepository,
)
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


# What a session produced, by table. Each row hangs off `source_session_id`, so
# the count is "what this hour of work is still standing behind", not "what
# exists".
_PRODUCED = (
    ("goals", "goal"),
    ("insights", "insight"),
    ("commitments", "commitment"),
)

DEFAULT_LIMIT = 50


class JourneyService:
    def __init__(self, database: CoachDatabase) -> None:
        self._database = database

    def recent(self, *, now: str, limit: int = DEFAULT_LIMIT) -> tuple[dict, ...]:
        connection = self._database.connection
        sessions = CoachingSessionRepository(connection).list_recent(limit=limit)
        return tuple(self._entry(session, now=now) for session in sessions)

    def _entry(self, session: CoachingSessionRow, *, now: str) -> dict:
        return {
            "id": session.id,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "intention": session.intention,
            # The stage it reached, whether or not it closed. A session
            # abandoned at Reality is not a failure and is not hidden.
            "stage": session.coaching_stage,
            "ended": session.ended_at is not None,
            "safety_state": session.safety_state or "normal",
            "produced": {
                name: self._count(table, session.id) for name, table in _PRODUCED
            },
            # Messages outlive nothing: they expire and are purged, while this
            # row is durable. `messages_ever` is what separates "nothing was
            # said here" from "what was said is gone".
            "messages": self._messages(session.id, now=now),
            "messages_ever": self._messages(session.id, now=None),
        }

    def _count(self, table: str, session_id: str) -> int:
        row = self._database.connection.execute(
            f"SELECT COUNT(*) AS n FROM {table} AS entity "
            f"WHERE entity.source_session_id = :session_id "
            f"AND {not_in_trash('entity')}",
            {"session_id": session_id, "trash_entity_type": table},
        ).fetchone()
        return row["n"]

    def _messages(self, session_id: str, *, now: str | None) -> int:
        """Live lines, or every line ever written when `now` is None.

        Once the retention sweep has actually deleted the rows both counts read
        zero, and the entry falls back to saying nothing rather than guessing.
        Silence is the right failure here: claiming a loss we cannot see would
        be worse than not mentioning one we can no longer prove.
        """
        window = "" if now is None else f"AND {not_expired('entity')} "
        row = self._database.connection.execute(
            "SELECT COUNT(*) AS n FROM session_message AS entity "
            "WHERE entity.session_id = :session_id "
            f"{window}AND {not_in_trash('entity')}",
            {
                "session_id": session_id,
                "now": now or "",
                "trash_entity_type": "session_message",
            },
        ).fetchone()
        return row["n"]
