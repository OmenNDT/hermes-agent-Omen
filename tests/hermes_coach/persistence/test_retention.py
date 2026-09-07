"""Retention clock boundaries.

Requirement families: `HC-PRIVACY`, `HC-MEMORY`, `HC-DATA-*`; sources `SRC-063`,
`SRC-068`, `SRC-076…086`, `SRC-091`.

Temporary data goes at 90 days, open Trash at 30. Durable structured records
never expire by age. The clock is injected: retention runs at startup and then
periodically, and a restart must catch deadlines that passed while the app was
closed.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from hermes_coach.application.retention_service import (
    TEMPORARY_DATA_WINDOW,
    TRASH_WINDOW,
    RetentionService,
)
from hermes_coach.domain.clock import shift
from hermes_coach.domain.records import (
    CandidateRecordRow,
    GoalRow,
    MemoryItemRow,
    SessionMessageRow,
    TrashEntryRow,
)
from hermes_coach.infrastructure.repositories.candidate_repository import (
    CandidateRepository,
)
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.memory_repository import MemoryRepository
from hermes_coach.infrastructure.repositories.session_message_repository import (
    SessionMessageRepository,
)
from hermes_coach.infrastructure.repositories.trash_repository import TrashRepository
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


CREATED = "2026-01-01T00:00:00Z"

# 2026 is not a leap year: 1 Jan + 90 days is 1 Apr.
DAY_89 = "2026-03-31T00:00:00Z"
DAY_90 = "2026-04-01T00:00:00Z"
DAY_91 = "2026-04-02T00:00:00Z"

TRASH_DAY_29 = "2026-01-30T00:00:00Z"
TRASH_DAY_30 = "2026-01-31T00:00:00Z"
TRASH_DAY_31 = "2026-02-01T00:00:00Z"

PROFILE = "profile-1"
SESSION = "session-1"


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        seed(db)
        yield db


def seed(database: CoachDatabase) -> None:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coachee_profile (id, display_name, created_at) "
            "VALUES (?, 'Coachee', ?)",
            (PROFILE, CREATED),
        )
        database.connection.execute(
            "INSERT INTO coaching_session (id, started_at, coaching_stage) "
            "VALUES (?, ?, 'goal')",
            (SESSION, CREATED),
        )


def retention(database: CoachDatabase) -> RetentionService:
    return RetentionService(database)


def add_message(
    database: CoachDatabase,
    message_id: str = "message-1",
    *,
    sequence_no: int = 0,
    expires_at: str | None = shift(CREATED, TEMPORARY_DATA_WINDOW),
) -> None:
    with database.transaction():
        SessionMessageRepository(database.connection).add(
            SessionMessageRow(
                id=message_id,
                session_id=SESSION,
                sequence_no=sequence_no,
                role="coachee",
                content="Tôi muốn đổi vai trò",
                created_at=CREATED,
                expires_at=expires_at,
            )
        )


def add_candidate(
    database: CoachDatabase,
    candidate_id: str = "candidate-1",
    *,
    status: str = "pending",
    expires_at: str | None = shift(CREATED, TEMPORARY_DATA_WINDOW),
) -> None:
    with database.transaction():
        CandidateRepository(database.connection).add(
            CandidateRecordRow(
                id=candidate_id,
                session_id=SESSION,
                record_type="goal",
                payload_json='{"title": "Mục tiêu"}',
                status=status,  # type: ignore[arg-type]
                created_at=CREATED,
                expires_at=expires_at,
            )
        )


def count(database: CoachDatabase, table: str) -> int:
    return database.connection.execute(
        f"SELECT COUNT(*) AS total FROM {table}"
    ).fetchone()["total"]


def test_the_windows_match_the_approved_retention_policy() -> None:
    assert TEMPORARY_DATA_WINDOW.days == 90
    assert TRASH_WINDOW.days == 30


@pytest.mark.parametrize(
    ("moment", "survives"),
    [(DAY_89, True), (DAY_90, False), (DAY_91, False)],
)
def test_transcript_purges_exactly_at_ninety_days(
    database: CoachDatabase, moment: str, survives: bool
) -> None:
    add_message(database)
    retention(database).run(now=moment)
    assert (count(database, "session_message") == 1) is survives


@pytest.mark.parametrize(
    ("moment", "survives"),
    [(DAY_89, True), (DAY_90, False), (DAY_91, False)],
)
def test_pending_candidate_purges_exactly_at_ninety_days(
    database: CoachDatabase, moment: str, survives: bool
) -> None:
    add_candidate(database)
    retention(database).run(now=moment)
    assert (count(database, "candidate_record") == 1) is survives


def test_a_resolved_candidate_is_not_temporary_data(
    database: CoachDatabase,
) -> None:
    """Only pending candidates are temporary; a resolved one is audit history."""
    add_candidate(database, "candidate-confirmed", status="confirmed")
    retention(database).run(now=DAY_91)
    assert count(database, "candidate_record") == 1


def test_a_missing_expiry_still_purges_at_ninety_days_from_creation(
    database: CoachDatabase,
) -> None:
    """A writer that forgets `expires_at` must not create immortal transcript."""
    add_message(database, "message-no-expiry", expires_at=None)
    retention(database).run(now=DAY_89)
    assert count(database, "session_message") == 1
    retention(database).run(now=DAY_90)
    assert count(database, "session_message") == 0


def test_durable_records_never_expire_by_age(database: CoachDatabase) -> None:
    with database.transaction():
        GoalRepository(database.connection).add(
            GoalRow(
                id="goal-1",
                profile_id=PROFILE,
                title="Mục tiêu dài hạn",
                status="active",
                confirmed_at=CREATED,
                created_at=CREATED,
            )
        )
        MemoryRepository(database.connection).add(
            MemoryItemRow(
                id="memory-1",
                content="Coachee coi trọng quyền tự chủ",
                user_confirmed=True,
            )
        )
    retention(database).run(now="2030-01-01T00:00:00Z")
    assert count(database, "goal") == 1
    assert count(database, "memory_item") == 1


def test_technical_logs_and_notifications_purge_at_ninety_days(
    database: CoachDatabase,
) -> None:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO internal_technical_log (id, level, message, created_at) "
            "VALUES ('log-1', 'info', 'started', ?)",
            (CREATED,),
        )
        database.connection.execute(
            "INSERT INTO internal_notification_history "
            "(id, channel, delivered_at, created_at) "
            "VALUES ('note-1', 'browser', ?, ?)",
            (CREATED, CREATED),
        )
    retention(database).run(now=DAY_89)
    assert count(database, "internal_technical_log") == 1
    assert count(database, "internal_notification_history") == 1

    retention(database).run(now=DAY_90)
    assert count(database, "internal_technical_log") == 0
    assert count(database, "internal_notification_history") == 0


def open_trash(database: CoachDatabase, entity_id: str = "message-1") -> None:
    with database.transaction():
        TrashRepository(database.connection).soft_delete(
            TrashEntryRow(
                id=f"trash-{entity_id}",
                profile_id=PROFILE,
                entity_type="session_message",
                entity_id=entity_id,
                deleted_at=CREATED,
                purge_after=shift(CREATED, TRASH_WINDOW),
                deletion_source="item",
            )
        )


@pytest.mark.parametrize(
    ("moment", "survives"),
    [(TRASH_DAY_29, True), (TRASH_DAY_30, False), (TRASH_DAY_31, False)],
)
def test_open_trash_purges_exactly_at_thirty_days(
    database: CoachDatabase, moment: str, survives: bool
) -> None:
    add_message(database)
    open_trash(database)
    retention(database).run(now=moment)
    assert (count(database, "session_message") == 1) is survives


def test_a_restored_item_is_never_purged_by_the_trash_clock(
    database: CoachDatabase,
) -> None:
    add_message(database)
    open_trash(database)
    with database.transaction():
        TrashRepository(database.connection).restore(
            "session_message", "message-1", TRASH_DAY_29
        )
    retention(database).run(now=TRASH_DAY_31)
    assert count(database, "session_message") == 1


def test_retention_is_idempotent(database: CoachDatabase) -> None:
    add_message(database)
    add_candidate(database)
    first = retention(database).run(now=DAY_91)
    second = retention(database).run(now=DAY_91)
    assert first.total_purged > 0
    assert second.total_purged == 0


def test_a_restart_catches_a_deadline_that_passed_while_closed(tmp_path) -> None:
    """Missed deadlines are caught on the next startup, not skipped."""
    path = tmp_path / "coach.db"
    with open_coach_database(path) as database:
        seed(database)
        add_message(database)
        retention(database).run(now=DAY_89)
        assert count(database, "session_message") == 1

    with open_coach_database(path) as reopened:
        outcome = retention(reopened).run(now=DAY_91)
        assert outcome.total_purged == 1
        assert count(reopened, "session_message") == 0


def test_a_failed_purge_rolls_the_whole_sweep_back(
    database: CoachDatabase, monkeypatch
) -> None:
    """A partial sweep would leave a deadline half-enforced and hard to audit."""
    add_message(database)
    add_candidate(database)

    real_execute = RetentionService._purge_expired_candidates

    def explode(self, now: str, cutoff: str) -> int:
        raise RuntimeError("disk full")

    monkeypatch.setattr(RetentionService, "_purge_expired_candidates", explode)
    with pytest.raises(RuntimeError):
        retention(database).run(now=DAY_91)

    assert count(database, "session_message") == 1
    assert count(database, "candidate_record") == 1

    monkeypatch.setattr(RetentionService, "_purge_expired_candidates", real_execute)
    retention(database).run(now=DAY_91)
    assert count(database, "session_message") == 0


def test_the_sweep_reports_what_it_removed(database: CoachDatabase) -> None:
    add_message(database)
    add_candidate(database)
    outcome = retention(database).run(now=DAY_91)
    assert outcome.purged["session_message"] == 1
    assert outcome.purged["candidate_record"] == 1
    assert outcome.total_purged == 2


def test_purging_a_message_leaves_its_session_and_goals_alone(
    database: CoachDatabase,
) -> None:
    add_message(database)
    with database.transaction():
        GoalRepository(database.connection).add(
            GoalRow(
                id="goal-1",
                profile_id=PROFILE,
                title="Mục tiêu",
                status="active",
                source_session_id=SESSION,
                confirmed_at=CREATED,
                created_at=CREATED,
            )
        )
    retention(database).run(now=DAY_91)
    assert count(database, "session_message") == 0
    assert count(database, "coaching_session") == 1
    assert count(database, "goal") == 1
