"""Mutating RPC commands over the socket.

Requirement families: `HC-PRODUCT`, `HC-DATA-*`; sources `SRC-104…106`.

`SessionRevisionRepository` and `IdempotencyRepository` are unit-tested against
the database; this file proves the dispatcher actually applies them, that a
read-only method is not burdened with them, and that a rejected command leaves
no trace.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from hermes_coach.api.app import COACH_WS_PATH, MethodRegistry, create_app
from hermes_coach.api.security import LoopbackGuard
from hermes_coach.infrastructure.repositories.rpc_repository import (
    SessionRevisionRepository,
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
        with db.transaction():
            db.connection.execute(
                "INSERT INTO coachee_profile (id, display_name, created_at) "
                "VALUES ('profile-1', 'Coachee', ?)",
                (NOW,),
            )
            db.connection.execute(
                "INSERT INTO coaching_session (id, started_at, coaching_stage) "
                "VALUES (?, ?, 'goal')",
                (SESSION, NOW),
            )
        yield db


@pytest.fixture
def applied() -> list[str]:
    return []


@pytest.fixture
def client(database: CoachDatabase, applied: list[str]) -> Iterator[TestClient]:
    methods = MethodRegistry()

    def rename(params: dict) -> dict:
        applied.append(params["title"])
        return {"title": params["title"]}

    methods.register("coach.rename", rename, mutating=True)
    methods.register("coach.read", lambda params: {"stage": "goal"})

    app = create_app(
        LoopbackGuard(token=TOKEN, port=PORT),
        methods,
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


def mutate(
    socket,
    *,
    request_id: int = 1,
    revision: int = 0,
    key: str = "key-1",
    title: str = "Mục tiêu mới",
) -> dict:
    socket.send_json(
        {
            "id": request_id,
            "method": "coach.rename",
            "params": {
                "session_id": SESSION,
                "revision": revision,
                "idempotency_key": key,
                "title": title,
            },
        }
    )
    return socket.receive_json()


def test_a_mutation_at_the_current_revision_is_applied(
    client: TestClient, applied: list[str], database: CoachDatabase
) -> None:
    with connect(client) as socket:
        assert mutate(socket)["result"] == {"title": "Mục tiêu mới"}
    assert applied == ["Mục tiêu mới"]
    assert SessionRevisionRepository(database.connection).current(SESSION) == 1


def test_a_mutation_on_a_stale_view_is_refused(
    client: TestClient, applied: list[str]
) -> None:
    with connect(client) as socket:
        mutate(socket, revision=0, key="key-1")
        reply = mutate(socket, request_id=2, revision=0, key="key-2")
    assert reply["error"]["code"] == "stale_revision"
    assert applied == ["Mục tiêu mới"]


def test_a_refused_mutation_does_not_move_the_revision(
    client: TestClient, database: CoachDatabase
) -> None:
    with connect(client) as socket:
        mutate(socket, revision=7, key="key-1")
    assert SessionRevisionRepository(database.connection).current(SESSION) == 0


def test_a_refused_mutation_remembers_nothing(
    client: TestClient, applied: list[str]
) -> None:
    """A rejected key must stay usable once the client refreshes its view."""
    with connect(client) as socket:
        assert mutate(socket, revision=7, key="key-1")["error"]["code"] == (
            "stale_revision"
        )
        assert mutate(socket, request_id=2, revision=0, key="key-1")["result"] == {
            "title": "Mục tiêu mới"
        }
    assert applied == ["Mục tiêu mới"]


def test_replaying_a_command_returns_the_first_result_without_reapplying(
    client: TestClient, applied: list[str], database: CoachDatabase
) -> None:
    with connect(client) as socket:
        first = mutate(socket, key="key-1", title="Bản đầu")
        # A retry after a dropped reply: same key, and the stale revision the
        # client still believes in.
        second = mutate(socket, request_id=2, revision=0, key="key-1", title="Bản hai")

    assert first["result"] == second["result"] == {"title": "Bản đầu"}
    assert applied == ["Bản đầu"]
    assert SessionRevisionRepository(database.connection).current(SESSION) == 1


def test_a_replay_is_answered_even_though_its_revision_is_now_stale(
    client: TestClient,
) -> None:
    """Idempotency is checked before revision, or no retry could ever succeed."""
    with connect(client) as socket:
        mutate(socket, key="key-1")
        reply = mutate(socket, request_id=2, revision=0, key="key-1")
    assert "error" not in reply


def test_a_mutation_without_an_idempotency_key_is_refused(
    client: TestClient, applied: list[str]
) -> None:
    with connect(client) as socket:
        socket.send_json(
            {
                "id": 1,
                "method": "coach.rename",
                "params": {"session_id": SESSION, "revision": 0, "title": "x"},
            }
        )
        reply = socket.receive_json()
    assert reply["error"]["code"] == "invalid_request"
    assert applied == []


def test_a_mutation_without_a_revision_is_refused(
    client: TestClient, applied: list[str]
) -> None:
    with connect(client) as socket:
        socket.send_json(
            {
                "id": 1,
                "method": "coach.rename",
                "params": {
                    "session_id": SESSION,
                    "idempotency_key": "key-1",
                    "title": "x",
                },
            }
        )
        reply = socket.receive_json()
    assert reply["error"]["code"] == "invalid_request"
    assert applied == []


def test_a_read_only_method_needs_no_envelope(client: TestClient) -> None:
    with connect(client) as socket:
        socket.send_json({"id": 1, "method": "coach.read"})
        assert socket.receive_json()["result"] == {"stage": "goal"}


def test_a_read_only_method_does_not_move_the_revision(
    client: TestClient, database: CoachDatabase
) -> None:
    with connect(client) as socket:
        socket.send_json({"id": 1, "method": "coach.read"})
        socket.receive_json()
    assert SessionRevisionRepository(database.connection).current(SESSION) == 0


def test_a_mutation_that_raises_leaves_no_revision_and_no_memory(
    database: CoachDatabase,
) -> None:
    """A failed command must not consume its key or advance the session."""
    methods = MethodRegistry()

    def explode(params: dict) -> dict:
        raise RuntimeError("write failed")

    methods.register("coach.explode", explode, mutating=True)
    app = create_app(
        LoopbackGuard(token=TOKEN, port=PORT),
        methods,
        database=database,
        clock=lambda: NOW,
    )
    test_client = TestClient(
        app, base_url=f"http://127.0.0.1:{PORT}", client=("127.0.0.1", 54321)
    )
    with test_client, connect(test_client) as socket:
        socket.send_json(
            {
                "id": 1,
                "method": "coach.explode",
                "params": {
                    "session_id": SESSION,
                    "revision": 0,
                    "idempotency_key": "key-1",
                },
            }
        )
        assert socket.receive_json()["error"]["code"] == "internal_error"

    assert SessionRevisionRepository(database.connection).current(SESSION) == 0
    assert database.connection.execute(
        "SELECT COUNT(*) AS total FROM internal_rpc_command"
    ).fetchone()["total"] == 0


def test_a_failure_recording_the_envelope_still_answers(
    client: TestClient, database: CoachDatabase, monkeypatch
) -> None:
    """The dispatcher must always reply.

    This bug shipped once: the envelope commit sat outside the error handling,
    so a failure there sent nothing at all and the client waited forever. An
    error reply is recoverable; silence is not.
    """
    from hermes_coach.infrastructure.repositories.rpc_repository import (
        IdempotencyRepository,
    )

    def explode(self, *args, **kwargs) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(IdempotencyRepository, "remember", explode)

    with connect(client) as socket:
        reply = mutate(socket)

    assert reply["error"]["code"] == "envelope_failed"


def test_declaring_a_mutation_without_a_database_is_refused(
    database: CoachDatabase,
) -> None:
    """Fail at wiring time, not at the first mutation in front of the user."""
    methods = MethodRegistry()
    methods.register("coach.rename", lambda params: {}, mutating=True)
    with pytest.raises(ValueError, match="database"):
        create_app(LoopbackGuard(token=TOKEN, port=PORT), methods)
