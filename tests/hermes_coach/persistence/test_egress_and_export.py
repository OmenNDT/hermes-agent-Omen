"""Egress audit and user-initiated export.

Requirement families: `HC-PRIVACY`; sources `SRC-026`, `SRC-070`, `SRC-072`,
`SRC-091`.

The audit records that data left and which items it named — never the payload
and never a secret. Provider retention that has not been verified must display
as unknown rather than reassuring. Export carries provenance and status, and no
credential.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest

from hermes_coach.application.consent_service import ConsentService, UiConsentAction
from hermes_coach.application.export_service import ExportService
from hermes_coach.contracts.egress_contract import (
    EgressCategory,
    EgressItemRef,
    EgressManifest,
    EgressRequirement,
    ProviderRetentionDisclosure,
    ProviderRetentionStatus,
)
from hermes_coach.domain.records import (
    GoalRow,
    InsightRow,
    MemoryItemRow,
    MemoryProvenanceRow,
)
from hermes_coach.infrastructure.egress_audit import EgressAuditRepository
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.insight_repository import (
    InsightRepository,
)
from hermes_coach.infrastructure.repositories.memory_repository import MemoryRepository
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-01-01T00:00:00Z"
MOMENT = datetime(2026, 1, 1, tzinfo=timezone.utc)

PROFILE = "profile-1"
SESSION = "session-1"
GOAL = "goal-1"

SECRET = "sk-live-do-not-store-this-anywhere"
PRIVATE = "Nội dung riêng tư của Coachee"


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
            GoalRepository(db.connection).add(
                GoalRow(
                    id=GOAL,
                    profile_id=PROFILE,
                    title="Chuyển sang vai trò kiến trúc sư",
                    status="active",
                    source_session_id=SESSION,
                    confirmed_at=NOW,
                    created_at=NOW,
                )
            )
        yield db


def audit(database: CoachDatabase) -> EgressAuditRepository:
    return EgressAuditRepository(database)


def unknown_retention() -> ProviderRetentionDisclosure:
    return ProviderRetentionDisclosure(
        status=ProviderRetentionStatus.UNKNOWN,
        label="Không rõ nhà cung cấp giữ dữ liệu bao lâu",
        version="2026-01",
    )


def manifest(
    *,
    manifest_id: str = "manifest-1",
    retention: ProviderRetentionDisclosure | None = None,
) -> EgressManifest:
    return EgressManifest(
        manifest_id=manifest_id,
        profile_id=PROFILE,
        session_id=SESSION,
        turn_id="turn-1",
        created_at=MOMENT,
        provider="nous",
        model="hermes-4",
        purpose="coaching_turn",
        requirement=EgressRequirement.REQUIRED,
        categories=(EgressCategory.CURRENT_TURN, EgressCategory.SELECTED_MEMORY),
        item_refs=(
            EgressItemRef(
                local_id=GOAL,
                category=EgressCategory.SELECTED_PROFILE,
                requirement=EgressRequirement.REQUIRED,
            ),
        ),
        consent_scope='{"goal_id": "goal-1"}',
        consent_version="2026-01",
        provider_retention=retention or unknown_retention(),
    )


def test_a_manifest_round_trips(database: CoachDatabase) -> None:
    audit(database).record(manifest(), decision="allowed")
    stored = audit(database).for_session(SESSION)
    assert len(stored) == 1
    assert stored[0].manifest_id == "manifest-1"
    assert stored[0].provider == "nous"
    assert stored[0].categories == (
        EgressCategory.CURRENT_TURN,
        EgressCategory.SELECTED_MEMORY,
    )
    assert stored[0].item_refs[0].local_id == GOAL


def test_the_audit_records_the_decision(database: CoachDatabase) -> None:
    audit(database).record(manifest(manifest_id="allowed-1"), decision="allowed")
    audit(database).record(manifest(manifest_id="blocked-1"), decision="blocked")
    decisions = {
        row["manifest_id"]: row["decision"]
        for row in database.connection.execute(
            "SELECT manifest_id, decision FROM internal_egress_audit"
        ).fetchall()
    }
    assert decisions == {"allowed-1": "allowed", "blocked-1": "blocked"}


def test_the_audit_stores_no_payload(database: CoachDatabase) -> None:
    with database.transaction():
        MemoryRepository(database.connection).add(
            MemoryItemRow(id="memory-1", content=PRIVATE, user_confirmed=True)
        )
    audit(database).record(manifest(), decision="allowed")

    rows = database.connection.execute(
        "SELECT * FROM internal_egress_audit"
    ).fetchall()
    items = database.connection.execute(
        "SELECT * FROM internal_egress_item"
    ).fetchall()
    for row in (*rows, *items):
        assert PRIVATE not in str(dict(row))


def test_unverified_provider_retention_displays_as_unknown(
    database: CoachDatabase,
) -> None:
    """Nothing may imply a retention policy that was never checked."""
    audit(database).record(manifest(), decision="allowed")
    stored = audit(database).for_session(SESSION)[0]
    assert stored.provider_retention.status is ProviderRetentionStatus.UNKNOWN
    assert stored.provider_retention.source_url is None


def test_documented_provider_retention_keeps_its_source_and_version(
    database: CoachDatabase,
) -> None:
    documented = ProviderRetentionDisclosure(
        status=ProviderRetentionStatus.DOCUMENTED,
        label="Giữ 30 ngày",
        source_url="https://example.invalid/policy",
        source_checked_at=MOMENT,
        version="2026-01",
    )
    audit(database).record(
        manifest(retention=documented), decision="allowed"
    )
    stored = audit(database).for_session(SESSION)[0]
    assert stored.provider_retention.source_url == "https://example.invalid/policy"
    assert stored.provider_retention.version == "2026-01"


def test_retention_disclosure_is_versioned_separately_from_the_manifest(
    database: CoachDatabase,
) -> None:
    audit(database).record(manifest(manifest_id="m-1"), decision="allowed")
    audit(database).record(
        manifest(
            manifest_id="m-2",
            retention=ProviderRetentionDisclosure(
                status=ProviderRetentionStatus.UNKNOWN,
                label="Vẫn chưa rõ",
                version="2026-02",
            ),
        ),
        decision="allowed",
    )
    versions = {
        entry.manifest_id: entry.provider_retention.version
        for entry in audit(database).for_session(SESSION)
    }
    assert versions == {"m-1": "2026-01", "m-2": "2026-02"}


def test_a_manifest_id_cannot_be_recorded_twice(database: CoachDatabase) -> None:
    import sqlite3

    audit(database).record(manifest(), decision="allowed")
    with pytest.raises(sqlite3.IntegrityError):
        audit(database).record(manifest(), decision="allowed")


def export(database: CoachDatabase) -> ExportService:
    return ExportService(database, profile_id=PROFILE)


def seed_export_material(database: CoachDatabase) -> None:
    with database.transaction():
        memory = MemoryRepository(database.connection)
        memory.add(
            MemoryItemRow(id="memory-1", content=PRIVATE, user_confirmed=True)
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
        InsightRepository(database.connection).add(
            InsightRow(
                id="insight-1",
                content="Tôi né tránh xung đột",
                source_session_id=SESSION,
                goal_id=GOAL,
                confirmed_at=NOW,
            )
        )
    ConsentService(database, profile_id=PROFILE).record(
        event_id="consent-1",
        consent_type="model_egress",
        scope={"goal_id": GOAL},
        ui_action=UiConsentAction.CONFIRM,
        control_id="btn-consent-confirm",
        now=NOW,
    )


def test_export_carries_the_coachees_own_records(database: CoachDatabase) -> None:
    seed_export_material(database)
    payload = export(database).to_json(now=NOW)

    assert [goal["id"] for goal in payload["goals"]] == [GOAL]
    assert [memory["id"] for memory in payload["memory"]] == ["memory-1"]
    assert [insight["id"] for insight in payload["insights"]] == ["insight-1"]


def test_export_includes_provenance_status_and_timestamps(
    database: CoachDatabase,
) -> None:
    seed_export_material(database)
    payload = export(database).to_json(now=NOW)

    assert payload["goals"][0]["status"] == "active"
    assert payload["goals"][0]["confirmed_at"] == NOW
    assert payload["memory"][0]["provenance"][0]["relation"] == "confirmed_from"
    assert payload["exported_at"] == NOW


def test_export_includes_the_consent_history(database: CoachDatabase) -> None:
    seed_export_material(database)
    payload = export(database).to_json(now=NOW)
    assert payload["consent_events"][0]["decision"] == "granted"
    assert payload["consent_events"][0]["control_id"] == "btn-consent-confirm"


def test_export_states_that_the_data_is_not_encrypted(
    database: CoachDatabase,
) -> None:
    """The disclosure travels with the file, not only with the UI that made it."""
    payload = export(database).to_json(now=NOW)
    assert payload["disclosure"]["encrypted_at_rest"] is False
    assert payload["disclosure"]["version"]


@pytest.mark.parametrize("marker", ["api_key", "sk-", "authorization", "bearer "])
def test_export_contains_no_credential_shaped_value(
    database: CoachDatabase, marker: str
) -> None:
    seed_export_material(database)
    rendered = str(export(database).to_json(now=NOW)).lower()
    assert marker not in rendered
    assert marker not in export(database).to_markdown(now=NOW).lower()


def test_a_secret_written_into_a_record_is_still_not_exported_as_a_credential(
    database: CoachDatabase,
) -> None:
    """Export must not become a credential exfiltration path."""
    with database.transaction():
        MemoryRepository(database.connection).add(
            MemoryItemRow(id="memory-secret", content=SECRET, user_confirmed=True)
        )
    payload = export(database).to_json(now=NOW)
    exported = [memory["content"] for memory in payload["memory"]]
    assert SECRET not in exported
    assert payload["redacted_count"] == 1


def test_markdown_export_is_human_readable(database: CoachDatabase) -> None:
    seed_export_material(database)
    rendered = export(database).to_markdown(now=NOW)
    assert "# Hermes Coach export" in rendered
    assert "Chuyển sang vai trò kiến trúc sư" in rendered
    assert "confirmed_from" in rendered


def test_export_excludes_trashed_records(database: CoachDatabase) -> None:
    from hermes_coach.application.trash_service import TrashService

    seed_export_material(database)
    TrashService(database, profile_id=PROFILE).soft_delete(
        "memory_item", "memory-1", now=NOW
    )
    payload = export(database).to_json(now=NOW)
    assert payload["memory"] == []


def test_export_writes_nothing_to_the_database(database: CoachDatabase) -> None:
    seed_export_material(database)
    before = database.connection.execute(
        "SELECT COUNT(*) AS total FROM memory_item"
    ).fetchone()["total"]
    export(database).to_json(now=NOW)
    export(database).to_markdown(now=NOW)
    after = database.connection.execute(
        "SELECT COUNT(*) AS total FROM memory_item"
    ).fetchone()["total"]
    assert before == after


# Exporting one session's transcript. Separate from the records export above:
# the Coachee asked for "what we said", not "what the system concluded".


def add_transcript(database: CoachDatabase) -> None:
    from hermes_coach.infrastructure.repositories.session_message_repository import (
        SessionMessageRepository,
        SessionMessageRow,
    )

    lines = [
        ("coachee", "Tôi muốn chuyển sang vai trò kiến trúc sư.", "goal"),
        ("coach", "Điều gì khiến việc này quan trọng với bạn?", "goal"),
        ("coachee", f"Khoá của tôi là {SECRET}", "goal"),
    ]
    with database.transaction():
        repository = SessionMessageRepository(database.connection)
        for index, (role, content, stage) in enumerate(lines):
            repository.add(
                SessionMessageRow(
                    id=f"message-{index}",
                    session_id=SESSION,
                    sequence_no=index,
                    role=role,
                    content=content,
                    coaching_stage=stage,
                    created_at=NOW,
                )
            )


def export_session(database: CoachDatabase) -> dict:
    return ExportService(database, profile_id=PROFILE).session_to_json(SESSION, now=NOW)


def test_a_session_export_carries_its_turns_in_order(database: CoachDatabase) -> None:
    add_transcript(database)
    turns = export_session(database)["turns"]
    assert [turn["voice"] for turn in turns] == ["coachee", "coach", "coachee"]


def test_a_session_export_keeps_the_coachees_own_words(
    database: CoachDatabase,
) -> None:
    add_transcript(database)
    turns = export_session(database)["turns"]
    assert turns[0]["content"] == "Tôi muốn chuyển sang vai trò kiến trúc sư."


def test_a_credential_in_the_transcript_is_redacted(database: CoachDatabase) -> None:
    """Export is the moment data leaves in bulk, exactly as for records."""
    add_transcript(database)
    payload = export_session(database)
    assert SECRET not in str(payload)
    assert payload["redacted_count"] == 1


def test_a_session_export_carries_the_disclosure(database: CoachDatabase) -> None:
    """An exported copy outlives the screen that explained the storage."""
    add_transcript(database)
    disclosure = export_session(database)["disclosure"]
    assert disclosure["encrypted_at_rest"] is False
    assert disclosure["note"]


def test_a_session_export_names_the_session_and_the_moment(
    database: CoachDatabase,
) -> None:
    add_transcript(database)
    payload = export_session(database)
    assert payload["session_id"] == SESSION
    assert payload["exported_at"] == NOW


def test_a_session_with_no_turns_exports_an_empty_transcript(
    database: CoachDatabase,
) -> None:
    """A session the retention window emptied is not an error."""
    payload = export_session(database)
    assert payload["turns"] == []
    assert payload["redacted_count"] == 0


def test_a_deleted_line_stays_out_of_the_export(database: CoachDatabase) -> None:
    """Export reads through the same active scope as every other read."""
    add_transcript(database)
    with database.transaction():
        database.connection.execute(
            "UPDATE session_message SET deleted_at = :now WHERE id = :id",
            {"now": NOW, "id": "message-0"},
        )
    turns = export_session(database)["turns"]
    assert all("kiến trúc sư" not in turn["content"] for turn in turns)


def test_another_sessions_lines_are_not_included(database: CoachDatabase) -> None:
    from hermes_coach.infrastructure.repositories.session_message_repository import (
        SessionMessageRepository,
        SessionMessageRow,
    )

    add_transcript(database)
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coaching_session (id, started_at, coaching_stage) "
            "VALUES (:id, :now, 'goal')",
            {"id": "session-2", "now": NOW},
        )
        SessionMessageRepository(database.connection).add(
            SessionMessageRow(
                id="other-1",
                session_id="session-2",
                sequence_no=0,
                role="coachee",
                content="Phiên khác",
                created_at=NOW,
            )
        )
    turns = export_session(database)["turns"]
    assert all(turn["content"] != "Phiên khác" for turn in turns)
