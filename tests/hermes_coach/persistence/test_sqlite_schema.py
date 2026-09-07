"""Fresh-schema contract for the Coach SQLite store.

Requirement family: `HC-DATA-*`, `HC-PRIVACY`; sources `SRC-076…SRC-086`,
`SRC-091`, `SRC-099`. Acceptance slice: `AC-49`, `AC-53…AC-55`.

Every assertion here runs against a real SQLite file under a temporary Coach
profile, never a repository mock.
"""

from __future__ import annotations

from collections.abc import Iterator

import sqlite3

import pytest

from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


CANONICAL_TABLES = {
    "coachee_profile",
    "career_snapshot",
    "coachee_value",
    "goal",
    "commitment",
    "evidence",
    "check_in",
    "coaching_session",
    "session_message",
    "candidate_record",
    "gate_confirmation",
    "insight",
    "memory_item",
    "memory_provenance",
    "consent_event",
    "trash_entry",
}

# Field lists are transcribed from the proposal Data Model section. A column
# added for storage convenience must not silently join a canonical entity.
CANONICAL_COLUMNS = {
    "coachee_profile": {
        "id",
        "display_name",
        "timezone",
        "preferred_language",
        "challenge_level",
        "quiet_hours",
        "created_at",
        "updated_at",
    },
    "career_snapshot": {
        "id",
        "profile_id",
        "current_role",
        "industry",
        "experience_summary",
        "strengths",
        "constraints",
        "career_vision",
        "clarity_score",
        "satisfaction_score",
        "energy_score",
        "confidence_score",
        "balance_score",
        "follow_through_score",
        "captured_at",
    },
    "coachee_value": {
        "id",
        "profile_id",
        "name",
        "description",
        "priority",
        "source_session_id",
        "confirmed_at",
        "created_at",
        "updated_at",
    },
    "goal": {
        "id",
        "profile_id",
        "title",
        "why_it_matters",
        "desired_outcome",
        "success_evidence",
        "target_date",
        "status",
        "priority",
        "source_session_id",
        "confirmed_at",
        "created_at",
        "updated_at",
    },
    "commitment": {
        "id",
        "goal_id",
        "action_text",
        "due_at",
        "evidence_definition",
        "confidence_score",
        "status",
        "source_session_id",
        "confirmed_at",
    },
    "evidence": {
        "id",
        "commitment_id",
        "kind",
        "content_or_path",
        "captured_at",
        "user_confirmed",
    },
    "check_in": {
        "id",
        "commitment_id",
        "scheduled_at",
        "completed_at",
        "result",
        "blockers",
        "still_relevant",
        "rescheduled_to",
        "review",
    },
    "coaching_session": {
        "id",
        "started_at",
        "ended_at",
        "intention",
        "success_definition",
        "coaching_stage",
        "coachee_takeaway",
        "summary",
        "safety_state",
    },
    "session_message": {
        "id",
        "session_id",
        "sequence_no",
        "role",
        "content",
        "modality",
        "coaching_stage",
        "question_kind",
        "safety_state",
        "created_at",
        "expires_at",
        "deleted_at",
    },
    "candidate_record": {
        "id",
        "session_id",
        "record_type",
        "payload_json",
        "source_message_id",
        "status",
        "created_at",
        "expires_at",
        "resolved_at",
    },
    "gate_confirmation": {
        "id",
        "session_id",
        "step",
        "revision",
        "result",
        "closing_question_message_id",
        "response_message_id",
        "confirmed_at",
        "invalidated_at",
        "invalidated_by_step",
    },
    "insight": {
        "id",
        "content",
        "topic",
        "sensitivity",
        "source_session_id",
        "goal_id",
        "confirmed_at",
    },
    "memory_item": {
        "id",
        "content",
        "category",
        "sensitivity",
        "user_confirmed",
        "expires_at",
        "last_used_at",
    },
    "memory_provenance": {
        "id",
        "memory_item_id",
        "source_type",
        "source_id",
        "source_session_id",
        "source_message_id",
        "relation",
        "created_at",
    },
    "consent_event": {
        "id",
        "profile_id",
        "session_id",
        "consent_type",
        "decision",
        "scope_json",
        "source",
        "ui_action",
        "control_id",
        "evidence_version",
        "created_at",
    },
    "trash_entry": {
        "id",
        "profile_id",
        "entity_type",
        "entity_id",
        "deleted_at",
        "purge_after",
        "restored_at",
        "purged_at",
        "deletion_source",
    },
}

