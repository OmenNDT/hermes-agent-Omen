"""Immutable, versioned migration files.

A published migration is never edited; correcting one means adding the next
version. Filenames are `<zero-padded version>_<slug>.sql` and the version is
parsed from the prefix, so the directory listing is the plan.

There is deliberately no separate `schema.sql`: a fresh database is built by
running every migration, which is the only way a new install and an upgraded
install are guaranteed to end up with the same shape.
"""

from __future__ import annotations

from pathlib import Path

from hermes_coach.infrastructure.sqlite.migration_runner import (
    Migration,
    split_statements,
)


_DIRECTORY = Path(__file__).parent


def _load() -> tuple[Migration, ...]:
    loaded: list[Migration] = []
    for path in sorted(_DIRECTORY.glob("*.sql")):
        prefix, _, _ = path.stem.partition("_")
        loaded.append(
            Migration(
                version=int(prefix),
                identifier=path.stem,
                statements=split_statements(path.read_text(encoding="utf-8")),
            )
        )
    return tuple(loaded)


ALL: tuple[Migration, ...] = _load()

LATEST_VERSION: int = ALL[-1].version if ALL else 0
