"""One coaching turn: consent, context, model call, persistence.

Requirement families: `HC-PRODUCT`, `HC-PRIVACY`, `HC-RECORDS`; sources
`SRC-026`, `SRC-070…075`, `SRC-079`, `SRC-091`, `SRC-104…106`.

Deliberately two phases.

Phase one runs with no write lock held: check consent, select the eligible
context, call the model. A provider call takes seconds, and holding a SQLite
write lock across it would stall every other write in the app.

Phase two is a single transaction the caller applies: transcript, candidates and
the gate event land together, or none of them do. The service hands that work
back as `Persisted` rather than committing it, so the RPC envelope can put these
rows and its own revision/idempotency bookkeeping in the same transaction.

The six-step gate lives here because a turn is the only thing that can move it.
A step closes when the Coach asked a yes/no closing question and the Coachee's
very next message is an explicit yes — the same adjacency the pure state machine
in `domain.transitions` requires, evaluated against the transcript rather than an
in-memory ledger. The classification itself is not reimplemented: it is
`classify_gate_answer`, so the wire and the domain cannot drift on what counts
as a yes.

What this does NOT yet enforce: the pure model also refuses to open a gate on an
incomplete stage (`stage_is_complete`), and that check needs the per-stage
snapshots, which nothing persists yet. Until they exist, completeness is the
Coach model's judgement — it is instructed not to close an unfinished step —
while the explicit yes is the database's. That is weaker than the design and is
written down rather than hidden.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from hermes_coach.application.consent_service import ConsentService
from hermes_coach.application.safety_service import (
    route_safety,
    safety_system_message,
)
from hermes_coach.application.context_selector import (
    EGRESS_CONSENT_TYPE,
    ContextSelector,
)
from hermes_coach.application.retention_service import TEMPORARY_DATA_WINDOW
from hermes_coach.contracts.runtime_contract import (
    CandidateRecord,
    CoachingStage,
    CoachOutput,
    GateAnswer,
    RuntimeRequest,
    stable_prompt_fingerprint,
)
from hermes_coach.domain.clock import shift
from hermes_coach.domain.enums import SafetyState
from hermes_coach.domain.records import (
    CandidateRecordRow,
    GateConfirmationRow,
    SessionMessageRow,
)
from hermes_coach.domain.session_state import STAGE_ORDER
from hermes_coach.domain.stage_completeness import missing_for
from hermes_coach.domain.transitions import classify_gate_answer
from hermes_coach.infrastructure.repositories.candidate_repository import (
    CandidateRepository,
)
from hermes_coach.infrastructure.repositories.coaching_session_repository import (
    CoachingSessionRepository,
)
from hermes_coach.infrastructure.repositories.gate_repository import GateRepository
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.session_message_repository import (
    SessionMessageRepository,
)
from hermes_coach.policies.question_policy import is_yes_no_closing_question
from hermes_coach.policies.safety_policy import escalate
from hermes_coach.infrastructure.sqlite.database import CoachDatabase
from hermes_coach.prompt.system_prompt import COACH_SYSTEM_PROMPT


DEFAULT_PROMPT_VERSION = "coach-1"

# How many already-proposed candidates travel in the prompt. Enough to stop
# the model repeating itself across a long session, bounded so a session that
# proposes a lot does not grow its own prompt without limit.
_PROPOSED_IN_PROMPT = 20

# The payload field the confirmation service reads when it promotes a candidate
# into an official record.
#
# `DurableConfirmationService._write_official_record` asks a goal for `title`, an
# insight and a memory for `content`, and a commitment for `action_text`. This
# module used to write every candidate under `value`, so no candidate could ever
# be confirmed: pressing Lưu answered `candidate payload has no title`. Nothing
# caught it because until the runtime told the model to emit candidates, there
# was never one to confirm — the two halves were written months apart against
# different payload shapes and never met.
PAYLOAD_FIELD: dict[str, str] = {
    "goal": "title",
    "insight": "content",
    "commitment": "action_text",
    "memory": "content",
}


def _is_worth_keeping(value: Any) -> bool:
    """Whether a snapshot value says anything. Mirrors `stage_completeness`.

    Kept as its own small function rather than imported so the merge rule and
    the completeness rule can be read side by side; a test pins them together.
    """
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def candidate_key(record_type: str, value: str) -> tuple[str, str]:
    """What makes two candidates the same proposal.

    Compared case-insensitively with whitespace collapsed and trailing
    punctuation dropped, because the model rewrites the same thought with a
    different comma every turn. Beyond that the match is exact: near-duplicate
    detection would silently drop a candidate that was genuinely new, and a
    candidate the Coachee never sees is worse than one they see twice.
    """
    normalized = " ".join(value.split()).casefold().strip(" .!?,;:")
    return (record_type, normalized)


def _payload_value(row: Any) -> str:
    """The stored candidate's text, whichever field its kind keeps it under."""
    try:
        payload = json.loads(row.payload_json)
    except (TypeError, ValueError):
        return ""
    field = PAYLOAD_FIELD.get(str(row.record_type), "value")
    value = payload.get(field) or payload.get("value") or ""
    return value if isinstance(value, str) else ""


