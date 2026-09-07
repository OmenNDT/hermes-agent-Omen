"""The Privacy Center's own surface, reachable at last.

Requirement families: `HC-PRIVACY`, `HC-DATA-*`; sources `SRC-070…075`,
`SRC-084`, `SRC-085`.

`ExportService` and `TrashService` were both written, both thoroughly tested,
and referenced by no RPC at all — so "tải dữ liệu về" and "xoá" were promises
the Privacy Center could not keep. A privacy screen that cannot delete is worse
than one that says it cannot: it tells the Coachee their data is under their
control while the control does nothing.

These tests go through the registry, not the services, because the services were
never what was broken.
"""

from __future__ import annotations

import json
import uuid
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
from hermes_coach.domain.records import GoalRow, InsightRow
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.insight_repository import (
    InsightRepository,
)
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-01-01T00:00:00Z"
TOKEN = "t" * 32
PORT = 8799
SESSION = "session-1"
GOAL = "goal-1"


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        yield db


def seed(database: CoachDatabase) -> None:
    with database.transaction():
        # `register_coach_methods` creates the profile on first run, but seeding
        # happens before the registry is built, so the foreign key needs it now.
        database.connection.execute(
            "INSERT OR IGNORE INTO coachee_profile (id, display_name, created_at) "
            "VALUES (?, 'Coachee', ?)",
            (DEFAULT_PROFILE_ID, NOW),
        )
        database.connection.execute(
            "INSERT INTO coaching_session (id, started_at, coaching_stage) "
            "VALUES (?, ?, 'goal')",
            (SESSION, NOW),
        )
        GoalRepository(database.connection).add(
            GoalRow(
                id=GOAL,
                profile_id=DEFAULT_PROFILE_ID,
                title="Dựng demo tra cứu",
                status="active",
                source_session_id=SESSION,
                confirmed_at=NOW,
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


def build(database: CoachDatabase) -> TestClient:
    registry = MethodRegistry()
    register_coach_methods(registry, database, adapter=None, clock=lambda: NOW)
    app = create_app(
        LoopbackGuard(token=TOKEN, port=PORT),
        registry,
        database=database,
        clock=lambda: NOW,
    )
    # The guard checks peer, Host and token independently, so the test
    # client has to look like a loopback caller on all three.
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


class TestTakingItAway:
    def test_the_export_carries_the_records_the_profile_holds(
        self, database: CoachDatabase
    ) -> None:
        seed(database)
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.export")
        assert reply["result"]["format"] == "json"
        assert json.dumps(reply["result"]["data"], ensure_ascii=False).count(
            "Dựng demo tra cứu"
        )

    def test_markdown_is_offered_for_a_human_to_read(
        self, database: CoachDatabase
    ) -> None:
        """A JSON blob is an export in name only for most people."""
        seed(database)
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.export", {"format": "markdown"})
        assert "Dựng demo tra cứu" in reply["result"]["markdown"]

    def test_an_unknown_format_is_refused_rather_than_guessed(
        self, database: CoachDatabase
    ) -> None:
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.export", {"format": "pdf"})
        assert reply["error"]["code"] == "invalid_request"

    def test_an_empty_profile_still_exports(self, database: CoachDatabase) -> None:
        """A first-run export must answer, not fail."""
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.export")
        assert "data" in reply["result"]


class TestDeletingAndGettingItBack:
    def test_the_trash_starts_empty(self, database: CoachDatabase) -> None:
        client = build(database)
        with client, connect(client) as socket:
            reply = call(socket, "coach.trash")
        assert reply["result"]["items"] == []

    def test_deleting_moves_it_to_the_trash_with_a_date(
        self, database: CoachDatabase
    ) -> None:
        """Deletion the Coachee can undo, and a date after which they cannot."""
        seed(database)
        client = build(database)
        with client, connect(client) as socket:
            call(
                socket,
                "coach.trash.delete",
                {"entity_type": "insight", "entity_id": "insight-1"},
            )
            listed = call(socket, "coach.trash", request_id=2)
        items = listed["result"]["items"]
        assert [item["entity_id"] for item in items] == ["insight-1"]
        assert items[0]["deleted_at"] == NOW
        assert items[0]["purge_after"] > NOW

    def test_a_deleted_insight_stops_being_read_back(
        self, database: CoachDatabase
    ) -> None:
        """The whole point: reads must agree with the deletion."""
        seed(database)
        client = build(database)
        with client, connect(client) as socket:
            before = call(socket, "coach.insights")
            call(
                socket,
                "coach.trash.delete",
                {"entity_type": "insight", "entity_id": "insight-1"},
                request_id=2,
            )
            after = call(socket, "coach.insights", request_id=3)
        assert len(before["result"]["insights"]) == 1
        assert after["result"]["insights"] == []

    def test_restoring_brings_it_back_and_empties_the_trash(
        self, database: CoachDatabase
    ) -> None:
        seed(database)
        client = build(database)
        with client, connect(client) as socket:
            call(
                socket,
                "coach.trash.delete",
                {"entity_type": "insight", "entity_id": "insight-1"},
            )
            call(
                socket,
                "coach.trash.restore",
                {"entity_type": "insight", "entity_id": "insight-1"},
                request_id=2,
            )
            listed = call(socket, "coach.trash", request_id=3)
            insights = call(socket, "coach.insights", request_id=4)
        assert listed["result"]["items"] == []
        assert len(insights["result"]["insights"]) == 1

    def test_restoring_something_that_was_never_deleted_is_refused(
        self, database: CoachDatabase
    ) -> None:
        seed(database)
        client = build(database)
        with client, connect(client) as socket:
            reply = call(
                socket,
                "coach.trash.restore",
                {"entity_type": "insight", "entity_id": "insight-1"},
            )
        assert reply["error"]["code"] == "restore_blocked"

    def test_an_unknown_entity_type_is_refused(self, database: CoachDatabase) -> None:
        client = build(database)
        with client, connect(client) as socket:
            reply = call(
                socket,
                "coach.trash.delete",
                {"entity_type": "not_a_thing", "entity_id": "x"},
            )
        assert reply["error"]["code"] == "invalid_request"


class TestErasingForGood:
    def test_a_purge_with_no_trusted_control_is_refused(
        self, database: CoachDatabase
    ) -> None:
        """Irreversible, so a stray call must not be able to do it.

        This is the check that makes purge a different command from delete
        rather than a flag on it.
        """
        seed(database)
        client = build(database)
        with client, connect(client) as socket:
            call(
                socket,
                "coach.trash.delete",
                {"entity_type": "insight", "entity_id": "insight-1"},
            )
            reply = call(
                socket,
                "coach.trash.purge",
                {"entity_type": "insight", "entity_id": "insight-1"},
                request_id=2,
            )
            listed = call(socket, "coach.trash", request_id=3)
        assert reply["error"]["code"] == "invalid_request"
        # Still recoverable: a refused purge must not have half-erased it.
        assert [item["entity_id"] for item in listed["result"]["items"]] == [
            "insight-1"
        ]

    def test_a_confirmed_purge_erases_the_row(self, database: CoachDatabase) -> None:
        seed(database)
        client = build(database)
        with client, connect(client) as socket:
            call(
                socket,
                "coach.trash.delete",
                {"entity_type": "insight", "entity_id": "insight-1"},
            )
            reply = call(
                socket,
                "coach.trash.purge",
                {
                    "entity_type": "insight",
                    "entity_id": "insight-1",
                    "control_id": "btn-purge-confirm",
                },
                request_id=2,
            )
        assert reply["result"]["purged"] is True
        remaining = database.connection.execute(
            "SELECT COUNT(*) AS n FROM insight WHERE id = 'insight-1'"
        ).fetchone()["n"]
        assert remaining == 0

    def test_purging_something_not_in_the_trash_is_refused(
        self, database: CoachDatabase
    ) -> None:
        """Purge is the end of a deletion, never a shortcut past it."""
        seed(database)
        client = build(database)
        with client, connect(client) as socket:
            reply = call(
                socket,
                "coach.trash.purge",
                {
                    "entity_type": "insight",
                    "entity_id": "insight-1",
                    "control_id": "btn-purge-confirm",
                },
            )
        assert reply["error"]["code"] == "purge_blocked"
        remaining = database.connection.execute(
            "SELECT COUNT(*) AS n FROM insight WHERE id = 'insight-1'"
        ).fetchone()["n"]
        assert remaining == 1
