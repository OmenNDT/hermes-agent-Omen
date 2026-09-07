"""Shared repository plumbing and the one active-scope definition.

Requirement families: `HC-DATA-*`, `HC-PRIVACY`, `HC-RECORDS`.

The phase risk is a single query that forgets to exclude deleted or expired
rows. Every active read composes its WHERE clause from the helpers here rather
than hand-writing the predicate, so the rule lives in one place.
"""

from __future__ import annotations

import sqlite3
from typing import Any, ClassVar, TypeVar

from hermes_coach.domain.models import ImmutableModel


RowModel = TypeVar("RowModel", bound=ImmutableModel)


def not_in_trash(alias: str) -> str:
    """Exclude rows carrying a Trash entry that has not been restored.

    A purged entry still hides the row: purging closes the entry but the row
    only disappears when it is actually deleted, and it must not resurface in
    the window between.
    """
    return (
        "NOT EXISTS (SELECT 1 FROM trash_entry AS trash "
        "WHERE trash.entity_type = :trash_entity_type "
        f"AND trash.entity_id = {alias}.id "
        "AND trash.restored_at IS NULL)"
    )


def not_expired(alias: str, column: str = "expires_at") -> str:
    """A NULL expiry means durable, never 'expired at the epoch'."""
    return f"({alias}.{column} IS NULL OR {alias}.{column} > :now)"


class Repository:
    """Base for a table-owning repository.

    Repositories own SQL and return domain records. They never open or commit a
    transaction — a service spanning several repositories owns that boundary,
    so a partial write cannot be committed by one of its participants.
    """

    table: ClassVar[str]
    entity_type: ClassVar[str]
    row_model: ClassVar[type[ImmutableModel]]

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def insert(self, row: ImmutableModel) -> None:
        values = row.model_dump()
        columns = ", ".join(values)
        placeholders = ", ".join(f":{name}" for name in values)
        self.connection.execute(
            f"INSERT INTO {self.table} ({columns}) VALUES ({placeholders})",
            _bindable(values),
        )

    def select(
        self,
        where: str,
        params: dict[str, Any],
        order_by: str = "",
        limit: int | None = None,
    ) -> list[Any]:
        """`limit` is bound, never interpolated, and only meaningful with an
        `order_by` — a limit over an unordered read returns an arbitrary slice."""
        clause = f" ORDER BY {order_by}" if order_by else ""
        if limit is not None:
            clause += " LIMIT :limit"
            # Bound here rather than by the caller. Asking every caller to pass
            # `limit` twice — once as an argument and once into `params` — is a
            # trap that fails at the database, not at the call site.
            params = {**params, "limit": limit}
        rows = self.connection.execute(
            f"SELECT * FROM {self.table} AS entity WHERE {where}{clause}", params
        ).fetchall()
        return [self.row_model.model_validate(dict(row)) for row in rows]

    def select_one(self, where: str, params: dict[str, Any]) -> Any | None:
        found = self.select(where, params)
        return found[0] if found else None

    def trash_params(self) -> dict[str, Any]:
        return {"trash_entity_type": self.entity_type}


def _bindable(values: dict[str, Any]) -> dict[str, Any]:
    """sqlite3 has no bool adapter; store the schema's 0/1 integers."""
    return {
        key: int(value) if isinstance(value, bool) else value
        for key, value in values.items()
    }