# The steps in which a promise can exist.
#
# Found in the first end-to-end run: at Options the Coachee listed three ways to
# start running, said plainly "I choose one and three" — and the session ended
# with five pending commitments, one of them the option they had just rejected.
# It sat there waiting for a click to become their official promise.
#
# Dedup could not catch it (every string genuinely differed) and
# `already_proposed` could not either (the model was not repeating, it was
# recombining). No string comparison distinguishes a possibility from a promise.
# The stage does: at Options a Coachee is weighing, at Will they are deciding.
#
# A commitment stated early is not lost — the framework brings the Coachee back
# to it at Will, and they will say it again when it is a decision rather than a
# candidate. Capturing a rejected option as a promise is the worse error, and it
# is the one with no undo: the product's whole privacy story rests on the
# Coachee confirming each record, and a list containing what they turned down
# turns that confirmation from ownership into a trap.
COMMITMENT_STAGES = frozenset({CoachingStage.WILL, CoachingStage.REVIEW})

# Which candidate array on the output maps to which stored record type.
_CANDIDATE_FIELDS = (
    ("candidate_goals", "goal"),
    ("candidate_insights", "insight"),
    ("candidate_commitments", "commitment"),
    ("candidate_memories", "memory"),
)


class UnknownSession(LookupError):
    """The turn names a session that does not exist."""


class SafetyInterrupted(RuntimeError):
    """The session's safety state has taken coaching off the table.

    Raised before the model is called, so a session already in possible_crisis
    or urgent costs no tokens and produces no further coaching question. The
    Coachee is not coached back down out of a state they were interrupted in;
    `transition_safety_state` requires a distinct new Pre-Coaching session for
    that, and this refusal is what makes the requirement real.
    """


class SessionEnded(RuntimeError):
    """The session already closed at Review; it takes no further turns.

    Without this a closed session keeps answering, and the Review the Coachee
    confirmed stops being the end of anything.
    """


@dataclass(frozen=True)
class GateResolution:
    """What the incoming message did to the closing gate, if one was open.

    `answer is None` means no gate was open, which is the ordinary case: most
    turns are inside a step, not at its edge.
    """

    answered_stage: CoachingStage
    stage_for_turn: CoachingStage
    answer: GateAnswer | None = None
    #: The Coachee gave an unmistakable yes, but there was no closing question
    #: for it to answer. Nothing is wrong and nothing was lost — but from where
    #: they sit, they agreed and the step did not move, and saying nothing about
    #: that is the product's fault, not theirs.
    unmatched_yes: bool = False
    question_message_id: str | None = None
    revision: int = 0
    advanced: bool = False
    ends_session: bool = False


@dataclass(frozen=True)
class Persisted:
    """A result plus the write that must accompany it.

    `apply` runs inside the caller's transaction. Returning it instead of
    committing lets one transaction cover both this write and the RPC
    envelope's revision and idempotency rows.
    """

    result: Any
    apply: Callable[[sqlite3.Connection], None]


