"""The Coach WebSocket app end to end over a real client.

Requirement families: `HC-PRODUCT`, `HC-PRIVACY`; sources `SRC-104…106`.

`LoopbackGuard` is unit-tested next door; this file proves the app actually
wires it in front of every connection, and that the RPC surface is an allowlist
rather than anything callable.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hermes_coach.api.app import (
    CLOSE_UNAUTHORIZED,
    COACH_WS_PATH,
    MethodRegistry,
    RpcError,
    create_app,
)
from hermes_coach.api.security import LoopbackGuard


TOKEN = "t" * 32
PORT = 8731  # Not 80: httpx omits the default port, and Host must carry one.


def registry() -> MethodRegistry:
    methods = MethodRegistry()
    methods.register("coach.echo", lambda params: {"said": params.get("text")})
    methods.register("coach.stage", lambda params: {"stage": "goal"})

    def explode(params: dict) -> None:
        raise RpcError("goal_not_found", "no such goal")

    def leak(params: dict) -> None:
        raise RuntimeError("secret path C:/Users/minht/.hermes/config.json")

    methods.register("coach.explode", explode)
    methods.register("coach.leak", leak)
    return methods


def client(token: str = TOKEN, peer: str = "127.0.0.1") -> TestClient:
    app = create_app(LoopbackGuard(token=token, port=PORT), registry())
    # TestClient reports "testclient" as the peer by default; the guard checks a
    # real address, so the harness has to present one.
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}", client=(peer, 54321))


def connect(
    test_client: TestClient,
    *,
    token: str = TOKEN,
    origin: str | None = None,
    host: str = f"127.0.0.1:{PORT}",
):
    # TestClient hardcodes `Host: testserver` for websockets, so a realistic
    # Host has to be supplied explicitly.
    headers = {"host": host}
    if origin:
        headers["origin"] = origin
    return test_client.websocket_connect(
        f"{COACH_WS_PATH}?token={token}", headers=headers
    )


def rejection_reason(test_client: TestClient, **kwargs) -> str:
    """Return why the socket was refused, so a test proves its own check.

    Asserting only the close code would let any rejection satisfy any test —
    a wrong-Host harness once made the origin and token tests pass vacuously.
    """
    with pytest.raises(WebSocketDisconnect) as disconnected:
        with connect(test_client, **kwargs) as socket:
            socket.receive_json()
    assert disconnected.value.code == CLOSE_UNAUTHORIZED
    return disconnected.value.reason


def test_an_authorized_client_can_call_a_method() -> None:
    with client() as test_client, connect(test_client) as socket:
        socket.send_json({"id": 1, "method": "coach.echo", "params": {"text": "chào"}})
        assert socket.receive_json() == {"id": 1, "result": {"said": "chào"}}


def test_a_browser_origin_on_this_server_is_accepted() -> None:
    with client() as test_client:
        with connect(test_client, origin=f"http://127.0.0.1:{PORT}") as socket:
            socket.send_json({"id": 1, "method": "coach.stage"})
            assert socket.receive_json()["result"] == {"stage": "goal"}


def test_a_foreign_origin_is_refused_before_the_socket_opens() -> None:
    with client() as test_client:
        assert "origin" in rejection_reason(test_client, origin="https://evil.invalid")


def test_a_wrong_token_is_refused_before_the_socket_opens() -> None:
    with client() as test_client:
        assert "token" in rejection_reason(test_client, token="x" * 32)


def test_a_foreign_host_is_refused_before_the_socket_opens() -> None:
    with client() as test_client:
        assert "host" in rejection_reason(test_client, host="coach.attacker.invalid")


def test_a_missing_token_is_refused() -> None:
    with client() as test_client:
        assert "token" in rejection_reason(test_client, token="")


def test_an_unregistered_method_is_not_callable() -> None:
    with client() as test_client, connect(test_client) as socket:
        socket.send_json({"id": 2, "method": "coach.drop_everything"})
        assert socket.receive_json()["error"]["code"] == "unknown_method"


def test_a_method_level_failure_keeps_its_stable_code() -> None:
    with client() as test_client, connect(test_client) as socket:
        socket.send_json({"id": 3, "method": "coach.explode"})
        error = socket.receive_json()["error"]
        assert error["code"] == "goal_not_found"
        assert error["message"] == "no such goal"


def test_an_unexpected_error_never_leaks_its_detail() -> None:
    with client() as test_client, connect(test_client) as socket:
        socket.send_json({"id": 4, "method": "coach.leak"})
        error = socket.receive_json()["error"]
        assert error["code"] == "internal_error"
        assert "minht" not in error["message"]
        assert "config.json" not in error["message"]


def test_an_unexpected_error_is_written_to_the_server_log(caplog) -> None:
    """The detail the client must not see, the operator must.

    A live `internal_error` that left no trace anywhere took a full
    reconstruction to diagnose. The traceback belongs in the server log.
    """
    with caplog.at_level(logging.ERROR, logger="hermes_coach"):
        with client() as test_client, connect(test_client) as socket:
            socket.send_json({"id": 40, "method": "coach.leak"})
            assert socket.receive_json()["error"]["code"] == "internal_error"

    traces = "\n".join(record.exc_text or "" for record in caplog.records)
    assert "config.json" in traces


def test_the_failing_method_name_is_logged_not_guessed(caplog) -> None:
    """Logging the wrong name would send the operator to the wrong code."""
    with caplog.at_level(logging.ERROR, logger="hermes_coach"):
        with client() as test_client, connect(test_client) as socket:
            socket.send_json({"id": 41, "method": "coach.leak"})
            socket.receive_json()
    assert any("coach.leak" in record.getMessage() for record in caplog.records)


def test_a_malformed_request_is_rejected_without_closing_the_socket() -> None:
    with client() as test_client, connect(test_client) as socket:
        socket.send_json({"id": 5, "method": 42})
        assert socket.receive_json()["error"]["code"] == "invalid_request"
        socket.send_json({"id": 6, "method": "coach.stage"})
        assert socket.receive_json()["result"] == {"stage": "goal"}


def test_non_object_params_are_rejected() -> None:
    with client() as test_client, connect(test_client) as socket:
        socket.send_json({"id": 7, "method": "coach.echo", "params": ["nope"]})
        assert socket.receive_json()["error"]["code"] == "invalid_request"


def test_the_request_id_is_echoed_back_on_success_and_failure() -> None:
    with client() as test_client, connect(test_client) as socket:
        socket.send_json({"id": "abc", "method": "coach.stage"})
        assert socket.receive_json()["id"] == "abc"
        socket.send_json({"id": "def", "method": "coach.nope"})
        assert socket.receive_json()["id"] == "def"


def test_registering_the_same_method_twice_is_refused() -> None:
    methods = MethodRegistry()
    methods.register("coach.stage", lambda params: None)
    with pytest.raises(ValueError, match="already registered"):
        methods.register("coach.stage", lambda params: None)


def test_the_app_exposes_no_http_surface_beyond_the_socket() -> None:
    """No docs, no schema dump, no admin routes."""
    app = create_app(LoopbackGuard(token=TOKEN, port=PORT))
    paths = {getattr(route, "path", None) for route in app.routes}
    assert paths == {COACH_WS_PATH}
    # No interactive docs and no schema dump on a single-user local server.
    assert app.openapi_url is None


def test_a_non_loopback_peer_is_refused_by_the_app() -> None:
    """The guard is unit-tested; this proves the app actually consults it."""
    with client(peer="192.168.1.10") as test_client:
        assert "peer" in rejection_reason(test_client)


def test_the_app_registers_no_method_by_default() -> None:
    app = create_app(LoopbackGuard(token=TOKEN, port=PORT))
    assert app.state.methods.names() == ()
