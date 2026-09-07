"""One coaching turn, from consent to persisted record.

Requirement families: `HC-PRODUCT`, `HC-PRIVACY`, `HC-RECORDS`; sources
`SRC-026`, `SRC-070…075`, `SRC-079`, `SRC-091`, `SRC-104…106`.

The ordering that matters: consent is checked before any model call, and the
accepted output is committed before it is emitted. A client that sees a question
can rely on it being in the database; a client that sees an error can rely on
nothing having been written.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from hermes_coach.api.app import CancellationRegistry, TurnCancelled
from hermes_coach.application.coaching_turn_service import CoachingTurnService
from hermes_coach.application.consent_service import ConsentService, UiConsentAction
from hermes_coach.contracts.runtime_contract import (
    CandidateRecord,
    CoachingStage,
    CoachOutput,
    RecordKind,
    RuntimeRequest,
    UsageAccounting,
    ValidatedRuntimeResult,
)
from hermes_coach.domain.records import GoalRow, MemoryItemRow
from hermes_coach.infrastructure.hermes_runtime_adapter import RuntimeRejected
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.memory_repository import MemoryRepository
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-01-01T00:00:00Z"
PROFILE = "profile-1"
SESSION = "session-1"
TURN = "turn-1"
GOAL = "goal-1"

QUESTION = "Điều gì khiến việc này quan trọng với bạn?"


class StubAdapter:
    """Stands in for the runtime. Records whether it was called at all."""

    def __init__(self, output: CoachOutput | None = None, error: Exception | None = None):
        self._output = output or CoachOutput(
            question=QUESTION, coaching_stage=CoachingStage.GOAL
        )
        self._error = error
        self.calls: list[RuntimeRequest] = []

    def generate(
        self, request: RuntimeRequest, *, sink=None
    ) -> ValidatedRuntimeResult:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        result = ValidatedRuntimeResult(
            output=self._output,
            attempts=1,
            usage=UsageAccounting(input_tokens=10, output_tokens=5),
        )
        if sink is not None:
            sink(result.output)
        return result


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
                    source_session_id=SESSION,
                    confirmed_at=NOW,
                    created_at=NOW,
                )
            )
        # Both layers, because they answer different questions. The profile
        # scope is what a turn requires — the transcript always leaves the
        # machine, whatever goal is named. The goal scope is an additional
        # grant over that one goal's title and insights. A turn runs without
        # it; it simply carries less.
        grant(db, PROFILE_SCOPE)
        grant(db, GOAL_SCOPE)
        yield db


PROFILE_SCOPE: dict = {}
GOAL_SCOPE = {"goal_id": GOAL}


def _event_id(scope: dict, action: str) -> str:
    """Stable and distinct per (scope, action), so grants do not collide."""
    return f"consent-{action}-{scope.get('goal_id', 'profile')}"


def grant(database: CoachDatabase, scope: dict) -> None:
    ConsentService(database, profile_id=PROFILE).record(
        event_id=_event_id(scope, "grant"),
        consent_type="model_egress",
        scope=scope,
        ui_action=UiConsentAction.CONFIRM,
        control_id="btn-consent-confirm",
        now=NOW,
    )


def withdraw(database: CoachDatabase, scope: dict | None = None) -> None:
    """Withdraws the profile scope by default — the one that stops a turn."""
    scope = PROFILE_SCOPE if scope is None else scope
    ConsentService(database, profile_id=PROFILE).record(
        event_id=_event_id(scope, "withdraw"),
        consent_type="model_egress",
        scope=scope,
        ui_action=UiConsentAction.WITHDRAW,
        control_id="btn-consent-withdraw",
        now="2026-01-02T00:00:00Z",
    )


def service(database: CoachDatabase, adapter: StubAdapter) -> CoachingTurnService:
    return CoachingTurnService(database, profile_id=PROFILE, adapter=adapter)


def run_turn(
    database: CoachDatabase,
    adapter: StubAdapter,
    *,
    message: str = "Tôi muốn đổi vai trò",
    turn_id: str = TURN,
):
    persisted = service(database, adapter).run(
        session_id=SESSION,
        turn_id=turn_id,
        goal_id=GOAL,
        user_message=message,
        now=NOW,
    )
    with database.transaction():
        persisted.apply(database.connection)
    return persisted.result


def messages(database: CoachDatabase) -> list[tuple]:
    rows = database.connection.execute(
        "SELECT role, content, sequence_no FROM session_message ORDER BY sequence_no"
    ).fetchall()
    return [(row["role"], row["content"], row["sequence_no"]) for row in rows]


def candidates(database: CoachDatabase) -> list[tuple]:
    rows = database.connection.execute(
        "SELECT record_type, status, payload_json FROM candidate_record ORDER BY id"
    ).fetchall()
    return [(r["record_type"], r["status"], r["payload_json"]) for r in rows]


def test_an_accepted_turn_returns_the_question(database: CoachDatabase) -> None:
    result = run_turn(database, StubAdapter())
    assert result["question"] == QUESTION
    assert result["coaching_stage"] == "goal"


def test_both_sides_of_the_turn_are_persisted_in_order(
    database: CoachDatabase,
) -> None:
    run_turn(database, StubAdapter())
    assert messages(database) == [
        ("coachee", "Tôi muốn đổi vai trò", 0),
        ("coach", QUESTION, 1),
    ]


def test_a_second_turn_continues_the_sequence(database: CoachDatabase) -> None:
    adapter = StubAdapter()
    run_turn(database, adapter, turn_id="turn-1")
    run_turn(database, adapter, message="Vì tôi muốn phát triển", turn_id="turn-2")
    assert [row[2] for row in messages(database)] == [0, 1, 2, 3]


def test_the_transcript_is_written_to_be_kept(database: CoachDatabase) -> None:
    """The Coachee's own words outlive the retention window now.

    This test used to assert the opposite — a 90-day deadline stamped on every
    line. Under that rule the conclusions drawn from a conversation lived
    forever while the conversation itself was deleted from under the person who
    had it: the record said "you decided X" and the only thing that could show
    why was gone.

    A NULL expiry is the schema's own word for durable, and the sweep reads it
    that way.
    """
    run_turn(database, StubAdapter())
    expiries = database.connection.execute(
        "SELECT DISTINCT expires_at FROM session_message"
    ).fetchall()
    assert [row["expires_at"] for row in expiries] == [None]


def test_pending_candidates_still_carry_their_deadline(
    database: CoachDatabase,
) -> None:
    """Only the transcript changed. An unresolved proposal is still temporary,
    and keeping every one forever is the confirmation-fatigue problem again."""
    output = CoachOutput(
        question=QUESTION,
        coaching_stage=CoachingStage.GOAL,
        candidate_insights=(
            CandidateRecord(
                candidate_id="c-1",
                kind=RecordKind.INSIGHT,
                value="Một điều đáng giữ",
                source_turn_id=TURN,
            ),
        ),
    )
    run_turn(database, StubAdapter(output))
    expiries = database.connection.execute(
        "SELECT DISTINCT expires_at FROM candidate_record"
    ).fetchall()
    assert [row["expires_at"] for row in expiries] == ["2026-04-01T00:00:00Z"]


def test_candidates_are_persisted_as_pending(database: CoachDatabase) -> None:
    output = CoachOutput(
        question=QUESTION,
        coaching_stage=CoachingStage.GOAL,
        candidate_goals=(
            CandidateRecord(
                candidate_id="c-1",
                kind=RecordKind.GOAL,
                value="Trở thành kiến trúc sư trong 6 tháng",
                source_turn_id=TURN,
            ),
        ),
    )
    run_turn(database, StubAdapter(output))
    # Stored under "title", not "value": that is the field
    # `DurableConfirmationService` reads when it promotes a goal candidate into a
    # goal. This assertion used to say "value", which is exactly why pressing Lưu
    # in the live app answered `candidate payload has no title`.
    assert candidates(database) == [
        ("goal", "pending", '{"title": "Trở thành kiến trúc sư trong 6 tháng"}')
    ]


def test_every_candidate_kind_reaches_its_own_record_type(
    database: CoachDatabase,
) -> None:
    # Driven from Will, because a commitment cannot be raised before it: at
    # Options a Coachee is still weighing possibilities, and one live session
    # ended with the option they had explicitly rejected sitting in the list as
    # a promise awaiting their click.
    with database.transaction():
        database.connection.execute(
            "UPDATE coaching_session SET coaching_stage = 'will' WHERE id = ?",
            (SESSION,),
        )
    output = CoachOutput(
        question=QUESTION,
        coaching_stage=CoachingStage.GOAL,
        candidate_goals=(
            CandidateRecord(
                candidate_id="c-goal", kind=RecordKind.GOAL, value="G", source_turn_id=TURN
            ),
        ),
        candidate_insights=(
            CandidateRecord(
                candidate_id="c-ins", kind=RecordKind.INSIGHT, value="I", source_turn_id=TURN
            ),
        ),
        candidate_commitments=(
            CandidateRecord(
                candidate_id="c-com",
                kind=RecordKind.COMMITMENT,
                value="C",
                source_turn_id=TURN,
            ),
        ),
        candidate_memories=(
            CandidateRecord(
                candidate_id="c-mem", kind=RecordKind.MEMORY, value="M", source_turn_id=TURN
            ),
        ),
    )
    run_turn(database, StubAdapter(output))
    assert {row[0] for row in candidates(database)} == {
        "goal",
        "insight",
        "commitment",
        "memory",
    }


def test_withdrawn_consent_stops_the_turn_before_any_model_call(
    database: CoachDatabase,
) -> None:
    """No request, no tokens, no transcript — the model is never reached."""
    withdraw(database)
    adapter = StubAdapter()
    with pytest.raises(PermissionError):
        service(database, adapter).run(
            session_id=SESSION,
            turn_id=TURN,
            goal_id=GOAL,
            user_message="Tôi muốn đổi vai trò",
            now=NOW,
        )
    assert adapter.calls == []
    assert messages(database) == []


def test_withdrawing_only_a_goals_scope_narrows_the_turn_instead_of_ending_it(
    database: CoachDatabase,
) -> None:
    """The other half of the rule, and the reason it is safe.

    A Coachee who takes one goal back has not asked the session to stop. The
    turn runs, the transcript still goes (they consented to that separately),
    and that goal's title and insights simply are not in the request.
    """
    withdraw(database, GOAL_SCOPE)
    adapter = StubAdapter()
    result = run_turn(database, adapter)

    assert result["question"] == QUESTION
    assert adapter.calls[0].structured_context["goal_count"] == 0
    assert "Chuyển vai trò" not in str(adapter.calls[0].structured_context)


def test_a_rejected_output_writes_nothing(database: CoachDatabase) -> None:
    from hermes_coach.contracts.runtime_contract import RuntimeFailure

    failure = RuntimeFailure(
        code="policy_error",
        retryable=True,
        safe_message="không đạt chuẩn",
        attempts=3,
        usage=UsageAccounting(input_tokens=1, output_tokens=1),
    )
    adapter = StubAdapter(error=RuntimeRejected(failure, "corr-1"))
    with pytest.raises(RuntimeRejected):
        service(database, adapter).run(
            session_id=SESSION,
            turn_id=TURN,
            goal_id=GOAL,
            user_message="Tôi muốn đổi vai trò",
            now=NOW,
        )
    assert messages(database) == []
    assert candidates(database) == []


def test_the_model_call_happens_outside_any_write_transaction(
    database: CoachDatabase,
) -> None:
    """Holding a write lock across a network call would stall every other write."""
    observed: list[bool] = []

    class ObservingAdapter(StubAdapter):
        def generate(self, request, *, sink=None):
            observed.append(database.connection.in_transaction)
            return super().generate(request, sink=sink)

    run_turn(database, ObservingAdapter())
    assert observed == [False]


def test_the_turn_carries_the_selected_context_to_the_model(
    database: CoachDatabase,
) -> None:
    adapter = StubAdapter()
    run_turn(database, adapter)
    request = adapter.calls[0]
    assert request.session_id == SESSION
    assert request.turn_id == TURN
    assert request.user_message == "Tôi muốn đổi vai trò"
    assert request.structured_context["goal_count"] == 1


def test_the_server_finds_the_goal_the_client_did_not_name(
    database: CoachDatabase,
) -> None:
    """The gap that made every real turn contextless.

    No browser has ever sent `goal_id`, so this was None on every turn the
    product actually made, and the model was asked to coach towards a goal it
    was never shown. The session's own goal is the server's to find.
    """
    adapter = StubAdapter()
    persisted = service(database, adapter).run(
        session_id=SESSION,
        turn_id=TURN,
        goal_id=None,
        user_message="Tôi muốn đổi vai trò",
        now=NOW,
    )
    with database.transaction():
        persisted.apply(database.connection)

    context = adapter.calls[0].structured_context
    assert context["goal_count"] == 1
    assert "Chuyển vai trò" in context["goal_titles"]


def test_the_server_declines_to_guess_between_several_goals(
    database: CoachDatabase,
) -> None:
    """Only when nothing links a goal to this session.

    Sending the wrong goal's history into a coaching question is worse than
    sending none, so an ambiguous profile gets none. Here the fixture's goal is
    detached from the session first, leaving two equally plausible candidates.
    """
    with database.transaction():
        database.connection.execute(
            "UPDATE goal SET source_session_id = NULL WHERE id = ?", (GOAL,)
        )
        GoalRepository(database.connection).add(
            GoalRow(
                id="goal-2",
                profile_id=PROFILE,
                title="Học tiếng Nhật",
                status="active",
                confirmed_at=NOW,
                created_at=NOW,
            )
        )
    adapter = StubAdapter()
    persisted = service(database, adapter).run(
        session_id=SESSION,
        turn_id=TURN,
        goal_id=None,
        user_message="Tôi muốn đổi vai trò",
        now=NOW,
    )
    with database.transaction():
        persisted.apply(database.connection)

    assert adapter.calls[0].structured_context["goal_count"] == 0


def test_a_goal_this_session_created_wins_over_the_others(
    database: CoachDatabase,
) -> None:
    with database.transaction():
        GoalRepository(database.connection).add(
            GoalRow(
                id="goal-2",
                profile_id=PROFILE,
                title="Học tiếng Nhật",
                status="active",
                confirmed_at=NOW,
                created_at=NOW,
            )
        )
    adapter = StubAdapter()
    persisted = service(database, adapter).run(
        session_id=SESSION,
        turn_id=TURN,
        goal_id=None,
        user_message="Tôi muốn đổi vai trò",
        now=NOW,
    )
    with database.transaction():
        persisted.apply(database.connection)

    assert adapter.calls[0].structured_context["goal_titles"] == ["Chuyển vai trò"]


def test_a_goal_scope_alone_cannot_run_a_turn(tmp_path) -> None:
    """Granting one goal is not permission to send the transcript.

    This test used to assert the opposite: that a goal grant alone was enough
    to run a turn, and that the selector would keep profile memory out of it.
    It was passing on a rule that let a Coachee who had withdrawn profile-wide
    consent keep having every word they typed sent to the model, as long as one
    goal grant survived. The transcript is always egressed, so the profile
    scope is always what a turn requires.
    """
    with open_coach_database(tmp_path / "coach.db") as database:
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
            GoalRepository(database.connection).add(
                GoalRow(
                    id=GOAL,
                    profile_id=PROFILE,
                    title="Chuyển vai trò",
                    status="active",
                    confirmed_at=NOW,
                    created_at=NOW,
                )
            )
        grant(database, GOAL_SCOPE)
        adapter = StubAdapter()
        with pytest.raises(PermissionError):
            service(database, adapter).run(
                session_id=SESSION,
                turn_id=TURN,
                goal_id=GOAL,
                user_message="Tôi muốn đổi vai trò",
                now=NOW,
            )
        assert adapter.calls == []


def test_a_cancel_that_arrives_before_the_call_costs_no_tokens(
    database: CoachDatabase,
) -> None:
    cancellations = CancellationRegistry()
    cancellations.cancel(SESSION, TURN)
    adapter = StubAdapter()

    with pytest.raises(TurnCancelled):
        service(database, adapter).run(
            session_id=SESSION,
            turn_id=TURN,
            goal_id=GOAL,
            user_message="Tôi muốn đổi vai trò",
            now=NOW,
            cancellations=cancellations,
        )
    assert adapter.calls == []


def test_a_cancel_that_arrives_during_the_call_is_still_honoured(
    database: CoachDatabase,
) -> None:
    """Otherwise a dismissed answer would be persisted anyway."""
    cancellations = CancellationRegistry()

    class CancellingAdapter(StubAdapter):
        def generate(self, request: RuntimeRequest, *, sink=None):
            result = super().generate(request, sink=sink)
            cancellations.cancel(SESSION, TURN)
            return result

    adapter = CancellingAdapter()
    with pytest.raises(TurnCancelled):
        service(database, adapter).run(
            session_id=SESSION,
            turn_id=TURN,
            goal_id=GOAL,
            user_message="Tôi muốn đổi vai trò",
            now=NOW,
            cancellations=cancellations,
        )
    assert adapter.calls != []
    assert messages(database) == []


def test_an_uncancelled_turn_runs_normally_with_a_registry_attached(
    database: CoachDatabase,
) -> None:
    adapter = StubAdapter()
    persisted = service(database, adapter).run(
        session_id=SESSION,
        turn_id=TURN,
        goal_id=GOAL,
        user_message="Tôi muốn đổi vai trò",
        now=NOW,
        cancellations=CancellationRegistry(),
    )
    with database.transaction():
        persisted.apply(database.connection)
    assert persisted.result["question"] == QUESTION


def test_unconfirmed_memory_never_reaches_the_structured_context(
    database: CoachDatabase,
) -> None:
    """The selector filters; this proves nothing routes around it.

    Memory the Coachee never confirmed is out regardless of consent, so this
    holds even on a fully granted profile — which is the only kind of profile
    that can run a turn at all now. Consent-scope filtering itself is covered
    where the filter lives, in `persistence/test_context_selection.py`.
    """
    secret = "Ghi nhớ chưa được đồng ý gửi đi"
    with database.transaction():
        MemoryRepository(database.connection).add(
            MemoryItemRow(id="memory-1", content=secret, user_confirmed=False)
        )
    adapter = StubAdapter()
    run_turn(database, adapter)

    rendered = str(adapter.calls[0].structured_context)
    assert secret not in rendered
    assert adapter.calls[0].structured_context["memory_count"] == 0


def test_consented_memory_does_reach_the_structured_context(
    database: CoachDatabase,
) -> None:
    """The negative test above must not be passing because nothing ever gets in."""
    allowed = "Coachee coi trọng quyền tự chủ"
    with database.transaction():
        MemoryRepository(database.connection).add(
            MemoryItemRow(id="memory-1", content=allowed, user_confirmed=True)
        )
    adapter = StubAdapter()
    run_turn(database, adapter)

    assert allowed in str(adapter.calls[0].structured_context)


def test_the_persisted_write_is_one_transaction(database: CoachDatabase) -> None:
    """A crash mid-write must leave neither half of the turn."""
    persisted = service(database, StubAdapter()).run(
        session_id=SESSION,
        turn_id=TURN,
        goal_id=GOAL,
        user_message="Tôi muốn đổi vai trò",
        now=NOW,
    )

    original = persisted.apply

    def failing(connection) -> None:
        original(connection)
        raise RuntimeError("crash after the rows went in")

    with pytest.raises(RuntimeError):
        with database.transaction():
            failing(database.connection)

    assert messages(database) == []
    assert candidates(database) == []
