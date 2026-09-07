"""Durable candidate confirmation.

Requirement families: `HC-RECORDS`, `HC-DATA-*`; sources `SRC-054…059`,
`SRC-079`, `SRC-080`, `SRC-084`, `SRC-085`.

Phase 2 made confirmation one-use inside a single process. Phase 3 must make the
intent check, the command guard, the candidate transition and the official
record write one durable transaction, so a restart or a second process cannot
replay a confirmation.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from hermes_coach.application.durable_confirmation_service import (
    ConfirmationRejected,
    DurableConfirmationService,
)
from hermes_coach.application.record_confirmation_service import (
    ConfirmationCommand,
    RecordAction,
)
from hermes_coach.domain.records import CandidateRecordRow
from hermes_coach.infrastructure.repositories.candidate_repository import (
    CandidateRepository,
)
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-08-22T00:00:00Z"
SOON = "2026-08-22T00:01:00Z"
AFTER = "2026-08-22T00:02:00Z"
LATE = "2026-08-22T01:00:00Z"

USER = "local-user"
PROFILE = "profile-1"
SESSION = "session-1"


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        seed(db)
        yield db


def seed(database: CoachDatabase) -> None:
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
        CandidateRepository(database.connection).add(
            CandidateRecordRow(
                id="candidate-1",
                session_id=SESSION,
                record_type="goal",
                payload_json='{"title": "Chuyển sang vai trò kiến trúc sư"}',
                status="pending",
                created_at=NOW,
            )
        )


def service(database: CoachDatabase) -> DurableConfirmationService:
    return DurableConfirmationService(database, profile_id=PROFILE)


def issue(
    database: CoachDatabase,
    *,
    candidate_id: str = "candidate-1",
    action: RecordAction = RecordAction.ACCEPT,
    edited_value: str | None = None,
    now: str = NOW,
    reconfirm: bool = False,
) -> str:
    return service(database).issue_intent(
        local_user_id=USER,
        session_id=SESSION,
        candidate_id=candidate_id,
        action=action,
        edited_value=edited_value,
        now=now,
        reconfirm=reconfirm,
    )


def command(
    token: str,
    *,
    command_id: str = "command-1",
    candidate_id: str = "candidate-1",
    action: RecordAction = RecordAction.ACCEPT,
    edited_value: str | None = None,
) -> ConfirmationCommand:
    return ConfirmationCommand(
        command_id=command_id,
        intent_token=token,
        candidate_id=candidate_id,
        action=action,
        edited_value=edited_value,
    )


def candidate_status(database: CoachDatabase, candidate_id: str) -> str:
    row = database.connection.execute(
        "SELECT status FROM candidate_record WHERE id = ?", (candidate_id,)
    ).fetchone()
    return row["status"]


def goal_count(database: CoachDatabase) -> int:
    return database.connection.execute(
        "SELECT COUNT(*) AS total FROM goal"
    ).fetchone()["total"]


def test_accept_creates_the_official_record_and_resolves_the_candidate(
    database: CoachDatabase,
) -> None:
    token = issue(database)
    outcome = service(database).apply(command(token), now=SOON)

    assert outcome.official_record_type == "goal"
    assert outcome.official_record_id
    assert candidate_status(database, "candidate-1") == "confirmed"

    goal = GoalRepository(database.connection).get(outcome.official_record_id)
    assert goal is not None
    assert goal.title == "Chuyển sang vai trò kiến trúc sư"
    assert goal.confirmed_at == SOON
    assert goal.source_session_id == SESSION


def test_edit_writes_the_edited_value_not_the_original(
    database: CoachDatabase,
) -> None:
    edited = "Chuyển sang vai trò kiến trúc sư trong 6 tháng"
    token = issue(database, action=RecordAction.EDIT, edited_value=edited)
    outcome = service(database).apply(
        command(token, action=RecordAction.EDIT, edited_value=edited), now=SOON
    )

    assert candidate_status(database, "candidate-1") == "edited"
    goal = GoalRepository(database.connection).get(outcome.official_record_id or "")
    assert goal is not None
    assert goal.title == edited


def test_discard_resolves_the_candidate_and_writes_no_official_record(
    database: CoachDatabase,
) -> None:
    token = issue(database, action=RecordAction.DISCARD)
    outcome = service(database).apply(command(token, action=RecordAction.DISCARD), now=SOON)

    assert outcome.official_record_id is None
    assert outcome.official_record_type is None
    assert candidate_status(database, "candidate-1") == "discarded"
    assert goal_count(database) == 0


def test_replaying_the_same_command_is_refused(database: CoachDatabase) -> None:
    """A fresh valid intent must not let an already-applied command run twice."""
    service(database).apply(command(issue(database)), now=SOON)

    edited = "Sửa lại trong Review"
    again = issue(
        database,
        action=RecordAction.EDIT,
        edited_value=edited,
        now=SOON,
        reconfirm=True,
    )
    with pytest.raises(ConfirmationRejected, match="command"):
        service(database).apply(
            command(again, action=RecordAction.EDIT, edited_value=edited),
            now=AFTER,
            reconfirm=True,
        )
    assert goal_count(database) == 1


def test_an_intent_is_single_use(database: CoachDatabase) -> None:
    token = issue(database)
    service(database).apply(command(token), now=SOON)

    with pytest.raises(ConfirmationRejected, match="intent"):
        service(database).apply(command(token, command_id="command-2"), now=SOON)
    assert goal_count(database) == 1


def test_a_consumed_intent_stays_consumed_after_restart(tmp_path) -> None:
    """In-memory single-use is not enough; a restart must not reopen the window."""
    path = tmp_path / "coach.db"
    with open_coach_database(path) as database:
        seed(database)
        token = issue(database)
        service(database).apply(command(token), now=SOON)

    with open_coach_database(path) as reopened:
        with pytest.raises(ConfirmationRejected, match="intent"):
            service(reopened).apply(command(token, command_id="command-2"), now=SOON)
        assert goal_count(reopened) == 1


def test_a_replayed_command_is_refused_after_restart(tmp_path) -> None:
    path = tmp_path / "coach.db"
    with open_coach_database(path) as database:
        seed(database)
        service(database).apply(command(issue(database)), now=SOON)

    with open_coach_database(path) as reopened:
        edited = "Sửa sau khi khởi động lại"
        fresh = issue(
            reopened,
            action=RecordAction.EDIT,
            edited_value=edited,
            now=SOON,
            reconfirm=True,
        )
        with pytest.raises(ConfirmationRejected, match="command"):
            service(reopened).apply(
                command(fresh, action=RecordAction.EDIT, edited_value=edited),
                now=AFTER,
                reconfirm=True,
            )
        assert goal_count(reopened) == 1


def test_an_expired_intent_is_refused(database: CoachDatabase) -> None:
    token = issue(database, now=NOW)
    with pytest.raises(ConfirmationRejected, match="expired"):
        service(database).apply(command(token), now=LATE)
    assert candidate_status(database, "candidate-1") == "pending"


def test_an_intent_issued_for_another_action_is_refused(
    database: CoachDatabase,
) -> None:
    token = issue(database, action=RecordAction.ACCEPT)
    with pytest.raises(ConfirmationRejected, match="binding"):
        service(database).apply(command(token, action=RecordAction.DISCARD), now=SOON)
    assert candidate_status(database, "candidate-1") == "pending"


def test_an_intent_issued_for_another_candidate_is_refused(
    database: CoachDatabase,
) -> None:
    with database.transaction():
        CandidateRepository(database.connection).add(
            CandidateRecordRow(
                id="candidate-2",
                session_id=SESSION,
                record_type="insight",
                payload_json='{"content": "Tôi né xung đột"}',
                status="pending",
                created_at=NOW,
            )
        )
    token = issue(database, candidate_id="candidate-1")
    with pytest.raises(ConfirmationRejected, match="binding"):
        service(database).apply(command(token, candidate_id="candidate-2"), now=SOON)
    assert candidate_status(database, "candidate-2") == "pending"


def test_an_edited_payload_that_differs_from_the_intent_is_refused(
    database: CoachDatabase,
) -> None:
    """The intent binds the payload, so the UI cannot swap it after issue."""
    token = issue(
        database, action=RecordAction.EDIT, edited_value="Giá trị đã duyệt"
    )
    with pytest.raises(ConfirmationRejected, match="binding"):
        service(database).apply(
            command(token, action=RecordAction.EDIT, edited_value="Giá trị khác"),
            now=SOON,
        )
    assert candidate_status(database, "candidate-1") == "pending"


def test_an_unknown_intent_token_is_refused(database: CoachDatabase) -> None:
    with pytest.raises(ConfirmationRejected, match="intent"):
        service(database).apply(command("x" * 48), now=SOON)


def test_a_failed_official_write_rolls_back_the_candidate_transition(
    database: CoachDatabase, monkeypatch
) -> None:
    """Both sides of the confirmation commit, or neither does."""

    def explode(self, goal) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(GoalRepository, "add", explode)

    token = issue(database)
    with pytest.raises(RuntimeError):
        service(database).apply(command(token), now=SOON)

    assert candidate_status(database, "candidate-1") == "pending"
    assert goal_count(database) == 0
    # The intent must survive too, or a transient failure would burn it.
    monkeypatch.undo()
    outcome = service(database).apply(command(token, command_id="command-3"), now=SOON)
    assert outcome.official_record_id


def test_a_resolved_candidate_is_not_offered_a_new_intent(
    database: CoachDatabase,
) -> None:
    service(database).apply(command(issue(database)), now=SOON)
    with pytest.raises(ConfirmationRejected, match="resolved"):
        issue(database)


def test_a_candidate_resolved_after_issue_is_refused_at_apply(
    database: CoachDatabase,
) -> None:
    """The issue-time check cannot see a resolution that happens after it."""
    token = issue(database)
    with database.transaction():
        database.connection.execute(
            "UPDATE candidate_record SET status = 'discarded', resolved_at = ? "
            "WHERE id = 'candidate-1'",
            (SOON,),
        )
    with pytest.raises(ConfirmationRejected, match="no longer pending"):
        service(database).apply(command(token, command_id="command-4"), now=SOON)
    assert goal_count(database) == 0


def test_reconfirmation_adds_a_revision_instead_of_mutating_the_first(
    database: CoachDatabase,
) -> None:
    first = service(database).apply(command(issue(database)), now=SOON)

    edited = "Mục tiêu đã chỉnh trong Review"
    token = service(database).issue_intent(
        local_user_id=USER,
        session_id=SESSION,
        candidate_id="candidate-1",
        action=RecordAction.EDIT,
        edited_value=edited,
        now=SOON,
        reconfirm=True,
    )
    second = service(database).apply(
        command(
            token,
            command_id="command-reconfirm",
            action=RecordAction.EDIT,
            edited_value=edited,
        ),
        now=AFTER,
        reconfirm=True,
    )

    assert second.revision == first.revision + 1
    assert second.official_record_id != first.official_record_id

    trail = service(database).audit_trail("candidate-1")
    assert [entry.revision for entry in trail] == [1, 2]
    assert [entry.official_record_id for entry in trail] == [
        first.official_record_id,
        second.official_record_id,
    ]
    # The earlier record is still there; provenance was not rewritten.
    assert GoalRepository(database.connection).get(first.official_record_id or "")


def test_audit_records_the_official_id_and_no_payload_content(
    database: CoachDatabase,
) -> None:
    secret = "Nội dung riêng tư không được vào audit"
    token = issue(database, action=RecordAction.EDIT, edited_value=secret)
    outcome = service(database).apply(
        command(token, action=RecordAction.EDIT, edited_value=secret), now=SOON
    )

    entry = service(database).audit_trail("candidate-1")[0]
    assert entry.official_record_id == outcome.official_record_id
    assert entry.action == "edit"
    assert secret not in repr(entry.model_dump())

    stored = database.connection.execute(
        "SELECT * FROM internal_confirmation_audit"
    ).fetchall()
    assert all(secret not in str(dict(row)) for row in stored)


def test_no_batch_confirmation_path_exists(database: CoachDatabase) -> None:
    """Candidates are confirmed one at a time; a bulk method would break that."""
    names = dir(service(database)) + dir(CandidateRepository(database.connection))
    for name in names:
        if name.startswith("_"):
            continue
        assert "batch" not in name.lower()
        assert "bulk" not in name.lower()
        assert not name.endswith("_all")


@pytest.mark.parametrize(
    ("record_type", "payload", "table", "column", "expected"),
    [
        ("goal", '{"title": "Mục tiêu"}', "goal", "title", "Mục tiêu"),
        ("insight", '{"content": "Nhận ra"}', "insight", "content", "Nhận ra"),
        ("memory", '{"content": "Giá trị"}', "memory_item", "content", "Giá trị"),
    ],
)
def test_each_candidate_type_materializes_its_own_official_table(
    database: CoachDatabase,
    record_type: str,
    payload: str,
    table: str,
    column: str,
    expected: str,
) -> None:
    candidate_id = f"candidate-{record_type}"
    with database.transaction():
        CandidateRepository(database.connection).add(
            CandidateRecordRow(
                id=candidate_id,
                session_id=SESSION,
                record_type=record_type,  # type: ignore[arg-type]
                payload_json=payload,
                status="pending",
                created_at=NOW,
            )
        )
    token = issue(database, candidate_id=candidate_id)
    outcome = service(database).apply(
        command(token, command_id=f"command-{record_type}", candidate_id=candidate_id),
        now=SOON,
    )

    assert outcome.official_record_type == table
    row = database.connection.execute(
        f"SELECT {column} AS value FROM {table} WHERE id = ?",
        (outcome.official_record_id,),
    ).fetchone()
    assert row["value"] == expected


def test_confirmed_memory_is_written_without_an_expiry(
    database: CoachDatabase,
) -> None:
    with database.transaction():
        CandidateRepository(database.connection).add(
            CandidateRecordRow(
                id="candidate-memory",
                session_id=SESSION,
                record_type="memory",
                payload_json='{"content": "Coachee coi trọng quyền tự chủ"}',
                status="pending",
                created_at=NOW,
            )
        )
    token = issue(database, candidate_id="candidate-memory")
    outcome = service(database).apply(
        command(token, command_id="command-memory", candidate_id="candidate-memory"),
        now=SOON,
    )

    row = database.connection.execute(
        "SELECT user_confirmed, expires_at FROM memory_item WHERE id = ?",
        (outcome.official_record_id,),
    ).fetchone()
    assert row["user_confirmed"] == 1
    assert row["expires_at"] is None


def test_confirming_memory_records_its_provenance(database: CoachDatabase) -> None:
    with database.transaction():
        CandidateRepository(database.connection).add(
            CandidateRecordRow(
                id="candidate-memory",
                session_id=SESSION,
                record_type="memory",
                payload_json='{"content": "Coachee coi trọng quyền tự chủ"}',
                status="pending",
                created_at=NOW,
            )
        )
    token = issue(database, candidate_id="candidate-memory")
    outcome = service(database).apply(
        command(token, command_id="command-memory", candidate_id="candidate-memory"),
        now=SOON,
    )

    rows = database.connection.execute(
        "SELECT * FROM memory_provenance WHERE memory_item_id = ?",
        (outcome.official_record_id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["source_type"] == "session"
    assert rows[0]["source_session_id"] == SESSION
    assert rows[0]["relation"] == "confirmed_from"


def test_the_intent_token_is_not_stored_in_the_clear(
    database: CoachDatabase,
) -> None:
    token = issue(database)
    stored = database.connection.execute(
        "SELECT * FROM internal_confirmation_intent"
    ).fetchall()
    assert stored
    assert all(token not in str(dict(row)) for row in stored)


def test_a_second_intent_for_the_same_candidate_supersedes_the_first(
    database: CoachDatabase,
) -> None:
    """Re-rendering the confirmation UI must not leave two usable tokens."""
    first = issue(database)
    second = issue(database)
    assert first != second

    with pytest.raises(ConfirmationRejected, match="intent"):
        service(database).apply(command(first), now=SOON)
    assert service(database).apply(command(second, command_id="command-5"), now=SOON)


def test_expired_intents_do_not_accumulate_forever(database: CoachDatabase) -> None:
    issue(database, now=NOW)
    service(database).purge_expired_intents(LATE)
    remaining = database.connection.execute(
        "SELECT COUNT(*) AS total FROM internal_confirmation_intent"
    ).fetchone()["total"]
    assert remaining == 0


def test_a_candidate_from_another_session_is_refused(
    database: CoachDatabase,
) -> None:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coaching_session (id, started_at, coaching_stage) "
            "VALUES ('session-2', ?, 'goal')",
            (NOW,),
        )
        CandidateRepository(database.connection).add(
            CandidateRecordRow(
                id="candidate-other",
                session_id="session-2",
                record_type="goal",
                payload_json='{"title": "Của phiên khác"}',
                status="pending",
                created_at=NOW,
            )
        )
    with pytest.raises(ConfirmationRejected, match="session"):
        issue(database, candidate_id="candidate-other")


def test_the_audit_table_is_internal_and_holds_a_unique_command(
    database: CoachDatabase,
) -> None:
    service(database).apply(command(issue(database)), now=SOON)
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction():
            database.connection.execute(
                "INSERT INTO internal_confirmation_audit "
                "(id, command_id, candidate_id, revision, action, created_at) "
                "VALUES ('forged', 'command-1', 'candidate-1', 9, 'accept', ?)",
                (NOW,),
            )
