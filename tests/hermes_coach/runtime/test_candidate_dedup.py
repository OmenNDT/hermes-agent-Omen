"""One proposal, once per session.

Requirement families: `HC-RECORDS`; sources `SRC-054…059`, `SRC-079`.

Found in the first session that ran all six steps end to end: fifteen turns
produced twenty pending candidates, and most of them were the same memory the
model re-offered on nearly every turn. Nothing was broken in the sense of
raising an error — every row was written exactly as designed. The design was
the problem.

It matters more than tidiness. The confirmation list is the feature by which
the Coachee owns their own records; a list of twenty cards that are really
three is a list they scroll past, and a product whose privacy story rests on
individual confirmation cannot afford confirmation fatigue.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from hermes_coach.application.coaching_turn_service import (
    CoachingTurnService,
    candidate_key,
)
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
from hermes_coach.infrastructure.hermes_runtime_adapter import OUTPUT_CONTRACT
from hermes_coach.infrastructure.repositories.candidate_repository import (
    CandidateRepository,
)
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-01-01T00:00:00Z"
PROFILE = "local"
SESSION = "session-1"
QUESTION = "Điều gì quan trọng với bạn?"
MEMORY = "Coachee coi trọng quyền tự chủ"


class StubAdapter:
    """Re-offers whatever it was told to, exactly as the real model does."""

    def __init__(self, *memories: str) -> None:
        self.memories = memories
        self.calls: list[RuntimeRequest] = []

    def generate(self, request: RuntimeRequest, *, sink=None) -> ValidatedRuntimeResult:
        self.calls.append(request)
        return ValidatedRuntimeResult(
            output=CoachOutput(
                question=QUESTION,
                coaching_stage=CoachingStage.GOAL,
                candidate_memories=tuple(
                    CandidateRecord(
                        candidate_id=f"m{index}",
                        kind=RecordKind.MEMORY,
                        value=value,
                        source_turn_id="t1",
                    )
                    for index, value in enumerate(self.memories)
                ),
            ),
            attempts=1,
            usage=UsageAccounting(input_tokens=1, output_tokens=1),
        )


class StubCommitments:
    """Proposes commitments, as the model does at every stage."""

    def __init__(self, *actions: str) -> None:
        self.actions = actions

    def generate(self, request: RuntimeRequest, *, sink=None) -> ValidatedRuntimeResult:
        return ValidatedRuntimeResult(
            output=CoachOutput(
                question=QUESTION,
                coaching_stage=CoachingStage.WILL,
                candidate_commitments=tuple(
                    CandidateRecord(
                        candidate_id=f"cm{index}",
                        kind=RecordKind.COMMITMENT,
                        value=value,
                        source_turn_id="t1",
                    )
                    for index, value in enumerate(self.actions)
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


def turn(database: CoachDatabase, adapter: StubAdapter, *, turn_id: str) -> None:
    persisted = CoachingTurnService(
        database, profile_id=PROFILE, adapter=adapter
    ).run(
        session_id=SESSION,
        turn_id=turn_id,
        goal_id=None,
        user_message="Tôi đang nghĩ",
        now=NOW,
    )
    with database.transaction():
        persisted.apply(database.connection)


def values(database: CoachDatabase) -> list[str]:
    return [
        json.loads(row["payload_json"])["content"]
        for row in database.connection.execute(
            "SELECT payload_json FROM candidate_record ORDER BY created_at, id"
        )
    ]


def test_the_same_memory_offered_every_turn_is_stored_once(
    database: CoachDatabase,
) -> None:
    """The observed failure, at the scale it was observed."""
    for index in range(10):
        turn(database, StubAdapter(MEMORY), turn_id=f"t{index}")
    assert values(database) == [MEMORY]


def test_one_turn_that_repeats_itself_still_writes_once(
    database: CoachDatabase,
) -> None:
    turn(database, StubAdapter(MEMORY, MEMORY), turn_id="t1")
    assert values(database) == [MEMORY]


def test_a_genuinely_new_candidate_is_never_dropped(
    database: CoachDatabase,
) -> None:
    """The negative test must not be passing because nothing gets through."""
    turn(database, StubAdapter(MEMORY), turn_id="t1")
    turn(database, StubAdapter(MEMORY, "Coachee làm việc tốt nhất vào buổi sáng"), turn_id="t2")
    assert values(database) == [MEMORY, "Coachee làm việc tốt nhất vào buổi sáng"]


def test_rewording_that_is_only_punctuation_counts_as_the_same(
    database: CoachDatabase,
) -> None:
    """The model rewrites the same thought with a different comma every turn."""
    turn(database, StubAdapter(MEMORY), turn_id="t1")
    turn(database, StubAdapter(f"  {MEMORY.upper()}.  "), turn_id="t2")
    assert len(values(database)) == 1


def test_a_discarded_candidate_does_not_come_back(database: CoachDatabase) -> None:
    """Re-proposing it would override a decision the Coachee already made."""
    turn(database, StubAdapter(MEMORY), turn_id="t1")
    with database.transaction():
        database.connection.execute(
            "UPDATE candidate_record SET status = 'discarded', resolved_at = ?", (NOW,)
        )
    turn(database, StubAdapter(MEMORY), turn_id="t2")
    assert len(values(database)) == 1
    assert CandidateRepository(database.connection).list_pending(SESSION) == ()


def test_a_confirmed_candidate_does_not_come_back(database: CoachDatabase) -> None:
    """They already have the record; offering it again is not a second choice."""
    turn(database, StubAdapter(MEMORY), turn_id="t1")
    with database.transaction():
        database.connection.execute(
            "UPDATE candidate_record SET status = 'confirmed', resolved_at = ?", (NOW,)
        )
    turn(database, StubAdapter(MEMORY), turn_id="t2")
    assert len(values(database)) == 1


def test_another_session_is_not_deduplicated_against(database: CoachDatabase) -> None:
    """Scope is the session. A new session is a new conversation, and a thought
    worth keeping may well surface again in it."""
    turn(database, StubAdapter(MEMORY), turn_id="t1")
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coaching_session (id, started_at, coaching_stage) "
            "VALUES ('session-2', ?, 'goal')",
            (NOW,),
        )
    persisted = CoachingTurnService(
        database, profile_id=PROFILE, adapter=StubAdapter(MEMORY)
    ).run(
        session_id="session-2",
        turn_id="t9",
        goal_id=None,
        user_message="Tôi đang nghĩ",
        now=NOW,
    )
    with database.transaction():
        persisted.apply(database.connection)
    assert len(values(database)) == 2


class TestTheKeyItself:
    def test_kind_separates_otherwise_identical_text(self) -> None:
        """A goal and a memory that read alike are two different records."""
        assert candidate_key("goal", "Đổi việc") != candidate_key("memory", "Đổi việc")

    def test_case_and_spacing_do_not_make_a_new_candidate(self) -> None:
        assert candidate_key("memory", "Đổi  việc") == candidate_key(
            "memory", "đổi việc"
        )

    def test_different_words_stay_different(self) -> None:
        """Near-duplicate matching would silently drop something new."""
        assert candidate_key("memory", "Đổi việc trước tháng 6") != candidate_key(
            "memory", "Đổi việc trước tháng 7"
        )


class TestTheModelIsToldWhatItAlreadySaid:
    """Exact matching is the floor, not the fix.

    The server drops a repeat only when the string matches. The model
    paraphrases: in a nine-turn live session, four of five candidates were the
    same idea in different words, and every one of them was a legitimately new
    string. No comparison in the server catches that — only the model can, and
    it cannot unless something tells it what it already proposed.
    """

    def test_the_prompt_carries_what_the_session_already_offered(
        self, database: CoachDatabase
    ) -> None:
        turn(database, StubAdapter(MEMORY), turn_id="t1")
        adapter = StubAdapter("điều gì đó khác")
        turn(database, adapter, turn_id="t2")
        assert adapter.calls[0].structured_context["already_proposed"] == [MEMORY]

    def test_the_first_turn_carries_an_empty_list_not_a_missing_key(
        self, database: CoachDatabase
    ) -> None:
        """A missing key reads as "unknown"; an empty list says "nothing yet"."""
        adapter = StubAdapter(MEMORY)
        turn(database, adapter, turn_id="t1")
        assert adapter.calls[0].structured_context["already_proposed"] == []

    def test_a_discarded_candidate_is_still_named_as_already_offered(
        self, database: CoachDatabase
    ) -> None:
        """Otherwise the model re-raises what the Coachee just turned down."""
        turn(database, StubAdapter(MEMORY), turn_id="t1")
        with database.transaction():
            database.connection.execute(
                "UPDATE candidate_record SET status = 'discarded', resolved_at = ?",
                (NOW,),
            )
        adapter = StubAdapter("điều gì đó khác")
        turn(database, adapter, turn_id="t2")
        assert adapter.calls[0].structured_context["already_proposed"] == [MEMORY]

    def test_the_list_is_capped_so_the_prompt_cannot_grow_without_limit(
        self, database: CoachDatabase
    ) -> None:
        for index in range(25):
            turn(database, StubAdapter(f"ghi nhớ số {index}"), turn_id=f"t{index}")
        adapter = StubAdapter("mới hoàn toàn")
        turn(database, adapter, turn_id="t99")
        proposed = adapter.calls[0].structured_context["already_proposed"]
        assert len(proposed) == 20
        # Newest kept: the cap must drop the oldest, not the most relevant.
        assert proposed[-1] == "ghi nhớ số 24"

    def test_the_contract_tells_the_model_to_read_it(self) -> None:
        """A field the prompt never mentions is a field the model ignores."""
        assert "already_proposed" in OUTPUT_CONTRACT


class TestAPromiseBelongsToWill:
    """The option the Coachee rejected, offered back as their commitment.

    From the first end-to-end run. At Options the Coachee listed three ways to
    start running and said plainly "I choose one and three". The session ended
    with five pending commitments — one of them the option they had just turned
    down, waiting for a click to become their official promise.

    Neither existing guard could catch it. Every string genuinely differed, so
    dedup saw nothing; the model was recombining rather than repeating, so
    `already_proposed` saw nothing either. No string comparison tells a
    possibility from a promise. The stage does.
    """

    def commitment_turn(self, database: CoachDatabase, *, stage: str, turn_id: str):
        with database.transaction():
            database.connection.execute(
                "UPDATE coaching_session SET coaching_stage = ? WHERE id = ?",
                (stage, SESSION),
            )
        adapter = StubCommitments("Tôi sẽ hẹn chạy với anh hàng xóm")
        persisted = CoachingTurnService(
            database, profile_id=PROFILE, adapter=adapter
        ).run(
            session_id=SESSION,
            turn_id=turn_id,
            goal_id=None,
            user_message="Tôi đang cân nhắc",
            now=NOW,
        )
        with database.transaction():
            persisted.apply(database.connection)

    def stored(self, database: CoachDatabase) -> int:
        return database.connection.execute(
            "SELECT COUNT(*) AS n FROM candidate_record WHERE record_type = 'commitment'"
        ).fetchone()["n"]

    @pytest.mark.parametrize("stage", ["pre_coaching", "goal", "reality", "options"])
    def test_an_option_being_weighed_is_not_captured_as_a_promise(
        self, database: CoachDatabase, stage: str
    ) -> None:
        self.commitment_turn(database, stage=stage, turn_id=f"t-{stage}")
        assert self.stored(database) == 0

    @pytest.mark.parametrize("stage", ["will", "review"])
    def test_a_promise_made_where_promises_are_made_is_kept(
        self, database: CoachDatabase, stage: str
    ) -> None:
        """The rule must not simply refuse commitments everywhere."""
        self.commitment_turn(database, stage=stage, turn_id=f"t-{stage}")
        assert self.stored(database) == 1

    def test_other_kinds_are_untouched_by_the_rule(
        self, database: CoachDatabase
    ) -> None:
        """An insight at Reality is exactly where insights come from."""
        turn(database, StubAdapter(MEMORY), turn_id="t1")
        assert len(values(database)) == 1
