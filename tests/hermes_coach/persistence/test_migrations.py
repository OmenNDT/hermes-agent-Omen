"""Migration runner contract.

Requirement family: `HC-DATA-*`; sources `SRC-076…SRC-086`, `SRC-099`.

Migrations are immutable and versioned. A migration either advances both the
data and the recorded version, or neither.
"""

from __future__ import annotations

from collections.abc import Iterator

import sqlite3

import pytest

from hermes_coach.infrastructure.sqlite import migrations
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    connect,
    open_coach_database,
)
from hermes_coach.infrastructure.sqlite.migration_runner import (
    MigrationError,
    Migration,
    current_version,
    migrate,
)


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        yield db


def test_fresh_database_lands_on_the_latest_version(database: CoachDatabase) -> None:
    assert current_version(database.connection) == migrations.LATEST_VERSION


def test_migrations_are_contiguous_and_start_at_one() -> None:
    versions = [migration.version for migration in migrations.ALL]
    assert versions == list(range(1, len(versions) + 1))


def test_migration_ids_are_unique() -> None:
    identifiers = [migration.identifier for migration in migrations.ALL]
    assert len(identifiers) == len(set(identifiers))


def test_rerunning_migrate_is_idempotent(database: CoachDatabase) -> None:
    before = table_snapshot(database.connection)
    migrate(database.connection)
    migrate(database.connection)
    assert current_version(database.connection) == migrations.LATEST_VERSION
    assert table_snapshot(database.connection) == before


def test_every_applied_migration_is_recorded(database: CoachDatabase) -> None:
    rows = database.connection.execute(
        "SELECT version, identifier FROM internal_schema_migration ORDER BY version"
    ).fetchall()
    applied = [(row["version"], row["identifier"]) for row in rows]
    assert applied == [(m.version, m.identifier) for m in migrations.ALL]


def test_a_legacy_database_is_upgraded_through_production_code(tmp_path) -> None:
    """An empty, unversioned file is the version-0 legacy fixture."""
    path = tmp_path / "legacy.db"
    with connect(path) as connection:
        assert current_version(connection) == 0
        migrate(connection)
        assert current_version(connection) == migrations.LATEST_VERSION
        assert "goal" in table_snapshot(connection)


def test_failing_migration_rolls_back_data_and_version(tmp_path) -> None:
    path = tmp_path / "failing.db"
    broken = Migration(
        version=migrations.LATEST_VERSION + 1,
        identifier="9999_broken",
        statements=(
            "CREATE TABLE never_committed (id TEXT PRIMARY KEY)",
            "THIS IS NOT VALID SQL",
        ),
    )
    with connect(path) as connection:
        migrate(connection)
        stable = current_version(connection)
        with pytest.raises(MigrationError):
            migrate(connection, plan=(*migrations.ALL, broken))
        assert current_version(connection) == stable
        assert "never_committed" not in table_snapshot(connection)


def test_failed_postcondition_rolls_back_the_whole_migration(tmp_path) -> None:
    path = tmp_path / "postcondition.db"
    unmet = Migration(
        version=migrations.LATEST_VERSION + 1,
        identifier="9999_postcondition",
        statements=("CREATE TABLE half_applied (id TEXT PRIMARY KEY)",),
        postcondition="SELECT 1 FROM sqlite_master WHERE name = 'table_never_created'",
    )
    with connect(path) as connection:
        migrate(connection)
        stable = current_version(connection)
        with pytest.raises(MigrationError):
            migrate(connection, plan=(*migrations.ALL, unmet))
        assert current_version(connection) == stable
        assert "half_applied" not in table_snapshot(connection)


def test_a_version_ahead_of_the_known_plan_is_refused(tmp_path) -> None:
    """A database written by a newer build must not be silently downgraded."""
    path = tmp_path / "from-the-future.db"
    with connect(path) as connection:
        migrate(connection)
        connection.execute(
            "INSERT INTO internal_schema_migration (version, identifier, applied_at) "
            "VALUES (?, ?, ?)",
            (migrations.LATEST_VERSION + 5, "9999_future", "2099-01-01T00:00:00Z"),
        )
        with pytest.raises(MigrationError, match="newer"):
            migrate(connection)


def test_corrupt_database_surfaces_an_error_instead_of_losing_data(tmp_path) -> None:
    path = tmp_path / "corrupt.db"
    path.write_bytes(b"SQLite format 3\x00" + b"\xde\xad\xbe\xef" * 512)
    with pytest.raises(sqlite3.DatabaseError):
        with connect(path) as connection:
            migrate(connection)


def table_snapshot(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row["name"] for row in rows}
