"""Context selection before model egress.

Requirement families: `HC-MEMORY`, `HC-PRIVACY`; sources `SRC-011`, `SRC-036`,
`SRC-070`, `SRC-072`, `SRC-091`.

The selector returns the minimum eligible confirmed material for the active
goal/session, plus its provenance. Expired, Trash, unconfirmed, withdrawn-scope
and unrelated records must never reach the manifest — this is the last gate
before data leaves the machine.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from hermes_coach.application.consent_service import ConsentService, UiConsentAction
from hermes_coach.application.context_selector import ContextSelector
from hermes_coach.application.trash_service import TrashService
from hermes_coach.contracts.egress_contract import EgressCategory
from hermes_coach.domain.records import (
    GoalRow,
    InsightRow,
    MemoryItemRow,
    MemoryProvenanceRow,
    SessionMessageRow,
)
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.insight_repository import (
    InsightRepository,
)
from hermes_coach.infrastructure.repositories.memory_repository import MemoryRepository
from hermes_coach.infrastructure.repositories.session_message_repository import (
    SessionMessageRepository,
)
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-01-01T00:00:00Z"
LATER = "2026-02-01T00:00:00Z"
PAST = "2025-12-01T00:00:00Z"

PROFILE = "profile-1"
SESSION = "session-1"
GOAL = "goal-1"
EGRESS = "model_egress"


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
                    title="Chuyển sang vai trò kiến trúc sư",
                    status="active",
                    source_session_id=SESSION,
                    confirmed_at=NOW,
                    created_at=NOW,
                )
            )
        grant(db, scope={"goal_id": GOAL})
        grant(db, event_id="consent-memory", scope={})
        yield db


def consent(database: CoachDatabase) -> ConsentService:
    return ConsentService(database, profile_id=PROFILE)


def grant(
    database: CoachDatabase,
    *,
    event_id: str = "consent-goal",
    scope: dict | None = None,
    at: str = NOW,
) -> None:
    consent(database).record(
        event_id=event_id,
        consent_type=EGRESS,
        scope=scope,
        ui_action=UiConsentAction.CONFIRM,
        control_id="btn-consent-confirm",
        now=at,
    )


def withdraw(
    database: CoachDatabase,
    *,
    event_id: str,
    scope: dict | None,
    at: str = LATER,
) -> None:
    consent(database).record(
        event_id=event_id,
        consent_type=EGRESS,
        scope=scope,
        ui_action=UiConsentAction.WITHDRAW,
        control_id="btn-consent-withdraw",
        now=at,
    )


def selector(database: CoachDatabase) -> ContextSelector:
    return ContextSelector(database, profile_id=PROFILE)


def select(database: CoachDatabase, *, now: str = NOW):
    return selector(database).select(
        session_id=SESSION, goal_id=GOAL, purpose="coaching_turn", now=now
    )


def add_memory(
    database: CoachDatabase,
    memory_id: str = "memory-1",
    *,
    confirmed: bool = True,
    with_provenance: bool = True,
) -> None:
    with database.transaction():
        memory = MemoryRepository(database.connection)
        memory.add(
            MemoryItemRow(
                id=memory_id,
                content="Coachee coi trọng quyền tự chủ",
                user_confirmed=confirmed,
            )
        )
        if with_provenance:
            memory.add_provenance(
                MemoryProvenanceRow(
                    id=f"provenance-of-{memory_id}",
                    memory_item_id=memory_id,
                    source_type="session",
                    source_id=SESSION,
                    source_session_id=SESSION,
                    relation="confirmed_from",
                    created_at=NOW,
                )
            )


def add_insight(
    database: CoachDatabase, insight_id: str = "insight-1", *, goal_id: str | None = GOAL
) -> None:
    with database.transaction():
        InsightRepository(database.connection).add(
            InsightRow(
                id=insight_id,
                content="Tôi né tránh xung đột",
                source_session_id=SESSION,
                goal_id=goal_id,
                confirmed_at=NOW,
            )
        )


def add_message(
    database: CoachDatabase,
    message_id: str = "message-1",
    *,
    sequence_no: int = 0,
    expires_at: str | None = LATER,
) -> None:
    with database.transaction():
        SessionMessageRepository(database.connection).add(
            SessionMessageRow(
                id=message_id,
                session_id=SESSION,
                sequence_no=sequence_no,
                role="coachee",
                content="Tôi muốn đổi vai trò",
                created_at=NOW,
                expires_at=expires_at,
            )
        )


def test_the_active_goal_is_selected(database: CoachDatabase) -> None:
    selection = select(database)
    assert [goal.id for goal in selection.goals] == [GOAL]


def test_confirmed_memory_is_selected_with_its_provenance(
    database: CoachDatabase,
) -> None:
    add_memory(database)
    selection = select(database)
    assert [memory.id for memory in selection.memories] == ["memory-1"]
    assert [row.id for row in selection.provenance] == ["provenance-of-memory-1"]


def test_unconfirmed_memory_never_reaches_the_selection(
    database: CoachDatabase,
) -> None:
    add_memory(database, "memory-candidate", confirmed=False, with_provenance=False)
    assert select(database).memories == ()


def test_trashed_memory_never_reaches_the_selection(
    database: CoachDatabase,
) -> None:
    add_memory(database)
    TrashService(database, profile_id=PROFILE).soft_delete(
        "memory_item", "memory-1", now=NOW
    )
    assert select(database).memories == ()


def test_expired_transcript_never_reaches_the_selection(
    database: CoachDatabase,
) -> None:
    add_message(database, "message-fresh", expires_at=LATER)
    add_message(database, "message-stale", sequence_no=1, expires_at=PAST)
    selection = select(database)
    assert [row.id for row in selection.messages] == ["message-fresh"]


def test_an_insight_for_another_goal_is_unrelated(database: CoachDatabase) -> None:
    add_insight(database, "insight-mine", goal_id=GOAL)
    with database.transaction():
        GoalRepository(database.connection).add(
            GoalRow(
                id="goal-2",
                profile_id=PROFILE,
                title="Mục tiêu khác",
                status="active",
                confirmed_at=NOW,
                created_at=NOW,
            )
        )
    add_insight(database, "insight-theirs", goal_id="goal-2")

    selection = select(database)
    assert [row.id for row in selection.insights] == ["insight-mine"]


def test_a_message_from_another_session_is_unrelated(
    database: CoachDatabase,
) -> None:
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coaching_session (id, started_at, coaching_stage) "
            "VALUES ('session-2', ?, 'goal')",
            (NOW,),
        )
        SessionMessageRepository(database.connection).add(
            SessionMessageRow(
                id="message-other",
                session_id="session-2",
                sequence_no=0,
                role="coachee",
                content="Phiên khác",
                created_at=NOW,
                expires_at=LATER,
            )
        )
    add_message(database, "message-mine")
    assert [row.id for row in select(database).messages] == ["message-mine"]


def test_withdrawing_goal_scope_drops_the_goal_from_the_selection(
    database: CoachDatabase,
) -> None:
    withdraw(database, event_id="withdraw-goal", scope={"goal_id": GOAL})
    selection = select(database, now=LATER)
    assert selection.goals == ()


def test_withdrawing_the_profile_scope_leaves_nothing_to_send(
    database: CoachDatabase,
) -> None:
    """The profile scope is the grant; a goal scope only ever narrows it.

    This used to assert that withdrawing the profile kept the goal, on the
    theory that the two scopes were independent keys. They are not, and the
    independence was doing harm in the other direction: because no control in
    the product ever recorded a per-goal grant, the goal was permanently
    excluded and the Coach never saw what it was coaching towards.

    Reading it the other way — the profile grant carries everything, a per-goal
    withdrawal takes one goal back out — makes the single consent control mean
    what it says, and makes withdrawal narrow rather than widen.
    """
    add_memory(database)
    withdraw(database, event_id="withdraw-memory", scope={})
    selection = select(database, now=LATER)
    assert selection.memories == ()
    assert selection.goals == ()
    assert selection.item_refs == ()


def test_a_goal_needs_no_grant_of_its_own(database: CoachDatabase) -> None:
    """The gap this rule closes, asserted directly.

    Nothing here records a per-goal decision. Under the old rule that alone
    kept the goal out of every request the product ever made.
    """
    with database.transaction():
        database.connection.execute(
            "DELETE FROM consent_event WHERE scope_json LIKE '%goal_id%'"
        )
    assert [goal.id for goal in select(database).goals] == [GOAL]


def test_no_consent_at_all_yields_nothing(tmp_path) -> None:
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
                    title="Mục tiêu",
                    status="active",
                    confirmed_at=NOW,
                    created_at=NOW,
                )
            )
        selection = select(database)
        assert selection.goals == ()
        assert selection.item_refs == ()


def test_item_refs_name_every_selected_item(database: CoachDatabase) -> None:
    add_memory(database)
    add_insight(database)
    add_message(database)
    selection = select(database)

    referenced = {ref.local_id for ref in selection.item_refs}
    selected = (
        {goal.id for goal in selection.goals}
        | {memory.id for memory in selection.memories}
        | {insight.id for insight in selection.insights}
        | {message.id for message in selection.messages}
    )
    assert referenced == selected


def test_item_refs_carry_no_content(database: CoachDatabase) -> None:
    """The manifest is metadata; content travels only in the request itself."""
    add_memory(database)
    selection = select(database)
    for ref in selection.item_refs:
        assert "Coachee coi trọng" not in repr(ref.model_dump())


def test_categories_describe_only_what_was_selected(
    database: CoachDatabase,
) -> None:
    add_memory(database)
    selection = select(database)
    assert EgressCategory.SELECTED_MEMORY in selection.categories
    assert EgressCategory.CANDIDATE_RECORD not in selection.categories


def test_an_empty_selection_has_no_categories(database: CoachDatabase) -> None:
    withdraw(database, event_id="withdraw-goal", scope={"goal_id": GOAL})
    withdraw(database, event_id="withdraw-memory", scope={})
    selection = select(database, now=LATER)
    assert selection.categories == ()
    assert selection.is_empty


def test_selection_is_read_only_and_writes_nothing(
    database: CoachDatabase,
) -> None:
    add_memory(database)
    before = database.connection.execute(
        "SELECT COUNT(*) AS total FROM memory_item"
    ).fetchone()["total"]
    select(database)
    after = database.connection.execute(
        "SELECT COUNT(*) AS total FROM memory_item"
    ).fetchone()["total"]
    assert before == after
