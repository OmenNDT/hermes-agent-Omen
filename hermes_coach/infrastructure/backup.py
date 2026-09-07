"""A copy of the database, taken before anything touches it.

Requirement families: `HC-DATA-*`.

Coaching is where someone writes down what they do not write anywhere else.
Losing that file is not losing data, it is losing part of a thing they had
already finished thinking. Until now nothing in this product copied it: one
SQLite file, one bad migration or one mistyped delete, and it was gone.

Taken at startup, *before* the database is opened and migrated, because the
migration is the most likely thing to damage it and a backup made afterwards
would already be the damaged version.

Deliberately not clever. No compression, no incremental format, no separate
index — just the file, named by the moment it was taken, restorable by copying
it back. A backup a person cannot restore by hand is not a backup they can rely
on when they most need it.
"""

from __future__ import annotations

import shutil
from pathlib import Path


BACKUP_DIRECTORY = "backups"
KEEP = 5

# SQLite in WAL mode keeps committed pages in the sidecar until a checkpoint, so
# a copy of the main file alone can be missing the last transactions. A clean
# close checkpoints and removes these; they exist here only after a crash, which
# is exactly the case a backup is for.
_SIDECARS = ("-wal", "-shm")


def backup_directory(database_path: Path) -> Path:
    return database_path.parent / BACKUP_DIRECTORY


def take(database_path: Path, *, now: str, keep: int = KEEP) -> Path | None:
    """Copy the database aside. Returns the copy, or None if there was nothing.

    Never raises. A machine with a full disk or a read-only directory should
    still be able to open Coach: refusing to start because the *backup* failed
    would turn a precaution into the outage it exists to prevent. The caller
    reports what happened instead.
    """
    try:
        if not database_path.exists():
            # First run. There is nothing to lose yet.
            return None

        directory = backup_directory(database_path)
        directory.mkdir(parents=True, exist_ok=True)

        stamp = now.replace(":", "").replace("-", "")
        target = directory / f"{database_path.stem}-{stamp}{database_path.suffix}"
        # A second start inside the same second must not overwrite the first.
        suffix = 1
        while target.exists():
            target = (
                directory / f"{database_path.stem}-{stamp}-{suffix}{database_path.suffix}"
            )
            suffix += 1

        shutil.copy2(database_path, target)
        for sidecar in _SIDECARS:
            source = database_path.with_name(database_path.name + sidecar)
            if source.exists():
                shutil.copy2(source, target.with_name(target.name + sidecar))

        prune(database_path, keep=keep)
        return target
    except OSError:
        return None


def existing(database_path: Path) -> list[Path]:
    """Backups newest first, by the name the stamp gives them.

    Sorted by filename rather than mtime: the name carries the moment the copy
    was taken, and a file copy or a restore rewrites mtime.
    """
    directory = backup_directory(database_path)
    if not directory.is_dir():
        return []
    pattern = f"{database_path.stem}-*{database_path.suffix}"
    return sorted(directory.glob(pattern), reverse=True)


def prune(database_path: Path, *, keep: int = KEEP) -> int:
    """Drop the oldest copies past `keep`. Returns how many were removed.

    Bounded on purpose: an unbounded backup directory quietly fills the disk,
    and a Coachee who runs out of space loses the live database too — the
    precaution eating the thing it protects.
    """
    removed = 0
    for stale in existing(database_path)[keep:]:
        try:
            stale.unlink()
            for sidecar in _SIDECARS:
                companion = stale.with_name(stale.name + sidecar)
                if companion.exists():
                    companion.unlink()
            removed += 1
        except OSError:
            continue
    return removed
