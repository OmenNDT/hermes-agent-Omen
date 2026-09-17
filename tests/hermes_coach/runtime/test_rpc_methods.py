"""The registered Coach RPC surface.

Requirement families: `HC-PRODUCT`, `HC-UX`, `HC-PRIVACY`; sources `SRC-062…069`,
`SRC-104…106`.

Every method here is reachable from the browser, so the two things that matter
are what it returns and what it refuses. Reads go through the same repository
scopes as everything else, so Trash and expired data cannot surface; the turn
degrades to a typed error rather than a stack trace when no provider is
configured.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from hermes_coach.api.app import COACH_WS_PATH, MethodRegistry, create_app
from hermes_coach.api.methods import DEFAULT_PROFILE_ID, register_coach_methods
from hermes_coach.api.security import LoopbackGuard
from hermes_coach.application.consent_service import ConsentService, UiConsentAction
from hermes_coach.application.trash_service import TrashService
from hermes_coach.contracts.runtime_contract import (
    CoachingStage,
    CoachOutput,
    UsageAccounting,
    ValidatedRuntimeResult,
)
from hermes_coach.domain.records import GoalRow, InsightRow
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.insight_repository import (
    InsightRepository,
)
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


TOKEN = "t" * 32
PORT = 8731
NOW = "2026-01-01T00:00:00Z"
QUESTION = "Điều gì khiến việc này quan trọng với bạn?"

# The one place the surface is written out. Adding a method has to be a
# deliberate edit here, which is the point of asserting an exact set.
EXPECTED_SURFACE = {
    "coach.today",
    "coach.insights",
    "coach.session.start",
    "coach.session.state",
    "coach.session.open",
    "coach.session.transcript",
    "coach.turn",
    "coach.candidate.intent",
    "coach.candidate.confirm",
    "coach.consent.record",
    "coach.consent.state",
    "coach.check_ins",
    "coach.journey",
    "coach.check_in.answer",
    "coach.export",
    "coach.session.export",
    "coach.trash",
    "coach.trash.delete",
    "coach.trash.restore",
    "coach.trash.purge",
}


class StubAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request, *, sink=None) -> ValidatedRuntimeResult:
        self.calls += 1
        return ValidatedRuntimeResult(
            output=CoachOutput(question=QUESTION, coaching_stage=CoachingStage.GOAL),
            attempts=1,
            usage=UsageAccounting(input_tokens=5, output_tokens=3),
        )


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        yield db


def build(database: CoachDatabase, adapter=None) -> TestClient:
    registry = MethodRegistry()
    register_coach_methods(
        registry, database, adapter=adapter, clock=lambda: NOW
    )
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


def grant_egress(database: CoachDatabase, goal_id: str) -> None:
    """Both layers, because a turn needs the profile one to run at all.

    The transcript is egressed on every turn whatever goal is named, so the
    profile-wide grant is the one `coach.turn` stands on. The goal grant is
    what additionally lets that goal's title and insights travel.
    """
    consent = ConsentService(database, profile_id=DEFAULT_PROFILE_ID)
    grants = (("consent-profile", {}), (f"consent-{goal_id}", {"goal_id": goal_id}))
    for event_id, scope in grants:
        consent.record(
            event_id=event_id,
            consent_type="model_egress",
            scope=scope,
            ui_action=UiConsentAction.CONFIRM,
            control_id="btn-consent-confirm",
            now=NOW,
        )


def add_goal(database: CoachDatabase, goal_id: str = "goal-1", **overrides) -> None:
    values = {
        "id": goal_id,
        "profile_id": DEFAULT_PROFILE_ID,
        "title": "Chuyển sang vai trò kiến trúc sư",
        "status": "active",
        "confirmed_at": NOW,
        "created_at": NOW,
    }
    values.update(overrides)
    with database.transaction():
        GoalRepository(database.connection).add(GoalRow.model_validate(values))


def test_the_registry_exposes_a_named_surface(database: CoachDatabase) -> None:
    registry = MethodRegistry()
    register_coach_methods(registry, database, adapter=None, clock=lambda: NOW)
    assert set(registry.names()) == EXPECTED_SURFACE


def test_no_method_name_suggests_a_bulk_operation(database: CoachDatabase) -> None:
    registry = MethodRegistry()
    register_coach_methods(registry, database, adapter=None, clock=lambda: NOW)
    for name in registry.names():
        assert "all" not in name.lower()
        assert "batch" not in name.lower()


def test_starting_the_backend_creates_the_default_profile(
    database: CoachDatabase,
) -> None:
    build(database)
    row = database.connection.execute(
        "SELECT id FROM coachee_profile WHERE id = ?", (DEFAULT_PROFILE_ID,)
    ).fetchone()
    assert row is not None


def test_today_reports_an_empty_profile_without_failing(
    database: CoachDatabase,
) -> None:
    client = build(database)
    with client, connect(client) as socket:
        result = call(socket, "coach.today")["result"]
    assert result["goals"] == []
    assert result["pending_check_ins"] == []
    assert result["disclosure"]["encrypted_at_rest"] is False


def test_today_lists_the_active_goal(database: CoachDatabase) -> None:
    client = build(database)
    add_goal(database)
    with client, connect(client) as socket:
        result = call(socket, "coach.today")["result"]
    assert [goal["title"] for goal in result["goals"]] == [
        "Chuyển sang vai trò kiến trúc sư"
    ]


def test_today_excludes_a_trashed_goal(database: CoachDatabase) -> None:
    """The read goes through the shared active scope, not a bespoke query."""
    client = build(database)
    add_goal(database)
    TrashService(database, profile_id=DEFAULT_PROFILE_ID).soft_delete(
        "goal", "goal-1", now=NOW
    )
    with client, connect(client) as socket:
        assert call(socket, "coach.today")["result"]["goals"] == []


def test_today_excludes_an_unconfirmed_goal(database: CoachDatabase) -> None:
    client = build(database)
    add_goal(database, "goal-draft", status="draft", confirmed_at=None)
    with client, connect(client) as socket:
        assert call(socket, "coach.today")["result"]["goals"] == []


def test_today_shows_the_most_recent_insight(database: CoachDatabase) -> None:
    client = build(database)
    with database.transaction():
        InsightRepository(database.connection).add(
            InsightRow(id="insight-1", content="Tôi né xung đột", confirmed_at=NOW)
        )
    with client, connect(client) as socket:
        result = call(socket, "coach.today")["result"]
    assert result["recent_insight"]["content"] == "Tôi né xung đột"


def test_starting_a_session_returns_its_id_and_stage(
    database: CoachDatabase,
) -> None:
    client = build(database)
    with client, connect(client) as socket:
        result = call(
            socket,
            "coach.session.start",
            {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
        )["result"]
    assert result["session_id"] == "session-1"
    assert result["stage"] == "pre_coaching"


def test_a_new_session_starts_at_pre_coaching_not_goal(
    database: CoachDatabase,
) -> None:
    """Skipping Pre-Coaching is the one shortcut the framework forbids."""
    client = build(database)
    with client, connect(client) as socket:
        call(
            socket,
            "coach.session.start",
            {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
        )
    row = database.connection.execute(
        "SELECT coaching_stage FROM coaching_session WHERE id = 'session-1'"
    ).fetchone()
    assert row["coaching_stage"] == "pre_coaching"


def test_restarting_the_same_session_id_replays_instead_of_duplicating(
    database: CoachDatabase,
) -> None:
    client = build(database)
    with client, connect(client) as socket:
        first = call(
            socket,
            "coach.session.start",
            {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
        )
        second = call(
            socket,
            "coach.session.start",
            {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
            request_id=2,
        )
    assert first["result"] == second["result"]
    total = database.connection.execute(
        "SELECT COUNT(*) AS n FROM coaching_session"
    ).fetchone()["n"]
    assert total == 1


def test_session_state_reports_what_the_server_confirmed(
    database: CoachDatabase,
) -> None:
    client = build(database)
    with client, connect(client) as socket:
        call(
            socket,
            "coach.session.start",
            {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
        )
        state = call(
            socket, "coach.session.state", {"session_id": "session-1"}, request_id=2
        )["result"]
    assert state["stage"] == "pre_coaching"
    assert state["confirmed_steps"] == []
    assert state["revision"] == 1


def test_session_state_of_an_unknown_session_is_empty_not_an_error(
    database: CoachDatabase,
) -> None:
    client = build(database)
    with client, connect(client) as socket:
        state = call(socket, "coach.session.state", {"session_id": "nope"})["result"]
    assert state["stage"] is None
    assert state["turns"] == []


def test_a_turn_without_a_configured_provider_degrades_cleanly(
    database: CoachDatabase,
) -> None:
    """No provider is a normal state on first run, not a crash."""
    client = build(database, adapter=None)
    add_goal(database)
    grant_egress(database, "goal-1")
    with client, connect(client) as socket:
        call(
            socket,
            "coach.session.start",
            {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
        )
        reply = call(
            socket,
            "coach.turn",
            {
                "session_id": "session-1",
                "revision": 1,
                "idempotency_key": "k2",
                "turn_id": "turn-1",
                "goal_id": "goal-1",
                "user_message": "Tôi muốn đổi vai trò",
            },
            request_id=2,
        )
    assert reply["error"]["code"] == "provider_not_configured"


def test_a_turn_with_a_provider_returns_the_question(
    database: CoachDatabase,
) -> None:
    adapter = StubAdapter()
    client = build(database, adapter=adapter)
    add_goal(database)
    grant_egress(database, "goal-1")
    with client, connect(client) as socket:
        call(
            socket,
            "coach.session.start",
            {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
        )
        reply = call(
            socket,
            "coach.turn",
            {
                "session_id": "session-1",
                "revision": 1,
                "idempotency_key": "k2",
                "turn_id": "turn-1",
                "goal_id": "goal-1",
                "user_message": "Tôi muốn đổi vai trò",
            },
            request_id=2,
        )
    assert reply["result"]["question"] == QUESTION
    assert adapter.calls == 1


def test_a_turn_without_consent_answers_locally(database: CoachDatabase) -> None:
    adapter = StubAdapter()
    client = build(database, adapter=adapter)
    add_goal(database)
    with client, connect(client) as socket:
        call(
            socket,
            "coach.session.start",
            {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
        )
        reply = call(
            socket,
            "coach.turn",
            {
                "session_id": "session-1",
                "revision": 1,
                "idempotency_key": "k2",
                "turn_id": "turn-1",
                "goal_id": "goal-1",
                "user_message": "Tôi muốn đổi vai trò",
            },
            request_id=2,
        )
    assert reply["error"]["code"] == "consent_withdrawn"
    assert adapter.calls == 0


def test_a_turn_for_an_unknown_session_is_refused(database: CoachDatabase) -> None:
    client = build(database, adapter=StubAdapter())
    with client, connect(client) as socket:
        reply = call(
            socket,
            "coach.turn",
            {
                "session_id": "nope",
                "revision": 0,
                "idempotency_key": "k1",
                "turn_id": "turn-1",
                "goal_id": None,
                "user_message": "xin chào",
            },
        )
    assert reply["error"]["code"] == "unknown_session"


def test_reads_do_not_move_the_revision(database: CoachDatabase) -> None:
    from hermes_coach.infrastructure.repositories.rpc_repository import (
        SessionRevisionRepository,
    )

    client = build(database)
    with client, connect(client) as socket:
        call(
            socket,
            "coach.session.start",
            {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
        )
        call(socket, "coach.today", request_id=2)
        call(socket, "coach.session.state", {"session_id": "session-1"}, request_id=3)
    assert SessionRevisionRepository(database.connection).current("session-1") == 1


def test_no_reply_ever_carries_a_credential_shaped_value(
    database: CoachDatabase,
) -> None:
    client = build(database, adapter=StubAdapter())
    add_goal(database)
    grant_egress(database, "goal-1")
    with client, connect(client) as socket:
        replies = [
            call(socket, "coach.today"),
            call(
                socket,
                "coach.session.start",
                {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
                request_id=2,
            ),
            call(
                socket, "coach.session.state", {"session_id": "session-1"}, request_id=3
            ),
        ]
    rendered = str(replies).lower()
    for marker in ("api_key", "sk-", "authorization", "bearer "):
        assert marker not in rendered


def test_session_state_lists_pending_candidates(database: CoachDatabase) -> None:
    from hermes_coach.domain.records import CandidateRecordRow
    from hermes_coach.infrastructure.repositories.candidate_repository import (
        CandidateRepository,
    )

    client = build(database)
    with client, connect(client) as socket:
        call(
            socket,
            "coach.session.start",
            {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
        )
        with database.transaction():
            CandidateRepository(database.connection).add(
                CandidateRecordRow(
                    id="cand-1",
                    session_id="session-1",
                    record_type="goal",
                    payload_json='{"title": "Chuyển vai trò"}',
                    status="pending",
                    created_at=NOW,
                )
            )
        state = call(
            socket, "coach.session.state", {"session_id": "session-1"}, request_id=2
        )["result"]

    assert state["candidates"] == [
        {"id": "cand-1", "kind": "goal", "value": "Chuyển vai trò"}
    ]


def test_session_state_omits_a_resolved_candidate(database: CoachDatabase) -> None:
    """Offering it again would invite a second confirmation of one record."""
    from hermes_coach.domain.records import CandidateRecordRow
    from hermes_coach.infrastructure.repositories.candidate_repository import (
        CandidateRepository,
    )

    client = build(database)
    with client, connect(client) as socket:
        call(
            socket,
            "coach.session.start",
            {"session_id": "session-1", "revision": 0, "idempotency_key": "k1"},
        )
        with database.transaction():
            CandidateRepository(database.connection).add(
                CandidateRecordRow(
                    id="cand-done",
                    session_id="session-1",
                    record_type="goal",
                    payload_json='{"title": "Đã xong"}',
                    status="confirmed",
                    created_at=NOW,
                    resolved_at=NOW,
                )
            )
        state = call(
            socket, "coach.session.state", {"session_id": "session-1"}, request_id=2
        )["result"]

    assert state["candidates"] == []


def test_insights_lists_only_what_the_coachee_confirmed(
    database: CoachDatabase,
) -> None:
    """An insight nobody accepted is not something they learned."""
    from hermes_coach.domain.records import InsightRow
    from hermes_coach.infrastructure.repositories.insight_repository import (
        InsightRepository,
    )

    with database.transaction():
        repository = InsightRepository(database.connection)
        repository.add(
            InsightRow(id="i-1", content="Tôi sợ chọn sai", confirmed_at=NOW)
        )
        repository.add(InsightRow(id="i-2", content="Chưa ai xác nhận"))

    registry = MethodRegistry()
    register_coach_methods(registry, database, adapter=None, clock=lambda: NOW)
    answer = registry.get("coach.insights").method({})

    assert [item["content"] for item in answer["insights"]] == ["Tôi sợ chọn sai"]


def test_session_state_says_whether_the_session_closed(
    database: CoachDatabase,
) -> None:
    session_id = "session-ended-1"
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coaching_session (id, started_at, coaching_stage) "
            "VALUES (?, ?, 'goal')",
            (session_id, NOW),
        )

    registry = MethodRegistry()
    register_coach_methods(registry, database, adapter=None, clock=lambda: NOW)
    state = registry.get("coach.session.state")

    assert state.method({"session_id": session_id})["ended"] is False

    with database.transaction():
        database.connection.execute(
            "UPDATE coaching_session SET ended_at = ? WHERE id = ?", (NOW, session_id)
        )

    assert state.method({"session_id": session_id})["ended"] is True
