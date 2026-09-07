"""RPC envelope state: optimistic revision and idempotency.

Requirement families: `HC-PRODUCT`, `HC-DATA-*`; sources `SRC-104…106`.

Both classes live here because they answer the same question from two sides —
"is this command still valid to apply?" Revision catches a command built on a
stale view; the idempotency key catches the same command arriving twice.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


class StaleRevision(RuntimeError):
    """The command was built on a view that has since moved on."""


class SessionRevisionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def current(self, session_id: str) -> int:
        row = self.connection.execute(
            "SELECT revision FROM internal_session_revision WHERE session_id = :id",
            {"id": session_id},
        ).fetchone()
        return row["revision"] if row else 0

    def bump(self, session_id: str, now: str) -> int:
        """Advance and return the new revision. Caller owns the transaction."""
        self.connection.execute(
            "INSERT INTO internal_session_revision (session_id, revision, updated_at) "
            "VALUES (:id, 1, :now) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "revision = revision + 1, updated_at = :now",
            {"id": session_id, "now": now},
        )
        return self.current(session_id)

    def require(self, session_id: str, expected: int) -> None:
        """Refuse anything but an exact match.

        Not `expected <= current`: a client claiming a revision that never
        happened is as wrong as one lagging behind, and both mean its view of
        the session cannot be trusted.
        """
        actual = self.current(session_id)
        if expected != actual:
            raise StaleRevision(
                f"stale revision for {session_id}: command has {expected}, "
                f"session is at {actual}"
            )


class IdempotencyRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def recall(self, idempotency_key: str) -> Any | None:
        row = self.connection.execute(
            "SELECT result_json FROM internal_rpc_command "
            "WHERE idempotency_key = :key",
            {"key": idempotency_key},
        ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def remember(
        self,
        idempotency_key: str,
        *,
        method: str,
        session_id: str | None,
        result: Any,
        now: str,
    ) -> None:
        """Record the outcome. A duplicate key raises rather than overwriting.

        Overwriting would hide the very thing this table exists to detect.
        """
        self.connection.execute(
            "INSERT INTO internal_rpc_command "
            "(idempotency_key, method, session_id, result_json, created_at) "
            "VALUES (:key, :method, :session_id, :result_json, :now)",
            {
                "key": idempotency_key,
                "method": method,
                "session_id": session_id,
                "result_json": json.dumps(result, ensure_ascii=False, sort_keys=True),
                "now": now,
            },
        )
