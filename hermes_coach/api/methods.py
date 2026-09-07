"""The Coach RPC surface.

Requirement families: `HC-PRODUCT`, `HC-UX`, `HC-PRIVACY`; sources
`SRC-062…069`, `SRC-104…106`.

Thin bindings only: every method resolves to an application service or a
repository that already enforces the rule. Nothing here re-derives active
scope, consent or gate state — a second implementation of those is how the two
drift apart.

Reads take no envelope. Mutations are registered `mutating=True`, so the
dispatcher requires session/revision/idempotency and commits the service's write
together with its own bookkeeping.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from hermes_coach.api.app import MethodRegistry, RpcError
from hermes_coach.application.coaching_turn_service import (
    CoachingTurnService,
    Persisted,
    SafetyInterrupted,
    SessionEnded,
    UnknownSession,
)
from hermes_coach.application.consent_service import (
    ConsentService,
    ConsentWithdrawn,
    UiConsentAction,
)
from hermes_coach.application.durable_confirmation_service import (
    ConfirmationRejected,
    DurableConfirmationService,
)
from hermes_coach.application.record_confirmation_service import (
    ConfirmationCommand,
    RecordAction,
)
from hermes_coach.application.session_recovery_service import SessionRecoveryService
from hermes_coach.bootstrap import disclosure
from hermes_coach.domain.records import CoachingSessionRow
from hermes_coach.infrastructure.repositories.candidate_repository import (
    CandidateRepository,
)
from hermes_coach.application.export_service import ExportService
from hermes_coach.application.journey_service import JourneyService
from hermes_coach.application.trash_service import (
    PurgeReason,
    RestoreBlocked,
    TrashService,
)
from hermes_coach.infrastructure.repositories.session_message_repository import (
    SessionMessageRepository,
)
from hermes_coach.infrastructure.repositories.trash_repository import (
    TrashRepository,
)
from hermes_coach.application.check_in_service import (
    CheckInAlreadyAnswered,
    CheckInService,
    UnknownCheckIn,
)
from hermes_coach.application.record_confirmation_service import (
    CheckInAction,
    CheckInChoiceCommand,
)
from hermes_coach.infrastructure.repositories.coaching_session_repository import (
    CoachingSessionRepository,
)
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.hermes_runtime_adapter import RuntimeRejected
from hermes_coach.infrastructure.repositories.insight_repository import (
    InsightRepository,
)
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


# Single user, single profile. A profile picker would be a multi-user feature.
DEFAULT_PROFILE_ID = "local"

# The one stage a session may start at.
INITIAL_STAGE = "pre_coaching"


def register_coach_methods(
    registry: MethodRegistry,
    database: CoachDatabase,
    *,
    adapter: Any | None,
    clock: Callable[[], str],
) -> None:
    """Bind the Coach methods onto `registry`.

    `adapter` may be None: a machine with no configured provider is a normal
    first-run state, and every read must keep working there.
    """
    ensure_profile(database, clock())

    registry.register("coach.today", lambda params: _today(database, clock()))
    registry.register(
        "coach.session.state", lambda params: _session_state(database, params)
    )
    registry.register("coach.insights", lambda params: _insights(database))
    # Two reads that make kept data reachable. Without the first, a reload
    # stranded whatever session the Coachee was in; without the second, the
    # transcript this product now promises to keep was kept somewhere nobody
    # could open — which is worse than deleting it, because it carries the
    # privacy cost of storage and returns none of its value.
    registry.register("coach.session.open", lambda params: _open_session(database))
    registry.register(
        "coach.session.transcript", lambda params: _transcript(database, params, clock())
    )
    registry.register(
        "coach.session.start",
        lambda params: _start_session(database, params, clock()),
        mutating=True,
    )
    registry.register(
        "coach.turn",
        lambda params: _turn(database, adapter, params, clock()),
        mutating=True,
        wants_cancellation=True,
    )

    # Confirmation is deliberately NOT wrapped in the RPC envelope.
    #
    # `DurableConfirmationService` already carries a stronger guarantee than the
    # envelope could: a single-use intent bound to user/session/candidate/
    # action/payload, a unique command id, and a compare-and-set on the
    # candidate row — all in one transaction. Adding `mutating=True` would open
    # a second transaction around one that already exists, and layer a weaker
    # replay check over a stronger one. The client refreshes session state after
    # confirming, which it must do anyway to see the new candidate list.
    registry.register(
        "coach.candidate.intent",
        lambda params: _mint_intent(database, params, clock()),
    )
    registry.register(
        "coach.candidate.confirm",
        lambda params: _confirm_candidate(database, params, clock()),
    )

    # Consent is append-only evidence, not session state: recording one moves no
    # revision, and `consent_event.id` is already the primary key, so a retried
    # click cannot double-record.
    registry.register(
        "coach.consent.record",
        lambda params: _record_consent(database, params, clock()),
    )
    registry.register(
        "coach.consent.state", lambda params: _consent_state(database, params)
    )

    # A check-in belongs to a commitment, not to a coaching session, so these
    # sit outside the session envelope. Answering twice is refused by the row's
    # own `completed_at` rather than by an idempotency key: a second answer is
    # a real conflict to report, not a retry to replay.
    registry.register("coach.check_ins", lambda params: _check_ins(database, clock()))
    registry.register("coach.journey", lambda params: _journey(database, clock()))

    # The Privacy Center's own surface. Export is a read; the three Trash
    # commands are writes to records rather than to a session, so like consent
    # they sit outside the session envelope.
    #
    # Every one of these had a service written and tested behind it and no way
    # to reach it: `ExportService` and `TrashService` were referenced by no RPC
    # at all, so "xoá" and "tải dữ liệu về" were promises the UI could not keep.
    registry.register("coach.export", lambda params: _export(database, params, clock()))
    registry.register("coach.trash", lambda params: _trash(database))
    registry.register(
        "coach.trash.delete", lambda params: _trash_delete(database, params, clock())
    )
    registry.register(
        "coach.trash.restore", lambda params: _trash_restore(database, params, clock())
    )
    registry.register(
        "coach.trash.purge", lambda params: _trash_purge(database, params, clock())
    )
    registry.register(
        "coach.check_in.answer",
        lambda params: _answer_check_in(database, params, clock()),
    )


def ensure_profile(database: CoachDatabase, now: str) -> None:
    """Create the single local profile if this is a fresh install."""
    existing = database.connection.execute(
        "SELECT 1 FROM coachee_profile WHERE id = :id", {"id": DEFAULT_PROFILE_ID}
    ).fetchone()
    if existing:
        return
    with database.transaction():
        database.connection.execute(
            "INSERT INTO coachee_profile (id, display_name, created_at) "
            "VALUES (:id, :name, :now)",
            {"id": DEFAULT_PROFILE_ID, "name": "Coachee", "now": now},
        )


def _today(database: CoachDatabase, now: str) -> dict[str, Any]:
    """What Home answers: destination, commitments, attention, learning."""
    connection = database.connection
    insights = InsightRepository(connection).list_active()
    return {
        "profile_id": DEFAULT_PROFILE_ID,
        "goals": [
            {
                "id": goal.id,
                "title": goal.title,
                "status": goal.status,
                "target_date": goal.target_date,
            }
            for goal in GoalRepository(connection).list_active(DEFAULT_PROFILE_ID)
        ],
        # The commitment's own words travel with the check-in. "You have one
        # check-in" is not something a Coachee can act on; "nhắn anh Tuấn chọn
        # 20 file" is.
        "pending_check_ins": list(CheckInService(database).pending(now=now)),
        # One, not a feed: Home shows the latest learning, not a scroll.
        "recent_insight": (
            {"id": insights[-1].id, "content": insights[-1].content}
            if insights
            else None
        ),
        "disclosure": disclosure(),
    }


def _export(
    database: CoachDatabase, params: dict[str, Any], now: str
) -> dict[str, Any]:
    """Everything the profile holds, in the shape the Coachee asked for.

    The service redacts as it goes; the count travels with the payload rather
    than being silently applied, because "we removed some things from your own
    export" is exactly the kind of fact a privacy screen must not hide.
    """
    service = ExportService(database, profile_id=DEFAULT_PROFILE_ID)
    fmt = params.get("format", "json")
    if fmt not in ("json", "markdown"):
        raise RpcError("invalid_request", f"unknown export format {fmt!r}")
    if fmt == "markdown":
        return {"format": fmt, "markdown": service.to_markdown(now=now)}
    return {"format": fmt, "data": service.to_json(now=now)}


def _trash(database: CoachDatabase) -> dict[str, Any]:
    """What deletion did, and how long it can still be undone."""
    return {
        "items": [
            {
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "deleted_at": entry.deleted_at,
                "purge_after": entry.purge_after,
                "deletion_source": entry.deletion_source,
            }
            for entry in TrashRepository(database.connection).open_entries()
        ]
    }


def _trash_target(params: dict[str, Any]) -> tuple[str, str]:
    return _required_str(params, "entity_type"), _required_str(params, "entity_id")


def _trash_delete(
    database: CoachDatabase, params: dict[str, Any], now: str
) -> dict[str, Any]:
    entity_type, entity_id = _trash_target(params)
    try:
        entry_id = _trash_service(database).soft_delete(entity_type, entity_id, now=now)
    except (KeyError, ValueError) as invalid:
        raise RpcError("invalid_request", str(invalid)) from invalid
    return {"entry_id": entry_id, "entity_type": entity_type, "entity_id": entity_id}


def _trash_restore(
    database: CoachDatabase, params: dict[str, Any], now: str
) -> dict[str, Any]:
    entity_type, entity_id = _trash_target(params)
    try:
        _trash_service(database).restore(entity_type, entity_id, now=now)
    except RestoreBlocked as blocked:
        raise RpcError("restore_blocked", str(blocked)) from blocked
    except (KeyError, ValueError) as invalid:
        raise RpcError("invalid_request", str(invalid)) from invalid
    return {"entity_type": entity_type, "entity_id": entity_id, "restored": True}


def _trash_purge(
    database: CoachDatabase, params: dict[str, Any], now: str
) -> dict[str, Any]:
    """Irreversible, so it needs the control the Coachee actually pressed.

    The service refuses a user-initiated purge with no `control_id`. That check
    is what keeps a stray call from erasing a record for good, and it is the
    reason this is not folded into delete.
    """
    entity_type, entity_id = _trash_target(params)
    try:
        _trash_service(database).purge(
            entity_type,
            entity_id,
            now=now,
            reason=PurgeReason.USER_CONFIRMED,
            control_id=params.get("control_id"),
        )
    except RestoreBlocked as blocked:
        raise RpcError("purge_blocked", str(blocked)) from blocked
    except (KeyError, ValueError) as invalid:
        raise RpcError("invalid_request", str(invalid)) from invalid
    return {"entity_type": entity_type, "entity_id": entity_id, "purged": True}


def _trash_service(database: CoachDatabase) -> TrashService:
    return TrashService(database, profile_id=DEFAULT_PROFILE_ID)


def _journey(database: CoachDatabase, now: str) -> dict[str, Any]:
    """Every session the Coachee has held, newest first."""
    return {"sessions": list(JourneyService(database).recent(now=now))}


def _check_ins(database: CoachDatabase, now: str) -> dict[str, Any]:
    """Every outstanding check-in: due ones first, then soonest."""
    return {"check_ins": list(CheckInService(database).pending(now=now))}


def _answer_check_in(
    database: CoachDatabase, params: dict[str, Any], now: str
) -> dict[str, Any]:
    """One choice about one commitment.

    The command model does the validating — edit needs new words, reschedule
    needs a date — so an incoherent request is refused here rather than
    half-applied inside the transaction.
    """
    try:
        command = CheckInChoiceCommand(
            command_id=_required_str(params, "command_id"),
            ui_event_id=_required_str(params, "ui_event_id"),
            check_in_id=_required_str(params, "check_in_id"),
            action=CheckInAction(_required_str(params, "action")),
            edited_commitment=params.get("edited_commitment"),
            rescheduled_for=params.get("rescheduled_for"),
        )
    except ValueError as invalid:
        raise RpcError("invalid_request", str(invalid)) from invalid

    try:
        return CheckInService(database).answer(command, now=now)
    except UnknownCheckIn as missing:
        raise RpcError("unknown_check_in", str(missing)) from missing
    except CheckInAlreadyAnswered as done:
        raise RpcError("check_in_already_answered", str(done)) from done


def _insights(database: CoachDatabase) -> dict[str, Any]:
    """Every learning the Coachee confirmed, oldest first.

    Home shows the latest one; this is the whole set. Only confirmed rows: an
    insight the Coachee never accepted is not theirs to be shown back to them as
    something they learned.
    """
    return {
        "insights": [
            {
                "id": row.id,
                "content": row.content,
                "topic": row.topic,
                "goal_id": row.goal_id,
                "source_session_id": row.source_session_id,
                "confirmed_at": row.confirmed_at,
            }
            for row in InsightRepository(database.connection).list_active()
            if row.confirmed_at
        ]
    }


def _open_session(database: CoachDatabase) -> dict[str, Any]:
    """The session to return to, or none.

    Deliberately just the identity and where it left off. The client re-reads
    `coach.session.state` for the rest, so there is one description of a
    session's contents rather than two that can disagree.
    """
    row = CoachingSessionRepository(database.connection).latest_open()
    if row is None:
        return {"session": None}
    return {
        "session": {
            "session_id": row.id,
            "started_at": row.started_at,
            "intention": row.intention,
            "stage": row.coaching_stage,
        }
    }


def _transcript(
    database: CoachDatabase, params: dict[str, Any], now: str
) -> dict[str, Any]:
    """What was actually said in one session.

    Reads through the same active scope as everything else, so a line the
    Coachee deleted stays deleted and an expired one stays gone. The Safety
    System's own messages travel under their own role: a reader must be able to
    tell them from the Coach months later, exactly as during the session.
    """
    session_id = _required_str(params, "session_id")
    messages = SessionMessageRepository(database.connection).list_active(
        session_id, now=now
    )
    return {
        "session_id": session_id,
        "turns": [
            {
                "id": row.id,
                "voice": row.role,
                "content": row.content,
                "stage": row.coaching_stage,
                "created_at": row.created_at,
            }
            for row in messages
        ],
    }


def _session_state(database: CoachDatabase, params: dict[str, Any]) -> dict[str, Any]:
    connection = database.connection
    session_id = _required_str(params, "session_id")
    recovery = SessionRecoveryService(database, profile_id=DEFAULT_PROFILE_ID)
    state = recovery.recover(session_id)
    from hermes_coach.infrastructure.repositories.rpc_repository import (
        SessionRevisionRepository,
    )

    return {
        "session_id": state.session.id if state.session else None,
        "stage": state.current_stage.value if state.current_stage else None,
        # A closed session takes no further turns, and the screen has to be able
        # to say so instead of letting the Coachee write into a finished record
        # and meet `session_ended` for their trouble.
        "ended": bool(state.session and state.session.ended_at),
        "revision": SessionRevisionRepository(database.connection).current(session_id),
        "confirmed_steps": list(state.confirmed_steps),
        "safety_state": state.session.safety_state if state.session else "normal",
        "turns": [
            {"id": row.id, "voice": row.role, "content": row.content}
            for row in state.messages
        ],
        # Pending only. A resolved candidate is history, and offering it again
        # would invite a second confirmation of the same record.
        "candidates": [
            {
                "id": row.id,
                "kind": row.record_type,
                "value": _candidate_value(row.payload_json),
            }
            for row in CandidateRepository(connection).list_pending(session_id)
        ],
        "pending_check_ins": [row.id for row in state.pending_check_ins],
    }


def _candidate_value(payload_json: str) -> str:
    """The one field a card shows. Never the whole payload."""
    payload = json.loads(payload_json)
    for field in ("title", "content", "action_text", "value"):
        if payload.get(field):
            return str(payload[field])
    return ""


def _start_session(
    database: CoachDatabase, params: dict[str, Any], now: str
) -> Persisted:
    session_id = _required_str(params, "session_id")
    row = CoachingSessionRow(
        id=session_id,
        started_at=now,
        # Never Goal: skipping Pre-Coaching is the one shortcut the framework
        # forbids, so the starting stage is not a caller-supplied value.
        coaching_stage=INITIAL_STAGE,
        intention=params.get("intention"),
    )

    def apply(connection) -> None:
        CoachingSessionRepository(connection).start(row)

    return Persisted(
        result={"session_id": session_id, "stage": INITIAL_STAGE}, apply=apply
    )


def _turn(
    database: CoachDatabase,
    adapter: Any | None,
    params: dict[str, Any],
    now: str,
) -> Persisted:
    if adapter is None:
        raise RpcError(
            "provider_not_configured",
            "Chưa cấu hình nhà cung cấp mô hình; dữ liệu đã lưu vẫn xem được.",
        )

    service = CoachingTurnService(database, profile_id=DEFAULT_PROFILE_ID, adapter=adapter)
    try:
        return service.run(
            session_id=_required_str(params, "session_id"),
            turn_id=_required_str(params, "turn_id"),
            goal_id=params.get("goal_id"),
            user_message=_required_str(params, "user_message"),
            now=now,
            cancellations=params.get("_cancellations"),
        )
    except UnknownSession as missing:
        raise RpcError("unknown_session", str(missing)) from missing
    except SafetyInterrupted as interrupted:
        # Not a failure: the product decided this needs a person, and said so on
        # the turn that decided it. Coaching does not resume by asking again.
        raise RpcError(
            "safety_interrupted",
            "Phần coaching đã dừng vì lý do an toàn. Dữ liệu đã lưu vẫn xem được.",
        ) from interrupted
    except SessionEnded as closed:
        # Not an error in the transport sense: the Coachee confirmed Review
        # and the session is over. Saying so is better than accepting a turn
        # into a record that is already closed.
        raise RpcError(
            "session_ended",
            "Phiên này đã kết thúc ở bước Review. Dữ liệu đã lưu vẫn xem được.",
        ) from closed
    except ConsentWithdrawn as withdrawn:
        # Degraded, not broken: the UI keeps showing stored data.
        raise RpcError("consent_withdrawn", str(withdrawn)) from withdrawn
    except RuntimeRejected as rejected:
        # The adapter already produced a typed code and a message written to be
        # shown. Letting it fall through would flatten every distinct provider
        # outcome into one `internal_error` the UI cannot act on.
        raise RpcError(
            rejected.failure.code, rejected.failure.safe_message
        ) from rejected


def _mint_intent(
    database: CoachDatabase, params: dict[str, Any], now: str
) -> dict[str, Any]:
    """Offer one candidate for confirmation.

    Minting is not a change to the session, so it moves no revision. The raw
    token is returned exactly once; the database keeps only its digest.
    """
    service = DurableConfirmationService(database, profile_id=DEFAULT_PROFILE_ID)
    try:
        token = service.issue_intent(
            local_user_id=DEFAULT_PROFILE_ID,
            session_id=_required_str(params, "session_id"),
            candidate_id=_required_str(params, "candidate_id"),
            action=_record_action(params),
            edited_value=params.get("edited_value"),
            now=now,
            reconfirm=bool(params.get("reconfirm", False)),
        )
    except ConfirmationRejected as rejected:
        raise RpcError("confirmation_rejected", str(rejected)) from rejected
    return {"intent_token": token, "candidate_id": params["candidate_id"]}


def _confirm_candidate(
    database: CoachDatabase, params: dict[str, Any], now: str
) -> dict[str, Any]:
    """Resolve exactly one candidate. There is no plural form of this."""
    service = DurableConfirmationService(database, profile_id=DEFAULT_PROFILE_ID)
    try:
        command = ConfirmationCommand(
            command_id=_required_str(params, "command_id"),
            intent_token=_required_str(params, "intent_token"),
            candidate_id=_required_str(params, "candidate_id"),
            action=_record_action(params),
            edited_value=params.get("edited_value"),
        )
    except ValidationError as invalid:
        raise RpcError("invalid_request", "malformed confirmation command") from invalid

    try:
        outcome = service.apply(
            command, now=now, reconfirm=bool(params.get("reconfirm", False))
        )
    except ConfirmationRejected as rejected:
        raise RpcError("confirmation_rejected", str(rejected)) from rejected

    return {
        "candidate_id": outcome.candidate_id,
        "action": outcome.action,
        "revision": outcome.revision,
        "official_record_type": outcome.official_record_type,
        "official_record_id": outcome.official_record_id,
    }


def _record_consent(
    database: CoachDatabase, params: dict[str, Any], now: str
) -> dict[str, Any]:
    """Record one consent decision from a trusted UI control.

    The decision is derived from the button, never taken from the request: a
    caller that sent `decision` alongside `ui_action` could otherwise claim a
    grant from a decline.
    """
    service = ConsentService(database, profile_id=DEFAULT_PROFILE_ID)
    consent_type = _required_str(params, "consent_type")
    scope = _scope(params)
    event_id = _required_str(params, "event_id")

    action = _ui_consent_action(params)
    control_id = params.get("control_id")
    if not isinstance(control_id, str) or not control_id.strip():
        raise RpcError("invalid_request", "consent needs a trusted UI control id")

    already = any(event.id == event_id for event in service.history(consent_type, scope))
    if not already:
        try:
            service.record(
                event_id=event_id,
                consent_type=consent_type,
                scope=scope,
                ui_action=action,
                control_id=control_id,
                now=now,
                session_id=params.get("session_id"),
            )
        except ValueError as invalid:
            raise RpcError("invalid_request", str(invalid)) from invalid

    decision = service.effective(consent_type, scope)
    return {
        "consent_type": consent_type,
        "decision": decision.value if decision else None,
        "granted": service.is_granted(consent_type, scope),
    }


def _consent_state(database: CoachDatabase, params: dict[str, Any]) -> dict[str, Any]:
    service = ConsentService(database, profile_id=DEFAULT_PROFILE_ID)
    consent_type = _required_str(params, "consent_type")
    scope = _scope(params)
    decision = service.effective(consent_type, scope)
    return {
        "consent_type": consent_type,
        "decision": decision.value if decision else None,
        "granted": service.is_granted(consent_type, scope),
        "history": [
            {
                "id": event.id,
                "decision": event.decision,
                "ui_action": event.ui_action,
                "created_at": event.created_at,
            }
            for event in service.history(consent_type, scope)
        ],
    }


def _ui_consent_action(params: dict[str, Any]) -> UiConsentAction:
    raw = params.get("ui_action")
    try:
        return UiConsentAction(raw)
    except ValueError as invalid:
        raise RpcError(
            "invalid_request", "ui_action must be confirm, decline or withdraw"
        ) from invalid


def _scope(params: dict[str, Any]) -> dict[str, Any]:
    scope = params.get("scope")
    if scope is None:
        return {}
    if not isinstance(scope, dict):
        raise RpcError("invalid_request", "scope must be an object")
    return scope


def _record_action(params: dict[str, Any]) -> RecordAction:
    raw = params.get("action")
    try:
        return RecordAction(raw)
    except ValueError as invalid:
        raise RpcError(
            "invalid_request", "action must be accept, edit or discard"
        ) from invalid


def _required_str(params: dict[str, Any], name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value:
        raise RpcError("invalid_request", f"{name} is required")
    return value
