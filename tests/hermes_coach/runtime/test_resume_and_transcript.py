"""Getting back to a session, and reading one back.

Requirement families: `HC-PROCESS`, `HC-PRIVACY`; sources `SRC-061`,
`SRC-076…086`.

Both found in the second end-to-end run, and they belong together.

The session id lived only in the browser's memory, so a reload — or a trip to
Goals and back — stranded whatever session the Coachee was in. The rows were
all still there and nothing could reach them. It also explained something we
had been reading wrong: thirteen of sixteen sessions in a real profile said
"chưa khép lại", and we had taken that for people abandoning sessions.

The second is worse, because it makes a promise false. Transcripts stopped
expiring earlier the same day, and the Privacy Center now says so — but no
screen could open one. Keeping someone's words forever somewhere they can never
read them carries the whole privacy cost of storage and returns none of its
value.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from hermes_coach.api.app import (
    COACH_WS_PATH,
    LoopbackGuard,
    MethodRegistry,
    create_app,
)
from hermes_coach.api.methods import DEFAULT_PROFILE_ID, register_coach_methods
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-03-01T00:00:00Z"
TOKEN = "t" * 32
PORT = 8797


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        yield db


def session(
    database: CoachDatabase,
    session_id: str,
    *,
    started_at: str = NOW,
    ended_at: str | None = None,
    stage: str = "goal",
    intention: str | None = None,
) -> None:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coaching_session "
            "(id, started_at, ended_at, intention, coaching_stage) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, started_at, ended_at, intention, stage),
        )


def message(
    database: CoachDatabase,
    session_id: str,
    message_id: str,
    *,
    role: str = "coachee",
    content: str = "Tôi muốn đổi vai trò",
    sequence_no: int = 0,
    expires_at: str | None = None,
) -> None:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO session_message "
            "(id, session_id, sequence_no, role, content, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message_id, session_id, sequence_no, role, content, NOW, expires_at),
        )


def build(database: CoachDatabase) -> TestClient:
    registry = MethodRegistry()
    register_coach_methods(registry, database, adapter=None, clock=lambda: NOW)
    app = create_app(
        LoopbackGuard(token=TOKEN, port=PORT),
        registry,
        database=database,
        clock=lambda: NOW,
    )
    return TestClient(
        app, base_url=f"http://127.0.0.1:{PORT}", client=("127.0.0.1", 54321)
    )


def connect(client: TestClient):
    return client.websocket_connect(
        f"{COACH_WS_PATH}?token={TOKEN}", headers={"host": f"127.0.0.1:{PORT}"}
    )


def call(socket, method: str, params: dict | None = None, request_id: int = 1) -> dict:
    socket.send_json({"id": request_id, "method": method, "params": params or {}})
    return socket.receive_json()


class TestGettingBackToASession:
    def test_a_fresh_profile_has_nothing_to_return_to(
        self, database: CoachDatabase
    ) -> None:
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.open")
        assert reply["result"]["session"] is None

    def test_an_unfinished_session_is_offered_back(
        self, database: CoachDatabase
    ) -> None:
        """The failure this exists for: a reload used to lose it for good."""
        session(database, "s1", stage="reality", intention="tìm hướng đi")
        message(database, "s1", "m1")
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.open")
        found = reply["result"]["session"]
        assert found["session_id"] == "s1"
        assert found["stage"] == "reality"
        assert found["intention"] == "tìm hướng đi"

    def test_a_finished_session_is_not_offered_back(
        self, database: CoachDatabase
    ) -> None:
        """Review closed it. Reopening would undo the Coachee's own ending."""
        session(database, "s1", ended_at="2026-03-01T01:00:00Z", stage="review")
        message(database, "s1", "m1")
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.open")
        assert reply["result"]["session"] is None

    def test_only_the_most_recent_unfinished_one(
        self, database: CoachDatabase
    ) -> None:
        """Older ones stay as they are: real history, honestly labelled."""
        session(database, "old", started_at="2026-01-01T00:00:00Z")
        message(database, "old", "m-old")
        session(database, "new", started_at="2026-02-01T00:00:00Z")
        message(database, "new", "m-new")
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.open")
        assert reply["result"]["session"]["session_id"] == "new"

    def test_a_session_with_nothing_said_is_not_offered_back(
        self, database: CoachDatabase
    ) -> None:
        """Opening the screen and walking away leaves a row behind.

        Inviting someone back into an empty conversation is an interruption
        with nothing on the other side of it.
        """
        session(database, "s1")
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.open")
        assert reply["result"]["session"] is None

    def test_an_empty_session_does_not_hide_a_real_one_behind_it(
        self, database: CoachDatabase
    ) -> None:
        """The empty row is newer, so a naive "most recent" would stop there."""
        session(database, "real", started_at="2026-01-01T00:00:00Z")
        message(database, "real", "m1")
        session(database, "empty", started_at="2026-02-01T00:00:00Z")
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.open")
        assert reply["result"]["session"]["session_id"] == "real"

    def test_a_deleted_session_is_never_offered_back(
        self, database: CoachDatabase
    ) -> None:
        import uuid

        session(database, "s1")
        message(database, "s1", "m1")
        with database.transaction():
            database.connection.execute(
                "INSERT OR IGNORE INTO coachee_profile (id, display_name, created_at) "
                "VALUES (?, 'Coachee', ?)",
                (DEFAULT_PROFILE_ID, NOW),
            )
            database.connection.execute(
                "INSERT INTO trash_entry (id, profile_id, entity_type, entity_id, "
                "deleted_at, purge_after, deletion_source) "
                "VALUES (?, ?, 'coaching_session', 's1', ?, ?, 'item')",
                (str(uuid.uuid4()), DEFAULT_PROFILE_ID, NOW, "2026-04-01T00:00:00Z"),
            )
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.open")
        assert reply["result"]["session"] is None


