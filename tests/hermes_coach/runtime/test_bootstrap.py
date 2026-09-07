"""Startup: profile, lock, migrations, retention, handshake.

Requirement families: `HC-PRODUCT`, `HC-PRIVACY`; sources `SRC-100`,
`SRC-104…106`.

The handshake is a promise: by the time the UI has a port and a token, the
database is migrated and overdue data is already gone. Anything the client can
reach has passed retention first.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from hermes_coach.bootstrap import (
    ProfileLocked,
    coach_profile,
    disclosure,
    profile_lock,
    select_port,
    start,
)
from hermes_coach.infrastructure.sqlite import migrations


REPO_ROOT = Path(__file__).parents[3]
NOW = "2026-06-01T00:00:00Z"


@pytest.fixture
def hermes_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def test_the_profile_lives_under_the_hermes_home(hermes_home: Path) -> None:
    profile = coach_profile()
    assert profile.root.is_relative_to(hermes_home)
    assert profile.database_path.name == "coach.db"


def test_the_coach_profile_is_separate_from_hermes_own_state(
    hermes_home: Path,
) -> None:
    """Coach owns its data; it must not sit alongside Hermes' own files."""
    profile = coach_profile()
    assert profile.root.parent.name == "coach"
    assert profile.root != hermes_home


def test_named_profiles_do_not_share_a_directory(hermes_home: Path) -> None:
    assert coach_profile("work").root != coach_profile("personal").root


def test_starting_creates_the_profile_directory(hermes_home: Path) -> None:
    profile = coach_profile()
    handshake, database = start(profile, port=0, now=NOW)
    try:
        assert profile.root.is_dir()
        assert profile.database_path.is_file()
    finally:
        database.close()


def test_the_handshake_reports_a_migrated_schema(hermes_home: Path) -> None:
    handshake, database = start(coach_profile(), port=0, now=NOW)
    try:
        assert handshake.schema_version == migrations.LATEST_VERSION
    finally:
        database.close()


def test_the_handshake_carries_a_usable_port_and_token(hermes_home: Path) -> None:
    handshake, database = start(coach_profile(), port=0, now=NOW)
    try:
        assert 1024 < handshake.port < 65536
        assert len(handshake.token) >= 32
    finally:
        database.close()


def test_a_requested_port_is_honoured(hermes_home: Path) -> None:
    chosen = select_port(0)
    handshake, database = start(coach_profile(), port=chosen, now=NOW)
    try:
        assert handshake.port == chosen
    finally:
        database.close()


def test_each_start_mints_a_new_token(hermes_home: Path) -> None:
    """The token is per process; it is never written to the profile."""
    first, first_db = start(coach_profile("a"), port=0, now=NOW)
    second, second_db = start(coach_profile("b"), port=0, now=NOW)
    try:
        assert first.token != second.token
    finally:
        first_db.close()
        second_db.close()


def test_the_token_is_not_written_anywhere_under_the_profile(
    hermes_home: Path,
) -> None:
    profile = coach_profile()
    handshake, database = start(profile, port=0, now=NOW)
    try:
        database.close()
        for path in profile.root.rglob("*"):
            if path.is_file():
                assert handshake.token.encode() not in path.read_bytes()
    finally:
        pass


def test_retention_runs_before_the_handshake_is_returned(hermes_home: Path) -> None:
    """Nothing the client can reach has skipped its deadline."""
    profile = coach_profile()
    handshake, database = start(profile, port=0, now="2026-01-01T00:00:00Z")
    try:
        with database.transaction():
            database.connection.execute(
                "INSERT INTO coaching_session (id, started_at, coaching_stage) "
                "VALUES ('session-1', '2026-01-01T00:00:00Z', 'goal')"
            )
            database.connection.execute(
                "INSERT INTO session_message "
                "(id, session_id, sequence_no, role, content, created_at, expires_at) "
                "VALUES ('m-1', 'session-1', 0, 'coachee', 'cũ', "
                "'2026-01-01T00:00:00Z', '2026-02-01T00:00:00Z')"
            )
    finally:
        database.close()

    # Reopen well past the message's expiry: startup must have swept it.
    reopened_handshake, reopened = start(profile, port=0, now="2026-06-01T00:00:00Z")
    try:
        assert reopened_handshake.retention_purged >= 1
        remaining = reopened.connection.execute(
            "SELECT COUNT(*) AS total FROM session_message"
        ).fetchone()["total"]
        assert remaining == 0
    finally:
        reopened.close()


def test_the_disclosure_says_the_store_is_not_encrypted() -> None:
    assert disclosure()["encrypted_at_rest"] is False
    assert disclosure()["version"]


def test_the_handshake_carries_the_disclosure(hermes_home: Path) -> None:
    """It must reach the user before the first profile is written to."""
    handshake, database = start(coach_profile(), port=0, now=NOW)
    try:
        assert handshake.disclosure["encrypted_at_rest"] is False
    finally:
        database.close()


def test_the_lock_is_held_while_the_profile_is_open(hermes_home: Path) -> None:
    profile = coach_profile()
    profile.root.mkdir(parents=True, exist_ok=True)
    with profile_lock(profile):
        assert profile.lock_path.is_file()


def test_a_second_writer_in_another_process_is_refused(hermes_home: Path) -> None:
    """One backend per profile. Two would race on the same SQLite file."""
    profile = coach_profile()
    profile.root.mkdir(parents=True, exist_ok=True)

    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from hermes_coach.bootstrap import ProfileLocked, coach_profile, profile_lock
        try:
            with profile_lock(coach_profile()):
                print("ACQUIRED")
        except ProfileLocked:
            print("REFUSED")
        """
    )

    with profile_lock(profile):
        completed = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={**os.environ, "HERMES_HOME": str(hermes_home)},
        )
    assert completed.returncode == 0, completed.stderr
    assert "REFUSED" in completed.stdout


def test_the_lock_is_released_when_the_holder_exits(hermes_home: Path) -> None:
    """A crash must not leave a profile permanently unopenable."""
    profile = coach_profile()
    profile.root.mkdir(parents=True, exist_ok=True)

    script = textwrap.dedent(
        f"""
        import os, sys
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from hermes_coach.bootstrap import coach_profile, profile_lock
        lock = profile_lock(coach_profile())
        lock.__enter__()
        os._exit(0)
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "HERMES_HOME": str(hermes_home)},
    )
    assert completed.returncode == 0, completed.stderr

    # The OS dropped the lock with the process; no manual cleanup needed.
    with profile_lock(profile):
        pass


def test_two_different_profiles_can_be_open_at_once(hermes_home: Path) -> None:
    work, personal = coach_profile("work"), coach_profile("personal")
    work.root.mkdir(parents=True, exist_ok=True)
    personal.root.mkdir(parents=True, exist_ok=True)
    with profile_lock(work), profile_lock(personal):
        pass


def test_select_port_returns_a_free_port() -> None:
    import socket

    port = select_port(0)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_the_bootstrap_binds_nothing_beyond_loopback(hermes_home: Path) -> None:
    handshake, database = start(coach_profile(), port=0, now=NOW)
    try:
        assert handshake.guard.bind_host == "127.0.0.1"
        assert handshake.guard.port == handshake.port
    finally:
        database.close()
