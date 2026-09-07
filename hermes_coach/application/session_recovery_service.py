"""Rebuild a session after a restart.

Requirement families: `HC-PROCESS`, `HC-DATA-*`, `HC-CHECKIN`; sources
`SRC-061`, `SRC-081`, `SRC-082`, `SRC-076…086`.

SQLite is the structured truth, so recovery is a read, not a repair: everything
below comes from committed rows through the same repositories the live app uses.
Two consequences matter. A half-written turn was never committed and therefore
never comes back, and a deletion the Coachee already made stays made — recovery
goes through the active scope like every other read.

This does not resume the session on its own. The proposal requires an explicit
non-automatic resume path, so this hands back the state and stops.
"""

from __future__ import annotations

from dataclasses import dataclass

from hermes_coach.contracts.runtime_contract import CoachingStage
from hermes_coach.domain.records import (
    CheckInRow,
    CoachingSessionRow,
    GateConfirmationRow,
    GoalRow,
    InsightRow,
    MemoryItemRow,
    MemoryProvenanceRow,
    SessionMessageRow,
)
from hermes_coach.infrastructure.repositories.check_in_repository import (
    CheckInRepository,
)
from hermes_coach.infrastructure.repositories.coaching_session_repository import (
    CoachingSessionRepository,
)
from hermes_coach.infrastructure.repositories.gate_repository import GateRepository
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.insight_repository import (
    InsightRepository,
)
from hermes_coach.infrastructure.repositories.memory_repository import MemoryRepository
from hermes_coach.infrastructure.repositories.session_message_repository import (
    SessionMessageRepository,
)
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


@dataclass(frozen=True)
class RecoveredSession:
    session: CoachingSessionRow | None = None
    current_stage: CoachingStage | None = None
    gate_history: tuple[GateConfirmationRow, ...] = ()
    confirmed_steps: tuple[str, ...] = ()
    goals: tuple[GoalRow, ...] = ()
    insights: tuple[InsightRow, ...] = ()
    memories: tuple[MemoryItemRow, ...] = ()
    provenance: tuple[MemoryProvenanceRow, ...] = ()
    messages: tuple[SessionMessageRow, ...] = ()
    pending_check_ins: tuple[CheckInRow, ...] = ()

    def is_step_confirmed(self, step: str) -> bool:
        return step in self.confirmed_steps


class SessionRecoveryService:
    def __init__(self, database: CoachDatabase, *, profile_id: str) -> None:
        self._database = database
        self._profile_id = profile_id

    def recover(self, session_id: str, *, now: str | None = None) -> RecoveredSession:
        connection = self._database.connection
        session = CoachingSessionRepository(connection).get(session_id)
        if session is None:
            # An unknown session is an empty state, not a failure: the caller
            # may be opening a profile whose session was purged by retention.
            return RecoveredSession()

        gates = GateRepository(connection)
        memory = MemoryRepository(connection)
        memories = memory.list_active(now=now)

        return RecoveredSession(
            session=session,
            current_stage=CoachingStage(session.coaching_stage),
            gate_history=gates.history(session_id),
            confirmed_steps=gates.confirmed_steps(session_id),
            goals=GoalRepository(connection).list_active(self._profile_id),
            insights=InsightRepository(connection).list_active(),
            memories=memories,
            provenance=tuple(
                row for item in memories for row in memory.provenance_for(item.id)
            ),
            messages=SessionMessageRepository(connection).list_active(
                session_id, now=now
            ),
            pending_check_ins=CheckInRepository(connection).pending(),
        )
