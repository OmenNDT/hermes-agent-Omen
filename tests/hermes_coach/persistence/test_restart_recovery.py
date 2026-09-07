"""Recovery across a real process restart.

Requirement families: `HC-PROCESS`, `HC-DATA-*`, `HC-CHECKIN`; sources
`SRC-061`, `SRC-081`, `SRC-082`, `SRC-076…086`.

Earlier phases reopened the database inside one interpreter, which cannot catch
state that only lives in a process — an unchecked WAL, a cached connection, an
in-memory registry. These tests write from a genuine child process and read back
from the parent, including one child that dies without ever closing cleanly.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from hermes_coach.application.session_recovery_service import SessionRecoveryService
from hermes_coach.contracts.runtime_contract import CoachingStage
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


REPO_ROOT = Path(__file__).parents[3]

NOW = "2026-01-01T00:00:00Z"
LATER = "2026-01-02T00:00:00Z"

PROFILE = "profile-1"
SESSION = "session-1"


def run_child(database_path: Path, body: str, *, clean_exit: bool = True) -> None:
    """Execute `body` in a separate interpreter against the same database file."""
    epilogue = "" if clean_exit else "\nimport os\nos._exit(0)\n"
    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from hermes_coach.infrastructure.sqlite.database import open_coach_database
        from hermes_coach.domain.records import *
        from hermes_coach.infrastructure.repositories.goal_repository import (
            GoalRepository,
        )
        from hermes_coach.infrastructure.repositories.memory_repository import (
            MemoryRepository,
        )
        from hermes_coach.infrastructure.repositories.gate_repository import (
            GateRepository,
        )
        from hermes_coach.infrastructure.repositories.coaching_session_repository import (
            CoachingSessionRepository,
        )
        from hermes_coach.infrastructure.repositories.check_in_repository import (
            CheckInRepository,
        )
        from hermes_coach.infrastructure.repositories.commitment_repository import (
            CommitmentRepository,
        )

        database = open_coach_database({str(database_path)!r})
        """
    )
    script += textwrap.dedent(body)
    if clean_exit:
        script += "\ndatabase.close()\n"
    else:
        script += epilogue

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": "0", "TZ": "UTC"},
    )
    assert completed.returncode == 0, completed.stderr


SEED = f"""
with database.transaction():
    database.connection.execute(
        "INSERT INTO coachee_profile (id, display_name, created_at) "
        "VALUES ('{PROFILE}', 'Coachee', '{NOW}')"
    )
    CoachingSessionRepository(database.connection).start(
        CoachingSessionRow(
            id='{SESSION}',
            started_at='{NOW}',
            coaching_stage='goal',
            intention='Chuyển vai trò',
        )
    )
"""


@pytest.fixture
def database_path(tmp_path) -> Path:
    return tmp_path / "coach.db"


@pytest.fixture
def reopened(database_path: Path) -> Iterator[CoachDatabase]:
    with open_coach_database(database_path) as db:
        yield db


def recovery(database: CoachDatabase) -> SessionRecoveryService:
    return SessionRecoveryService(database, profile_id=PROFILE)


def test_a_confirmed_record_written_by_another_process_survives(
    database_path: Path, reopened: CoachDatabase
) -> None:
    run_child(
        database_path,
        SEED
        + f"""
with database.transaction():
    GoalRepository(database.connection).add(
        GoalRow(
            id='goal-1',
            profile_id='{PROFILE}',
            title='Chuyển sang vai trò kiến trúc sư',
            status='active',
            source_session_id='{SESSION}',
            confirmed_at='{NOW}',
            created_at='{NOW}',
        )
    )
""",
    )
    state = recovery(reopened).recover(SESSION)
    assert [goal.id for goal in state.goals] == ["goal-1"]
    assert state.goals[0].title == "Chuyển sang vai trò kiến trúc sư"


def test_the_current_stage_survives(
    database_path: Path, reopened: CoachDatabase
) -> None:
    run_child(
        database_path,
        SEED
        + f"""
with database.transaction():
    CoachingSessionRepository(database.connection).set_stage(
        '{SESSION}', 'options'
    )
""",
    )
    state = recovery(reopened).recover(SESSION)
    assert state.current_stage is CoachingStage.OPTIONS


