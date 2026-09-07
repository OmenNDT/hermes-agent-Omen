"""Candidate record repository.

Requirement families: `HC-RECORDS`, `HC-DATA-*`; sources `SRC-054…059`,
`SRC-079`, `SRC-080`, `SRC-084`, `SRC-085`.

A candidate is data awaiting confirmation, never the structured truth. There is
deliberately no batch method here: each candidate is confirmed individually.
"""

from __future__ import annotations

from hermes_coach.domain.records import CandidateRecordRow
from hermes_coach.infrastructure.repositories.base import (
    Repository,
    not_expired,
    not_in_trash,
)


class CandidateRepository(Repository):
    table = "candidate_record"
    entity_type = "candidate_record"
    row_model = CandidateRecordRow

    def add(self, candidate: CandidateRecordRow) -> None:
        self.insert(candidate)

    def get(
        self, candidate_id: str, *, now: str | None = None
    ) -> CandidateRecordRow | None:
        return self.select_one(
            f"entity.id = :candidate_id AND {not_expired('entity')} "
            f"AND {not_in_trash('entity')}",
            {"candidate_id": candidate_id, "now": now or "", **self.trash_params()},
        )

    def list_for_session(self, session_id: str) -> tuple[CandidateRecordRow, ...]:
        """Every candidate this session has raised, whatever became of it.

        Unlike `list_pending` this ignores status and expiry, because it exists
        to answer "has this already been proposed here?". A candidate the
        Coachee declined must not come back around, and one they confirmed is
        already a record — both are reasons not to raise it a second time, and
        neither is pending.
        """
        return tuple(
            self.select(
                f"entity.session_id = :session_id AND {not_in_trash('entity')}",
                {"session_id": session_id, **self.trash_params()},
                # rowid, not id, as the tiebreaker: several candidates share a
                # timestamp when they come from one turn, and ordering those by
                # id sorts "t10" before "t9". Callers that trim this list keep
                # the tail, so a wrong tail silently keeps the wrong ones.
                order_by="entity.created_at, entity.rowid",
            )
        )

    def list_pending(
        self, session_id: str, *, now: str | None = None
    ) -> tuple[CandidateRecordRow, ...]:
        """Only unresolved candidates may be offered for confirmation."""
        return tuple(
            self.select(
                "entity.session_id = :session_id AND entity.status = 'pending' "
                f"AND {not_expired('entity')} AND {not_in_trash('entity')}",
                {"session_id": session_id, "now": now or "", **self.trash_params()},
                order_by="entity.created_at, entity.id",
            )
        )
