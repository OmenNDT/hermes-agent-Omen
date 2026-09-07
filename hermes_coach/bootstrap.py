"""Bring one Coach profile up.

Requirement families: `HC-PRODUCT`, `HC-PRIVACY`; sources `SRC-100`,
`SRC-104…106`.

The handshake is a promise about ordering: by the time the caller holds a port
and a token, the database has been migrated and retention has already swept.
Nothing the UI can reach has skipped its deadline.

The profile sits under the Hermes home so a user has one place to look, but it
is a directory of its own. Coach never reads or writes Hermes' own state.
"""

from __future__ import annotations

import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from hermes_constants import get_hermes_home

from hermes_coach.api.security import LoopbackGuard, new_token
from hermes_coach.application.retention_service import RetentionService
from hermes_coach.infrastructure import backup
from hermes_coach.infrastructure.sqlite.database import CoachDatabase, open_coach_database
from hermes_coach.infrastructure.sqlite.migration_runner import current_version


DISCLOSURE_VERSION = "2026-01"

DEFAULT_PROFILE = "default"

LOOPBACK = "127.0.0.1"


class ProfileLocked(RuntimeError):
    """Another process already holds this profile."""


class PortUnavailable(RuntimeError):
    """The requested port is already taken.

    Reported before anything is printed, because the alternative is worse than a
    crash: the launcher used to announce a URL for a port it had not tried to
    bind, uvicorn then failed on it, and the operator was left with a link that
    answers — served by the older Coach process still holding that port, whose
    token theirs does not match. Every WebSocket closed with no explanation.
    """


@dataclass(frozen=True)
class CoachProfile:
    name: str
    root: Path

    @property
    def database_path(self) -> Path:
        return self.root / "coach.db"

    @property
    def lock_path(self) -> Path:
        return self.root / "profile.lock"


@dataclass(frozen=True)
class Handshake:
    """What the UI needs, and nothing it does not."""

    port: int
    token: str
    profile_root: str
    schema_version: int
    retention_purged: int
    #: Where this start put its copy of the database, or None on a first run
    #: (nothing to copy) or when the copy could not be written.
    backup_path: str | None
    #: True when there *was* a database and it could not be copied. A backup
    #: that stops working without saying so is worth less than none, because
    #: the Coachee is relying on one.
    backup_failed: bool
    disclosure: dict
    guard: LoopbackGuard


def coach_profile(name: str = DEFAULT_PROFILE) -> CoachProfile:
    return CoachProfile(name=name, root=get_hermes_home() / "coach" / name)


def disclosure() -> dict:
    return {
        "encrypted_at_rest": False,
        "note": (
            "Dữ liệu Coach lưu trên máy này và không được mã hoá. "
            "Người hoặc tiến trình có quyền đọc tệp đều đọc được nội dung."
        ),
        "version": DISCLOSURE_VERSION,
    }


def select_port(requested: int) -> int:
    """Resolve to a loopback port this process can actually serve on.

    The port is resolved up front so the handshake can state it, and so the
    guard can pin the Host header to it before anything is served. A requested
    port is bind-tested rather than taken on trust — a port that is stated but
    cannot be bound is how the URL and the server come apart.

    The probe closes before uvicorn opens the real listener, so there is a
    window in which something else could take the port. Losing that race gives
    an ordinary bind error from uvicorn; not probing at all gave a URL that
    silently pointed at another process, which is the failure worth removing.
    """
    if requested:
        with socket.socket() as probe:
            try:
                probe.bind((LOOPBACK, requested))
            except OSError as taken:
                raise PortUnavailable(
                    f"port {requested} is already in use — another Coach may still "
                    f"be running; close it or pass a different --port"
                ) from taken
        return requested
    with socket.socket() as probe:
        probe.bind((LOOPBACK, 0))
        return probe.getsockname()[1]


@contextmanager
def profile_lock(profile: CoachProfile) -> Iterator[None]:
    """Hold an exclusive OS lock on the profile for as long as this runs.

    An OS-level lock, not a pid file: the kernel drops it when the process
    dies, so a crash can never leave a profile permanently unopenable. Two
    writers on one SQLite file is the thing being prevented.
    """
    profile.root.mkdir(parents=True, exist_ok=True)
    handle = profile.lock_path.open("a+b")
    try:
        _acquire(handle)
    except OSError as busy:
        handle.close()
        raise ProfileLocked(
            f"another Coach process already holds profile {profile.name!r}"
        ) from busy
    try:
        yield
    finally:
        try:
            _release(handle)
        finally:
            handle.close()


def start(
    profile: CoachProfile, *, port: int = 0, now: str
) -> tuple[Handshake, CoachDatabase]:
    """Open, migrate, sweep, then hand back the handshake and the database.

    The caller owns the returned database and must close it. The profile lock
    belongs to the process that serves the profile, so it is taken by the
    launcher around this call rather than here — `start` is also used to
    inspect a profile in tests.
    """
    profile.root.mkdir(parents=True, exist_ok=True)

    # Before the database is opened, and therefore before migrations run: a
    # migration is the likeliest thing to damage the file, and a copy taken
    # afterwards would already be the damaged one. `take` never raises — a
    # failed backup must not become the outage it exists to prevent.
    #
    # But it must not be silent either. `take` returns None both for "first run,
    # nothing to copy" and for "could not write", and those are opposite facts:
    # one is fine, the other means the safety net has quietly stopped existing.
    # The caller is the only place that can tell them apart, so it does.
    had_database = profile.database_path.exists()
    backed_up = backup.take(profile.database_path, now=now)

    # Migrations run inside open_coach_database.
    database = open_coach_database(profile.database_path)
    try:
        swept = RetentionService(database).run(now=now)
        resolved_port = select_port(port)
        token = new_token()
        handshake = Handshake(
            port=resolved_port,
            token=token,
            profile_root=str(profile.root),
            schema_version=current_version(database.connection),
            retention_purged=swept.total_purged,
            backup_path=str(backed_up) if backed_up else None,
            backup_failed=had_database and backed_up is None,
            disclosure=disclosure(),
            guard=LoopbackGuard(token=token, port=resolved_port, bind_host=LOOPBACK),
        )
    except Exception:
        database.close()
        raise
    return handshake, database


def use_selector_event_loop() -> None:
    """Windows needs the Selector loop for the server stack Coach uses.

    The Proactor loop is the 3.8+ default on Windows and breaks parts of that
    stack; this is the same choice Hermes makes for its own server.
    """
    if sys.platform == "win32":
        import asyncio

        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


if sys.platform == "win32":
    import msvcrt

    def _acquire(handle) -> None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _release(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _acquire(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
