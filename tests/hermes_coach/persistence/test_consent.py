"""Consent evidence and withdrawal.

Requirement families: `HC-PRIVACY`, `HC-RECORDS`; sources `SRC-026`, `SRC-091`,
`SRC-092`.

Only a trusted UI control is consent evidence — a conversational "yes" is not.
Effective consent is the latest event for a normalized type/scope, and
withdrawal takes effect on the very next scoped write or model egress.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from hermes_coach.application.consent_service import (
    ConsentDecision,
    ConsentService,
    ConsentWithdrawn,
    UiConsentAction,
)
from hermes_coach.infrastructure.sqlite.database import (
    CoachDatabase,
    open_coach_database,
)


NOW = "2026-08-22T00:00:00Z"
LATER = "2026-08-22T02:00:00Z"
LATEST = "2026-08-22T04:00:00Z"

PROFILE = "profile-1"
EGRESS = "model_egress"
SCOPE = {"goal_id": "goal-1"}


@pytest.fixture
def database(tmp_path) -> Iterator[CoachDatabase]:
    with open_coach_database(tmp_path / "coach.db") as db:
        with db.transaction():
            db.connection.execute(
                "INSERT INTO coachee_profile (id, display_name, created_at) "
                "VALUES (?, 'Coachee', ?)",
                (PROFILE, NOW),
            )
        yield db


def service(database: CoachDatabase) -> ConsentService:
    return ConsentService(database, profile_id=PROFILE)


def grant(
    database: CoachDatabase,
    *,
    event_id: str = "consent-1",
    consent_type: str = EGRESS,
    scope: dict | None = None,
    at: str = NOW,
) -> None:
    service(database).record(
        event_id=event_id,
        consent_type=consent_type,
        scope=SCOPE if scope is None else scope,
        ui_action=UiConsentAction.CONFIRM,
        control_id="btn-consent-confirm",
        now=at,
    )


def test_a_ui_confirm_grants_consent(database: CoachDatabase) -> None:
    grant(database)
    assert service(database).effective(EGRESS, SCOPE) is ConsentDecision.GRANTED
    assert service(database).is_granted(EGRESS, SCOPE)


def test_absent_consent_is_not_granted(database: CoachDatabase) -> None:
    assert service(database).effective(EGRESS, SCOPE) is None
    assert not service(database).is_granted(EGRESS, SCOPE)


def test_the_latest_event_wins(database: CoachDatabase) -> None:
    grant(database, event_id="consent-1", at=NOW)
    service(database).record(
        event_id="consent-2",
        consent_type=EGRESS,
        scope=SCOPE,
        ui_action=UiConsentAction.WITHDRAW,
        control_id="btn-consent-withdraw",
        now=LATER,
    )
    assert service(database).effective(EGRESS, SCOPE) is ConsentDecision.WITHDRAWN
    assert not service(database).is_granted(EGRESS, SCOPE)


def test_consent_can_be_granted_again_after_withdrawal(
    database: CoachDatabase,
) -> None:
    grant(database, event_id="consent-1", at=NOW)
    service(database).record(
        event_id="consent-2",
        consent_type=EGRESS,
        scope=SCOPE,
        ui_action=UiConsentAction.WITHDRAW,
        control_id="btn-consent-withdraw",
        now=LATER,
    )
    grant(database, event_id="consent-3", at=LATEST)
    assert service(database).is_granted(EGRESS, SCOPE)


def test_history_is_append_only(database: CoachDatabase) -> None:
    grant(database, event_id="consent-1", at=NOW)
    service(database).record(
        event_id="consent-2",
        consent_type=EGRESS,
        scope=SCOPE,
        ui_action=UiConsentAction.WITHDRAW,
        control_id="btn-consent-withdraw",
        now=LATER,
    )
    history = service(database).history(EGRESS, SCOPE)
    assert [event.id for event in history] == ["consent-1", "consent-2"]
    assert [event.decision for event in history] == ["granted", "withdrawn"]


def test_the_service_exposes_no_way_to_edit_or_delete_an_event(
    database: CoachDatabase,
) -> None:
    consent = service(database)
    for forbidden in ("update", "delete", "revoke_event", "clear"):
        assert not hasattr(consent, forbidden)


def test_a_blank_control_id_is_not_evidence(database: CoachDatabase) -> None:
    """A command without a trusted UI control has no standing to write consent."""
    with pytest.raises(ValueError, match="control"):
        service(database).record(
            event_id="consent-forged",
            consent_type=EGRESS,
            scope=SCOPE,
            ui_action=UiConsentAction.CONFIRM,
            control_id="   ",
            now=NOW,
        )
    assert service(database).effective(EGRESS, SCOPE) is None


def test_every_stored_event_is_ui_sourced(database: CoachDatabase) -> None:
    grant(database)
    rows = database.connection.execute("SELECT source FROM consent_event").fetchall()
    assert {row["source"] for row in rows} == {"ui"}


def test_the_schema_refuses_a_non_ui_source(database: CoachDatabase) -> None:
    """Even a direct writer cannot record a conversational consent."""
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction():
            database.connection.execute(
                "INSERT INTO consent_event (id, profile_id, consent_type, decision, "
                "scope_json, source, ui_action, control_id, evidence_version, "
                "created_at) VALUES ('c', ?, ?, 'granted', '{}', 'chat', 'confirm', "
                "'btn', 1, ?)",
                (PROFILE, EGRESS, NOW),
            )


@pytest.mark.parametrize(
    ("written", "queried"),
    [
        ("Model_Egress", "model_egress"),
        ("  model_egress  ", "model_egress"),
        ("MODEL_EGRESS", "Model_Egress"),
    ],
)
def test_consent_type_is_normalized_before_comparison(
    database: CoachDatabase, written: str, queried: str
) -> None:
    grant(database, consent_type=written)
    assert service(database).is_granted(queried, SCOPE)


def test_scope_comparison_ignores_key_order(database: CoachDatabase) -> None:
    grant(database, scope={"goal_id": "goal-1", "session_id": "session-1"})
    assert service(database).is_granted(
        EGRESS, {"session_id": "session-1", "goal_id": "goal-1"}
    )


def test_consent_for_one_scope_does_not_cover_another(
    database: CoachDatabase,
) -> None:
    grant(database, scope={"goal_id": "goal-1"})
    assert not service(database).is_granted(EGRESS, {"goal_id": "goal-2"})


def test_consent_for_one_type_does_not_cover_another(
    database: CoachDatabase,
) -> None:
    grant(database, consent_type="model_egress")
    assert not service(database).is_granted("export", SCOPE)


def test_require_granted_passes_while_consent_stands(
    database: CoachDatabase,
) -> None:
    grant(database)
    service(database).require_granted(EGRESS, SCOPE)


def test_require_granted_blocks_the_next_call_after_withdrawal(
    database: CoachDatabase,
) -> None:
    """Withdrawal is checked fresh, not cached from an earlier pass."""
    consent = service(database)
    grant(database)
    consent.require_granted(EGRESS, SCOPE)

    consent.record(
        event_id="consent-withdraw",
        consent_type=EGRESS,
        scope=SCOPE,
        ui_action=UiConsentAction.WITHDRAW,
        control_id="btn-consent-withdraw",
        now=LATER,
    )
    with pytest.raises(ConsentWithdrawn):
        consent.require_granted(EGRESS, SCOPE)


def test_require_granted_blocks_when_consent_was_declined(
    database: CoachDatabase,
) -> None:
    service(database).record(
        event_id="consent-decline",
        consent_type=EGRESS,
        scope=SCOPE,
        ui_action=UiConsentAction.DECLINE,
        control_id="btn-consent-decline",
        now=NOW,
    )
    with pytest.raises(ConsentWithdrawn):
        service(database).require_granted(EGRESS, SCOPE)


def test_withdrawal_does_not_delete_stored_data(database: CoachDatabase) -> None:
    """Withdrawal stops new use; erasing what exists is the Trash flow."""
    grant(database)
    service(database).record(
        event_id="consent-withdraw",
        consent_type=EGRESS,
        scope=SCOPE,
        ui_action=UiConsentAction.WITHDRAW,
        control_id="btn-consent-withdraw",
        now=LATER,
    )
    assert len(service(database).history(EGRESS, SCOPE)) == 2


def test_a_ui_action_and_its_decision_cannot_disagree(
    database: CoachDatabase,
) -> None:
    grant(database, event_id="consent-1")
    row = database.connection.execute(
        "SELECT ui_action, decision FROM consent_event WHERE id = 'consent-1'"
    ).fetchone()
    assert (row["ui_action"], row["decision"]) == ("confirm", "granted")


def test_consent_survives_restart(tmp_path) -> None:
    path = tmp_path / "coach.db"
    with open_coach_database(path) as database:
        with database.transaction():
            database.connection.execute(
                "INSERT INTO coachee_profile (id, display_name, created_at) "
                "VALUES (?, 'Coachee', ?)",
                (PROFILE, NOW),
            )
        grant(database)

    with open_coach_database(path) as reopened:
        assert service(reopened).is_granted(EGRESS, SCOPE)
