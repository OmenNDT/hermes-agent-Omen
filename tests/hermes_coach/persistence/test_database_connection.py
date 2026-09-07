"""Connection and durability pragmas for the Coach store.

Requirement family: `HC-DATA-*`, `HC-PRIVACY`; sources `SRC-076…SRC-086`,
`SRC-091`.

`secure_delete` is best-effort hygiene, not encryption. The MVP database is
unencrypted at rest and the product discloses that separately.
"""

from __future__ import annotations

from collections.abc import Iterator

import sqlite3

import pytest

from hermes_coach.infrastructure.sqlite.database import (
    BUSY_TIMEOUT_MS,
    CoachDatabase,
    connect,
    open_coach_database,
)


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        yield db


def pragma(database: CoachDatabase, name: str) -> object:
    return database.connection.execute(f"PRAGMA {name}").fetchone()[0]


def test_manual_transaction_control_is_retained(database: CoachDatabase) -> None:
    """Services own transaction boundaries; the driver must not open its own."""
    assert database.connection.isolation_level is None


def test_rows_are_addressable_by_column_name(database: CoachDatabase) -> None:
    row = database.connection.execute("SELECT 1 AS answer").fetchone()
    assert row["answer"] == 1


def test_foreign_keys_are_on(database: CoachDatabase) -> None:
    assert pragma(database, "foreign_keys") == 1


def test_busy_timeout_is_configured(database: CoachDatabase) -> None:
    assert pragma(database, "busy_timeout") == BUSY_TIMEOUT_MS


def test_critical_writes_are_fully_synchronous(database: CoachDatabase) -> None:
    assert pragma(database, "synchronous") == 2


def test_secure_delete_is_enabled(database: CoachDatabase) -> None:
    assert pragma(database, "secure_delete") == 1


def test_wal_is_used_when_the_filesystem_supports_it(
    database: CoachDatabase,
) -> None:
    assert database.journal_mode == "wal"
    assert pragma(database, "journal_mode") == "wal"


class WalRefusingConnection(sqlite3.Connection):
    """Stands in for a filesystem that errors when asked to switch to WAL."""

    def execute(self, sql, *args, **kwargs):
        if "journal_mode = wal" in sql.lower():
            raise sqlite3.OperationalError("cannot change into wal mode")
        return super().execute(sql, *args, **kwargs)


def assert_database_is_writable(database: CoachDatabase) -> None:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coachee_profile (id, display_name, created_at) "
            "VALUES ('p1', 'Coachee', '2026-08-22T00:00:00Z')"
        )
    row = database.connection.execute(
        "SELECT display_name FROM coachee_profile WHERE id = 'p1'"
    ).fetchone()
    assert row["display_name"] == "Coachee"


def test_wal_error_falls_back_instead_of_refusing_to_open(
    tmp_path, monkeypatch
) -> None:
    """A filesystem that errors on WAL must still yield a usable database."""
    real_connect = sqlite3.connect
    monkeypatch.setattr(
        sqlite3,
        "connect",
        lambda *args, **kwargs: real_connect(
            *args, **kwargs, factory=WalRefusingConnection
        ),
    )
    with open_coach_database(tmp_path / "fallback.db") as database:
        assert database.journal_mode != "wal"
        assert_database_is_writable(database)


def test_silently_ignored_journal_mode_is_not_reported_as_applied(
    tmp_path, monkeypatch
) -> None:
    """SQLite ignores an unknown mode rather than failing; detect that too."""
    monkeypatch.setattr(
        "hermes_coach.infrastructure.sqlite.database.JOURNAL_MODES",
        ("not_a_journal_mode", "delete"),
    )
    with open_coach_database(tmp_path / "ignored.db") as database:
        assert database.journal_mode == "delete"
        assert_database_is_writable(database)


def test_close_is_deterministic_and_repeatable(tmp_path) -> None:
    database = open_coach_database(tmp_path / "coach.db")
    database.close()
    database.close()
    with pytest.raises(sqlite3.ProgrammingError):
        database.connection.execute("SELECT 1")


def test_committed_write_survives_reopen(tmp_path) -> None:
    path = tmp_path / "coach.db"
    with open_coach_database(path) as database:
        with database.transaction():
            database.connection.execute(
                "INSERT INTO coachee_profile (id, display_name, created_at) "
                "VALUES ('p1', 'Coachee', '2026-08-22T00:00:00Z')"
            )
    with open_coach_database(path) as reopened:
        row = reopened.connection.execute(
            "SELECT display_name FROM coachee_profile WHERE id = 'p1'"
        ).fetchone()
        assert row["display_name"] == "Coachee"


def test_transaction_rolls_back_on_error(tmp_path) -> None:
    with open_coach_database(tmp_path / "coach.db") as database:
        with pytest.raises(RuntimeError):
            with database.transaction():
                database.connection.execute(
                    "INSERT INTO coachee_profile (id, display_name, created_at) "
                    "VALUES ('p1', 'Coachee', '2026-08-22T00:00:00Z')"
                )
                raise RuntimeError("service failed mid-transaction")
        assert database.connection.execute(
            "SELECT COUNT(*) AS total FROM coachee_profile"
        ).fetchone()["total"] == 0


def test_transaction_takes_an_immediate_write_lock(tmp_path) -> None:
    """Deferred locks upgrade mid-transaction and deadlock concurrent writers."""
    path = tmp_path / "coach.db"
    with open_coach_database(path) as first, connect(path) as second:
        second.execute("PRAGMA busy_timeout = 50")
        with first.transaction():
            first.connection.execute(
                "INSERT INTO coachee_profile (id, display_name, created_at) "
                "VALUES ('p1', 'Coachee', '2026-08-22T00:00:00Z')"
            )
            with pytest.raises(sqlite3.OperationalError):
                second.execute("BEGIN IMMEDIATE")


def test_database_file_holds_no_credential_shaped_value(tmp_path) -> None:
    path = tmp_path / "coach.db"
    with open_coach_database(path) as database:
        with database.transaction():
            database.connection.execute(
                "INSERT INTO coachee_profile (id, display_name, created_at) "
                "VALUES ('p1', 'Coachee', '2026-08-22T00:00:00Z')"
            )
    blob = path.read_bytes()
    for marker in (b"api_key", b"sk-", b"authorization", b"bearer "):
        assert marker not in blob.lower()
