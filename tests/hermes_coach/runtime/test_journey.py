"""The Journey screen's read.

Requirement families: `HC-PROCESS`, `HC-RECORDS`; sources `SRC-061`,
`SRC-076…086`.

`/journey` was the last placeholder in the navigation. A list of dates would
have been an activity log; what makes a history worth opening is what each
session left behind, so these tests are mostly about the counts being real —
tied to `source_session_id`, respecting Trash, and honest about a transcript
that has since expired.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from hermes_coach.application.journey_service import JourneyService
from hermes_coach.domain.records import (
    CommitmentRow,
    GoalRow,
    InsightRow,
    SessionMessageRow,
)
from hermes_coach.infrastructure.repositories.commitment_repository import (
    CommitmentRepository,
)
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.insight_repository import (
    InsightRepository,
)
from hermes_coach.infrastructure.repositories.session_message_repository import (
    SessionMessageRepository,
)
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-03-01T00:00:00Z"
PROFILE = "local"


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        with db.transaction():
            db.connection.execute(
                "INSERT INTO coachee_profile (id, display_name, created_at) "
                "VALUES (?, 'Coachee', ?)",
                (PROFILE, NOW),
            )
        yield db


def session(
    database: CoachDatabase,
    session_id: str,
    *,
    started_at: str,
    stage: str = "goal",
    ended_at: str | None = None,
    intention: str | None = None,
) -> str:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coaching_session "
            "(id, started_at, ended_at, intention, coaching_stage) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, started_at, ended_at, intention, stage),
        )
    return session_id


def add_goal(database: CoachDatabase, session_id: str, goal_id: str = "goal-1") -> str:
    with database.transaction():
        GoalRepository(database.connection).add(
            GoalRow(
                id=goal_id,
                profile_id=PROFILE,
                title="Một mục tiêu",
                status="active",
                source_session_id=session_id,
                confirmed_at=NOW,
                created_at=NOW,
            )
        )
    return goal_id


def add_insight(database: CoachDatabase, session_id: str, insight_id: str) -> None:
    with database.transaction():
        InsightRepository(database.connection).add(
            InsightRow(
                id=insight_id,
                content="Tôi né tránh xung đột",
                source_session_id=session_id,
                confirmed_at=NOW,
            )
        )


def add_commitment(database: CoachDatabase, session_id: str, goal_id: str) -> None:
    with database.transaction():
        CommitmentRepository(database.connection).add(
            CommitmentRow(
                id=str(uuid.uuid4()),
                goal_id=goal_id,
                action_text="Nhắn anh Tuấn",
                status="active",
                source_session_id=session_id,
                confirmed_at=NOW,
            )
        )


def add_message(
    database: CoachDatabase, session_id: str, message_id: str, *, expires_at: str | None
) -> None:
    with database.transaction():
        SessionMessageRepository(database.connection).add(
            SessionMessageRow(
                id=message_id,
                session_id=session_id,
                sequence_no=0,
                role="coachee",
                content="Tôi muốn đổi vai trò",
                created_at=NOW,
                expires_at=expires_at,
            )
        )


def trash(database: CoachDatabase, entity_type: str, entity_id: str) -> None:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO trash_entry (id, profile_id, entity_type, entity_id, "
            "deleted_at, purge_after, deletion_source) "
            "VALUES (?, ?, ?, ?, ?, ?, 'item')",
            (str(uuid.uuid4()), PROFILE, entity_type, entity_id, NOW, "2026-04-01T00:00:00Z"),
        )


def journey(database: CoachDatabase, **kwargs):
    return JourneyService(database).recent(now=NOW, **kwargs)


class TestTheHistoryItself:
    def test_an_empty_history_is_empty_not_an_error(
        self, database: CoachDatabase
    ) -> None:
        assert journey(database) == ()

    def test_newest_first(self, database: CoachDatabase) -> None:
        """A history read top-down should start with what just happened."""
        session(database, "old", started_at="2026-01-01T00:00:00Z")
        session(database, "new", started_at="2026-02-01T00:00:00Z")
        assert [entry["id"] for entry in journey(database)] == ["new", "old"]

    def test_a_session_the_coachee_deleted_is_gone_from_the_history(
        self, database: CoachDatabase
    ) -> None:
        session(database, "kept", started_at="2026-01-01T00:00:00Z")
        session(database, "removed", started_at="2026-02-01T00:00:00Z")
        trash(database, "coaching_session", "removed")
        assert [entry["id"] for entry in journey(database)] == ["kept"]

    def test_the_history_is_bounded(self, database: CoachDatabase) -> None:
        """A Coachee two years in does not want two years of rows."""
        for index in range(5):
            session(database, f"s{index}", started_at=f"2026-01-0{index + 1}T00:00:00Z")
        assert len(journey(database, limit=3)) == 3

    def test_an_unfinished_session_is_shown_rather_than_hidden(
        self, database: CoachDatabase
    ) -> None:
        """Stopping at Reality is not a failure, and not something to bury."""
        session(database, "s1", started_at=NOW, stage="reality")
        entry = journey(database)[0]
        assert entry["ended"] is False
        assert entry["stage"] == "reality"

    def test_a_finished_session_says_so(self, database: CoachDatabase) -> None:
        session(
            database, "s1", started_at=NOW, stage="review", ended_at="2026-03-01T01:00:00Z"
        )
        entry = journey(database)[0]
        assert entry["ended"] is True
        assert entry["ended_at"] == "2026-03-01T01:00:00Z"

    def test_the_intention_the_coachee_wrote_is_carried(
        self, database: CoachDatabase
    ) -> None:
        session(database, "s1", started_at=NOW, intention="tìm hướng đi")
        assert journey(database)[0]["intention"] == "tìm hướng đi"


class TestWhatEachSessionLeftBehind:
    def test_the_counts_are_what_this_session_produced(
        self, database: CoachDatabase
    ) -> None:
        """Tied to `source_session_id`, not to what exists in the profile."""
        session(database, "s1", started_at="2026-01-01T00:00:00Z")
        session(database, "s2", started_at="2026-02-01T00:00:00Z")
        goal = add_goal(database, "s1")
        add_insight(database, "s1", "insight-1")
        add_insight(database, "s2", "insight-2")
        add_commitment(database, "s2", goal)

        entries = {entry["id"]: entry["produced"] for entry in journey(database)}
        assert entries["s1"] == {"goals": 1, "insights": 1, "commitments": 0}
        assert entries["s2"] == {"goals": 0, "insights": 1, "commitments": 1}

    def test_a_session_that_produced_nothing_says_zero(
        self, database: CoachDatabase
    ) -> None:
        """It must not look identical to one that produced three records."""
        session(database, "s1", started_at=NOW)
        assert journey(database)[0]["produced"] == {
            "goals": 0,
            "insights": 0,
            "commitments": 0,
        }

    def test_a_deleted_record_stops_being_counted(
        self, database: CoachDatabase
    ) -> None:
        """The history must agree with what the Coachee can actually open."""
        session(database, "s1", started_at=NOW)
        add_insight(database, "s1", "insight-1")
        assert journey(database)[0]["produced"]["insights"] == 1
        trash(database, "insight", "insight-1")
        assert journey(database)[0]["produced"]["insights"] == 0


class TestTheTranscriptOutlivesNothing:
    def test_a_live_transcript_is_counted(self, database: CoachDatabase) -> None:
        session(database, "s1", started_at=NOW)
        add_message(database, "s1", "m1", expires_at="2026-06-01T00:00:00Z")
        assert journey(database)[0]["messages"] == 1

    def test_an_expired_transcript_leaves_the_session_with_nothing_to_read(
        self, database: CoachDatabase
    ) -> None:
        """Session rows are durable; messages are purged on the window.

        The entry stays real — it produced what it produced — but offering to
        open the transcript would promise the Coachee their own words back and
        then not have them.
        """
        session(database, "s1", started_at="2025-01-01T00:00:00Z")
        add_message(database, "s1", "m1", expires_at="2025-04-01T00:00:00Z")
        entry = journey(database)[0]
        assert entry["messages"] == 0
        assert entry["messages_ever"] == 1
        assert entry["id"] == "s1"

    def test_a_session_where_nothing_was_said_is_not_a_lost_transcript(
        self, database: CoachDatabase
    ) -> None:
        """Found live, on real data.

        Three sessions three days old — well inside a ninety-day window — were
        being reported as having lost their contents. They had simply been
        opened and abandoned before the first turn. Telling a Coachee their own
        words were lost when none were ever written is a false alarm about
        their data, and the two counts are what tell the cases apart.
        """
        session(database, "s1", started_at=NOW)
        entry = journey(database)[0]
        assert entry["messages"] == 0
        assert entry["messages_ever"] == 0

    def test_a_live_transcript_reads_the_same_both_ways(
        self, database: CoachDatabase
    ) -> None:
        session(database, "s1", started_at=NOW)
        add_message(database, "s1", "m1", expires_at="2026-06-01T00:00:00Z")
        entry = journey(database)[0]
        assert entry["messages"] == entry["messages_ever"] == 1

    def test_a_deleted_message_counts_as_neither(
        self, database: CoachDatabase
    ) -> None:
        """Trash is the Coachee's own choice, not a retention loss to report."""
        session(database, "s1", started_at=NOW)
        add_message(database, "s1", "m1", expires_at=None)
        trash(database, "session_message", "m1")
        entry = journey(database)[0]
        assert entry["messages"] == 0
        assert entry["messages_ever"] == 0

    def test_a_durable_message_never_counts_as_expired(
        self, database: CoachDatabase
    ) -> None:
        session(database, "s1", started_at=NOW)
        add_message(database, "s1", "m1", expires_at=None)
        assert journey(database)[0]["messages"] == 1


class TestSafety:
    def test_a_session_with_no_recorded_state_reads_as_normal(
        self, database: CoachDatabase
    ) -> None:
        session(database, "s1", started_at=NOW)
        assert journey(database)[0]["safety_state"] == "normal"

    def test_an_interrupted_session_carries_its_state(
        self, database: CoachDatabase
    ) -> None:
        session(database, "s1", started_at=NOW)
        with database.transaction():
            database.connection.execute(
                "UPDATE coaching_session SET safety_state = 'possible_crisis'"
            )
        assert journey(database)[0]["safety_state"] == "possible_crisis"
