"""The Safety System, actually in the path of a turn.

Requirement families: `HC-SAFETY`; sources `SRC-093…099`.

`SafetyService` was written, tested and then called by nothing. `safety_state`
was never written by any code path, so it stayed `normal` for the life of every
session, `route_safety` never ran, and the interruption the system prompt
promises — *"possible_crisis tạm dừng coaching để safety check; urgent ngắt
coaching"* — could not happen. The model returned a `safety_signal` on every
single turn and it was discarded.

These tests are the wiring. They assert the two things that make the promise
real: that a signal changes the session, and that once it has, the Coach's
question is neither written nor shown.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from hermes_coach.application.coaching_turn_service import (
    CoachingTurnService,
    SafetyInterrupted,
)
from hermes_coach.application.consent_service import ConsentService, UiConsentAction
from hermes_coach.application.safety_service import (
    BLOCKED_MESSAGE,
    SAFETY_CHECK_MESSAGE,
)
from hermes_coach.contracts.runtime_contract import (
    CandidateRecord,
    CoachingStage,
    CoachOutput,
    RecordKind,
    RuntimeRequest,
    SafetySignal,
    UsageAccounting,
    ValidatedRuntimeResult,
)
from hermes_coach.domain.enums import SafetyState
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)
from hermes_coach.policies.safety_policy import escalate


NOW = "2026-01-01T00:00:00Z"
PROFILE = "local"
SESSION = "session-1"
QUESTION = "Điều gì quan trọng với bạn?"


class StubAdapter:
    """Answers with one signal, and records whether it was called at all."""

    def __init__(self, signal: SafetySignal = SafetySignal.NONE) -> None:
        self.signal = signal
        self.calls: list[RuntimeRequest] = []

    def generate(self, request: RuntimeRequest, *, sink=None) -> ValidatedRuntimeResult:
        self.calls.append(request)
        return ValidatedRuntimeResult(
            output=CoachOutput(
                question=QUESTION,
                coaching_stage=CoachingStage.GOAL,
                safety_signal=self.signal,
                candidate_insights=(
                    CandidateRecord(
                        candidate_id="c-1",
                        kind=RecordKind.INSIGHT,
                        value="Một điều đáng giữ",
                        source_turn_id="t1",
                    ),
                ),
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
                "VALUES (?, ?, 'goal')",
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


def turn(database: CoachDatabase, adapter: StubAdapter, *, turn_id: str = "t1"):
    persisted = CoachingTurnService(
        database, profile_id=PROFILE, adapter=adapter
    ).run(
        session_id=SESSION,
        turn_id=turn_id,
        goal_id=None,
        user_message="Tôi thấy không ổn",
        now=NOW,
    )
    with database.transaction():
        persisted.apply(database.connection)
    return persisted.result


def state_of(database: CoachDatabase) -> str | None:
    return database.connection.execute(
        "SELECT safety_state FROM coaching_session WHERE id = ?", (SESSION,)
    ).fetchone()["safety_state"]


def reply(database: CoachDatabase, turn_id: str = "t1") -> tuple[str, str]:
    row = database.connection.execute(
        "SELECT role, content FROM session_message WHERE id = ?", (f"{turn_id}-coach",)
    ).fetchone()
    return row["role"], row["content"]


def set_state(database: CoachDatabase, state: SafetyState) -> None:
    with database.transaction():
        database.connection.execute(
            "UPDATE coaching_session SET safety_state = ? WHERE id = ?",
            (state.value, SESSION),
        )


class TestTheSignalReachesTheSession:
    def test_a_calm_turn_leaves_the_state_alone(self, database) -> None:
        turn(database, StubAdapter(SafetySignal.NONE))
        assert state_of(database) in (None, "normal")
        assert reply(database) == ("coach", QUESTION)

    def test_distress_is_recorded_without_stopping_coaching(self, database) -> None:
        """Sensitive asks permission; it does not take the session away."""
        turn(database, StubAdapter(SafetySignal.DISTRESS))
        assert state_of(database) == "sensitive"
        assert reply(database) == ("coach", QUESTION)

    def test_self_harm_moves_the_session_to_possible_crisis(self, database) -> None:
        turn(database, StubAdapter(SafetySignal.SELF_HARM))
        assert state_of(database) == "possible_crisis"

    def test_immediate_danger_moves_the_session_to_urgent(self, database) -> None:
        turn(database, StubAdapter(SafetySignal.IMMEDIATE_DANGER))
        assert state_of(database) == "urgent"

    def test_every_message_carries_the_state_it_was_written_under(
        self, database
    ) -> None:
        turn(database, StubAdapter(SafetySignal.SELF_HARM))
        states = [
            row["safety_state"]
            for row in database.connection.execute(
                "SELECT safety_state FROM session_message ORDER BY sequence_no"
            )
        ]
        assert states == ["possible_crisis", "possible_crisis"]


class TestTheCoachStopsSpeaking:
    def test_the_models_question_is_never_written_once_coaching_is_interrupted(
        self, database
    ) -> None:
        """The one that matters. A crisis turn must not be coached through."""
        turn(database, StubAdapter(SafetySignal.SELF_HARM))
        role, content = reply(database)
        assert role == "safety_system"
        assert content == SAFETY_CHECK_MESSAGE
        assert QUESTION not in content

    def test_urgent_is_blocked_rather_than_answered(self, database) -> None:
        """With no signed attestation, urgent has nothing approved to say."""
        turn(database, StubAdapter(SafetySignal.IMMEDIATE_DANGER))
        role, content = reply(database)
        assert role == "safety_system"
        assert content == BLOCKED_MESSAGE

    def test_the_client_is_told_who_is_speaking(self, database) -> None:
        result = turn(database, StubAdapter(SafetySignal.SELF_HARM))
        assert result["safety"]["voice"] == "safety_system"
        assert result["safety"]["coaching_interrupted"] is True
        assert result["question"] == SAFETY_CHECK_MESSAGE

    def test_a_normal_turn_still_speaks_as_the_coach(self, database) -> None:
        result = turn(database, StubAdapter(SafetySignal.NONE))
        assert result["safety"]["voice"] == "coach"
        assert result["safety"]["coaching_interrupted"] is False
        assert result["question"] == QUESTION

    def test_an_interrupted_turn_keeps_no_records(self, database) -> None:
        """Minting records out of what someone said in crisis would be the
        product harvesting the moment it just refused to coach through."""
        turn(database, StubAdapter(SafetySignal.SELF_HARM))
        kept = database.connection.execute(
            "SELECT COUNT(*) AS n FROM candidate_record"
        ).fetchone()["n"]
        assert kept == 0

    def test_a_calm_turn_keeps_its_records(self, database) -> None:
        turn(database, StubAdapter(SafetySignal.NONE))
        kept = database.connection.execute(
            "SELECT COUNT(*) AS n FROM candidate_record"
        ).fetchone()["n"]
        assert kept == 1


class TestAnInterruptedSessionStaysInterrupted:
    @pytest.mark.parametrize(
        "state", [SafetyState.POSSIBLE_CRISIS, SafetyState.URGENT]
    )
    def test_a_further_turn_is_refused(self, database, state) -> None:
        set_state(database, state)
        with pytest.raises(SafetyInterrupted):
            turn(database, StubAdapter())

    @pytest.mark.parametrize(
        "state", [SafetyState.POSSIBLE_CRISIS, SafetyState.URGENT]
    )
    def test_the_refusal_costs_no_tokens(self, database, state) -> None:
        """Refused before the model is called, not after."""
        set_state(database, state)
        adapter = StubAdapter()
        with pytest.raises(SafetyInterrupted):
            turn(database, adapter)
        assert adapter.calls == []

    def test_a_sensitive_session_still_accepts_turns(self, database) -> None:
        set_state(database, SafetyState.SENSITIVE)
        turn(database, StubAdapter(SafetySignal.NONE))
        assert reply(database) == ("coach", QUESTION)

    def test_a_calmer_answer_does_not_lower_the_state(self, database) -> None:
        """De-escalation needs a distinct new Pre-Coaching session, not a turn.

        Tested on the rule directly, because a session that has been interrupted
        cannot take another turn to be tested through.
        """
        assert (
            escalate(SafetyState.POSSIBLE_CRISIS, SafetySignal.NONE)
            is SafetyState.POSSIBLE_CRISIS
        )
        assert (
            escalate(SafetyState.URGENT, SafetySignal.DISTRESS) is SafetyState.URGENT
        )

    def test_sensitive_escalates_but_never_slips_back(self, database) -> None:
        turn(database, StubAdapter(SafetySignal.DISTRESS), turn_id="t1")
        assert state_of(database) == "sensitive"
        turn(database, StubAdapter(SafetySignal.NONE), turn_id="t2")
        assert state_of(database) == "sensitive"
