"""Trash lifecycle: soft delete, restore and permanent purge.

Requirement families: `HC-PRIVACY`, `HC-RECORDS`; sources `SRC-058`, `SRC-092`,
`SRC-076…086`.

Deleting is reversible by default. Permanent purge is a separate, explicitly
confirmed UI command, removes dependents in order, and leaves audit evidence
that contains no deleted content.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from hermes_coach.application.retention_service import TRASH_WINDOW
from hermes_coach.application.trash_service import (
    PurgeReason,
    RestoreBlocked,
    TrashService,
)
from hermes_coach.domain.clock import shift
from hermes_coach.domain.records import (
    CommitmentRow,
    GoalRow,
    InsightRow,
    MemoryItemRow,
    MemoryProvenanceRow,
)
from hermes_coach.infrastructure.repositories.commitment_repository import (
    CommitmentRepository,
)
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.insight_repository import (
    InsightRepository,
)
from hermes_coach.infrastructure.repositories.memory_repository import MemoryRepository
from hermes_coach.infrastructure.repositories.trash_repository import TrashRepository
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-01-01T00:00:00Z"
LATER = "2026-01-10T00:00:00Z"

PROFILE = "profile-1"
SESSION = "session-1"
CONTROL = "btn-purge-confirm"


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        with db.transaction():
            db.connection.execute(
                "INSERT INTO coachee_profile (id, display_name, created_at) "
                "VALUES (?, 'Coachee', ?)",
                (PROFILE, NOW),
            )
            db.connection.execute(
                "INSERT INTO coaching_session (id, started_at, coaching_stage) "
                "VALUES (?, ?, 'goal')",
                (SESSION, NOW),
            )
        yield db


def trash(database: CoachDatabase) -> TrashService:
    return TrashService(database, profile_id=PROFILE)


def add_goal(database: CoachDatabase, goal_id: str = "goal-1") -> None:
    with database.transaction():
        GoalRepository(database.connection).add(
            GoalRow(
                id=goal_id,
                profile_id=PROFILE,
                title="Chuyển vai trò",
                status="active",
                source_session_id=SESSION,
                confirmed_at=NOW,
                created_at=NOW,
            )
        )


def add_commitment(
    database: CoachDatabase,
    commitment_id: str = "commitment-1",
    goal_id: str = "goal-1",
) -> None:
    with database.transaction():
        CommitmentRepository(database.connection).add(
            CommitmentRow(
                id=commitment_id,
                goal_id=goal_id,
                action_text="Nói chuyện với quản lý",
                status="active",
                confirmed_at=NOW,
            )
        )
        database.connection.execute(
            "INSERT INTO evidence (id, commitment_id, kind, captured_at, "
            "user_confirmed) VALUES (?, ?, 'note', ?, 1)",
            (f"evidence-of-{commitment_id}", commitment_id, NOW),
        )
        database.connection.execute(
            "INSERT INTO check_in (id, commitment_id, scheduled_at) VALUES (?, ?, ?)",
            (f"checkin-of-{commitment_id}", commitment_id, NOW),
        )


def count(database: CoachDatabase, table: str) -> int:
    return database.connection.execute(
        f"SELECT COUNT(*) AS total FROM {table}"
    ).fetchone()["total"]


def test_soft_delete_opens_a_trash_entry_and_hides_the_entity(
    database: CoachDatabase,
) -> None:
    add_goal(database)
    trash(database).soft_delete("goal", "goal-1", now=NOW)

    assert count(database, "goal") == 1
    assert GoalRepository(database.connection).list_active(PROFILE) == ()
    entry = TrashRepository(database.connection).open_entry("goal", "goal-1")
    assert entry is not None
    assert entry.purge_after == shift(NOW, TRASH_WINDOW)


def test_soft_delete_and_its_marker_commit_together(
    database: CoachDatabase, monkeypatch
) -> None:
    add_goal(database)

    def explode(self, entry) -> str:
        raise RuntimeError("disk full")

    monkeypatch.setattr(TrashRepository, "soft_delete", explode)
    with pytest.raises(RuntimeError):
        trash(database).soft_delete("goal", "goal-1", now=NOW)

    assert len(GoalRepository(database.connection).list_active(PROFILE)) == 1
    assert count(database, "trash_entry") == 0


def test_restore_brings_the_entity_back_and_cancels_the_purge(
    database: CoachDatabase,
) -> None:
    add_goal(database)
    trash(database).soft_delete("goal", "goal-1", now=NOW)
    trash(database).restore("goal", "goal-1", now=LATER)

    assert len(GoalRepository(database.connection).list_active(PROFILE)) == 1
    assert TrashRepository(database.connection).open_entry("goal", "goal-1") is None
    assert TrashRepository(database.connection).due_for_purge("2027-01-01T00:00:00Z") == ()


def test_restore_is_per_item_not_per_batch(database: CoachDatabase) -> None:
    add_goal(database, "goal-1")
    add_goal(database, "goal-2")
    trash(database).soft_delete("goal", "goal-1", now=NOW)
    trash(database).soft_delete("goal", "goal-2", now=NOW)
    trash(database).restore("goal", "goal-1", now=LATER)

    active = {row.id for row in GoalRepository(database.connection).list_active(PROFILE)}
    assert active == {"goal-1"}

    for name in dir(trash(database)):
        if not name.startswith("_"):
            assert "batch" not in name.lower() and "all" not in name.lower()


def test_restoring_a_child_whose_parent_is_gone_is_blocked(
    database: CoachDatabase,
) -> None:
    """A commitment without its goal would come back dangling."""
    add_goal(database)
    add_commitment(database)
    trash(database).soft_delete("commitment", "commitment-1", now=NOW)
    trash(database).soft_delete("goal", "goal-1", now=NOW)
    trash(database).purge("goal", "goal-1", now=LATER, reason=PurgeReason.USER_CONFIRMED, control_id=CONTROL)

    with pytest.raises(RestoreBlocked, match="goal"):
        trash(database).restore("commitment", "commitment-1", now=LATER)


def test_restoring_an_item_that_was_never_deleted_is_blocked(
    database: CoachDatabase,
) -> None:
    add_goal(database)
    with pytest.raises(RestoreBlocked, match="no open"):
        trash(database).restore("goal", "goal-1", now=LATER)


def test_permanent_purge_needs_a_confirmed_ui_control(
    database: CoachDatabase,
) -> None:
    add_goal(database)
    trash(database).soft_delete("goal", "goal-1", now=NOW)
    with pytest.raises(ValueError, match="control"):
        trash(database).purge(
            "goal", "goal-1", now=LATER, reason=PurgeReason.USER_CONFIRMED, control_id="  "
        )
    assert count(database, "goal") == 1


def test_retention_purge_needs_no_ui_control(database: CoachDatabase) -> None:
    """The 30-day sweep is automatic; only the user-initiated path needs a click."""
    add_goal(database)
    trash(database).soft_delete("goal", "goal-1", now=NOW)
    trash(database).purge("goal", "goal-1", now=LATER, reason=PurgeReason.RETENTION)
    assert count(database, "goal") == 0


def test_purge_removes_dependents_in_order(database: CoachDatabase) -> None:
    add_goal(database)
    add_commitment(database)
    trash(database).soft_delete("goal", "goal-1", now=NOW)
    trash(database).purge(
        "goal", "goal-1", now=LATER, reason=PurgeReason.USER_CONFIRMED, control_id=CONTROL
    )

    assert count(database, "goal") == 0
    assert count(database, "commitment") == 0
    assert count(database, "evidence") == 0
    assert count(database, "check_in") == 0
    assert database.connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_purging_a_goal_keeps_its_insights_and_drops_only_the_link(
    database: CoachDatabase,
) -> None:
    """An insight is durable truth of its own, not a child of the goal."""
    add_goal(database)
    with database.transaction():
        InsightRepository(database.connection).add(
            InsightRow(
                id="insight-1",
                content="Tôi né xung đột",
                source_session_id=SESSION,
                goal_id="goal-1",
                confirmed_at=NOW,
            )
        )
    trash(database).soft_delete("goal", "goal-1", now=NOW)
    trash(database).purge(
        "goal", "goal-1", now=LATER, reason=PurgeReason.USER_CONFIRMED, control_id=CONTROL
    )

    insight = InsightRepository(database.connection).get("insight-1")
    assert insight is not None
    assert insight.goal_id is None


def test_purging_memory_removes_its_provenance(database: CoachDatabase) -> None:
    with database.transaction():
        memory = MemoryRepository(database.connection)
        memory.add(
            MemoryItemRow(id="memory-1", content="Giá trị", user_confirmed=True)
        )
        memory.add_provenance(
            MemoryProvenanceRow(
                id="provenance-1",
                memory_item_id="memory-1",
                source_type="session",
                source_id=SESSION,
                source_session_id=SESSION,
                relation="confirmed_from",
                created_at=NOW,
            )
        )
    trash(database).soft_delete("memory_item", "memory-1", now=NOW)
    trash(database).purge(
        "memory_item",
        "memory-1",
        now=LATER,
        reason=PurgeReason.USER_CONFIRMED,
        control_id=CONTROL,
    )

    assert count(database, "memory_item") == 0
    assert count(database, "memory_provenance") == 0


def test_purge_audit_records_the_event_without_the_content(
    database: CoachDatabase,
) -> None:
    secret = "Nội dung riêng tư tuyệt đối không được vào audit"
    with database.transaction():
        MemoryRepository(database.connection).add(
            MemoryItemRow(id="memory-1", content=secret, user_confirmed=True)
        )
    trash(database).soft_delete("memory_item", "memory-1", now=NOW)
    trash(database).purge(
        "memory_item",
        "memory-1",
        now=LATER,
        reason=PurgeReason.USER_CONFIRMED,
        control_id=CONTROL,
    )

    rows = database.connection.execute(
        "SELECT * FROM internal_purge_audit"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["entity_type"] == "memory_item"
    assert rows[0]["entity_id"] == "memory-1"
    assert rows[0]["reason"] == "user_confirmed"
    assert all(secret not in str(dict(row)) for row in rows)


def test_purge_closes_the_trash_entry(database: CoachDatabase) -> None:
    add_goal(database)
    trash(database).soft_delete("goal", "goal-1", now=NOW)
    trash(database).purge(
        "goal", "goal-1", now=LATER, reason=PurgeReason.USER_CONFIRMED, control_id=CONTROL
    )
    entry = database.connection.execute(
        "SELECT purged_at FROM trash_entry WHERE entity_id = 'goal-1'"
    ).fetchone()
    assert entry["purged_at"] == LATER
    assert TrashRepository(database.connection).due_for_purge("2027-01-01T00:00:00Z") == ()


def test_purging_something_that_is_not_in_the_trash_is_refused(
    database: CoachDatabase,
) -> None:
    """Permanent deletion always goes through the reversible step first."""
    add_goal(database)
    with pytest.raises(RestoreBlocked, match="no open"):
        trash(database).purge(
            "goal", "goal-1", now=LATER, reason=PurgeReason.USER_CONFIRMED, control_id=CONTROL
        )
    assert count(database, "goal") == 1


def test_a_failed_purge_leaves_the_entity_and_its_children_intact(
    database: CoachDatabase, monkeypatch
) -> None:
    add_goal(database)
    add_commitment(database)
    trash(database).soft_delete("goal", "goal-1", now=NOW)

    def explode(self, entity_type, entity_id, purged_at) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(TrashRepository, "mark_purged", explode)
    with pytest.raises(RuntimeError):
        trash(database).purge(
            "goal", "goal-1", now=LATER, reason=PurgeReason.USER_CONFIRMED, control_id=CONTROL
        )

    assert count(database, "goal") == 1
    assert count(database, "commitment") == 1
    assert count(database, "evidence") == 1
    assert count(database, "internal_purge_audit") == 0


def test_soft_delete_of_an_unknown_entity_type_is_refused(
    database: CoachDatabase,
) -> None:
    """An unmapped type would soft delete something purge cannot finish."""
    with pytest.raises(ValueError, match="unsupported"):
        trash(database).soft_delete("career_snapshot", "snapshot-1", now=NOW)