# Enum values are closed sets: the proposal says a field "chỉ được nhận các giá
# trị được ghi trong ngoặc".
CANONICAL_ENUMS = {
    ("session_message", "role"): ("coach", "coachee", "product_ui", "safety_system"),
    ("session_message", "modality"): ("text",),
    ("candidate_record", "record_type"): ("goal", "insight", "commitment", "memory"),
    ("candidate_record", "status"): ("pending", "confirmed", "edited", "discarded"),
    ("gate_confirmation", "step"): (
        "pre_coaching",
        "goal",
        "reality",
        "options",
        "will",
        "review",
    ),
    ("gate_confirmation", "result"): ("yes", "no", "unclear", "invalidated"),
    ("consent_event", "decision"): ("granted", "declined", "withdrawn"),
    ("consent_event", "source"): ("ui",),
    ("consent_event", "ui_action"): ("confirm", "decline", "withdraw"),
    ("trash_entry", "deletion_source"): (
        "item",
        "session",
        "goal",
        "transcript",
        "all_data",
    ),
    ("memory_provenance", "source_type"): (
        "session",
        "message",
        "goal",
        "insight",
        "manual",
    ),
    ("memory_provenance", "relation"): (
        "derived_from",
        "confirmed_from",
        "manually_entered",
    ),
    ("goal", "status"): ("draft", "active", "paused", "achieved", "abandoned"),
}


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        yield db


def table_names(database: CoachDatabase) -> set[str]:
    rows = database.connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row["name"] for row in rows}


def column_names(database: CoachDatabase, table: str) -> set[str]:
    rows = database.connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def test_fresh_database_creates_every_canonical_table(database: CoachDatabase) -> None:
    assert CANONICAL_TABLES <= table_names(database)


@pytest.mark.parametrize("table", sorted(CANONICAL_COLUMNS))
def test_canonical_entity_has_exactly_its_proposal_fields(
    database: CoachDatabase, table: str
) -> None:
    """Internal columns must not redefine a canonical product entity."""
    assert column_names(database, table) == CANONICAL_COLUMNS[table]


def test_internal_tables_do_not_shadow_canonical_entities(
    database: CoachDatabase,
) -> None:
    internal = {name for name in table_names(database) if name.startswith("internal_")}
    assert internal
    assert not internal & CANONICAL_TABLES


def test_foreign_keys_are_enforced_not_merely_declared(
    database: CoachDatabase,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        database.connection.execute(
            "INSERT INTO career_snapshot (id, profile_id, captured_at) "
            "VALUES ('snap-1', 'missing-profile', '2026-08-22T00:00:00Z')"
        )


def test_foreign_key_check_reports_no_violation_on_fresh_schema(
    database: CoachDatabase,
) -> None:
    assert database.connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize(
    ("table", "column", "allowed"),
    [(table, column, allowed) for (table, column), allowed in CANONICAL_ENUMS.items()],
)
def test_enum_column_rejects_value_outside_the_closed_set(
    database: CoachDatabase, table: str, column: str, allowed: tuple[str, ...]
) -> None:
    seeded = seed_parent_rows(database)
    rejected = f"not-a-valid-{column}"
    assert rejected not in allowed
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(database, table, {**seeded[table], column: rejected})


@pytest.mark.parametrize(
    ("table", "column", "allowed"),
    [(table, column, allowed) for (table, column), allowed in CANONICAL_ENUMS.items()],
)
def test_enum_column_accepts_every_declared_value(
    database: CoachDatabase, table: str, column: str, allowed: tuple[str, ...]
) -> None:
    seeded = seed_parent_rows(database)
    for index, value in enumerate(allowed):
        row = uniquify(table, {**seeded[table], column: value}, index)
        insert_row(database, table, row)


def test_confirmed_memory_item_must_not_carry_an_expiry(
    database: CoachDatabase,
) -> None:
    """`expires_at` is always NULL for confirmed memory; no sentinel date."""
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            database,
            "memory_item",
            {
                "id": "memory-expiring",
                "content": "Coachee values autonomy",
                "category": "value",
                "sensitivity": "normal",
                "user_confirmed": 1,
                "expires_at": "2099-01-01T00:00:00Z",
            },
        )


def test_confirmed_memory_item_persists_with_null_expiry(
    database: CoachDatabase,
) -> None:
    insert_row(
        database,
        "memory_item",
        {
            "id": "memory-durable",
            "content": "Coachee values autonomy",
            "category": "value",
            "sensitivity": "normal",
            "user_confirmed": 1,
            "expires_at": None,
        },
    )
    row = database.connection.execute(
        "SELECT expires_at FROM memory_item WHERE id = 'memory-durable'"
    ).fetchone()
    assert row["expires_at"] is None


def test_manual_provenance_is_the_only_source_type_without_a_source_id(
    database: CoachDatabase,
) -> None:
    seed_parent_rows(database)
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            database,
            "memory_provenance",
            {
                "id": "prov-invalid",
                "memory_item_id": "memory-seed",
                "source_type": "session",
                "source_id": None,
                "relation": "derived_from",
                "created_at": "2026-08-22T00:00:00Z",
            },
        )