class CoachingTurnService:
    def __init__(
        self,
        database: CoachDatabase,
        *,
        profile_id: str,
        adapter: Any,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
    ) -> None:
        self._database = database
        self._profile_id = profile_id
        self._adapter = adapter
        self._prompt_version = prompt_version

    def run(
        self,
        *,
        session_id: str,
        turn_id: str,
        goal_id: str | None,
        user_message: str,
        now: str,
        cancellations: Any | None = None,
    ) -> Persisted:
        connection = self._database.connection
        session = CoachingSessionRepository(connection).get(session_id)
        if session is None:
            raise UnknownSession(f"no such session: {session_id}")
        if session.ended_at:
            raise SessionEnded(f"session already closed: {session_id}")

        # Consent first: a withdrawn scope must cost no tokens and leave no
        # transcript, so this runs before the context is even assembled.
        #
        # The scope required is the profile-wide grant, always, whatever goal the
        # session is about. What a turn sends is this session's transcript, and
        # `ContextSelector` — the authority on the layering — says in its own
        # words that the empty scope is what covers the transcript and memory,
        # while a goal scope is an additional grant over that goal's data.
        #
        # This used to check the goal scope *instead* whenever a goal was named,
        # which was wrong in both directions. A Coachee who withdrew profile-wide
        # consent but still had one goal granted kept having their transcript
        # sent. And naming a goal was refused outright without per-goal consent,
        # so no client ever named one — which is why a commitment candidate had
        # no goal to point at and could never be confirmed.
        #
        # Withdrawing a goal's scope no longer stops the session. It stops that
        # goal's data reaching the model, which is what `ContextSelector` already
        # enforces and what the scope was for.
        consent = ConsentService(self._database, profile_id=self._profile_id)
        consent.require_granted(EGRESS_CONSENT_TYPE, {})

        # Safety before anything else, including consent: a session that is
        # already interrupted must not reach the model at all. This is the check
        # that was missing — `SafetyService` existed, was tested, and nothing
        # called it, so `safety_state` stayed `normal` for the life of every
        # session and the interruption the system prompt promises never happened.
        entry_state = SafetyState(session.safety_state or SafetyState.NORMAL.value)
        if route_safety(entry_state).coaching_interrupted:
            raise SafetyInterrupted(
                f"coaching is interrupted by safety state {entry_state.value}"
            )

        stage = CoachingStage(session.coaching_stage)

        # The gate is resolved before the model is asked anything, because its
        # answer decides which step the Coach must work in: a Coachee who just
        # said yes is owed the next step's opening question, not another one
        # about the step they closed.
        gate = self._resolve_gate(
            connection, session_id=session_id, stage=stage, user_message=user_message
        )

        # No client has ever named a goal, so the server names it.
        #
        # `goal_id` reached this method as None on every real turn: the browser
        # does not send one, and until now sending one would have been refused
        # for want of a per-goal consent grant that no control issues. The
        # result was a Coach with no idea what it was coaching towards, and
        # commitment candidates with no goal to attach to — which is why a
        # commitment could be proposed but never confirmed.
        #
        # Resolved here rather than in the browser because which goal a session
        # is about is the server's judgement, like the stage and the gates.
        if goal_id is None:
            goal_id = self._goal_for_session(connection, session_id)

        selection = ContextSelector(self._database, profile_id=self._profile_id).select(
            session_id=session_id, goal_id=goal_id, purpose="coaching_turn", now=now
        )

        request = RuntimeRequest(
            session_id=session_id,
            turn_id=turn_id,
            prompt_version=self._prompt_version,
            system_prompt_hash=stable_prompt_fingerprint(COACH_SYSTEM_PROMPT),
            current_stage=gate.stage_for_turn,
            user_message=user_message,
            structured_context=self._describe(
                selection,
                already_proposed=self._proposed_so_far(connection, session_id),
            ),
        )

        # Two cancellation points around the slow part: before, so a cancel that
        # arrived while the context was being assembled costs no tokens; after,
        # so one that arrived during the call is honoured instead of persisting
        # an answer the Coachee already dismissed.
        if cancellations is not None:
            cancellations.raise_if_cancelled(session_id, turn_id)

        # No write lock is held here. A rejected turn raises out of this call
        # and nothing below runs, so nothing is written.
        outcome = self._adapter.generate(request)
        output = outcome.output

        if cancellations is not None:
            cancellations.raise_if_cancelled(session_id, turn_id)

        # The model's own reading of this turn, escalated into the session's
        # state. Never lowered: see `escalate`.
        safety_state = escalate(entry_state, output.safety_signal)
        route = route_safety(safety_state)
        replacement = safety_system_message(route)

        # Candidates are temporary; the transcript is not.
        #
        # The transcript used to carry the same 90-day expiry, which meant a
        # Coachee's own words were deleted from under them while the
        # conclusions drawn from those words stayed forever. That is backwards:
        # the record says "you decided X", and the only thing that could ever
        # show *why* was the conversation.
        #
        # Kept because the Coachee asked for it kept, and because it costs them
        # nothing they did not already accept: this is their own machine, the
        # disclosure already says the file is unencrypted, and the Trash and
        # Privacy Center give them a way to remove any of it deliberately. The
        # lifecycle contract's retention rules cover confirmed memory, pending
        # candidates and Trash entries — transcript was never one of them, so
        # nothing stated is being broken here.
        expires_at = shift(now, TEMPORARY_DATA_WINDOW)
        transcript_expires_at = None
        first_sequence = SessionMessageRepository(connection).next_sequence(session_id)

        def apply(active: sqlite3.Connection) -> None:
            self._write_turn(
                active,
                session_id=session_id,
                turn_id=turn_id,
                goal_id=goal_id,
                # The Coachee's message is filed under the step they were
                # answering in, not the one their yes opened.
                stage=gate.answered_stage,
                user_message=user_message,
                output=output,
                first_sequence=first_sequence,
                now=now,
                expires_at=expires_at,
                transcript_expires_at=transcript_expires_at,
                safety_state=safety_state,
                replacement=replacement,
            )
            # After the transcript, never before: the event points at the two
            # messages that are its evidence, and they must exist first.
            #
            # Skipped entirely when safety took over: a turn the Coach never
            # answered cannot have closed a step.
            if replacement is None:
                self._write_gate(
                    active, gate=gate, session_id=session_id, turn_id=turn_id, now=now
                )
            if safety_state is not entry_state:
                CoachingSessionRepository(active).set_safety_state(
                    session_id, safety_state.value
                )

        return Persisted(
            result=self._render(
                output,
                outcome,
                gate,
                route,
                replacement,
                # From the step as a whole, not this turn alone. Reading only
                # the incoming snapshot reported three Pre-Coaching fields as
                # missing one turn after they had been answered, because the
                # model was reporting what changed rather than restating
                # everything each time.
                stage_gaps=list(
                    missing_for(
                        gate.answered_stage,
                        self._merge_snapshot(
                            connection,
                            session_id,
                            gate.answered_stage,
                            output.stage_snapshot,
                        ),
                    )
                ),
            ),
            apply=apply,
        )

    def _resolve_gate(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        stage: CoachingStage,
        user_message: str,
    ) -> GateResolution:
        """Read the transcript tail and decide whether this message closes a step.

        Adjacency is the whole rule. A gate counts only when the Coach's closing
        question is the last thing said and this message is the reply to it, so a
        yes cannot be harvested from somewhere earlier in the conversation, and a
        Coachee who answers something else in between has to be asked again.
        """
        messages = SessionMessageRepository(connection).list_active(session_id)
        tail = messages[-1] if messages else None

        # A plain yes with nothing open is the failure that has no error.
        #
        # Twice in one live session the Coach closed with a phrasing the
        # predicate does not accept — "…sẵn sàng kết thúc phiên này chứ?" and an
        # either/or — and the Coachee answered "Đồng ý" to silence. No message,
        # no step moving, nothing to tell them the words were fine and the
        # question was not. A person would conclude the app is broken.
        said_yes = classify_gate_answer(user_message) is GateAnswer.YES

        if tail is None or tail.role != "coach":
            return GateResolution(
                answered_stage=stage, stage_for_turn=stage, unmatched_yes=said_yes
            )
        if not is_yes_no_closing_question(tail.content):
            return GateResolution(
                answered_stage=stage, stage_for_turn=stage, unmatched_yes=said_yes
            )

        # The domain owns what a yes is. Re-deriving it here is how the wire and
        # the state machine would start disagreeing.
        answer = classify_gate_answer(user_message)
        advanced = answer is GateAnswer.YES
        ends_session = advanced and stage is CoachingStage.REVIEW
        following = (
            STAGE_ORDER[STAGE_ORDER.index(stage) + 1]
            if advanced and not ends_session
            else stage
        )
        return GateResolution(
            answered_stage=stage,
            stage_for_turn=following,
            answer=answer,
            question_message_id=tail.id,
            revision=GateRepository(connection).next_revision(session_id, stage.value),
            advanced=advanced,
            ends_session=ends_session,
        )

    @staticmethod
    def _write_gate(
        connection: sqlite3.Connection,
        *,
        gate: GateResolution,
        session_id: str,
        turn_id: str,
        now: str,
    ) -> None:
        """Record the answer, then move the session if it was a yes.

        A `no` and an `unclear` are written too. They cost one row and they are
        the difference between "this step was never confirmed" and "this step was
        offered and the Coachee declined it", which is exactly what an audit of a
        coaching record needs to be able to tell apart.
        """
        if gate.answer is None:
            return
        GateRepository(connection).append(
            GateConfirmationRow(
                id=f"{turn_id}-gate",
                session_id=session_id,
                step=gate.answered_stage.value,
                revision=gate.revision,
                result=gate.answer.value,
                closing_question_message_id=gate.question_message_id,
                response_message_id=f"{turn_id}-coachee",
                confirmed_at=now if gate.advanced else None,
            )
        )
        if not gate.advanced:
            return
        sessions = CoachingSessionRepository(connection)
        if gate.ends_session:
            # Review is the last step: its yes closes the session rather than
            # advancing to a seventh one that does not exist.
            sessions.close(session_id, now)
            return
        sessions.set_stage(session_id, gate.stage_for_turn.value)

    @staticmethod
    def _stored_snapshot(
        connection: sqlite3.Connection, session_id: str, stage: CoachingStage
    ) -> dict[str, Any]:
        row = connection.execute(
            "SELECT payload_json FROM stage_snapshot "
            "WHERE session_id = :session_id AND stage = :stage",
            {"session_id": session_id, "stage": stage.value},
        ).fetchone()
        if row is None:
            return {}
        try:
            stored = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            return {}
        return stored if isinstance(stored, dict) else {}

    @classmethod
    def _merge_snapshot(
        cls,
        connection: sqlite3.Connection,
        session_id: str,
        stage: CoachingStage,
        incoming: Mapping[str, Any],
    ) -> dict[str, Any]:
        """What the step knows now, given what it knew and what this turn added.

        A key the model omitted keeps whatever was there. A key it sent with an
        empty value is treated the same way — the prompt tells it to leave a
        field out rather than fill it with something hollow, and honouring an
        empty string as an erasure would punish it for following that.
        """
        merged = cls._stored_snapshot(connection, session_id, stage)
        for key, value in (incoming or {}).items():
            if _is_worth_keeping(value):
                merged[key] = value
        return merged

    def _goal_for_session(self, connection, session_id: str) -> str | None:
        """The goal this session is about, or None when that is genuinely unclear.

        A goal this session created wins outright. Failing that, a profile with
        exactly one active goal has no ambiguity to resolve. With several and no
        link to this session, the server declines to guess: sending the wrong
        goal's history into a coaching question is worse than sending none.
        """
        active = GoalRepository(connection).list_active(self._profile_id)
        for goal in active:
            if goal.source_session_id == session_id:
                return goal.id
        return active[0].id if len(active) == 1 else None

    @staticmethod
    def _proposed_so_far(connection, session_id: str) -> list[str]:
        """What this session has already put in front of the Coachee.

        The model re-offered the same thought on nearly every turn of a real
        session, and it was not being careless: nothing ever told it what it had
        already offered. The server drops exact repeats, but the model rephrases
        — four of five candidates in one run were the same idea in different
        words — and no string comparison catches that. Only the model can.

        Capped because this rides in the prompt on every turn, and newest last
        so the cap drops the oldest rather than the most relevant.
        """
        rows = CandidateRepository(connection).list_for_session(session_id)
        values = [text for row in rows if (text := _payload_value(row))]
        return values[-_PROPOSED_IN_PROMPT:]

    @staticmethod
    def _describe(selection: Any, *, already_proposed: list[str]) -> dict[str, Any]:
        """Counts and ids only — the content travels in the request body."""
        return {
            "already_proposed": already_proposed,
            "goal_count": len(selection.goals),
            "insight_count": len(selection.insights),
            "memory_count": len(selection.memories),
            "message_count": len(selection.messages),
            "goal_titles": [goal.title for goal in selection.goals],
            "memories": [item.content for item in selection.memories],
        }

    def _write_turn(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        turn_id: str,
        goal_id: str | None,
        stage: CoachingStage,
        user_message: str,
        output: CoachOutput,
        first_sequence: int,
        now: str,
        expires_at: str,
        transcript_expires_at: str | None,
        safety_state: SafetyState,
        replacement: str | None,
    ) -> None:
        messages = SessionMessageRepository(connection)
        messages.add(
            SessionMessageRow(
                id=f"{turn_id}-coachee",
                session_id=session_id,
                sequence_no=first_sequence,
                role="coachee",
                content=user_message,
                coaching_stage=stage.value,
                safety_state=safety_state.value,
                created_at=now,
                expires_at=transcript_expires_at,
            )
        )
        # The reply the Coachee actually receives. When routing interrupted
        # coaching, the model's question is not it: it is never written and
        # never shown, and the Safety System speaks in its own voice and under
        # its own role so no reader can mistake one for the other.
        messages.add(
            SessionMessageRow(
                id=f"{turn_id}-coach",
                session_id=session_id,
                sequence_no=first_sequence + 1,
                role="safety_system" if replacement else "coach",
                content=replacement or output.question,
                coaching_stage=(
                    None if replacement else output.coaching_stage.value
                ),
                safety_state=safety_state.value,
                created_at=now,
                expires_at=transcript_expires_at,
            )
        )

        # The step's own content, accumulated across the turns that built it.
        #
        # Merged, never replaced. The model reports what *this* turn revealed,
        # so a wholesale overwrite made a step forget everything established two
        # turns earlier: a live run filled three of Pre-Coaching's four fields,
        # then dropped all three on the next answer. A step could only ever have
        # read as complete if the model happened to restate everything at once,
        # which is not how a conversation goes.
        #
        # An omitted key means "nothing new about this", not "retract it", so
        # only a value that is actually present overwrites. Retraction belongs
        # to rollback, which invalidates the gate rather than editing the
        # snapshot underneath it.
        merged = self._merge_snapshot(connection, session_id, stage, output.stage_snapshot)
        if merged:
            connection.execute(
                "INSERT INTO stage_snapshot "
                "(session_id, stage, payload_json, updated_at) "
                "VALUES (:session_id, :stage, :payload, :now) "
                "ON CONFLICT(session_id, stage) DO UPDATE SET "
                "payload_json = :payload, updated_at = :now",
                {
                    "session_id": session_id,
                    "stage": stage.value,
                    "payload": json.dumps(merged, ensure_ascii=False),
                    "now": now,
                },
            )

        # A turn the Coach never answered offers nothing to keep. Minting
        # records out of what someone said in crisis would be the product
        # harvesting the worst moment it just refused to coach through.
        if replacement:
            return

        # One proposal, once per session.
        #
        # The model re-offers what it already offered: a fifteen-turn session
        # produced twenty pending candidates, most of them the same memory
        # proposed again on nearly every turn. Each one is a row and a card the
        # Coachee has to read and dismiss, so the confirmation list — the
        # feature by which they own their own records — becomes the thing they
        # scroll past.
        #
        # Deduplicated against every candidate this session has raised, not
        # just the pending ones. Re-proposing something already declined
        # overrides a decision the Coachee made; re-proposing something already
        # confirmed offers them a record they already have.
        #
        # This runs inside the caller's transaction, so the read cannot miss a
        # write that is about to land beside it.
        candidates = CandidateRepository(connection)
        seen = {
            candidate_key(row.record_type, _payload_value(row))
            for row in candidates.list_for_session(session_id)
        }
        for field_name, record_type in _CANDIDATE_FIELDS:
            # A promise belongs to Will. Anything the model calls a commitment
            # before then is an option the Coachee is still turning over.
            if record_type == "commitment" and stage not in COMMITMENT_STAGES:
                continue
            for candidate in getattr(output, field_name):
                key = candidate_key(record_type, candidate.value)
                # `seen` grows as we go, so a turn that emits the same thought
                # twice writes it once.
                if key in seen:
                    continue
                seen.add(key)
                candidates.add(
                    self._candidate_row(
                        candidate,
                        record_type=record_type,
                        session_id=session_id,
                        turn_id=turn_id,
                        goal_id=goal_id,
                        now=now,
                        expires_at=expires_at,
                    )
                )

    @staticmethod
    def _candidate_row(
        candidate: CandidateRecord,
        *,
        record_type: str,
        session_id: str,
        turn_id: str,
        goal_id: str | None,
        now: str,
        expires_at: str,
    ) -> CandidateRecordRow:
        payload: dict[str, str] = {PAYLOAD_FIELD[record_type]: candidate.value}
        # A commitment is an action towards a goal, and `_write_official_record`
        # refuses one that cannot name it. The goal comes from the turn rather
        # than from the model: which goal a session is about is the Coachee's
        # choice, not something to infer from what they just said.
        if record_type == "commitment" and goal_id:
            payload["goal_id"] = goal_id
        return CandidateRecordRow(
            id=f"{turn_id}-{candidate.candidate_id}",
            session_id=session_id,
            record_type=record_type,  # type: ignore[arg-type]
            payload_json=json.dumps(payload, ensure_ascii=False),
            source_message_id=f"{turn_id}-coach",
            status="pending",
            created_at=now,
            # Pending candidates are temporary data on the 90-day clock.
            expires_at=expires_at,
        )

    @staticmethod
    def _render(
        output: CoachOutput,
        outcome: Any,
        gate: GateResolution,
        route: Any,
        replacement: str | None,
        stage_gaps: list[str],
    ) -> dict[str, Any]:
        return {
            # What the Coachee is shown. The model's question only when the
            # Safety System did not take the turn over.
            "question": replacement or output.question,
            "safety": {
                "state": route.state.value,
                "output_mode": route.output_mode.value,
                "coaching_interrupted": route.coaching_interrupted,
                # Said in the payload as well as in the message role, so a
                # client cannot render safety text as if the Coach said it.
                "voice": "safety_system" if replacement else "coach",
            },
            # The stage the server moved the session to, not the one the model
            # claimed. Only one of them is what the next turn will actually run
            # in, and it is this one.
            "coaching_stage": gate.stage_for_turn.value,
            "safety_signal": output.safety_signal.value,
            "attempts": outcome.attempts,
            "gate": (
                None
                if gate.answer is None
                else {
                    "step": gate.answered_stage.value,
                    "answer": gate.answer.value,
                    "advanced": gate.advanced,
                    "session_ended": gate.ends_session,
                }
            ),
            # Reported so the screen can say it. A Coachee who agreed and saw
            # nothing move needs to know the words were fine and there was
            # simply no question open — otherwise the only conclusion available
            # to them is that the product is broken.
            "unmatched_yes": gate.unmatched_yes,
            # What this step still has not covered, named.
            #
            # Reported, not enforced — see `_stage_gaps`. Making it visible is
            # what turns "the Coach wandered into the next step and nothing
            # objected" into something a Coachee can see happening.
            "stage_gaps": stage_gaps,
            "candidates": [
                {"id": candidate.candidate_id, "kind": candidate.kind.value,
                 "value": candidate.value}
                for field_name, _ in _CANDIDATE_FIELDS
                for candidate in getattr(output, field_name)
            ],
        }
