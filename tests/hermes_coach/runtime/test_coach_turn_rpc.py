"""`coach.turn` over the socket: persisted before emitted.

Requirement families: `HC-PRODUCT`, `HC-PRIVACY`, `HC-RECORDS`; sources
`SRC-079`, `SRC-091`, `SRC-104…106`.

The turn service and the RPC envelope are each tested on their own. What this
file proves is the join: the transcript, the candidates, the revision bump and
the idempotency record all land in one transaction, and the reply goes out only
after that transaction commits.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from hermes_coach.api.app import COACH_WS_PATH, MethodRegistry, RpcError, create_app
from hermes_coach.api.security import LoopbackGuard
from hermes_coach.application.coaching_turn_service import CoachingTurnService
from hermes_coach.application.consent_service import (
    ConsentService,
    ConsentWithdrawn,
    UiConsentAction,
)
from hermes_coach.contracts.runtime_contract import (
    CandidateRecord,
    CoachingStage,
    CoachOutput,
    RecordKind,
    UsageAccounting,
    ValidatedRuntimeResult,
)
from hermes_coach.domain.records import GoalRow
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
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
PROFILE = "profile-1"
SESSION = "session-1"
GOAL = "goal-1"
QUESTION = "Điều gì khiến việc này quan trọng với bạn?"


class StubAdapter:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.calls = 0

    def generate(self, request, *, sink=None) -> ValidatedRuntimeResult:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return ValidatedRuntimeResult(
            output=CoachOutput(
                question=QUESTION,
                coaching_stage=CoachingStage.GOAL,
                candidate_goals=(
                    CandidateRecord(
                        candidate_id="c-1",
                        kind=RecordKind.GOAL,
                        value="Trở thành kiến trúc sư",
                        source_turn_id=request.turn_id,
                    ),
                ),
            ),
            attempts=1,
            usage=UsageAccounting(input_tokens=10, output_tokens=5),
        )


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
                    title="Chuyển vai trò",
                    status="active",
                    confirmed_at=NOW,
                    created_at=NOW,
                )
            )
        # The profile scope is what a turn requires: the transcript always
        # leaves the machine. The goal scope is the extra grant that lets this
        # goal's title and insights travel with it.
        for index, scope in enumerate(({}, {"goal_id": GOAL})):
            ConsentService(db, profile_id=PROFILE).record(
                event_id=f"consent-{index}",
                consent_type="model_egress",
                scope=scope,
                ui_action=UiConsentAction.CONFIRM,
                control_id="btn-consent-confirm",
                now=NOW,
            )
        yield db


def build(database: CoachDatabase, adapter: StubAdapter) -> TestClient:
    service = CoachingTurnService(database, profile_id=PROFILE, adapter=adapter)

    def turn(params: dict):
        try:
            return service.run(
                session_id=params["session_id"],
                turn_id=params["turn_id"],
                goal_id=params.get("goal_id"),
                user_message=params["user_message"],
                now=NOW,
            )
        except ConsentWithdrawn:
            # A local, degraded answer: the UI can still show stored data.
            raise RpcError("consent_withdrawn", "model egress has no standing consent")

    methods = MethodRegistry()
    methods.register("coach.turn", turn, mutating=True)
    app = create_app(
        LoopbackGuard(token=TOKEN, port=PORT),
        methods,
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


def send_turn(socket, *, request_id=1, revision=0, key="key-1", turn_id="turn-1"):
    socket.send_json(
        {
            "id": request_id,
            "method": "coach.turn",
            "params": {
                "session_id": SESSION,
                "revision": revision,
                "idempotency_key": key,
                "turn_id": turn_id,
                "goal_id": GOAL,
                "user_message": "Tôi muốn đổi vai trò",
            },
        }
    )
    return socket.receive_json()


def count(database: CoachDatabase, table: str) -> int:
    return database.connection.execute(
        f"SELECT COUNT(*) AS total FROM {table}"
    ).fetchone()["total"]


def test_a_turn_answers_with_the_question(database: CoachDatabase) -> None:
    client = build(database, StubAdapter())
    with client, connect(client) as socket:
        reply = send_turn(socket)
    assert reply["result"]["question"] == QUESTION
    assert reply["result"]["candidates"][0]["value"] == "Trở thành kiến trúc sư"


def test_everything_the_reply_mentions_is_already_in_the_database(
    database: CoachDatabase,
) -> None:
    """Persist before emit: a client that saw it can rely on it being stored."""
    client = build(database, StubAdapter())
    with client, connect(client) as socket:
        send_turn(socket)
    assert count(database, "session_message") == 2
    assert count(database, "candidate_record") == 1
    assert SessionRevisionRepository(database.connection).current(SESSION) == 1


def test_a_rejected_turn_emits_an_error_and_stores_nothing(
    database: CoachDatabase,
) -> None:
    client = build(database, StubAdapter(error=RuntimeError("provider down")))
    with client, connect(client) as socket:
        reply = send_turn(socket)
    assert reply["error"]["code"] == "internal_error"
    assert count(database, "session_message") == 0
    assert count(database, "candidate_record") == 0
    assert SessionRevisionRepository(database.connection).current(SESSION) == 0


def test_withdrawn_consent_answers_locally_without_calling_the_model(
    database: CoachDatabase,
) -> None:
    # The profile scope, because that is the one a turn stands on. Taking a
    # single goal back narrows the request; taking the profile back ends it.
    ConsentService(database, profile_id=PROFILE).record(
        event_id="consent-withdraw",
        consent_type="model_egress",
        scope={},
        ui_action=UiConsentAction.WITHDRAW,
        control_id="btn-consent-withdraw",
        now="2026-01-02T00:00:00Z",
    )
    adapter = StubAdapter()
    client = build(database, adapter)
    with client, connect(client) as socket:
        reply = send_turn(socket)
    assert reply["error"]["code"] == "consent_withdrawn"
    assert adapter.calls == 0
    assert count(database, "session_message") == 0


def test_a_retried_turn_replays_its_answer_without_a_second_model_call(
    database: CoachDatabase,
) -> None:
    adapter = StubAdapter()
    client = build(database, adapter)
    with client, connect(client) as socket:
        first = send_turn(socket, key="key-1")
        second = send_turn(socket, request_id=2, revision=0, key="key-1")

    assert first["result"] == second["result"]
    assert adapter.calls == 1
    assert count(database, "session_message") == 2
    assert SessionRevisionRepository(database.connection).current(SESSION) == 1


def test_a_second_genuine_turn_needs_the_new_revision(
    database: CoachDatabase,
) -> None:
    client = build(database, StubAdapter())
    with client, connect(client) as socket:
        send_turn(socket, key="key-1", turn_id="turn-1")
        stale = send_turn(socket, request_id=2, revision=0, key="key-2", turn_id="turn-2")
        fresh = send_turn(socket, request_id=3, revision=1, key="key-3", turn_id="turn-2")

    assert stale["error"]["code"] == "stale_revision"
    assert fresh["result"]["question"] == QUESTION
    assert count(database, "session_message") == 4


def test_a_failed_write_leaves_neither_transcript_nor_revision(
    database: CoachDatabase, monkeypatch
) -> None:
    """The turn's rows and the envelope's bookkeeping share one transaction."""
    from hermes_coach.infrastructure.repositories.candidate_repository import (
        CandidateRepository,
    )

    def explode(self, candidate) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(CandidateRepository, "add", explode)

    client = build(database, StubAdapter())
    with client, connect(client) as socket:
        reply = send_turn(socket)

    assert reply["error"]["code"] == "envelope_failed"
    assert count(database, "session_message") == 0
    assert count(database, "candidate_record") == 0
    assert SessionRevisionRepository(database.connection).current(SESSION) == 0
