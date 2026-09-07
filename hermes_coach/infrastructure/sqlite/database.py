"""Connection lifecycle for the Coach SQLite store.

Requirement families: `HC-DATA-*`, `HC-PRIVACY`; sources `SRC-076…SRC-086`,
`SRC-091`.

`secure_delete` is hygiene, not encryption: the MVP database is unencrypted at
rest and the product discloses that. No provider credential is ever written
here.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from hermes_coach.infrastructure.sqlite.migration_runner import migrate


BUSY_TIMEOUT_MS = 5_000

# Preferred first, then the fallback for filesystems that refuse WAL (some
# network shares). Opening must degrade, never fail.
JOURNAL_MODES = ("wal", "delete")


class CoachDatabase:
    """An open, migrated Coach database with explicit transaction control."""

    def __init__(self, connection: sqlite3.Connection, journal_mode: str) -> None:
        self.connection = connection
        self.journal_mode = journal_mode
        self._closed = False

    def __enter__(self) -> CoachDatabase:
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a unit of work under an immediate write lock.

        Immediate, not deferred: a deferred lock upgrades mid-transaction and
        two writers that both read first can deadlock instead of one waiting.
        """
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        self.connection.execute("COMMIT")

    def close(self) -> None:
        """Close once, idempotently, checkpointing WAL so the file is complete."""
        if self._closed:
            return
        self._closed = True
        try:
            if self.journal_mode == "wal":
                self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            # A checkpoint failure must not prevent the handle from closing.
            pass
        self.connection.close()


def open_coach_database(path: Path | str) -> CoachDatabase:
    """Open the store at `path`, creating and migrating it when needed."""
    connection, journal_mode = _connect(path)
    try:
        migrate(connection)
    except Exception:
        connection.close()
        raise
    return CoachDatabase(connection, journal_mode)


@contextmanager
def connect(path: Path | str) -> Iterator[sqlite3.Connection]:
    """Yield a configured connection without applying migrations."""
    connection, _ = _connect(path)
    try:
        yield connection
    finally:
        connection.close()


def _connect(path: Path | str) -> tuple[sqlite3.Connection, str]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None hands transaction control to the caller; services
    # own the boundaries, so the driver must not open one implicitly.
    #
    # check_same_thread=False because the connection is opened and migrated on
    # the startup thread and then used by the server's event-loop thread. That
    # is safe here: `sqlite3.threadsafety == 3` (serialized), Coach is a
    # single-writer local app, and `transaction()` takes an immediate lock, so
    # two writers queue rather than interleave.
    connection = sqlite3.connect(target, isolation_level=None, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA synchronous = FULL")
    connection.execute("PRAGMA secure_delete = ON")
    return connection, _apply_journal_mode(connection)


def _apply_journal_mode(connection: sqlite3.Connection) -> str:
    for mode in JOURNAL_MODES:
        try:
            row = connection.execute(f"PRAGMA journal_mode = {mode}").fetchone()
        except sqlite3.OperationalError:
            continue
        if row is not None and str(row[0]).lower() == mode:
            return mode
    row = connection.execute("PRAGMA journal_mode").fetchone()
    return str(row[0]).lower()
