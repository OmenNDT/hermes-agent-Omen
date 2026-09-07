"""Versioned, immutable SQLite migrations.

Requirement family: `HC-DATA-*`; sources `SRC-076…SRC-086`, `SRC-099`.

A migration advances DDL, postcondition and recorded version inside one
`BEGIN IMMEDIATE` transaction. Partial advance is not representable: a failure
rolls back the data and the version together.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field


VERSION_TABLE = "internal_schema_migration"

_CREATE_VERSION_TABLE = f"""
CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
    version INTEGER PRIMARY KEY,
    identifier TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL
)
"""


class MigrationError(RuntimeError):
    """A migration could not be applied; the database is unchanged."""


@dataclass(frozen=True)
class Migration:
    version: int
    identifier: str
    statements: tuple[str, ...]
    # A postcondition is a SELECT that must return at least one row once the
    # statements have run. It catches DDL that succeeded but did not produce
    # the shape the next migration assumes.
    postcondition: str | None = field(default=None)


def split_statements(script: str) -> tuple[str, ...]:
    """Split a migration file into individually executable statements.

    Statements are terminated by a line ending in `;`, and `--` comment lines
    are dropped. Compound statements (triggers with `BEGIN ... END;`) are not
    supported; add an explicit delimiter here on the first migration that needs
    one rather than letting this splitter guess.
    """
    statements: list[str] = []
    buffer: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(buffer).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            buffer = []
    if buffer:
        raise ValueError("migration ends with an unterminated statement")
    return tuple(statements)


def current_version(connection: sqlite3.Connection) -> int:
    """Return the highest applied version, or 0 for an unversioned database."""
    if not _version_table_exists(connection):
        return 0
    row = connection.execute(f"SELECT MAX(version) AS version FROM {VERSION_TABLE}").fetchone()
    return row["version"] or 0


def migrate(
    connection: sqlite3.Connection,
    *,
    plan: Sequence[Migration] | None = None,
    now: str | None = None,
) -> int:
    """Apply every pending migration in order and return the resulting version."""
    if plan is None:
        from hermes_coach.infrastructure.sqlite import migrations

        plan = migrations.ALL

    ordered = sorted(plan, key=lambda migration: migration.version)
    connection.execute(_CREATE_VERSION_TABLE)

    version = current_version(connection)
    highest_known = ordered[-1].version if ordered else 0
    if version > highest_known:
        raise MigrationError(
            f"database is at version {version}, newer than the highest known "
            f"migration {highest_known}; refusing to downgrade"
        )

    for migration in ordered:
        if migration.version <= version:
            continue
        _apply(connection, migration, now=now)
        version = migration.version
    return version


def _apply(
    connection: sqlite3.Connection, migration: Migration, *, now: str | None
) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        for statement in migration.statements:
            connection.execute(statement)
        if migration.postcondition is not None:
            if connection.execute(migration.postcondition).fetchone() is None:
                raise MigrationError(
                    f"migration {migration.identifier} failed its postcondition"
                )
        connection.execute(
            f"INSERT INTO {VERSION_TABLE} (version, identifier, applied_at) "
            "VALUES (?, ?, ?)",
            (migration.version, migration.identifier, now or _timestamp(connection)),
        )
    except Exception as error:
        connection.execute("ROLLBACK")
        if isinstance(error, MigrationError):
            raise
        raise MigrationError(
            f"migration {migration.identifier} failed and was rolled back: {error}"
        ) from error
    connection.execute("COMMIT")


def _timestamp(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now') AS stamp"
    ).fetchone()
    return row["stamp"]


def _version_table_exists(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (VERSION_TABLE,),
    ).fetchone()
    return row is not None