def test_gate_confirmation_is_unique_per_session_step_and_revision(
    database: CoachDatabase,
) -> None:
    seeded = seed_parent_rows(database)
    insert_row(database, "gate_confirmation", seeded["gate_confirmation"])
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            database,
            "gate_confirmation",
            {**seeded["gate_confirmation"], "id": "gate-duplicate"},
        )


def test_session_message_sequence_is_unique_per_session(
    database: CoachDatabase,
) -> None:
    seeded = seed_parent_rows(database)
    insert_row(database, "session_message", seeded["session_message"])
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            database,
            "session_message",
            {**seeded["session_message"], "id": "message-duplicate"},
        )


@pytest.mark.parametrize(
    ("table", "columns"),
    [
        ("session_message", ("session_id", "sequence_no")),
        ("candidate_record", ("session_id", "status")),
        ("trash_entry", ("purge_after",)),
        ("goal", ("profile_id", "status")),
    ],
)
def test_retention_and_active_scope_lookups_are_indexed(
    database: CoachDatabase, table: str, columns: tuple[str, ...]
) -> None:
    """Trash/expiry exclusion runs on every active query; it must not scan."""
    indexes = database.connection.execute(f"PRAGMA index_list({table})").fetchall()
    indexed = set()
    for index in indexes:
        info = database.connection.execute(
            f"PRAGMA index_info({index['name']})"
        ).fetchall()
        indexed.add(tuple(entry["name"] for entry in info))
    assert any(covered[: len(columns)] == columns for covered in indexed)


def uniquify(table: str, row: dict[str, object], index: int) -> dict[str, object]:
    """Move a probe row off the natural key so repeated inserts test the enum only."""
    row = {**row, "id": f"{table}-probe-{index}"}
    if table == "session_message":
        row["sequence_no"] = 100 + index
    if table == "gate_confirmation":
        row["revision"] = 100 + index
    if table == "trash_entry":
        # Only one open Trash entry may exist per entity.
        row["entity_id"] = f"goal-seed-{index}"
    return row


def insert_row(database: CoachDatabase, table: str, values: dict[str, object]) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    database.connection.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def seed_parent_rows(database: CoachDatabase) -> dict[str, dict[str, object]]:
    """Insert the FK parents an enum probe needs, return one valid row per table."""
    now = "2026-08-22T00:00:00Z"
    insert_row(
        database,
        "coachee_profile",
        {"id": "profile-seed", "display_name": "Coachee", "created_at": now},
    )
    insert_row(
        database,
        "coaching_session",
        {"id": "session-seed", "started_at": now, "coaching_stage": "goal"},
    )
    insert_row(
        database,
        "session_message",
        {
            "id": "message-seed",
            "session_id": "session-seed",
            "sequence_no": 0,
            "role": "coach",
            "content": "Điều gì quan trọng với bạn?",
            "created_at": now,
        },
    )
    insert_row(
        database,
        "goal",
        {
            "id": "goal-seed",
            "profile_id": "profile-seed",
            "title": "Chuyển vai trò",
            "status": "draft",
            "created_at": now,
        },
    )
    insert_row(
        database,
        "memory_item",
        {
            "id": "memory-seed",
            "content": "Coachee values autonomy",
            "user_confirmed": 1,
        },
    )
    return {
        "session_message": {
            "id": "message-probe",
            "session_id": "session-seed",
            "sequence_no": 1,
            "role": "coach",
            "content": "Bạn muốn đạt điều gì?",
            "modality": "text",
            "created_at": now,
        },
        "candidate_record": {
            "id": "candidate-probe",
            "session_id": "session-seed",
            "record_type": "goal",
            "payload_json": "{}",
            "status": "pending",
            "created_at": now,
        },
        "gate_confirmation": {
            "id": "gate-probe",
            "session_id": "session-seed",
            "step": "goal",
            "revision": 1,
            "result": "yes",
        },
        "consent_event": {
            "id": "consent-probe",
            "profile_id": "profile-seed",
            "consent_type": "model_egress",
            "decision": "granted",
            "scope_json": "{}",
            "source": "ui",
            "ui_action": "confirm",
            "control_id": "btn-confirm",
            "evidence_version": 1,
            "created_at": now,
        },
        "trash_entry": {
            "id": "trash-probe",
            "profile_id": "profile-seed",
            "entity_type": "goal",
            "entity_id": "goal-seed",
            "deleted_at": now,
            "purge_after": "2026-09-21T00:00:00Z",
            "deletion_source": "item",
        },
        "memory_provenance": {
            "id": "provenance-probe",
            "memory_item_id": "memory-seed",
            "source_type": "session",
            "source_id": "session-seed",
            "relation": "derived_from",
            "created_at": now,
        },
        "goal": {
            "id": "goal-probe",
            "profile_id": "profile-seed",
            "title": "Mục tiêu thử",
            "status": "draft",
            "created_at": now,
        },
    }