class TestReadingOneBack:
    def test_the_words_come_back_in_the_order_they_were_said(
        self, database: CoachDatabase
    ) -> None:
        session(database, "s1")
        message(database, "s1", "m1", role="coachee", content="Tôi thấy bế tắc")
        message(database, "s1", "m2", role="coach", content="Điều gì khiến vậy?", sequence_no=1)
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.transcript", {"session_id": "s1"})
        turns = reply["result"]["turns"]
        assert [t["content"] for t in turns] == ["Tôi thấy bế tắc", "Điều gì khiến vậy?"]
        assert [t["voice"] for t in turns] == ["coachee", "coach"]

    def test_the_safety_voice_stays_distinguishable_months_later(
        self, database: CoachDatabase
    ) -> None:
        """A reader must be able to tell it from the Coach, exactly as during
        the session. Flattening the roles here would let a safety message read
        as coaching advice."""
        session(database, "s1")
        message(
            database, "s1", "m1", role="safety_system", content="Mình dừng ở đây."
        )
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.transcript", {"session_id": "s1"})
        assert reply["result"]["turns"][0]["voice"] == "safety_system"

    def test_a_session_with_nothing_left_answers_empty_rather_than_failing(
        self, database: CoachDatabase
    ) -> None:
        session(database, "s1")
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.transcript", {"session_id": "s1"})
        assert reply["result"]["turns"] == []

    def test_an_expired_line_stays_gone(self, database: CoachDatabase) -> None:
        """Reading a transcript must not route around retention."""
        session(database, "s1")
        message(database, "s1", "m1", expires_at="2026-01-01T00:00:00Z")
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.transcript", {"session_id": "s1"})
        assert reply["result"]["turns"] == []

    def test_another_sessions_words_never_leak_in(
        self, database: CoachDatabase
    ) -> None:
        session(database, "s1")
        session(database, "s2")
        message(database, "s1", "m1", content="của phiên một")
        message(database, "s2", "m2", content="của phiên hai")
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.transcript", {"session_id": "s1"})
        assert [t["content"] for t in reply["result"]["turns"]] == ["của phiên một"]

    def test_a_transcript_needs_a_session(self, database: CoachDatabase) -> None:
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.session.transcript")
        assert reply["error"]["code"] == "invalid_request"
