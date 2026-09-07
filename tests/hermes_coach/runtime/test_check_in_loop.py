"""A commitment, and the coming back to it.

Requirement families: `HC-CHECKIN`, `HC-RECORDS`; sources `SRC-083`, `SRC-084`.

The `check_in` table, `CheckInRow`, a Trash-aware `CheckInRepository.pending()`,
a `pending_check_ins` slot in `coach.today`, a Check-in screen in the app, and a
`CheckInChoiceCommand` spelling out four actions — all of it written, all of it
tested, and no line of code anywhere that inserted a row or read a command. Every
install answered "no check-ins pending" because none could exist.

These tests run the whole length of it: confirm a commitment, find the check-in
that confirmation owes, answer it, and find the next one.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import pytest

from hermes_coach.application.check_in_service import (
    CADENCE_DAYS,
    CheckInAlreadyAnswered,
    CheckInService,
    UnknownCheckIn,
)
from hermes_coach.application.durable_confirmation_service import (
    DurableConfirmationService,
)
from hermes_coach.application.record_confirmation_service import (
    CheckInAction,
    CheckInChoiceCommand,
    ConfirmationCommand,
    RecordAction,
)
from hermes_coach.domain.records import GoalRow
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-01-01T00:00:00Z"
PROFILE = "local"
SESSION = "session-1"
GOAL = "goal-1"
ACTION = "Thứ Hai nhắn anh Tuấn chọn 20 file"


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        with db.transaction():
            db.connection.execute(
                "INSERT INTO coachee_profile (id, display_name, created_at) "
                "VALUES (?, 'Coachee', ?)",
                (PROFILE, NOW),
            )
            db.connection.execute(
                "INSERT INTO coaching_session (id, started_at, coaching_stage) "
                "VALUES (?, ?, 'will')",
                (SESSION, NOW),
            )
            GoalRepository(db.connection).add(
                GoalRow(
                    id=GOAL,
                    profile_id=PROFILE,
                    title="Dựng demo tra cứu",
                    status="active",
                    source_session_id=SESSION,
                    confirmed_at=NOW,
                    created_at=NOW,
                )
            )
        yield db


def confirm_commitment(
    database: CoachDatabase, *, action_text: str = ACTION, due_at: str | None = None
) -> str:
    """Put a pending commitment candidate through the real confirmation path."""
    candidate_id = str(uuid.uuid4())
    payload = {"action_text": action_text, "goal_id": GOAL}
    if due_at:
        payload["due_at"] = due_at
    with database.transaction():
        database.connection.execute(
            "INSERT INTO candidate_record "
            "(id, session_id, record_type, payload_json, status, created_at) "
            "VALUES (?, ?, 'commitment', ?, 'pending', ?)",
            (candidate_id, SESSION, json.dumps(payload), NOW),
        )
    return accept(database, candidate_id).official_record_id


def accept(database: CoachDatabase, candidate_id: str, action=RecordAction.ACCEPT):
    """The real confirmation path: mint an intent, then spend it."""
    service = DurableConfirmationService(database, profile_id=PROFILE)
    token = service.issue_intent(
        local_user_id=PROFILE,
        session_id=SESSION,
        candidate_id=candidate_id,
        action=action,
        edited_value=None,
        now=NOW,
    )
    return service.apply(
        ConfirmationCommand(
            command_id=str(uuid.uuid4()),
            intent_token=token,
            candidate_id=candidate_id,
            action=action,
        ),
        now=NOW,
    )


def answer(
    database: CoachDatabase, check_in_id: str, action: CheckInAction, **extra
) -> dict:
    return CheckInService(database).answer(
        CheckInChoiceCommand(
            command_id=str(uuid.uuid4()),
            ui_event_id=str(uuid.uuid4()),
            check_in_id=check_in_id,
            action=action,
            **extra,
        ),
        now=NOW,
    )


class TestConfirmationOwesACheckIn:
    def test_confirming_a_commitment_schedules_one(
        self, database: CoachDatabase
    ) -> None:
        """The failure this whole file exists for."""
        commitment_id = confirm_commitment(database)
        pending = CheckInService(database).pending()
        assert [row["commitment_id"] for row in pending] == [commitment_id]

    def test_the_check_in_carries_the_commitments_own_words(
        self, database: CoachDatabase
    ) -> None:
        """An id alone is not something a Coachee can act on."""
        confirm_commitment(database)
        assert CheckInService(database).pending()[0]["action_text"] == ACTION

    def test_the_default_cadence_comes_from_the_lifecycle_contract(
        self, database: CoachDatabase
    ) -> None:
        """Two copies of a number are two numbers waiting to disagree."""
        confirm_commitment(database)
        assert CADENCE_DAYS == 14
        assert CheckInService(database).pending()[0]["scheduled_at"] == (
            "2026-01-15T00:00:00Z"
        )

    def test_the_coachees_own_due_date_wins_over_the_cadence(
        self, database: CoachDatabase
    ) -> None:
        confirm_commitment(database, due_at="2026-01-05T00:00:00Z")
        assert CheckInService(database).pending()[0]["scheduled_at"] == (
            "2026-01-05T00:00:00Z"
        )

    def test_confirming_a_goal_owes_nothing(self, database: CoachDatabase) -> None:
        """Only a commitment is a promise to come back to."""
        candidate_id = str(uuid.uuid4())
        with database.transaction():
            database.connection.execute(
                "INSERT INTO candidate_record "
                "(id, session_id, record_type, payload_json, status, created_at) "
                "VALUES (?, ?, 'goal', ?, 'pending', ?)",
                (candidate_id, SESSION, json.dumps({"title": "Một mục tiêu"}), NOW),
            )
        accept(database, candidate_id, RecordAction.ACCEPT)
        assert CheckInService(database).pending() == ()

    def test_a_discarded_commitment_owes_nothing(
        self, database: CoachDatabase
    ) -> None:
        candidate_id = str(uuid.uuid4())
        with database.transaction():
            database.connection.execute(
                "INSERT INTO candidate_record "
                "(id, session_id, record_type, payload_json, status, created_at) "
                "VALUES (?, ?, 'commitment', ?, 'pending', ?)",
                (
                    candidate_id,
                    SESSION,
                    json.dumps({"action_text": ACTION, "goal_id": GOAL}),
                    NOW,
                ),
            )
        accept(database, candidate_id, RecordAction.DISCARD)
        assert CheckInService(database).pending() == ()


class TestAnsweringOne:
    def test_keeping_it_closes_this_one_and_opens_the_next(
        self, database: CoachDatabase
    ) -> None:
        """A live commitment with no next check-in is the note this prevents."""
        confirm_commitment(database)
        first = CheckInService(database).pending()[0]
        result = answer(database, first["id"], CheckInAction.KEEP)

        pending = CheckInService(database).pending()
        assert result["next_check_in_id"] == pending[0]["id"]
        assert pending[0]["id"] != first["id"]
        assert pending[0]["scheduled_at"] == "2026-01-15T00:00:00Z"

    def test_editing_changes_the_commitment_the_next_one_is_about(
        self, database: CoachDatabase
    ) -> None:
        confirm_commitment(database)
        first = CheckInService(database).pending()[0]
        answer(
            database,
            first["id"],
            CheckInAction.EDIT,
            edited_commitment="Nhắn anh Tuấn chọn 10 file thôi",
        )
        assert CheckInService(database).pending()[0]["action_text"] == (
            "Nhắn anh Tuấn chọn 10 file thôi"
        )

    def test_rescheduling_moves_it_without_answering_it(
        self, database: CoachDatabase
    ) -> None:
        """Moving a question is not answering it, so no next one is opened."""
        confirm_commitment(database)
        first = CheckInService(database).pending()[0]
        result = answer(
            database,
            first["id"],
            CheckInAction.RESCHEDULE,
            rescheduled_for="2026-02-01T00:00:00Z",
        )
        pending = CheckInService(database).pending()
        assert result["next_check_in_id"] is None
        assert [row["id"] for row in pending] == [first["id"]]
        assert pending[0]["scheduled_at"] == "2026-02-01T00:00:00Z"

    def test_cancelling_ends_the_commitment_and_asks_nothing_further(
        self, database: CoachDatabase
    ) -> None:
        commitment_id = confirm_commitment(database)
        first = CheckInService(database).pending()[0]
        result = answer(database, first["id"], CheckInAction.CANCEL)

        assert result["commitment_status"] == "cancelled"
        assert CheckInService(database).pending() == ()
        status = database.connection.execute(
            "SELECT status FROM commitment WHERE id = ?", (commitment_id,)
        ).fetchone()["status"]
        assert status == "cancelled"

    def test_answering_twice_is_refused_rather_than_overwriting(
        self, database: CoachDatabase
    ) -> None:
        confirm_commitment(database)
        first = CheckInService(database).pending()[0]
        answer(database, first["id"], CheckInAction.KEEP)
        with pytest.raises(CheckInAlreadyAnswered):
            answer(database, first["id"], CheckInAction.CANCEL)

    def test_an_unknown_check_in_is_refused(self, database: CoachDatabase) -> None:
        with pytest.raises(UnknownCheckIn):
            answer(database, "no-such-check-in", CheckInAction.KEEP)

    def test_an_edit_with_no_new_words_is_refused_before_anything_is_written(
        self, database: CoachDatabase
    ) -> None:
        confirm_commitment(database)
        first = CheckInService(database).pending()[0]
        with pytest.raises(ValueError):
            answer(database, first["id"], CheckInAction.EDIT)
        assert CheckInService(database).pending()[0]["action_text"] == ACTION

    def test_a_reschedule_with_no_date_is_refused(
        self, database: CoachDatabase
    ) -> None:
        confirm_commitment(database)
        first = CheckInService(database).pending()[0]
        with pytest.raises(ValueError):
            answer(database, first["id"], CheckInAction.RESCHEDULE)


class TestATrashedCommitmentAsksNothing:
    def test_a_check_in_for_a_trashed_commitment_never_surfaces(
        self, database: CoachDatabase
    ) -> None:
        """Deleting the commitment must not leave the question behind."""
        commitment_id = confirm_commitment(database)
        with database.transaction():
            database.connection.execute(
                "INSERT INTO trash_entry (id, profile_id, entity_type, entity_id, "
                "deleted_at, purge_after, deletion_source) "
                "VALUES (?, ?, 'commitment', ?, ?, ?, 'item')",
                (
                    str(uuid.uuid4()),
                    PROFILE,
                    commitment_id,
                    NOW,
                    "2026-02-01T00:00:00Z",
                ),
            )
        assert CheckInService(database).pending() == ()


class TestDueVersusStillComing:
    """Home shows both, and must never present one as the other.

    Filtering to due-only would leave Home blank for the thirteen days between
    a commitment and its check-in — exactly the stretch in which someone
    forgets what they promised. But an item fourteen days out cannot sit under
    "Cần bạn hôm nay" as if it needed them today, so the row says which it is.
    """

    def test_a_freshly_scheduled_check_in_is_not_yet_due(
        self, database: CoachDatabase
    ) -> None:
        confirm_commitment(database)
        row = CheckInService(database).pending(now=NOW)[0]
        assert row["due"] is False
        assert row["days_until"] == CADENCE_DAYS

    def test_it_comes_due_on_the_day_it_was_scheduled_for(
        self, database: CoachDatabase
    ) -> None:
        confirm_commitment(database)
        row = CheckInService(database).pending(now="2026-01-15T00:00:00Z")[0]
        assert row["due"] is True
        assert row["days_until"] == 0

    def test_an_overdue_check_in_stays_due(self, database: CoachDatabase) -> None:
        confirm_commitment(database)
        row = CheckInService(database).pending(now="2026-02-01T00:00:00Z")[0]
        assert row["due"] is True
        assert row["days_until"] < 0

    def test_days_are_counted_by_date_not_by_elapsed_hours(
        self, database: CoachDatabase
    ) -> None:
        """"Còn 1 ngày" must mean tomorrow, even at 11pm tonight."""
        confirm_commitment(database)
        row = CheckInService(database).pending(now="2026-01-14T23:00:00Z")[0]
        assert row["days_until"] == 1
        assert row["due"] is False

    def test_what_is_due_is_listed_before_what_is_not(
        self, database: CoachDatabase
    ) -> None:
        """A Coachee should not have to scroll past three not-yet items."""
        confirm_commitment(database, action_text="Việc sắp tới")
        confirm_commitment(
            database, action_text="Việc đã tới hạn", due_at="2026-01-02T00:00:00Z"
        )
        rows = CheckInService(database).pending(now="2026-01-03T00:00:00Z")
        assert [row["action_text"] for row in rows] == [
            "Việc đã tới hạn",
            "Việc sắp tới",
        ]

    def test_nothing_is_hidden_just_because_it_is_not_due(
        self, database: CoachDatabase
    ) -> None:
        confirm_commitment(database)
        assert len(CheckInService(database).pending(now=NOW)) == 1