def test_gate_history_survives_including_invalidated_events(
    database_path: Path, reopened: CoachDatabase
) -> None:
    """Rollback evidence is history: it must not be lost or silently compacted."""
    run_child(
        database_path,
        SEED
        + f"""
gates = GateRepository(database.connection)
with database.transaction():
    for index, (step, revision, result) in enumerate((
        ('pre_coaching', 1, 'yes'),
        ('goal', 1, 'yes'),
        ('reality', 1, 'no'),
        ('reality', 2, 'yes'),
        ('goal', 3, 'invalidated'),
        ('goal', 4, 'yes'),
    )):
        gates.append(
            GateConfirmationRow(
                id=f'gate-{{index}}',
                session_id='{SESSION}',
                step=step,
                revision=revision,
                result=result,
                confirmed_at='{NOW}',
            )
        )
""",
    )
    state = recovery(reopened).recover(SESSION)

    assert len(state.gate_history) == 6
    assert [event.result for event in state.gate_history if event.step == "goal"] == [
        "yes",
        "invalidated",
        "yes",
    ]


def test_only_the_latest_revision_decides_whether_a_step_is_open(
    database_path: Path, reopened: CoachDatabase
) -> None:
    run_child(
        database_path,
        SEED
        + f"""
gates = GateRepository(database.connection)
with database.transaction():
    gates.append(GateConfirmationRow(
        id='gate-open', session_id='{SESSION}', step='goal', revision=1,
        result='yes', confirmed_at='{NOW}',
    ))
    gates.append(GateConfirmationRow(
        id='gate-rolled-back', session_id='{SESSION}', step='goal', revision=2,
        result='invalidated', invalidated_at='{LATER}', invalidated_by_step='goal',
    ))
""",
    )
    state = recovery(reopened).recover(SESSION)
    assert state.confirmed_steps == ()
    assert not state.is_step_confirmed("goal")


def test_a_replayed_step_reopens_at_the_higher_revision(
    database_path: Path, reopened: CoachDatabase
) -> None:
    run_child(
        database_path,
        SEED
        + f"""
gates = GateRepository(database.connection)
with database.transaction():
    gates.append(GateConfirmationRow(
        id='g1', session_id='{SESSION}', step='goal', revision=1, result='yes',
        confirmed_at='{NOW}',
    ))
    gates.append(GateConfirmationRow(
        id='g2', session_id='{SESSION}', step='goal', revision=2,
        result='invalidated', invalidated_at='{LATER}',
    ))
    gates.append(GateConfirmationRow(
        id='g3', session_id='{SESSION}', step='goal', revision=3, result='yes',
        confirmed_at='{LATER}',
    ))
""",
    )
    state = recovery(reopened).recover(SESSION)
    assert state.is_step_confirmed("goal")
    assert state.confirmed_steps == ("goal",)


def test_a_no_answer_does_not_open_a_step(
    database_path: Path, reopened: CoachDatabase
) -> None:
    run_child(
        database_path,
        SEED
        + f"""
with database.transaction():
    GateRepository(database.connection).append(GateConfirmationRow(
        id='g1', session_id='{SESSION}', step='goal', revision=1, result='no',
    ))
""",
    )
    state = recovery(reopened).recover(SESSION)
    assert state.confirmed_steps == ()


def test_memory_and_its_provenance_survive(
    database_path: Path, reopened: CoachDatabase
) -> None:
    run_child(
        database_path,
        SEED
        + f"""
with database.transaction():
    memory = MemoryRepository(database.connection)
    memory.add(MemoryItemRow(
        id='memory-1', content='Coachee coi trọng quyền tự chủ', user_confirmed=True,
    ))
    memory.add_provenance(MemoryProvenanceRow(
        id='provenance-1', memory_item_id='memory-1', source_type='session',
        source_id='{SESSION}', source_session_id='{SESSION}',
        relation='confirmed_from', created_at='{NOW}',
    ))
""",
    )
    state = recovery(reopened).recover(SESSION)
    assert [item.id for item in state.memories] == ["memory-1"]
    assert [row.relation for row in state.provenance] == ["confirmed_from"]


