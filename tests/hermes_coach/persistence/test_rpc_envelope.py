"""Revision safety and idempotency for mutating RPC commands.

Requirement families: `HC-PRODUCT`, `HC-DATA-*`; sources `SRC-104…106`.

Single user, but not single tab: two windows onto the same session, or a retry
after a dropped socket, both produce the same two hazards — a command built on a
stale view, and a command applied twice. Revision catches the first, the
idempotency key catches the second.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from hermes_coach.infrastructure.repositories.rpc_repository import (
    IdempotencyRepository,
    SessionRevisionRepository,
    StaleRevision,
)
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-01-01T00:00:00Z"
LATER = "2026-01-01T01:00:00Z"
SESSION = "session-1"


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        with db.transaction():
            db.connection.execute(
                "INSERT INTO coachee_profile (id, display_name, created_at) "
                "VALUES ('profile-1', 'Coachee', ?)",
                (NOW,),
            )
            db.connection.execute(
                "INSERT INTO coaching_session (id, started_at, coaching_stage) "
                "VALUES (?, ?, 'goal')",
                (SESSION, NOW),
            )
        yield db


def revisions(database: CoachDatabase) -> SessionRevisionRepository:
    return SessionRevisionRepository(database.connection)


def commands(database: CoachDatabase) -> IdempotencyRepository:
    return IdempotencyRepository(database.connection)


def test_an_untouched_session_starts_at_revision_zero(
    database: CoachDatabase,
) -> None:
    assert revisions(database).current(SESSION) == 0


def test_a_mutation_bumps_the_revision(database: CoachDatabase) -> None:
    with database.transaction():
        assert revisions(database).bump(SESSION, NOW) == 1
        assert revisions(database).bump(SESSION, LATER) == 2
    assert revisions(database).current(SESSION) == 2


def test_a_command_carrying_the_current_revision_is_accepted(
    database: CoachDatabase,
) -> None:
    with database.transaction():
        revisions(database).bump(SESSION, NOW)
    revisions(database).require(SESSION, 1)


def test_a_command_built_on_a_stale_view_is_refused(
    database: CoachDatabase,
) -> None:
    with database.transaction():
        revisions(database).bump(SESSION, NOW)
        revisions(database).bump(SESSION, LATER)
    with pytest.raises(StaleRevision, match="stale"):
        revisions(database).require(SESSION, 1)


def test_a_command_claiming_a_future_revision_is_refused(
    database: CoachDatabase,
) -> None:
    """A client cannot talk its way forward past what actually happened."""
    with pytest.raises(StaleRevision):
        revisions(database).require(SESSION, 5)


def test_revisions_are_per_session(database: CoachDatabase) -> None:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coaching_session (id, started_at, coaching_stage) "
            "VALUES ('session-2', ?, 'goal')",
            (NOW,),
        )
        revisions(database).bump(SESSION, NOW)
    assert revisions(database).current(SESSION) == 1
    assert revisions(database).current("session-2") == 0


def test_the_revision_survives_reopen(tmp_path) -> None:
    path = tmp_path / "coach.db"
    with open_coach_database(path) as database:
        with database.transaction():
            database.connection.execute(
                "INSERT INTO coaching_session (id, started_at, coaching_stage) "
                "VALUES (?, ?, 'goal')",
                (SESSION, NOW),
            )
            revisions(database).bump(SESSION, NOW)
    with open_coach_database(path) as reopened:
        assert revisions(reopened).current(SESSION) == 1


def test_a_fresh_key_has_no_remembered_result(database: CoachDatabase) -> None:
    assert commands(database).recall("key-1") is None


def test_a_remembered_result_comes_back_verbatim(database: CoachDatabase) -> None:
    with database.transaction():
        commands(database).remember(
            "key-1", method="coach.turn", session_id=SESSION,
            result={"question": "Bạn muốn gì?"}, now=NOW,
        )
    assert commands(database).recall("key-1") == {"question": "Bạn muốn gì?"}


def test_replaying_a_key_returns_the_first_result_instead_of_running_again(
    database: CoachDatabase,
) -> None:
    runs = []

    def apply(key: str, value: str) -> dict:
        remembered = commands(database).recall(key)
        if remembered is not None:
            return remembered
        runs.append(value)
        result = {"value": value}
        with database.transaction():
            commands(database).remember(
                key, method="coach.turn", session_id=SESSION, result=result, now=NOW
            )
        return result

    assert apply("key-1", "first") == {"value": "first"}
    assert apply("key-1", "second") == {"value": "first"}
    assert runs == ["first"]


def test_remembering_the_same_key_twice_is_refused(database: CoachDatabase) -> None:
    """The UNIQUE key is the guard; a silent overwrite would hide a double-apply."""
    import sqlite3

    with database.transaction():
        commands(database).remember(
            "key-1", method="coach.turn", session_id=SESSION, result={}, now=NOW
        )
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction():
            commands(database).remember(
                "key-1", method="coach.turn", session_id=SESSION, result={}, now=NOW
            )


def test_a_remembered_result_survives_reopen(tmp_path) -> None:
    path = tmp_path / "coach.db"
    with open_coach_database(path) as database:
        with database.transaction():
            commands(database).remember(
                "key-1", method="coach.turn", session_id=None,
                result={"ok": True}, now=NOW,
            )
    with open_coach_database(path) as reopened:
        assert commands(reopened).recall("key-1") == {"ok": True}


def test_different_keys_do_not_share_a_result(database: CoachDatabase) -> None:
    with database.transaction():
        commands(database).remember(
            "key-1", method="coach.turn", session_id=SESSION,
            result={"n": 1}, now=NOW,
        )
    assert commands(database).recall("key-2") is None
