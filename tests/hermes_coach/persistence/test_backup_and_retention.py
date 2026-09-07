"""The copy taken before anything touches the file, and the words now kept.

Requirement families: `HC-DATA-*`, `HC-PRIVACY`.

Two changes made when Quantum asked whether the product was safe to start using
for real. Both are about the same thing: coaching is where someone writes down
what they write nowhere else, and this product was casual with it in two ways —
nothing ever copied the database, and the transcript was deleted on a 90-day
clock while the conclusions drawn from it lived forever.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from hermes_coach.application.retention_service import RetentionService
from hermes_coach.infrastructure import backup
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)
from hermes_coach.infrastructure.sqlite.migration_runner import current_version


NOW = "2026-03-01T00:00:00Z"


@pytest.fixture
def database_path(tmp_path) -> Path:
    return tmp_path / "coach.db"


@pytest.fixture
def database(database_path) -> Iterator[CoachDatabase]:
    with open_coach_database(database_path) as db:
        with db.transaction():
            db.connection.execute(
                "INSERT INTO coaching_session (id, started_at, coaching_stage) "
                "VALUES ('s1', ?, 'goal')",
                (NOW,),
            )
        yield db


def add_message(
    database: CoachDatabase, message_id: str, *, expires_at: str | None, created_at: str
) -> None:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO session_message "
            "(id, session_id, sequence_no, role, content, created_at, expires_at) "
            "VALUES (?, 's1', ?, 'coachee', 'xin chào', ?, ?)",
            (message_id, len(message_id), created_at, expires_at),
        )


def messages(database: CoachDatabase) -> set[str]:
    return {
        row["id"]
        for row in database.connection.execute("SELECT id FROM session_message")
    }


class TestTheTranscriptIsKept:
    def test_a_durable_line_survives_a_sweep_long_after_the_old_window(
        self, database: CoachDatabase
    ) -> None:
        """The change, stated as the behaviour it produces."""
        add_message(database, "m1", expires_at=None, created_at="2020-01-01T00:00:00Z")
        RetentionService(database).run(now=NOW)
        assert messages(database) == {"m1"}

    def test_a_line_still_carrying_a_deadline_is_honoured(
        self, database: CoachDatabase
    ) -> None:
        """Nothing here says "never delete a transcript" — it says NULL is
        durable. A row someone deliberately gave a deadline still gets one."""
        add_message(
            database,
            "m1",
            expires_at="2026-01-01T00:00:00Z",
            created_at="2025-12-01T00:00:00Z",
        )
        RetentionService(database).run(now=NOW)
        assert messages(database) == set()

    def test_pending_candidates_are_still_swept(
        self, database: CoachDatabase
    ) -> None:
        """Only the transcript changed. An unresolved proposal is temporary."""
        with database.transaction():
            database.connection.execute(
                "INSERT INTO candidate_record "
                "(id, session_id, record_type, payload_json, status, created_at) "
                "VALUES ('c1', 's1', 'insight', '{}', 'pending', '2020-01-01T00:00:00Z')"
            )
        RetentionService(database).run(now=NOW)
        remaining = database.connection.execute(
            "SELECT COUNT(*) AS n FROM candidate_record"
        ).fetchone()["n"]
        assert remaining == 0


class TestTheBackfill:
    def test_lines_written_before_the_change_lose_their_deadline(
        self, database_path: Path
    ) -> None:
        """Otherwise the promise holds only for conversations after the upgrade
        — silently true for new data and silently false for old, which is worse
        than not making it.

        The old database is built by stopping the migration plan at 0005 rather
        than by deleting version rows from a current one: re-running a
        `CREATE TABLE` is not idempotent, so faking the version backwards only
        produces a collision. This is what a real pre-0006 install looks like.
        """
        import sqlite3

        from hermes_coach.infrastructure.sqlite import migrations
        from hermes_coach.infrastructure.sqlite.migration_runner import migrate

        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        before_the_change = [m for m in migrations.ALL if m.version <= 5]
        migrate(connection, plan=before_the_change, now=NOW)
        connection.execute(
            "INSERT INTO coaching_session (id, started_at, coaching_stage) "
            "VALUES ('s1', ?, 'goal')",
            (NOW,),
        )
        connection.execute(
            "INSERT INTO session_message "
            "(id, session_id, sequence_no, role, content, created_at, expires_at) "
            "VALUES ('m1', 's1', 0, 'coachee', 'xin chào', ?, ?)",
            (NOW, "2026-06-01T00:00:00Z"),
        )
        connection.commit()
        connection.close()

        with open_coach_database(database_path) as database:
            stamp = database.connection.execute(
                "SELECT expires_at FROM session_message WHERE id = 'm1'"
            ).fetchone()["expires_at"]
            assert stamp is None
            assert current_version(database.connection) >= 6


class TestTheBackup:
    def test_a_first_run_has_nothing_to_copy(self, database_path: Path) -> None:
        assert backup.take(database_path, now=NOW) is None

    def test_a_copy_is_taken_and_holds_the_data(
        self, database: CoachDatabase, database_path: Path
    ) -> None:
        add_message(database, "m1", expires_at=None, created_at=NOW)
        database.close()

        copy = backup.take(database_path, now=NOW)
        assert copy is not None and copy.exists()
        with open_coach_database(copy) as restored:
            assert messages(restored) == {"m1"}

    def test_the_copy_is_restorable_by_hand(
        self, database: CoachDatabase, database_path: Path
    ) -> None:
        """A backup someone cannot restore by copying a file back is not one
        they can rely on at the moment they need it."""
        database.close()
        copy = backup.take(database_path, now=NOW)
        assert copy is not None
        assert copy.suffix == database_path.suffix
        assert copy.parent.name == backup.BACKUP_DIRECTORY

    def test_two_starts_in_the_same_second_do_not_overwrite_each_other(
        self, database: CoachDatabase, database_path: Path
    ) -> None:
        database.close()
        first = backup.take(database_path, now=NOW)
        second = backup.take(database_path, now=NOW)
        assert first != second
        assert first.exists() and second.exists()

    def test_only_the_five_newest_are_kept(
        self, database: CoachDatabase, database_path: Path
    ) -> None:
        """Unbounded backups quietly fill the disk, and a Coachee out of space
        loses the live database too — the precaution eating what it protects."""
        database.close()
        for day in range(1, 9):
            backup.take(database_path, now=f"2026-03-0{day}T00:00:00Z")
        kept = backup.existing(database_path)
        assert len(kept) == 5
        # Newest kept, oldest dropped.
        assert "20260308" in kept[0].name
        assert not any("20260301" in path.name for path in kept)

    def test_a_directory_it_cannot_write_does_not_stop_the_app(
        self, database: CoachDatabase, database_path: Path, monkeypatch
    ) -> None:
        """Refusing to start because the *backup* failed would turn a
        precaution into the outage it exists to prevent."""
        database.close()

        def refuse(*args, **kwargs):
            raise OSError("read-only file system")

        monkeypatch.setattr(backup.shutil, "copy2", refuse)
        assert backup.take(database_path, now=NOW) is None

    def test_the_sidecar_travels_with_the_file(
        self, database: CoachDatabase, database_path: Path
    ) -> None:
        """WAL keeps committed pages beside the database until a checkpoint, so
        a copy of the main file alone can be missing the last transactions."""
        database.close()
        sidecar = database_path.with_name(database_path.name + "-wal")
        sidecar.write_bytes(b"pretend-wal")

        copy = backup.take(database_path, now=NOW)
        assert copy is not None
        assert copy.with_name(copy.name + "-wal").read_bytes() == b"pretend-wal"


class TestStartupTakesOne:
    def test_a_second_start_leaves_a_copy_of_the_first(self, tmp_path) -> None:
        """The end-to-end shape: this is what protects a bad migration."""
        from hermes_coach.bootstrap import CoachProfile, start

        profile = CoachProfile(name="test", root=tmp_path / "coach")
        first, database = start(profile, now=NOW)
        assert first.backup_path is None  # nothing existed yet
        database.close()

        second, database = start(profile, now="2026-03-02T00:00:00Z")
        try:
            assert second.backup_path is not None
            assert Path(second.backup_path).exists()
            assert second.backup_failed is False
        finally:
            database.close()

    def test_a_first_run_is_not_reported_as_a_failure(self, tmp_path) -> None:
        """Nothing to copy is not the same fact as could not copy."""
        from hermes_coach.bootstrap import CoachProfile, start

        profile = CoachProfile(name="test", root=tmp_path / "coach")
        handshake, database = start(profile, now=NOW)
        try:
            assert handshake.backup_path is None
            assert handshake.backup_failed is False
        finally:
            database.close()

    def test_a_backup_that_cannot_be_written_is_reported(
        self, tmp_path, monkeypatch
    ) -> None:
        """The failure mode that matters.

        A backup that stops working without saying so is worth less than no
        backup at all: the Coachee is relying on one, and the first time they
        find out is the time they needed it.
        """
        from hermes_coach.bootstrap import CoachProfile, start

        profile = CoachProfile(name="test", root=tmp_path / "coach")
        _, database = start(profile, now=NOW)
        database.close()

        def refuse(*args, **kwargs):
            raise OSError("read-only file system")

        monkeypatch.setattr(backup.shutil, "copy2", refuse)
        handshake, database = start(profile, now="2026-03-02T00:00:00Z")
        try:
            assert handshake.backup_path is None
            assert handshake.backup_failed is True
        finally:
            database.close()
