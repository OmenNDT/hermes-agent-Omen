"""Coming back to a commitment.

Requirement families: `HC-CHECKIN`, `HC-RECORDS`; sources `SRC-083`, `SRC-084`.

A commitment nobody returns to is a note. The check-in is the return, and until
now it was the one part of the loop that existed only on paper: `check_in` had a
table, a row model, a Trash-aware repository, a slot in `coach.today` and a
screen in the app, and `CheckInChoiceCommand` spelled out four actions the
Coachee could take — with nothing anywhere that wrote a row or read a command.
Every install answered "no check-ins pending" because none could exist.

What this owns is the answer. Scheduling belongs to confirmation, which is the
moment that knows a check-in is owed.

The four actions are deliberately not "done" and "not done". A commitment the
Coachee did not keep is information about the commitment, not a verdict on
them; the choices are about what the commitment should now be, which is the
question a coach would actually ask.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from hermes_coach.application.record_confirmation_service import (
    CheckInAction,
    CheckInChoiceCommand,
)
from hermes_coach.contracts.lifecycle_contract import CheckInRecovery
from hermes_coach.domain.clock import parse, shift
from hermes_coach.domain.records import CheckInRow
from hermes_coach.infrastructure.repositories.check_in_repository import (
    CheckInRepository,
)
from hermes_coach.infrastructure.repositories.commitment_repository import (
    CommitmentRepository,
)
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


CADENCE_DAYS: int = CheckInRecovery.model_fields["default_cadence_days"].default


class UnknownCheckIn(LookupError):
    """The answer names a check-in that does not exist, or is in Trash."""


class CheckInAlreadyAnswered(RuntimeError):
    """This check-in is closed. Answering twice would overwrite the first."""


def next_due(now: str) -> str:
    return shift(now, timedelta(days=CADENCE_DAYS))


def _has_come_due(scheduled_at: str, now: str | None) -> bool:
    """Compared as instants, so a check-in due this morning is due."""
    if now is None:
        return True
    try:
        return parse(scheduled_at) <= parse(now)
    except ValueError:
        # An unparseable timestamp is shown rather than hidden: a check-in the
        # Coachee cannot see is a promise the product quietly dropped.
        return True


def _days_until(scheduled_at: str, now: str | None) -> int | None:
    """Whole days, by calendar date rather than by elapsed hours.

    "Còn 1 ngày" should mean tomorrow, not "in more than 24 hours" — a check-in
    due tomorrow morning is one day away even at 11pm tonight.
    """
    if now is None:
        return None
    try:
        return (parse(scheduled_at).date() - parse(now).date()).days
    except ValueError:
        return None


class CheckInService:
    def __init__(self, database: CoachDatabase) -> None:
        self._database = database

    def pending(self, *, now: str | None = None) -> tuple[dict, ...]:
        """Outstanding check-ins, each carrying the commitment it is about.

        The id alone is useless to a screen: "you have one check-in" tells the
        Coachee nothing they can act on. The commitment's own words are what
        the question is.

        Everything outstanding is returned, not only what has come due, and
        each row says which it is. Filtering to due-only would leave Home blank
        for the thirteen days between a commitment and its check-in — which is
        exactly the stretch in which someone forgets what they promised. But an
        item fourteen days out cannot be presented as needing them today, so
        `due` and `days_until` travel with it and the screen says which.

        Due first, then soonest. What has come due is what a Coachee can act on
        now, and it should not sit below three things that have not.
        """
        connection = self._database.connection
        commitments = CommitmentRepository(connection)
        answered = []
        for row in CheckInRepository(connection).pending():
            commitment = commitments.get(row.commitment_id)
            if commitment is None:
                # The commitment went to Trash between the two reads, or its
                # row is gone. A check-in about nothing is not shown.
                continue
            answered.append(
                {
                    "id": row.id,
                    "commitment_id": commitment.id,
                    "action_text": commitment.action_text,
                    "goal_id": commitment.goal_id,
                    "scheduled_at": row.scheduled_at,
                    "due_at": commitment.due_at,
                    "due": _has_come_due(row.scheduled_at, now),
                    "days_until": _days_until(row.scheduled_at, now),
                }
            )
        answered.sort(key=lambda item: (not item["due"], item["scheduled_at"]))
        return tuple(answered)

    def answer(self, command: CheckInChoiceCommand, *, now: str) -> dict:
        """Apply one choice. Runs inside its own transaction.

        Reschedule is the only action that leaves the check-in open: the
        Coachee has not answered the question, they have moved it. Everything
        else closes this one, and keep and edit open the next.
        """
        connection = self._database.connection
        check_ins = CheckInRepository(connection)

        existing = check_ins.get(command.check_in_id)
        if existing is None:
            raise UnknownCheckIn(f"no such check-in: {command.check_in_id}")
        if existing.completed_at is not None:
            raise CheckInAlreadyAnswered(
                f"check-in {command.check_in_id} was already answered"
            )

        commitment = CommitmentRepository(connection).get(existing.commitment_id)
        if commitment is None:
            raise UnknownCheckIn("the commitment this check-in is about is gone")

        with self._database.transaction():
            if command.action is CheckInAction.RESCHEDULE:
                connection.execute(
                    "UPDATE check_in SET scheduled_at = :when, rescheduled_to = :when "
                    "WHERE id = :id",
                    {"when": command.rescheduled_for, "id": existing.id},
                )
                return {
                    "check_in_id": existing.id,
                    "action": command.action.value,
                    "scheduled_at": command.rescheduled_for,
                    "next_check_in_id": None,
                    "commitment_status": commitment.status,
                }

            if command.action is CheckInAction.EDIT:
                connection.execute(
                    "UPDATE commitment SET action_text = :text WHERE id = :id",
                    {"text": command.edited_commitment, "id": commitment.id},
                )

            if command.action is CheckInAction.CANCEL:
                connection.execute(
                    "UPDATE commitment SET status = 'cancelled' WHERE id = :id",
                    {"id": commitment.id},
                )

            connection.execute(
                "UPDATE check_in SET completed_at = :now, still_relevant = :relevant "
                "WHERE id = :id",
                {
                    "now": now,
                    "relevant": 0 if command.action is CheckInAction.CANCEL else 1,
                    "id": existing.id,
                },
            )

            # A cancelled commitment is finished, so there is nothing to come
            # back to. Keep and edit both leave a live commitment, and a live
            # commitment with no next check-in is exactly the note this whole
            # feature exists to stop it becoming.
            next_id: str | None = None
            if command.action is not CheckInAction.CANCEL:
                next_id = str(uuid.uuid4())
                check_ins.schedule(
                    CheckInRow(
                        id=next_id,
                        commitment_id=commitment.id,
                        scheduled_at=next_due(now),
                    )
                )

        return {
            "check_in_id": existing.id,
            "action": command.action.value,
            "scheduled_at": existing.scheduled_at,
            "next_check_in_id": next_id,
            "commitment_status": (
                "cancelled" if command.action is CheckInAction.CANCEL else commitment.status
            ),
        }
