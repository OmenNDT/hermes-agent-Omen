"""Gate confirmation repository.

Requirement families: `HC-PROCESS`; sources `SRC-030…057`, `SRC-059…061`.

Append-only. A rollback records an `invalidated` event rather than editing or
deleting the `yes` that came before, so the history stays auditable and a
restart can rebuild exactly which steps are open.
"""

from __future__ import annotations

from hermes_coach.domain.records import GateConfirmationRow
from hermes_coach.infrastructure.repositories.base import Repository


class GateRepository(Repository):
    table = "gate_confirmation"
    entity_type = "gate_confirmation"
    row_model = GateConfirmationRow

    def append(self, event: GateConfirmationRow) -> None:
        self.insert(event)

    def next_revision(self, session_id: str, step: str) -> int:
        """The revision a new event for this step must take.

        Events sit above one another and `confirmed_steps` reads the highest, so
        a new one must sit strictly above every earlier event for the same step
        — the `invalidated` rows a rollback writes included. Starting at 1
        matches the domain, where a stage that has never been rolled back is at
        revision 1.
        """
        row = self.connection.execute(
            "SELECT MAX(revision) AS highest FROM gate_confirmation "
            "WHERE session_id = :session_id AND step = :step",
            {"session_id": session_id, "step": step},
        ).fetchone()
        highest = row["highest"]
        return 1 if highest is None else highest + 1

    def history(self, session_id: str) -> tuple[GateConfirmationRow, ...]:
        """Every event, oldest first, including `no` and `invalidated`."""
        return tuple(
            self.select(
                "entity.session_id = :session_id",
                {"session_id": session_id},
                order_by="entity.revision, entity.id",
            )
        )

    def confirmed_steps(self, session_id: str) -> tuple[str, ...]:
        """Steps whose highest-revision event is a `yes`.

        Highest revision wins because that is how rollback and replay work: the
        rollback writes `invalidated` above the old `yes`, and the replay writes
        a new `yes` above that. Counting `yes` events would keep a rolled-back
        step open forever.
        """
        rows = self.connection.execute(
            "SELECT step, result FROM gate_confirmation AS outer_event "
            "WHERE session_id = :session_id AND revision = ("
            "  SELECT MAX(revision) FROM gate_confirmation AS inner_event "
            "  WHERE inner_event.session_id = outer_event.session_id "
            "  AND inner_event.step = outer_event.step"
            ") ORDER BY step",
            {"session_id": session_id},
        ).fetchall()
        return tuple(row["step"] for row in rows if row["result"] == "yes")
