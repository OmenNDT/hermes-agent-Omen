"""The six-step gate, driven by a turn.

Requirement families: `HC-PROCESS`; sources `SRC-030…057`, `SRC-059…061`.

A step closes on one thing only: the Coach asked a yes/no closing question and
the Coachee's very next message was an explicit yes. These tests are written
against that adjacency, because every way of getting it wrong — harvesting a yes
from earlier in the conversation, accepting one that answers a different
question, advancing on an unclear reply — produces a coaching record that claims
a confirmation the Coachee never gave.

The gate answer is classified by `domain.transitions.classify_gate_answer`, so
what counts as a yes is asserted there. What is asserted here is that the turn
writes the evidence and moves the session.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from hermes_coach.application.coaching_turn_service import (
    CoachingTurnService,
    SessionEnded,
)
from hermes_coach.application.consent_service import ConsentService, UiConsentAction
from hermes_coach.contracts.runtime_contract import (
    CoachingStage,
    CoachOutput,
    RuntimeRequest,
    UsageAccounting,
    ValidatedRuntimeResult,
)
from hermes_coach.infrastructure.repositories.gate_repository import GateRepository
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-01-01T00:00:00Z"
PROFILE = "profile-1"
SESSION = "session-1"

# Passes `is_yes_no_closing_question`: it asks for confirmation and offers the
# no pole. This is the shape that opens a gate.
CLOSING = "Bạn có xác nhận nội dung bước này là đúng không?"

# A perfectly good coaching question that is not a closing one.
OPEN_QUESTION = "Điều gì khiến việc này quan trọng với bạn?"


class StubAdapter:
    """Answers with whatever question the test needs, and records the request."""

    def __init__(
        self, question: str = OPEN_QUESTION, snapshot: dict | None = None
    ) -> None:
        self.question = question
        self.snapshot = snapshot or {}
        self.calls: list[RuntimeRequest] = []

    def generate(self, request: RuntimeRequest, *, sink=None) -> ValidatedRuntimeResult:
        self.calls.append(request)
        return ValidatedRuntimeResult(
            output=CoachOutput(
                question=self.question,
                coaching_stage=request.current_stage,
                stage_snapshot=self.snapshot,
            ),
            attempts=1,
            usage=UsageAccounting(input_tokens=1, output_tokens=1),
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
                "VALUES (?, ?, 'pre_coaching')",
                (SESSION, NOW),
            )
        ConsentService(db, profile_id=PROFILE).record(
            event_id="consent-1",
            consent_type="model_egress",
            scope={},
            ui_action=UiConsentAction.CONFIRM,
            control_id="btn-consent-confirm",
            now=NOW,
        )
        yield db


def turn(
    database: CoachDatabase,
    adapter: StubAdapter,
    *,
    message: str,
    turn_id: str,
) -> dict:
    persisted = CoachingTurnService(
        database, profile_id=PROFILE, adapter=adapter
    ).run(
        session_id=SESSION,
        turn_id=turn_id,
        goal_id=None,
        user_message=message,
        now=NOW,
    )
    with database.transaction():
        persisted.apply(database.connection)
    return persisted.result


def open_the_gate(database: CoachDatabase, *, turn_id: str = "t1") -> None:
    """Get the transcript into the state where a closing question is the tail."""
    turn(database, StubAdapter(CLOSING), message="Tôi sẵn sàng", turn_id=turn_id)


def stage_of(database: CoachDatabase) -> str:
    row = database.connection.execute(
        "SELECT coaching_stage FROM coaching_session WHERE id = ?", (SESSION,)
    ).fetchone()
    return row["coaching_stage"]


def gate_rows(database: CoachDatabase) -> list[tuple]:
    rows = database.connection.execute(
        "SELECT step, revision, result, confirmed_at, closing_question_message_id, "
        "response_message_id FROM gate_confirmation ORDER BY revision, id"
    ).fetchall()
    return [tuple(row) for row in rows]


def set_stage(database: CoachDatabase, stage: str) -> None:
    with database.transaction():
        database.connection.execute(
            "UPDATE coaching_session SET coaching_stage = ? WHERE id = ?",
            (stage, SESSION),
        )


class TestNoGateIsOpen:
    def test_an_ordinary_turn_writes_no_gate_event(self, database) -> None:
        turn(database, StubAdapter(), message="Tôi thấy bế tắc", turn_id="t1")
        assert gate_rows(database) == []

    def test_an_ordinary_turn_does_not_move_the_step(self, database) -> None:
        turn(database, StubAdapter(), message="Tôi thấy bế tắc", turn_id="t1")
        assert stage_of(database) == "pre_coaching"

    def test_a_yes_to_an_open_question_confirms_nothing(self, database) -> None:
        """A yes is only evidence when something asked for confirmation.

        Without this, any agreeable Coachee closes every step by accident.
        """
        turn(database, StubAdapter(OPEN_QUESTION), message="Chào Coach", turn_id="t1")
        turn(database, StubAdapter(), message="Có, đúng vậy", turn_id="t2")
        assert gate_rows(database) == []
        assert stage_of(database) == "pre_coaching"


class TestAnsweringTheGate:
    def test_an_explicit_yes_advances_one_step(self, database) -> None:
        open_the_gate(database)
        turn(database, StubAdapter(), message="Có, tôi đồng ý", turn_id="t2")
        assert stage_of(database) == "goal"

    def test_an_explicit_yes_is_recorded_as_evidence(self, database) -> None:
        open_the_gate(database)
        turn(database, StubAdapter(), message="Có, tôi đồng ý", turn_id="t2")
        step, revision, result, confirmed_at, question_id, response_id = gate_rows(
            database
        )[0]
        assert (step, revision, result) == ("pre_coaching", 1, "yes")
        assert confirmed_at == NOW
        # The evidence points at the two messages it was built from, so an audit
        # can re-read the exact exchange rather than trusting the row.
        assert question_id == "t1-coach"
        assert response_id == "t2-coachee"

    def test_the_step_reads_as_confirmed(self, database) -> None:
        open_the_gate(database)
        turn(database, StubAdapter(), message="Có, tôi đồng ý", turn_id="t2")
        confirmed = GateRepository(database.connection).confirmed_steps(SESSION)
        assert confirmed == ("pre_coaching",)

    def test_a_no_records_the_refusal_and_stays(self, database) -> None:
        open_the_gate(database)
        turn(database, StubAdapter(), message="Không", turn_id="t2")
        assert stage_of(database) == "pre_coaching"
        assert gate_rows(database)[0][2] == "no"
        assert gate_rows(database)[0][3] is None
        assert GateRepository(database.connection).confirmed_steps(SESSION) == ()

    def test_an_unclear_answer_stays(self, database) -> None:
        """Silence, hedging and a story are all "not yet", never "yes"."""
        open_the_gate(database)
        turn(database, StubAdapter(), message="Ừm, để tôi nghĩ thêm", turn_id="t2")
        assert stage_of(database) == "pre_coaching"
        assert gate_rows(database)[0][2] == "unclear"

    def test_a_refusal_then_a_yes_confirms_the_step(self, database) -> None:
        """The second event sits above the first, so the later answer wins."""
        open_the_gate(database)
        turn(database, StubAdapter(CLOSING), message="Không", turn_id="t2")
        turn(database, StubAdapter(), message="Có, tôi đồng ý", turn_id="t3")
        assert [(row[1], row[2]) for row in gate_rows(database)] == [
            (1, "no"),
            (2, "yes"),
        ]
        assert GateRepository(database.connection).confirmed_steps(SESSION) == (
            "pre_coaching",
        )
        assert stage_of(database) == "goal"


class TestAdjacency:
    def test_a_yes_that_is_not_the_next_message_confirms_nothing(
        self, database
    ) -> None:
        """The gate closes when the Coachee changes the subject.

        The yes below is a real yes, but it answers whatever the Coach asked
        after the closing question — not the closing question itself.
        """
        open_the_gate(database)
        turn(database, StubAdapter(OPEN_QUESTION), message="Kể thêm chút", turn_id="t2")
        turn(database, StubAdapter(), message="Có, tôi đồng ý", turn_id="t3")
        assert stage_of(database) == "pre_coaching"
        assert GateRepository(database.connection).confirmed_steps(SESSION) == ()

    def test_the_coach_is_asked_to_work_in_the_step_the_yes_opened(
        self, database
    ) -> None:
        """A Coachee who just closed Pre-Coaching is owed a Goal question."""
        open_the_gate(database)
        adapter = StubAdapter()
        turn(database, adapter, message="Có, tôi đồng ý", turn_id="t2")
        assert adapter.calls[0].current_stage is CoachingStage.GOAL

    def test_the_coachees_yes_is_filed_under_the_step_it_closed(
        self, database
    ) -> None:
        open_the_gate(database)
        turn(database, StubAdapter(), message="Có, tôi đồng ý", turn_id="t2")
        row = database.connection.execute(
            "SELECT coaching_stage FROM session_message WHERE id = 't2-coachee'"
        ).fetchone()
        assert row["coaching_stage"] == "pre_coaching"


class TestTheEndOfTheSession:
    def test_a_yes_at_review_closes_the_session(self, database) -> None:
        set_stage(database, "review")
        open_the_gate(database)
        turn(database, StubAdapter(), message="Có, tôi đồng ý", turn_id="t2")
        row = database.connection.execute(
            "SELECT ended_at, coaching_stage FROM coaching_session WHERE id = ?",
            (SESSION,),
        ).fetchone()
        assert row["ended_at"] == NOW
        # There is no seventh step to advance into.
        assert row["coaching_stage"] == "review"

    def test_a_closed_session_takes_no_further_turns(self, database) -> None:
        set_stage(database, "review")
        open_the_gate(database)
        turn(database, StubAdapter(), message="Có, tôi đồng ý", turn_id="t2")
        with pytest.raises(SessionEnded):
            turn(database, StubAdapter(), message="Còn một điều nữa", turn_id="t3")

    def test_a_refused_turn_costs_no_model_call(self, database) -> None:
        set_stage(database, "review")
        open_the_gate(database)
        turn(database, StubAdapter(), message="Có, tôi đồng ý", turn_id="t2")
        adapter = StubAdapter()
        with pytest.raises(SessionEnded):
            turn(database, adapter, message="Còn một điều nữa", turn_id="t3")
        assert adapter.calls == []


class TestWhatTheClientIsTold:
    def test_the_reported_stage_is_the_one_the_server_moved_to(self, database) -> None:
        open_the_gate(database)
        result = turn(database, StubAdapter(), message="Có, tôi đồng ý", turn_id="t2")
        assert result["coaching_stage"] == "goal"

    def test_the_gate_outcome_is_reported(self, database) -> None:
        open_the_gate(database)
        result = turn(database, StubAdapter(), message="Có, tôi đồng ý", turn_id="t2")
        assert result["gate"] == {
            "step": "pre_coaching",
            "answer": "yes",
            "advanced": True,
            "session_ended": False,
        }

    def test_no_gate_is_reported_when_none_was_open(self, database) -> None:
        result = turn(database, StubAdapter(), message="Tôi thấy bế tắc", turn_id="t1")
        assert result["gate"] is None


class TestAtomicity:
    def test_a_gate_event_never_lands_without_its_turn(self, database) -> None:
        """One transaction covers transcript and gate, or neither.

        A gate row whose evidence messages were rolled back would claim a
        confirmation with nothing behind it.
        """
        open_the_gate(database)
        persisted = CoachingTurnService(
            database, profile_id=PROFILE, adapter=StubAdapter()
        ).run(
            session_id=SESSION,
            turn_id="t2",
            goal_id=None,
            user_message="Có, tôi đồng ý",
            now=NOW,
        )
        with pytest.raises(RuntimeError):
            with database.transaction():
                persisted.apply(database.connection)
                raise RuntimeError("the caller failed after the write")
        assert gate_rows(database) == []
        assert stage_of(database) == "pre_coaching"


class TestAStepRemembersWhatItWasTold:
    """Found live, and it would have made enforcement impossible.

    The model reports what *this* turn revealed, not the whole step. Writing
    that over the stored snapshot made a step forget everything established
    earlier: a real Pre-Coaching filled three of its four fields, then dropped
    all three on the very next answer. A step could only ever have read as
    complete if the model happened to restate everything in one turn, which is
    not how a conversation goes.
    """

    def said(self, database: CoachDatabase, snapshot: dict, *, turn_id: str) -> dict:
        return turn(
            database,
            StubAdapter(snapshot=snapshot),
            message="Tôi đang nghĩ",
            turn_id=turn_id,
        )

    def snapshot_of(self, database: CoachDatabase) -> dict:
        import json

        row = database.connection.execute(
            "SELECT payload_json FROM stage_snapshot WHERE session_id = ?",
            (SESSION,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else {}

    def test_later_turns_add_to_the_step_rather_than_replace_it(
        self, database: CoachDatabase
    ) -> None:
        self.said(database, {"ready": True, "roles_agreed": True}, turn_id="t1")
        self.said(database, {"boundaries_agreed": True}, turn_id="t2")
        assert self.snapshot_of(database) == {
            "ready": True,
            "roles_agreed": True,
            "boundaries_agreed": True,
        }

    def test_a_later_turn_can_correct_an_earlier_one(
        self, database: CoachDatabase
    ) -> None:
        self.said(database, {"title": "chạy 5km"}, turn_id="t1")
        self.said(database, {"title": "chạy 20 phút"}, turn_id="t2")
        assert self.snapshot_of(database)["title"] == "chạy 20 phút"

    def test_an_omitted_key_is_not_an_erasure(self, database: CoachDatabase) -> None:
        """Omitting means "nothing new about this", not "take it back"."""
        self.said(database, {"ready": True}, turn_id="t1")
        self.said(database, {"roles_agreed": True}, turn_id="t2")
        assert self.snapshot_of(database)["ready"] is True

    def test_an_empty_value_does_not_erase_a_real_one(
        self, database: CoachDatabase
    ) -> None:
        """The prompt tells the model to leave a field out rather than fill it
        with something hollow; honouring "" as an erasure would punish it for
        doing as it was told."""
        self.said(database, {"title": "chạy 20 phút"}, turn_id="t1")
        self.said(database, {"title": "   "}, turn_id="t2")
        assert self.snapshot_of(database)["title"] == "chạy 20 phút"

    def test_the_reported_gaps_shrink_as_the_step_fills(
        self, database: CoachDatabase
    ) -> None:
        """What the Coachee actually sees, across turns.

        This is the sequence that exposed the bug live: the second turn used to
        report the first turn's answers as missing again.
        """
        first = self.said(database, {"ready": True}, turn_id="t1")
        second = self.said(
            database,
            {
                "coaching_understood": True,
                "roles_agreed": True,
                "boundaries_agreed": True,
            },
            turn_id="t2",
        )
        assert len(first["stage_gaps"]) == 3
        assert second["stage_gaps"] == []
