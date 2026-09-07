"""Minimum eligible context for one model call.

Requirement families: `HC-MEMORY`, `HC-PRIVACY`; sources `SRC-011`, `SRC-036`,
`SRC-070`, `SRC-072`, `SRC-091`.

This is the last gate before data leaves the machine, so it applies two
independent filters. The repositories already exclude Trash, expired and
unconfirmed rows; on top of that, every item must sit in a scope whose consent
currently stands. Consent is re-read here rather than trusted from an earlier
turn, because a withdrawal must take effect on the very next request.

Relevance is deliberately narrow: the active goal, that goal's insights, this
session's live transcript, and approved memory. Having data is not a reason to
send it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hermes_coach.application.consent_service import ConsentDecision, ConsentService
from hermes_coach.contracts.egress_contract import (
    EgressCategory,
    EgressItemRef,
    EgressRequirement,
)
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
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


EGRESS_CONSENT_TYPE = "model_egress"


@dataclass(frozen=True)
class ContextSelection:
    purpose: str
    goals: tuple[GoalRow, ...] = ()
    insights: tuple[InsightRow, ...] = ()
    memories: tuple[MemoryItemRow, ...] = ()
    provenance: tuple[MemoryProvenanceRow, ...] = ()
    messages: tuple[SessionMessageRow, ...] = ()
    item_refs: tuple[EgressItemRef, ...] = field(default_factory=tuple)
    categories: tuple[EgressCategory, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not self.item_refs


class ContextSelector:
    def __init__(self, database: CoachDatabase, *, profile_id: str) -> None:
        self._database = database
        self._profile_id = profile_id

    def select(
        self, *, session_id: str, goal_id: str | None, purpose: str, now: str
    ) -> ContextSelection:
        connection = self._database.connection
        consent = ConsentService(self._database, profile_id=self._profile_id)

        # The empty scope is the profile-wide grant. It is the only consent the
        # product actually collects — one control, "Gửi nội dung phiên tới mô
        # hình" — and it covers the transcript, approved memory, and the goal
        # the session is working on.
        profile_allowed = consent.is_granted(EGRESS_CONSENT_TYPE, {})

        # A goal scope is a narrowing layer on top of that, not a second key.
        #
        # It used to be a separate grant that had to be given before a goal
        # could travel. Nothing in the product ever gave it: there is no
        # per-goal consent control, so `is_granted` was always False and the
        # model never once received the Coachee's goal or its insights. The
        # Coach was asking questions about a goal it could not see, and every
        # test that said otherwise granted the scope by hand in a fixture.
        #
        # So the profile grant carries the goal, and a per-goal WITHDRAWN
        # decision — which a future Privacy Center control can record — takes
        # that one goal back out without touching the rest. Absence of a goal
        # decision means "not narrowed", never "not permitted".
        goal_scope = {"goal_id": goal_id} if goal_id else None
        goal_allowed = (
            profile_allowed
            and goal_id is not None
            and consent.effective(EGRESS_CONSENT_TYPE, goal_scope)
            is not ConsentDecision.WITHDRAWN
        )

        goals: tuple[GoalRow, ...] = ()
        insights: tuple[InsightRow, ...] = ()
        if goal_allowed and goal_id:
            goal = GoalRepository(connection).get(goal_id)
            goals = (goal,) if goal else ()
            insights = InsightRepository(connection).list_for_goal(goal_id)

        memories: tuple[MemoryItemRow, ...] = ()
        provenance: tuple[MemoryProvenanceRow, ...] = ()
        messages: tuple[SessionMessageRow, ...] = ()
        if profile_allowed:
            memory_repository = MemoryRepository(connection)
            memories = memory_repository.list_active(now=now)
            provenance = tuple(
                row
                for memory in memories
                for row in memory_repository.provenance_for(memory.id)
            )
            messages = SessionMessageRepository(connection).list_active(
                session_id, now=now
            )

        item_refs = (
            *self._refs(goals, EgressCategory.SELECTED_PROFILE),
            *self._refs(insights, EgressCategory.SELECTED_PROFILE),
            *self._refs(memories, EgressCategory.SELECTED_MEMORY),
            *self._refs(messages, EgressCategory.CURRENT_TURN),
        )
        categories = tuple(dict.fromkeys(ref.category for ref in item_refs))

        return ContextSelection(
            purpose=purpose,
            goals=goals,
            insights=insights,
            memories=memories,
            provenance=provenance,
            messages=messages,
            item_refs=item_refs,
            categories=categories,
        )

    @staticmethod
    def _refs(rows, category: EgressCategory) -> tuple[EgressItemRef, ...]:
        return tuple(
            EgressItemRef(
                local_id=row.id,
                category=category,
                requirement=EgressRequirement.REQUIRED,
            )
            for row in rows
        )
