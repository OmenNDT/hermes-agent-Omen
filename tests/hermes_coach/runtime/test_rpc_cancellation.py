"""Cancellation and disconnect cleanup.

Requirement families: `HC-PRODUCT`; sources `SRC-104…106`.

A coaching turn is a slow model call. Two things must be true while one is in
flight: the socket keeps listening, so a cancel can arrive at all, and closing
the window actually stops the work rather than leaving it running against a
socket nobody is reading.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hermes_coach.api.app import (
    COACH_WS_PATH,
    CancellationRegistry,
    MethodRegistry,
    TurnCancelled,
    create_app,
)
from hermes_coach.api.security import LoopbackGuard


TOKEN = "t" * 32
PORT = 8731
SESSION = "session-1"


def build(methods: MethodRegistry) -> tuple[TestClient, FastAPI, CancellationRegistry]:
    cancellations = CancellationRegistry()
    app = create_app(
        LoopbackGuard(token=TOKEN, port=PORT), methods, cancellations=cancellations
    )
    client = TestClient(
        app, base_url=f"http://127.0.0.1:{PORT}", client=("127.0.0.1", 54321)
    )
    return client, app, cancellations


def connect(client: TestClient):
    return client.websocket_connect(
        f"{COACH_WS_PATH}?token={TOKEN}", headers={"host": f"127.0.0.1:{PORT}"}
    )


def slow_turn_methods() -> MethodRegistry:
    """A turn that blocks until released, so nothing here waits on a clock."""
    methods = MethodRegistry()
    release = asyncio.Event()

    async def slow(params: dict) -> dict:
        registry: CancellationRegistry = params["_cancellations"]
        while not release.is_set():
            registry.raise_if_cancelled(params["session_id"], params["turn_id"])
            await asyncio.sleep(0)
        return {"finished": True}

    def finish(params: dict) -> dict:
        release.set()
        return {"released": True}

    methods.register("coach.slow", slow, wants_cancellation=True)
    methods.register("coach.finish", finish)
    methods.register("coach.ping", lambda params: {"pong": True})
    return methods


def test_a_slow_turn_does_not_block_the_next_request() -> None:
    """Without this, a cancel could never reach the server.

    The slow turn waits on an event rather than a timer, so the ping answering
    first is a fact about dispatch order, not about who won a race.
    """
    client, _app, _ = build(slow_turn_methods())
    with client, connect(client) as socket:
        socket.send_json(
            {
                "id": 1,
                "method": "coach.slow",
                "params": {"session_id": SESSION, "turn_id": "turn-1"},
            }
        )
        socket.send_json({"id": 2, "method": "coach.ping"})
        # The slow turn cannot have finished: nothing has released it yet.
        assert socket.receive_json() == {"id": 2, "result": {"pong": True}}

        socket.send_json({"id": 3, "method": "coach.finish"})
        replies = {socket.receive_json()["id"] for _ in range(2)}
        assert replies == {1, 3}


def test_a_cancelled_turn_reports_cancellation() -> None:
    client, _app, _ = build(slow_turn_methods())
    with client, connect(client) as socket:
        socket.send_json(
            {
                "id": 1,
                "method": "coach.slow",
                "params": {"session_id": SESSION, "turn_id": "turn-1"},
            }
        )
        socket.send_json(
            {
                "id": 2,
                "method": "coach.cancel",
                "params": {"session_id": SESSION, "turn_id": "turn-1"},
            }
        )
        replies = {}
        for _ in range(2):
            message = socket.receive_json()
            replies[message["id"]] = message
        assert replies[2]["result"] == {"cancelled": True}
        assert replies[1]["error"]["code"] == "cancelled"


def test_cancellation_targets_one_turn_not_the_whole_session() -> None:
    client, _app, cancellations = build(slow_turn_methods())
    cancellations.cancel(SESSION, "turn-1")
    assert cancellations.is_cancelled(SESSION, "turn-1")
    assert not cancellations.is_cancelled(SESSION, "turn-2")
    assert not cancellations.is_cancelled("session-2", "turn-1")


def test_cancelling_an_unknown_turn_is_not_an_error() -> None:
    """The UI may cancel a turn that already finished; that is a no-op."""
    client, _app, _ = build(slow_turn_methods())
    with client, connect(client) as socket:
        socket.send_json(
            {
                "id": 1,
                "method": "coach.cancel",
                "params": {"session_id": SESSION, "turn_id": "turn-does-not-exist"},
            }
        )
        assert socket.receive_json()["result"] == {"cancelled": True}


def test_cancel_requires_a_session_and_turn() -> None:
    client, _app, _ = build(slow_turn_methods())
    with client, connect(client) as socket:
        socket.send_json({"id": 1, "method": "coach.cancel", "params": {}})
        assert socket.receive_json()["error"]["code"] == "invalid_request"


def test_raise_if_cancelled_is_silent_until_it_is_cancelled() -> None:
    registry = CancellationRegistry()
    registry.raise_if_cancelled(SESSION, "turn-1")
    registry.cancel(SESSION, "turn-1")
    with pytest.raises(TurnCancelled):
        registry.raise_if_cancelled(SESSION, "turn-1")


def test_finishing_a_turn_clears_its_cancellation_state() -> None:
    """Otherwise a cancelled turn id would poison its own retry."""
    registry = CancellationRegistry()
    registry.cancel(SESSION, "turn-1")
    registry.forget(SESSION, "turn-1")
    registry.raise_if_cancelled(SESSION, "turn-1")


def test_disconnecting_stops_work_that_is_still_running() -> None:
    finished: list[str] = []
    methods = MethodRegistry()

    async def slow(params: dict) -> dict:
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            finished.append("cancelled")
            raise
        finished.append("completed")
        return {}

    methods.register("coach.slow", slow)
    client, _app, _ = build(methods)

    with client:
        with connect(client) as socket:
            socket.send_json({"id": 1, "method": "coach.slow"})
        # Leaving the block closes the socket while the turn is in flight.
    assert finished == ["cancelled"]


def test_disconnect_cleanup_leaves_no_task_behind() -> None:
    methods = MethodRegistry()

    async def slow(params: dict) -> dict:
        await asyncio.sleep(5)
        return {}

    methods.register("coach.slow", slow)
    app_client, app, _ = build(methods)

    with app_client:
        with connect(app_client) as socket:
            socket.send_json({"id": 1, "method": "coach.slow"})
        assert app.state.in_flight == {}


def test_a_second_connection_is_unaffected_by_the_first_disconnecting() -> None:
    client, _app, _ = build(slow_turn_methods())
    with client:
        with connect(client) as first:
            first.send_json({"id": 1, "method": "coach.ping"})
            assert first.receive_json()["result"] == {"pong": True}
        with connect(client) as second:
            second.send_json({"id": 2, "method": "coach.ping"})
            assert second.receive_json()["result"] == {"pong": True}
