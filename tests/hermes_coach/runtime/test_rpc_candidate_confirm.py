"""Candidate confirmation over RPC.

Requirement families: `HC-RECORDS`, `HC-UX`; sources `SRC-054…059`, `SRC-079`,
`SRC-080`, `SRC-084`, `SRC-085`.

The invariant this closes: a record becomes official one at a time, on an
explicit UI action, and never twice. Everything that enforces it already exists
in `DurableConfirmationService`; these tests prove the RPC surface exposes it
without adding a path around it.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from hermes_coach.api.app import COACH_WS_PATH, MethodRegistry, create_app
from hermes_coach.api.methods import DEFAULT_PROFILE_ID, register_coach_methods
from hermes_coach.api.security import LoopbackGuard
from hermes_coach.domain.records import CandidateRecordRow
from hermes_coach.infrastructure.repositories.candidate_repository import (
    CandidateRepository,
)
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


TOKEN = "t" * 32
PORT = 8731
NOW = "2026-01-01T00:00:00Z"
SESSION = "session-1"


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        yield db


@pytest.fixture
def client(database: CoachDatabase) -> Iterator[TestClient]:
    registry = MethodRegistry()
    register_coach_methods(registry, database, adapter=None, clock=lambda: NOW)
    app = create_app(
        LoopbackGuard(token=TOKEN, port=PORT),
        registry,
        database=database,
        clock=lambda: NOW,
    )
    test_client = TestClient(
        app, base_url=f"http://127.0.0.1:{PORT}", client=("127.0.0.1", 54321)
    )
    with test_client:
        yield test_client


def connect(test_client: TestClient):
    return test_client.websocket_connect(
        f"{COACH_WS_PATH}?token={TOKEN}", headers={"host": f"127.0.0.1:{PORT}"}
    )


def call(socket, method: str, params: dict, request_id: int = 1) -> dict:
    socket.send_json({"id": request_id, "method": method, "params": params})
    return socket.receive_json()


def seed(database: CoachDatabase, candidate_id: str = "candidate-1", **overrides):
    with database.transaction():
        database.connection.execute(
            "INSERT OR IGNORE INTO coaching_session (id, started_at, coaching_stage) "
            "VALUES (?, ?, 'goal')",
            (SESSION, NOW),
        )
        values = {
            "id": candidate_id,
            "session_id": SESSION,
            "record_type": "goal",
            "payload_json": '{"title": "Chuyển sang vai trò kiến trúc sư"}',
            "status": "pending",
            "created_at": NOW,
        }
        values.update(overrides)
        CandidateRepository(database.connection).add(
            CandidateRecordRow.model_validate(values)
        )


def mint(socket, candidate_id: str = "candidate-1", action: str = "accept", **extra):
    params = {"session_id": SESSION, "candidate_id": candidate_id, "action": action}
    params.update(extra)
    return call(socket, "coach.candidate.intent", params)


def confirm(socket, token: str, *, command_id="cmd-1", candidate_id="candidate-1",
            action="accept", request_id=2, **extra):
    params = {
        "command_id": command_id,
        "intent_token": token,
        "candidate_id": candidate_id,
        "action": action,
    }
    params.update(extra)
    return call(socket, "coach.candidate.confirm", params, request_id=request_id)


def status_of(database: CoachDatabase, candidate_id: str) -> str:
    return database.connection.execute(
        "SELECT status FROM candidate_record WHERE id = ?", (candidate_id,)
    ).fetchone()["status"]


def test_both_methods_are_registered(database: CoachDatabase) -> None:
    registry = MethodRegistry()
    register_coach_methods(registry, database, adapter=None, clock=lambda: NOW)
    assert "coach.candidate.intent" in registry.names()
    assert "coach.candidate.confirm" in registry.names()


def test_no_method_confirms_more_than_one_record(database: CoachDatabase) -> None:
    """The whole point: there is no bulk path, at any layer."""
    registry = MethodRegistry()
    register_coach_methods(registry, database, adapter=None, clock=lambda: NOW)
    for name in registry.names():
        assert not name.endswith(".confirm_all")
        assert "batch" not in name and "bulk" not in name


def test_accepting_a_candidate_creates_the_official_record(
    client: TestClient, database: CoachDatabase
) -> None:
    seed(database)
    with connect(client) as socket:
        token = mint(socket)["result"]["intent_token"]
        result = confirm(socket, token)["result"]

    assert result["official_record_type"] == "goal"
    assert status_of(database, "candidate-1") == "confirmed"
    goal = database.connection.execute(
        "SELECT title FROM goal WHERE id = ?", (result["official_record_id"],)
    ).fetchone()
    assert goal["title"] == "Chuyển sang vai trò kiến trúc sư"


def test_editing_writes_the_edited_value(
    client: TestClient, database: CoachDatabase
) -> None:
    seed(database)
    edited = "Chuyển vai trò trong 6 tháng"
    with connect(client) as socket:
        token = mint(socket, action="edit", edited_value=edited)["result"][
            "intent_token"
        ]
        result = confirm(socket, token, action="edit", edited_value=edited)["result"]

    assert status_of(database, "candidate-1") == "edited"
    goal = database.connection.execute(
        "SELECT title FROM goal WHERE id = ?", (result["official_record_id"],)
    ).fetchone()
    assert goal["title"] == edited


def test_discarding_creates_no_official_record(
    client: TestClient, database: CoachDatabase
) -> None:
    seed(database)
    with connect(client) as socket:
        token = mint(socket, action="discard")["result"]["intent_token"]
        result = confirm(socket, token, action="discard")["result"]

    assert result["official_record_id"] is None
    assert status_of(database, "candidate-1") == "discarded"
    assert database.connection.execute(
        "SELECT COUNT(*) AS n FROM goal"
    ).fetchone()["n"] == 0


def test_confirming_without_an_intent_is_refused(
    client: TestClient, database: CoachDatabase
) -> None:
    """A forged confirmation with no minted intent must not apply."""
    seed(database)
    with connect(client) as socket:
        reply = confirm(socket, "x" * 43, request_id=1)
    assert reply["error"]["code"] == "confirmation_rejected"
    assert status_of(database, "candidate-1") == "pending"


def test_an_intent_cannot_be_used_twice(
    client: TestClient, database: CoachDatabase
) -> None:
    seed(database)
    with connect(client) as socket:
        token = mint(socket)["result"]["intent_token"]
        confirm(socket, token)
        replay = confirm(socket, token, command_id="cmd-2", request_id=3)
    assert replay["error"]["code"] == "confirmation_rejected"
    assert database.connection.execute(
        "SELECT COUNT(*) AS n FROM goal"
    ).fetchone()["n"] == 1


def test_a_replayed_command_id_is_refused(
    client: TestClient, database: CoachDatabase
) -> None:
    """The service's own replay guard, reachable through RPC."""
    seed(database)
    with connect(client) as socket:
        confirm(socket, mint(socket)["result"]["intent_token"])
        # Re-present the record in Review, which needs `reconfirm`, then reuse
        # the command id. A fresh valid intent must not resurrect a spent
        # command.
        again = mint(socket, request_id=3, reconfirm=True)["result"]["intent_token"]
        replay = confirm(
            socket, again, command_id="cmd-1", request_id=4, reconfirm=True
        )
    assert replay["error"]["code"] == "confirmation_rejected"
    assert database.connection.execute(
        "SELECT COUNT(*) AS n FROM goal"
    ).fetchone()["n"] == 1