def test_pending_check_ins_survive(
    database_path: Path, reopened: CoachDatabase
) -> None:
    run_child(
        database_path,
        SEED
        + f"""
with database.transaction():
    GoalRepository(database.connection).add(GoalRow(
        id='goal-1', profile_id='{PROFILE}', title='Mục tiêu', status='active',
        confirmed_at='{NOW}', created_at='{NOW}',
    ))
    CommitmentRepository(database.connection).add(CommitmentRow(
        id='commitment-1', goal_id='goal-1', action_text='Nói chuyện với quản lý',
        status='active', confirmed_at='{NOW}',
    ))
    checkins = CheckInRepository(database.connection)
    checkins.schedule(CheckInRow(
        id='checkin-pending', commitment_id='commitment-1', scheduled_at='{LATER}',
    ))
    checkins.schedule(CheckInRow(
        id='checkin-done', commitment_id='commitment-1', scheduled_at='{NOW}',
        completed_at='{NOW}', result='done',
    ))
""",
    )
    state = recovery(reopened).recover(SESSION)
    assert [row.id for row in state.pending_check_ins] == ["checkin-pending"]


def test_committed_work_survives_a_child_that_never_closes_cleanly(
    database_path: Path, reopened: CoachDatabase
) -> None:
    """The real crash case: committed, then the process dies mid-flight."""
    run_child(
        database_path,
        SEED
        + f"""
with database.transaction():
    GoalRepository(database.connection).add(GoalRow(
        id='goal-committed', profile_id='{PROFILE}', title='Đã commit',
        status='active', confirmed_at='{NOW}', created_at='{NOW}',
    ))
    CoachingSessionRepository(database.connection).set_stage('{SESSION}', 'will')
""",
        clean_exit=False,
    )
    state = recovery(reopened).recover(SESSION)
    assert [goal.id for goal in state.goals] == ["goal-committed"]
    assert state.current_stage is CoachingStage.WILL


def test_an_uncommitted_write_does_not_survive_a_crash(
    database_path: Path, reopened: CoachDatabase
) -> None:
    """Recovery must not resurrect a half-written turn."""
    run_child(
        database_path,
        SEED
        + f"""
database.connection.execute("BEGIN IMMEDIATE")
database.connection.execute(
    "INSERT INTO goal (id, profile_id, title, status, created_at) "
    "VALUES ('goal-uncommitted', '{PROFILE}', 'Chưa commit', 'active', '{NOW}')"
)
""",
        clean_exit=False,
    )
    state = recovery(reopened).recover(SESSION)
    assert state.goals == ()
    assert reopened.connection.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0] == "ok"


def test_recovery_of_an_unknown_session_is_empty_not_an_error(
    database_path: Path, reopened: CoachDatabase
) -> None:
    run_child(database_path, SEED)
    state = recovery(reopened).recover("session-does-not-exist")
    assert state.session is None
    assert state.current_stage is None
    assert state.gate_history == ()


def test_recovery_reads_only_and_writes_nothing(
    database_path: Path, reopened: CoachDatabase
) -> None:
    run_child(database_path, SEED)

    def snapshot() -> list:
        return reopened.connection.execute(
            "SELECT name FROM sqlite_master ORDER BY name"
        ).fetchall()

    before = snapshot()
    recovery(reopened).recover(SESSION)
    assert snapshot() == before


def test_trashed_records_do_not_come_back_on_restart(
    database_path: Path, reopened: CoachDatabase
) -> None:
    """A restart must not undo a deletion the Coachee already made."""
    run_child(
        database_path,
        SEED
        + f"""
from hermes_coach.application.trash_service import TrashService
with database.transaction():
    GoalRepository(database.connection).add(GoalRow(
        id='goal-deleted', profile_id='{PROFILE}', title='Đã xoá', status='active',
        confirmed_at='{NOW}', created_at='{NOW}',
    ))
TrashService(database, profile_id='{PROFILE}').soft_delete(
    'goal', 'goal-deleted', now='{NOW}'
)
""",
    )
    state = recovery(reopened).recover(SESSION)
    assert state.goals == ()


def test_the_schema_version_is_unchanged_by_a_restart(
    database_path: Path, reopened: CoachDatabase
) -> None:
    from hermes_coach.infrastructure.sqlite import migrations
    from hermes_coach.infrastructure.sqlite.migration_runner import current_version

    run_child(database_path, SEED)
    assert current_version(reopened.connection) == migrations.LATEST_VERSION
