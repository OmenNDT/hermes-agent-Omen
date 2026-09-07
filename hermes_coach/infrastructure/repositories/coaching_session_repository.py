"""Coaching session repository.

Requirement families: `HC-PROCESS`, `HC-DATA-*`; sources `SRC-061`,
`SRC-076…086`.

The session row carries the current stage, which is what a restart needs to
resume where the Coachee left off.
"""

from __future__ import annotations

from hermes_coach.domain.records import CoachingSessionRow
from hermes_coach.infrastructure.repositories.base import Repository, not_in_trash


class CoachingSessionRepository(Repository):
    table = "coaching_session"
    entity_type = "coaching_session"
    row_model = CoachingSessionRow

    def start(self, session: CoachingSessionRow) -> None:
        self.insert(session)

    def get(self, session_id: str) -> CoachingSessionRow | None:
        return self.select_one(
            "entity.id = :session_id", {"session_id": session_id}
        )

    def list_recent(self, *, limit: int = 50) -> tuple[CoachingSessionRow, ...]:
        """Sessions newest first, excluding any the Coachee deleted.

        Bounded because the Journey screen is a history, not an archive: a
        Coachee two years in does not want two years of rows, and an unbounded
        read would hand the browser every session ever held.
        """
        return tuple(
            self.select(
                not_in_trash("entity"),
                self.trash_params(),
                order_by="entity.started_at DESC, entity.id DESC",
                limit=limit,
            )
        )

    def latest_open(self) -> CoachingSessionRow | None:
        """The most recent session the Coachee never finished, if any.

        A session id lives only in the browser's memory, so a reload — or a trip
        to the Goals screen and back — used to strand the session it was in.
        The rows were all still here; nothing could reach them. Thirteen of the
        sixteen sessions in one real profile read "chưa khép lại", and most were
        not abandoned on purpose, they were simply lost.

        Only the most recent one is offered. Older unfinished sessions stay
        exactly as they are: real history, honestly labelled, not resumed.

        A session with nothing said in it is not offered at all. Opening the
        screen and walking away leaves a row behind, and inviting someone back
        into an empty conversation is an interruption with nothing on the other
        side of it — three such rows already sit in one real profile.
        """
        found = self.select(
            "entity.ended_at IS NULL "
            f"AND {not_in_trash('entity')} "
            "AND EXISTS (SELECT 1 FROM session_message AS said "
            "WHERE said.session_id = entity.id)",
            self.trash_params(),
            order_by="entity.started_at DESC, entity.id DESC",
            limit=1,
        )
        return found[0] if found else None

    def set_stage(self, session_id: str, stage: str) -> None:
        self.connection.execute(
            "UPDATE coaching_session SET coaching_stage = :stage WHERE id = :session_id",
            {"stage": stage, "session_id": session_id},
        )

    def set_safety_state(self, session_id: str, safety_state: str) -> None:
        """Raise the session's safety state. Callers escalate only."""
        self.connection.execute(
            "UPDATE coaching_session SET safety_state = :safety_state "
            "WHERE id = :session_id",
            {"safety_state": safety_state, "session_id": session_id},
        )

    def close(self, session_id: str, ended_at: str) -> None:
        self.connection.execute(
            "UPDATE coaching_session SET ended_at = :ended_at WHERE id = :session_id",
            {"ended_at": ended_at, "session_id": session_id},
        )
