"""Consent over RPC.

Requirement families: `HC-PRIVACY`, `HC-UX`; sources `SRC-026`, `SRC-091`,
`SRC-092`.

Onboarding is where consent is first collected, so this is the surface that has
to refuse everything but a real UI control. A conversational "yes" is not
consent, and the method offers no way to express one.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from hermes_coach.api.app import COACH_WS_PATH, MethodRegistry, create_app
from hermes_coach.api.methods import DEFAULT_PROFILE_ID, register_coach_methods
from hermes_coach.api.security import LoopbackGuard
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


TOKEN = "t" * 32
PORT = 8731
NOW = "2026-01-01T00:00:00Z"
EGRESS = "model_egress"


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


def record(socket, *, event_id="consent-1", action="confirm", scope=None,
           control_id="btn-consent-confirm", consent_type=EGRESS, request_id=1):
    return call(
        socket,
        "coach.consent.record",
        {
            "event_id": event_id,
            "consent_type": consent_type,
            "scope": scope if scope is not None else {},
            "ui_action": action,
            "control_id": control_id,
        },
        request_id=request_id,
    )


def state(socket, *, consent_type=EGRESS, scope=None, request_id=9) -> dict:
    return call(
        socket,
        "coach.consent.state",
        {"consent_type": consent_type, "scope": scope if scope is not None else {}},
        request_id=request_id,
    )["result"]


def test_both_consent_methods_are_registered(database: CoachDatabase) -> None:
    registry = MethodRegistry()
    register_coach_methods(registry, database, adapter=None, clock=lambda: NOW)
    assert "coach.consent.record" in registry.names()
    assert "coach.consent.state" in registry.names()


def test_a_confirm_grants_consent(client: TestClient) -> None:
    with connect(client) as socket:
        assert record(socket)["result"]["decision"] == "granted"
        assert state(socket)["granted"] is True


def test_a_decline_does_not_grant(client: TestClient) -> None:
    with connect(client) as socket:
        record(socket, action="decline", control_id="btn-consent-decline")
        assert state(socket)["granted"] is False
        assert state(socket)["decision"] == "declined"


def test_a_withdrawal_takes_effect_immediately(client: TestClient) -> None:
    with connect(client) as socket:
        record(socket, event_id="c1", action="confirm")
        assert state(socket)["granted"] is True
        record(
            socket,
            event_id="c2",
            action="withdraw",
            control_id="btn-consent-withdraw",
            request_id=2,
        )
        assert state(socket)["granted"] is False


def test_absent_consent_reads_as_not_granted(client: TestClient) -> None:
    with connect(client) as socket:
        answer = state(socket)
    assert answer["granted"] is False
    assert answer["decision"] is None


def test_a_control_id_is_required(client: TestClient) -> None:
    """A UI control is the only evidence; there is no other way in."""
    with connect(client) as socket:
        reply = record(socket, control_id="   ")
    assert reply["error"]["code"] == "invalid_request"


def test_an_unknown_ui_action_is_refused(client: TestClient) -> None:
    with connect(client) as socket:
        reply = record(socket, action="probably")
    assert reply["error"]["code"] == "invalid_request"


def test_the_caller_cannot_choose_the_decision(client: TestClient) -> None:
    """The decision follows from the button, so a caller cannot forge one."""
    with connect(client) as socket:
        socket.send_json(
            {
                "id": 1,
                "method": "coach.consent.record",
                "params": {
                    "event_id": "forged",
                    "consent_type": EGRESS,
                    "scope": {},
                    "ui_action": "decline",
                    "control_id": "btn-consent-decline",
                    "decision": "granted",
                },
            }
        )
        socket.receive_json()
        assert state(socket)["granted"] is False


def test_the_history_is_append_only(client: TestClient, database: CoachDatabase) -> None:
    with connect(client) as socket:
        record(socket, event_id="c1", action="confirm")
        record(
            socket,
            event_id="c2",
            action="withdraw",
            control_id="btn-consent-withdraw",
            request_id=2,
        )
        answer = state(socket)
    assert [event["decision"] for event in answer["history"]] == [
        "granted",
        "withdrawn",
    ]
    assert database.connection.execute(
        "SELECT COUNT(*) AS n FROM consent_event"
    ).fetchone()["n"] == 2


def test_replaying_the_same_event_id_is_idempotent(
    client: TestClient, database: CoachDatabase
) -> None:
    """A retry after a dropped reply must not fail, nor double-record."""
    with connect(client) as socket:
        first = record(socket, event_id="c1")
        second = record(socket, event_id="c1", request_id=2)
    assert first["result"] == second["result"]
    assert database.connection.execute(
        "SELECT COUNT(*) AS n FROM consent_event"
    ).fetchone()["n"] == 1


def test_scopes_are_independent(client: TestClient) -> None:
    with connect(client) as socket:
        record(socket, event_id="c1", scope={"goal_id": "goal-1"})
        assert state(socket, scope={"goal_id": "goal-1"})["granted"] is True
        assert state(socket, scope={"goal_id": "goal-2"})["granted"] is False
        assert state(socket, scope={})["granted"] is False


def test_consent_types_are_independent(client: TestClient) -> None:
    with connect(client) as socket:
        record(socket, event_id="c1", consent_type="local_storage")
        assert state(socket, consent_type="local_storage")["granted"] is True
        assert state(socket, consent_type=EGRESS)["granted"] is False


def test_recording_consent_does_not_move_a_session_revision(
    client: TestClient, database: CoachDatabase
) -> None:
    from hermes_coach.infrastructure.repositories.rpc_repository import (
        SessionRevisionRepository,
    )

    with connect(client) as socket:
        record(socket)
    assert SessionRevisionRepository(database.connection).current("session-1") == 0


def test_every_stored_event_is_ui_sourced(
    client: TestClient, database: CoachDatabase
) -> None:
    with connect(client) as socket:
        record(socket)
    rows = database.connection.execute("SELECT source FROM consent_event").fetchall()
    assert {row["source"] for row in rows} == {"ui"}
