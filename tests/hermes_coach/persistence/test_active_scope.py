"""Active-scope contract shared by every repository.

Requirement family: `HC-DATA-*`, `HC-PRIVACY`, `HC-RECORDS`; sources `SRC-054…059`,
`SRC-063`, `SRC-068`, `SRC-076…086`, `SRC-092`.

The named risk for this phase is "one query leaks Trash/expired/unconfirmed
data". These tests are table-driven over every registered repository so a new
repository cannot quietly opt out of the exclusion.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from hermes_coach.domain.records import (
    CandidateRecordRow,
    CareerSnapshotRow,
    GoalRow,
    MemoryItemRow,
    MemoryProvenanceRow,
    SessionMessageRow,
    TrashEntryRow,
)
from hermes_coach.infrastructure.repositories import ACTIVE_SCOPE_REPOSITORIES
from hermes_coach.infrastructure.repositories.candidate_repository import (
    CandidateRepository,
)
from hermes_coach.infrastructure.repositories.career_snapshot_repository import (
    CareerSnapshotRepository,
)
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.memory_repository import MemoryRepository
from hermes_coach.infrastructure.repositories.session_message_repository import (
    SessionMessageRepository,
)
from hermes_coach.infrastructure.repositories.trash_repository import TrashRepository
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-08-22T00:00:00Z"
EARLIER = "2026-01-01T00:00:00Z"
LATER = "2027-01-01T00:00:00Z"

PROFILE = "profile-1"
SESSION = "session-1"


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        seed_roots(db)
        yield db


def seed_roots(database: CoachDatabase) -> None:
    """Insert the profile and session every other row hangs off."""
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coachee_profile (id, display_name, created_at) "
            "VALUES (?, 'Coachee', ?)",
            (PROFILE, NOW),
        )
        database.connection.execute(
            "INSERT INTO coaching_session (id, started_at, coaching_stage) "
            "VALUES (?, ?, 'goal')",
            (SESSION, NOW),
        )


def goal_row(goal_id: str = "goal-1", **overrides: object) -> GoalRow:
    values: dict[str, object] = {
        "id": goal_id,
        "profile_id": PROFILE,
        "title": "Chuyển sang vai trò kiến trúc sư",
        "status": "active",
        "created_at": NOW,
        "confirmed_at": NOW,
    }
    values.update(overrides)
    return GoalRow.model_validate(values)


def message_row(message_id: str = "message-1", **overrides: object) -> SessionMessageRow:
    values: dict[str, object] = {
        "id": message_id,
        "session_id": SESSION,
        "sequence_no": 0,
        "role": "coach",
        "content": "Điều gì quan trọng với bạn?",
        "created_at": NOW,
    }
    values.update(overrides)
    return SessionMessageRow.model_validate(values)


def candidate_row(
    candidate_id: str = "candidate-1", **overrides: object
) -> CandidateRecordRow:
    values: dict[str, object] = {
        "id": candidate_id,
        "session_id": SESSION,
        "record_type": "goal",
        "payload_json": "{}",
        "status": "pending",
        "created_at": NOW,
    }
    values.update(overrides)
    return CandidateRecordRow.model_validate(values)


def memory_row(memory_id: str = "memory-1", **overrides: object) -> MemoryItemRow:
    values: dict[str, object] = {
        "id": memory_id,
        "content": "Coachee coi trọng quyền tự chủ",
        "user_confirmed": True,
    }
    values.update(overrides)
    return MemoryItemRow.model_validate(values)


def insert_one(database: CoachDatabase, entity_type: str, entity_id: str) -> None:
    repositories = {
        "goal": lambda: GoalRepository(database.connection).add(goal_row(entity_id)),
        "session_message": lambda: SessionMessageRepository(database.connection).add(
            message_row(entity_id)
        ),
        "candidate_record": lambda: CandidateRepository(database.connection).add(
            candidate_row(entity_id)
        ),
        "memory_item": lambda: MemoryRepository(database.connection).add(
            memory_row(entity_id)
        ),
    }
    with database.transaction():
        repositories[entity_type]()


def list_active_ids(database: CoachDatabase, entity_type: str) -> set[str]:
    listers = {
        "goal": lambda: GoalRepository(database.connection).list_active(PROFILE),
        "session_message": lambda: SessionMessageRepository(
            database.connection
        ).list_active(SESSION),
        "candidate_record": lambda: CandidateRepository(
            database.connection
        ).list_pending(SESSION),
        "memory_item": lambda: MemoryRepository(database.connection).list_active(),
    }
    return {row.id for row in listers[entity_type]()}


def get_one(database: CoachDatabase, entity_type: str, entity_id: str) -> object | None:
    getters = {
        "goal": lambda: GoalRepository(database.connection).get(entity_id),
        "session_message": lambda: SessionMessageRepository(database.connection).get(
            entity_id
        ),
        "candidate_record": lambda: CandidateRepository(database.connection).get(
            entity_id
        ),
        "memory_item": lambda: MemoryRepository(database.connection).get(entity_id),
    }
    return getters[entity_type]()


ENTITY_TYPES = ["goal", "session_message", "candidate_record", "memory_item"]


def soft_delete(database: CoachDatabase, entity_type: str, entity_id: str) -> str:
    trash = TrashRepository(database.connection)
    with database.transaction():
        return trash.soft_delete(
            TrashEntryRow(
                id=f"trash-{entity_id}",
                profile_id=PROFILE,
                entity_type=entity_type,
                entity_id=entity_id,
                deleted_at=NOW,
                purge_after=LATER,
                deletion_source="item",
            )
        )


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_every_repository_lists_a_row_it_owns(
    database: CoachDatabase, entity_type: str
) -> None:
    insert_one(database, entity_type, f"{entity_type}-visible")
    assert list_active_ids(database, entity_type) == {f"{entity_type}-visible"}


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_soft_deleted_row_disappears_from_every_active_list(
    database: CoachDatabase, entity_type: str
) -> None:
    entity_id = f"{entity_type}-deleted"
    insert_one(database, entity_type, entity_id)
    soft_delete(database, entity_type, entity_id)
    assert list_active_ids(database, entity_type) == set()


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_soft_deleted_row_is_not_reachable_by_direct_get(
    database: CoachDatabase, entity_type: str
) -> None:
    """Hiding a row from lists but serving it by id is the same leak."""
    entity_id = f"{entity_type}-deleted"
    insert_one(database, entity_type, entity_id)
    soft_delete(database, entity_type, entity_id)
    assert get_one(database, entity_type, entity_id) is None


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_restoring_the_entry_makes_the_row_active_again(
    database: CoachDatabase, entity_type: str
) -> None:
    entity_id = f"{entity_type}-restored"
    insert_one(database, entity_type, entity_id)
    soft_delete(database, entity_type, entity_id)
    with database.transaction():
        TrashRepository(database.connection).restore(entity_type, entity_id, NOW)
    assert list_active_ids(database, entity_type) == {entity_id}


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_a_purged_entry_keeps_the_row_hidden(
    database: CoachDatabase, entity_type: str
) -> None:
    """Purge closes the entry; the row must not reappear before it is deleted."""
    entity_id = f"{entity_type}-purged"
    insert_one(database, entity_type, entity_id)
    soft_delete(database, entity_type, entity_id)
    with database.transaction():
        TrashRepository(database.connection).mark_purged(entity_type, entity_id, NOW)
    assert list_active_ids(database, entity_type) == set()


def test_every_active_scope_repository_is_covered_by_these_tests() -> None:
    """A new repository must be added here, not silently skipped."""
    assert set(ACTIVE_SCOPE_REPOSITORIES) == set(ENTITY_TYPES)


def test_expired_session_message_is_excluded(database: CoachDatabase) -> None:
    repository = SessionMessageRepository(database.connection)
    with database.transaction():
        repository.add(message_row("message-fresh", expires_at=LATER))
        repository.add(message_row("message-stale", sequence_no=1, expires_at=EARLIER))
    active = {row.id for row in repository.list_active(SESSION, now=NOW)}
    assert active == {"message-fresh"}


def test_message_without_expiry_is_never_treated_as_expired(
    database: CoachDatabase,
) -> None:
    repository = SessionMessageRepository(database.connection)
    with database.transaction():
        repository.add(message_row("message-durable", expires_at=None))
    assert {row.id for row in repository.list_active(SESSION, now=LATER)} == {
        "message-durable"
    }


def test_expired_pending_candidate_is_excluded(database: CoachDatabase) -> None:
    repository = CandidateRepository(database.connection)
    with database.transaction():
        repository.add(candidate_row("candidate-fresh", expires_at=LATER))
        repository.add(candidate_row("candidate-stale", expires_at=EARLIER))
    pending = {row.id for row in repository.list_pending(SESSION, now=NOW)}
    assert pending == {"candidate-fresh"}


def test_only_pending_candidates_are_offered_for_confirmation(
    database: CoachDatabase,
) -> None:
    repository = CandidateRepository(database.connection)
    with database.transaction():
        repository.add(candidate_row("candidate-pending"))
        repository.add(candidate_row("candidate-done", status="confirmed"))
        repository.add(candidate_row("candidate-gone", status="discarded"))
    assert {row.id for row in repository.list_pending(SESSION)} == {"candidate-pending"}


def test_unconfirmed_memory_is_not_active_memory(database: CoachDatabase) -> None:
    """Only confirmed memory is approved for reuse."""
    repository = MemoryRepository(database.connection)
    with database.transaction():
        repository.add(memory_row("memory-confirmed", user_confirmed=True))
        repository.add(memory_row("memory-candidate", user_confirmed=False))
    assert {row.id for row in repository.list_active()} == {"memory-confirmed"}


def test_confirmed_memory_never_expires_by_age(database: CoachDatabase) -> None:
    repository = MemoryRepository(database.connection)
    with database.transaction():
        repository.add(memory_row("memory-old"))
    assert {row.id for row in repository.list_active(now=LATER)} == {"memory-old"}


def test_goal_list_is_scoped_to_the_owning_profile(database: CoachDatabase) -> None:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coachee_profile (id, display_name, created_at) "
            "VALUES ('profile-2', 'Other', ?)",
            (NOW,),
        )
    repository = GoalRepository(database.connection)
    with database.transaction():
        repository.add(goal_row("goal-mine"))
        repository.add(goal_row("goal-theirs", profile_id="profile-2"))
    assert {row.id for row in repository.list_active(PROFILE)} == {"goal-mine"}


def test_abandoned_and_achieved_goals_leave_the_active_list(
    database: CoachDatabase,
) -> None:
    repository = GoalRepository(database.connection)
    with database.transaction():
        repository.add(goal_row("goal-active"))
        repository.add(goal_row("goal-done", status="achieved"))
        repository.add(goal_row("goal-dropped", status="abandoned"))
    assert {row.id for row in repository.list_active(PROFILE)} == {"goal-active"}


def test_unconfirmed_goal_is_not_structured_truth(database: CoachDatabase) -> None:
    repository = GoalRepository(database.connection)
    with database.transaction():
        repository.add(goal_row("goal-confirmed"))
        repository.add(goal_row("goal-draft", status="draft", confirmed_at=None))
        # Status alone would not catch this one.
        repository.add(goal_row("goal-unconfirmed", confirmed_at=None))
    assert {row.id for row in repository.list_active(PROFILE)} == {"goal-confirmed"}


def test_career_snapshots_are_append_only(database: CoachDatabase) -> None:
    repository = CareerSnapshotRepository(database.connection)
    with database.transaction():
        repository.add(
            CareerSnapshotRow(
                id="snapshot-1", profile_id=PROFILE, captured_at=EARLIER, energy_score=4
            )
        )
        repository.add(
            CareerSnapshotRow(
                id="snapshot-2", profile_id=PROFILE, captured_at=NOW, energy_score=7
            )
        )
    history = repository.history(PROFILE)
    assert [row.id for row in history] == ["snapshot-1", "snapshot-2"]
    assert [row.energy_score for row in history] == [4, 7]


def test_career_snapshot_repository_exposes_no_mutation(
    database: CoachDatabase,
) -> None:
    repository = CareerSnapshotRepository(database.connection)
    for forbidden in ("update", "delete", "upsert"):
        assert not hasattr(repository, forbidden)


def test_memory_provenance_is_append_only_and_multi_source(
    database: CoachDatabase,
) -> None:
    repository = MemoryRepository(database.connection)
    with database.transaction():
        repository.add(memory_row("memory-1"))
        repository.add_provenance(
            MemoryProvenanceRow(
                id="provenance-1",
                memory_item_id="memory-1",
                source_type="session",
                source_id=SESSION,
                source_session_id=SESSION,
                relation="derived_from",
                created_at=EARLIER,
            )
        )
        repository.add_provenance(
            MemoryProvenanceRow(
                id="provenance-2",
                memory_item_id="memory-1",
                source_type="manual",
                source_id=None,
                relation="manually_entered",
                created_at=NOW,
            )
        )
    provenance = repository.provenance_for("memory-1")
    assert [row.id for row in provenance] == ["provenance-1", "provenance-2"]
    assert {row.source_type for row in provenance} == {"session", "manual"}


def test_soft_delete_and_the_trash_entry_land_in_one_transaction(
    database: CoachDatabase,
) -> None:
    """A crash must not leave a row deleted without its Trash marker."""
    insert_one(database, "goal", "goal-atomic")
    trash = TrashRepository(database.connection)
    with pytest.raises(RuntimeError):
        with database.transaction():
            trash.soft_delete(
                TrashEntryRow(
                    id="trash-atomic",
                    profile_id=PROFILE,
                    entity_type="goal",
                    entity_id="goal-atomic",
                    deleted_at=NOW,
                    purge_after=LATER,
                    deletion_source="item",
                )
            )
            raise RuntimeError("service failed after the marker was written")
    assert list_active_ids(database, "goal") == {"goal-atomic"}
    assert trash.open_entry("goal", "goal-atomic") is None


def test_a_second_open_trash_entry_for_one_entity_is_refused(
    database: CoachDatabase,
) -> None:
    insert_one(database, "goal", "goal-twice")
    soft_delete(database, "goal", "goal-twice")
    with pytest.raises(sqlite3.IntegrityError):
        soft_delete(database, "goal", "goal-twice")


def test_a_repository_that_drops_the_predicate_does_leak(
    database: CoachDatabase,
) -> None:
    """Prove the exclusion is doing the work, not the test setup.

    A subclass that queries without `not_in_trash` must return the soft-deleted
    row. If this ever stops leaking, the active-scope tests above have become
    vacuous and prove nothing.
    """

    class LeakyGoalRepository(GoalRepository):
        def list_active(self, profile_id: str) -> tuple[GoalRow, ...]:
            return tuple(
                self.select(
                    "entity.profile_id = :profile_id",
                    {"profile_id": profile_id},
                )
            )

    insert_one(database, "goal", "goal-leaked")
    soft_delete(database, "goal", "goal-leaked")

    assert list_active_ids(database, "goal") == set()
    leaked = LeakyGoalRepository(database.connection).list_active(PROFILE)
    assert {row.id for row in leaked} == {"goal-leaked"}


def test_due_purges_list_only_entries_past_their_deadline(
    database: CoachDatabase,
) -> None:
    insert_one(database, "goal", "goal-due")
    insert_one(database, "goal", "goal-not-due")
    trash = TrashRepository(database.connection)
    with database.transaction():
        trash.soft_delete(
            TrashEntryRow(
                id="trash-due",
                profile_id=PROFILE,
                entity_type="goal",
                entity_id="goal-due",
                deleted_at=EARLIER,
                purge_after=EARLIER,
                deletion_source="item",
            )
        )
        trash.soft_delete(
            TrashEntryRow(
                id="trash-not-due",
                profile_id=PROFILE,
                entity_type="goal",
                entity_id="goal-not-due",
                deleted_at=NOW,
                purge_after=LATER,
                deletion_source="item",
            )
        )
    assert {entry.id for entry in trash.due_for_purge(NOW)} == {"trash-due"}