def test_an_intent_bound_to_another_action_is_refused(
    client: TestClient, database: CoachDatabase
) -> None:
    seed(database)
    with connect(client) as socket:
        token = mint(socket, action="accept")["result"]["intent_token"]
        reply = confirm(socket, token, action="discard")
    assert reply["error"]["code"] == "confirmation_rejected"
    assert status_of(database, "candidate-1") == "pending"


def test_an_intent_bound_to_another_candidate_is_refused(
    client: TestClient, database: CoachDatabase
) -> None:
    seed(database)
    seed(database, "candidate-2")
    with connect(client) as socket:
        token = mint(socket, "candidate-1")["result"]["intent_token"]
        reply = confirm(socket, token, candidate_id="candidate-2")
    assert reply["error"]["code"] == "confirmation_rejected"
    assert status_of(database, "candidate-2") == "pending"


def test_an_edited_payload_that_differs_from_the_intent_is_refused(
    client: TestClient, database: CoachDatabase
) -> None:
    seed(database)
    with connect(client) as socket:
        token = mint(socket, action="edit", edited_value="Giá trị đã duyệt")["result"][
            "intent_token"
        ]
        reply = confirm(socket, token, action="edit", edited_value="Giá trị khác")
    assert reply["error"]["code"] == "confirmation_rejected"
    assert status_of(database, "candidate-1") == "pending"


def test_minting_an_intent_for_a_resolved_candidate_is_refused(
    client: TestClient, database: CoachDatabase
) -> None:
    seed(database, "candidate-done", status="confirmed", resolved_at=NOW)
    with connect(client) as socket:
        reply = mint(socket, "candidate-done")
    assert reply["error"]["code"] == "confirmation_rejected"


def test_minting_never_returns_the_stored_form_of_the_token(
    client: TestClient, database: CoachDatabase
) -> None:
    """The database keeps a digest; the raw token exists only in the reply."""
    seed(database)
    with connect(client) as socket:
        token = mint(socket)["result"]["intent_token"]
    stored = database.connection.execute(
        "SELECT * FROM internal_confirmation_intent"
    ).fetchall()
    assert stored
    assert all(token not in str(dict(row)) for row in stored)


def test_minting_does_not_move_the_session_revision(
    client: TestClient, database: CoachDatabase
) -> None:
    """Offering a confirmation is not a change to the session."""
    from hermes_coach.infrastructure.repositories.rpc_repository import (
        SessionRevisionRepository,
    )

    seed(database)
    with connect(client) as socket:
        mint(socket)
    assert SessionRevisionRepository(database.connection).current(SESSION) == 0


def test_a_failed_confirmation_leaves_the_candidate_offerable(
    client: TestClient, database: CoachDatabase
) -> None:
    """A rejected attempt must not burn the candidate."""
    seed(database)
    with connect(client) as socket:
        confirm(socket, "y" * 43, request_id=1)
        token = mint(socket, request_id=2)["result"]["intent_token"]
        result = confirm(socket, token, request_id=3)["result"]
    assert result["official_record_id"]
    assert status_of(database, "candidate-1") == "confirmed"


def test_the_audit_trail_is_reachable_and_content_free(
    client: TestClient, database: CoachDatabase
) -> None:
    secret = "Nội dung riêng tư"
    seed(database, payload_json=f'{{"title": "{secret}"}}')
    with connect(client) as socket:
        confirm(socket, mint(socket)["result"]["intent_token"])
    rows = database.connection.execute(
        "SELECT * FROM internal_confirmation_audit"
    ).fetchall()
    assert len(rows) == 1
    assert all(secret not in str(dict(row)) for row in rows)
