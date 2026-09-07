"""A candidate the Coach proposed, confirmed into an official record.

Requirement families: `HC-RECORDS`; sources `SRC-070…075`, `SRC-079`.

This is the join nobody had ever crossed. `CoachingTurnService` writes a
candidate; `DurableConfirmationService` promotes it. Both halves had tests, both
passed, and they disagreed about the payload: the turn wrote every candidate as
`{"value": …}` while promotion asked a goal for `title`, an insight and a memory
for `content`, a commitment for `action_text`. Pressing Lưu in the live app
answered `candidate payload has no title`, and no session could leave a record
behind.

Neither side's unit tests could see it. Only a test that walks the whole path
can, which is what this file is.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from hermes_coach.application.coaching_turn_service import (
    PAYLOAD_FIELD,
    CoachingTurnService,
)
from hermes_coach.application.consent_service import ConsentService, UiConsentAction
from hermes_coach.application.durable_confirmation_service import (
    ConfirmationRejected,
    DurableConfirmationService,
)
from hermes_coach.application.record_confirmation_service import (
    ConfirmationCommand,
    RecordAction,
)
from hermes_coach.contracts.runtime_contract import (
    CandidateRecord,
    CoachingStage,
    CoachOutput,
    RecordKind,
    RuntimeRequest,
    UsageAccounting,
    ValidatedRuntimeResult,
)
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-01-01T00:00:00Z"
PROFILE = "local"
SESSION = "session-1"
TURN = "turn-1"
QUESTION = "Điều gì quan trọng với bạn?"

# The array each kind travels in, and the table its official record lands in.
KINDS = {
    RecordKind.GOAL: ("candidate_goals", "goal", "goal"),
    RecordKind.INSIGHT: ("candidate_insights", "insight", "insight"),
    RecordKind.MEMORY: ("candidate_memories", "memory_item", "memory_item"),
}


class StubAdapter:
    def __init__(self, output: CoachOutput) -> None:
        self._output = output

    def generate(self, request: RuntimeRequest, *, sink=None) -> ValidatedRuntimeResult:
        return ValidatedRuntimeResult(
            output=self._output,
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


def propose(database: CoachDatabase, kind: RecordKind, value: str) -> str:
    """Run one turn whose output carries a single candidate; return its id."""
    array, _, _ = KINDS[kind]
    output = CoachOutput(
        question=QUESTION,
        coaching_stage=CoachingStage.GOAL,
        **{
            array: (
                CandidateRecord(
                    candidate_id="c-1", kind=kind, value=value, source_turn_id=TURN
                ),
            )
        },
    )
    persisted = CoachingTurnService(
        database, profile_id=PROFILE, adapter=StubAdapter(output)
    ).run(
        session_id=SESSION,
        turn_id=TURN,
        goal_id=None,
        user_message="Tôi muốn đổi hướng đi",
        now=NOW,
    )
    with database.transaction():
        persisted.apply(database.connection)
    return f"{TURN}-c-1"


def confirm(
    database: CoachDatabase,
    candidate_id: str,
    *,
    action: RecordAction = RecordAction.ACCEPT,
    edited_value: str | None = None,
):
    """Mint an intent and consume it, exactly as the UI does."""
    service = DurableConfirmationService(database, profile_id=PROFILE)
    token = service.issue_intent(
        local_user_id=PROFILE,
        session_id=SESSION,
        candidate_id=candidate_id,
        action=action,
        edited_value=edited_value,
        now=NOW,
    )
    return service.apply(
        ConfirmationCommand(
            command_id="cmd-1",
            intent_token=token,
            candidate_id=candidate_id,
            action=action,
            edited_value=edited_value,
        ),
        now=NOW,
    )


@pytest.mark.parametrize("kind", sorted(KINDS, key=lambda item: item.value))
def test_a_proposed_candidate_can_be_confirmed_into_a_record(
    database: CoachDatabase, kind: RecordKind
) -> None:
    """The whole point of a coaching session: it leaves something behind."""
    _, record_type, table = KINDS[kind]
    candidate_id = propose(database, kind, "Đổi hướng trước tháng 6")

    outcome = confirm(database, candidate_id)

    assert outcome.official_record_type == record_type
    stored = database.connection.execute(
        f"SELECT 1 FROM {table} WHERE id = ?", (outcome.official_record_id,)
    ).fetchone()
    assert stored is not None


@pytest.mark.parametrize("kind", sorted(KINDS, key=lambda item: item.value))
def test_the_candidate_is_written_under_the_field_promotion_reads(
    database: CoachDatabase, kind: RecordKind
) -> None:
    """Named explicitly, because the mismatch was invisible from either side."""
    candidate_id = propose(database, kind, "Một điều đáng giữ")
    row = database.connection.execute(
        "SELECT payload_json FROM candidate_record WHERE id = ?", (candidate_id,)
    ).fetchone()
    assert PAYLOAD_FIELD[kind.value] in row["payload_json"]


def test_an_edit_replaces_the_text_the_coachee_saw(database: CoachDatabase) -> None:
    candidate_id = propose(database, RecordKind.GOAL, "Đổi hướng trước tháng 6")

    outcome = confirm(
        database,
        candidate_id,
        action=RecordAction.EDIT,
        edited_value="Đổi hướng trước 30/06",
    )

    title = database.connection.execute(
        "SELECT title FROM goal WHERE id = ?", (outcome.official_record_id,)
    ).fetchone()["title"]
    assert title == "Đổi hướng trước 30/06"


def test_a_discarded_candidate_leaves_no_record(database: CoachDatabase) -> None:
    candidate_id = propose(database, RecordKind.GOAL, "Đổi hướng trước tháng 6")

    outcome = confirm(database, candidate_id, action=RecordAction.DISCARD)

    assert outcome.official_record_id is None
    assert database.connection.execute("SELECT COUNT(*) AS n FROM goal").fetchone()["n"] == 0


def test_a_commitment_still_cannot_be_confirmed_without_a_goal(
    database: CoachDatabase,
) -> None:
    """A known, deliberate gap — recorded here so it stays visible.

    `_write_official_record` refuses a commitment whose payload names no goal,
    and nothing yet puts a `goal_id` into a commitment candidate: the turn knows
    one only when the caller passes it, and the web client never does. Until that
    is wired, a commitment the Coach proposes cannot be kept.
    """
    # The session itself must be at Will: a commitment raised earlier is an
    # option the Coachee is still weighing, and the turn drops it.
    with database.transaction():
        database.connection.execute(
            "UPDATE coaching_session SET coaching_stage = 'will' WHERE id = ?",
            (SESSION,),
        )
    output = CoachOutput(
        question=QUESTION,
        coaching_stage=CoachingStage.WILL,
        candidate_commitments=(
            CandidateRecord(
                candidate_id="c-1",
                kind=RecordKind.COMMITMENT,
                value="Mỗi sáng làm 2 tiếng",
                source_turn_id=TURN,
            ),
        ),
    )
    persisted = CoachingTurnService(
        database, profile_id=PROFILE, adapter=StubAdapter(output)
    ).run(
        session_id=SESSION,
        turn_id=TURN,
        goal_id=None,
        user_message="Tôi sẽ làm mỗi sáng",
        now=NOW,
    )
    with database.transaction():
        persisted.apply(database.connection)

    with pytest.raises(ConfirmationRejected, match="goal"):
        confirm(database, f"{TURN}-c-1")
