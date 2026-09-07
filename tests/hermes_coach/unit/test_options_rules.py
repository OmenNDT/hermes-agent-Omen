from __future__ import annotations

import pytest
from pydantic import ValidationError

from hermes_coach.domain.enums import DecompositionLayer, NoveltyStatus, RecoveryMove
from hermes_coach.domain.models import OptionAssessment, OptionIdea, OptionsSnapshot
from hermes_coach.domain.options_rules import (
    DECOMPOSITION_SEQUENCE,
    STUCK_RECOVERY_SEQUENCE,
    assess_option_novelty,
    next_decomposition_layer,
    next_recovery_move,
    options_are_complete,
)
from hermes_coach.domain.session_state import SessionTurn, TurnActor


BASELINE = (OptionIdea(text="Xin tăng lương", mechanism="đàm phán lương"),)
CANDIDATE = OptionIdea(
    text="Xây portfolio để đổi vai trò",
    mechanism="xây portfolio",
    coachee_generated=True,
    material_difference_confirmed=True,
)


def valid_assessment(**updates: object) -> OptionAssessment:
    values: dict[str, object] = {
        "session_id": "s-1",
        "stage_revision": 1,
        "baseline": BASELINE,
        "candidate": CANDIDATE,
        "candidate_source_turn_id": "candidate-turn",
        "confirmation_turn_id": "confirmation-turn",
    }
    values.update(updates)
    return OptionAssessment.model_validate(values)


def valid_ledger(
    *,
    source_actor: TurnActor = "coachee",
    source_content: str = "  XAY PORTFOLIO de doi vai tro!!! ",
    confirmation_actor: TurnActor = "coachee",
    confirmation_content: str = "Đúng, đây là một cơ chế khác.",
) -> tuple[SessionTurn, ...]:
    return (
        SessionTurn(
            turn_id="candidate-turn",
            sequence=0,
            actor=source_actor,
            content=source_content,
        ),
        SessionTurn(
            turn_id="coach-check",
            sequence=1,
            actor="coach",
            content="Đây có phải một cơ chế khác không?",
        ),
        SessionTurn(
            turn_id="confirmation-turn",
            sequence=2,
            actor=confirmation_actor,
            content=confirmation_content,
        ),
    )


def valid_snapshot(**assessment_updates: object) -> OptionsSnapshot:
    return OptionsSnapshot(
        canonical_baseline=BASELINE,
        assessments=(valid_assessment(**assessment_updates),),
    )


def aggregate_complete(
    snapshot: OptionsSnapshot, ledger: tuple[SessionTurn, ...] | None = None
) -> bool:
    return options_are_complete(
        snapshot,
        session_id="s-1",
        stage_revision=1,
        turn_ledger=valid_ledger() if ledger is None else ledger,
    )


def test_option_idea_defaults_to_untrusted_ownership() -> None:
    idea = OptionIdea(text="Xây portfolio", mechanism="xây portfolio")

    assert not idea.coachee_generated
    assert not idea.material_difference_confirmed


def test_exact_duplicate_and_same_mechanism_do_not_count_as_new() -> None:
    duplicate = assess_option_novelty(
        BASELINE, OptionIdea(text="Xin tăng lương", mechanism="đàm phán lương")
    )
    reworded = assess_option_novelty(
        BASELINE, OptionIdea(text="Đề nghị điều chỉnh lương", mechanism="dam phan luong")
    )

    assert duplicate.status is NoveltyStatus.DUPLICATE
    assert reworded.status is NoveltyStatus.SAME_MECHANISM
    assert not duplicate.materially_new and not reworded.materially_new


def test_new_mechanism_requires_ownership_and_confirmation_flags() -> None:
    idea = OptionIdea(
        text="Xây portfolio để đổi vai trò",
        mechanism="xây portfolio",
        coachee_generated=True,
    )

    ambiguous = assess_option_novelty(BASELINE, idea)
    supplied = assess_option_novelty(
        BASELINE,
        idea.model_copy(
            update={"material_difference_confirmed": True, "coachee_generated": False}
        ),
    )
    accepted = assess_option_novelty(
        BASELINE, idea.model_copy(update={"material_difference_confirmed": True})
    )

    assert ambiguous.status is NoveltyStatus.NEEDS_CLARIFICATION
    assert supplied.status is NoveltyStatus.NOT_COACHEE_OWNED
    assert accepted.status is NoveltyStatus.MATERIALLY_NEW
    assert accepted.materially_new


@pytest.mark.parametrize("field", ["text", "mechanism"])
def test_option_idea_rejects_whitespace_only_fields(field: str) -> None:
    values = {"text": "Xin tăng lương", "mechanism": "đàm phán lương"}
    values[field] = " \t\n "

    with pytest.raises(ValidationError):
        OptionIdea.model_validate(values)


@pytest.mark.parametrize(
    "mechanism",
    [
        "tiếp tục đàm phán lương",
        "lương đàm phán",
        "đàm phán",
    ],
)
def test_modifier_reordered_or_subset_mechanism_is_not_novel(mechanism: str) -> None:
    assessment = assess_option_novelty(
        BASELINE,
        OptionIdea(
            text=f"Thử {mechanism}",
            mechanism=mechanism,
            coachee_generated=True,
            material_difference_confirmed=True,
        ),
    )

    assert assessment.status is NoveltyStatus.SAME_MECHANISM
    assert not assessment.materially_new


def test_options_completion_accepts_normalized_ledger_grounding() -> None:
    snapshot = valid_snapshot()

    assert aggregate_complete(snapshot)
    assert not snapshot.complete


@pytest.mark.parametrize(
    ("assessment_updates", "session_id", "stage_revision"),
    [
        ({"session_id": "other-session"}, "s-1", 1),
        ({"stage_revision": 2}, "s-1", 1),
        ({}, "other-session", 1),
        ({}, "s-1", 2),
    ],
)
def test_options_completion_rejects_cross_session_or_stale_assessments(
    assessment_updates: dict[str, object], session_id: str, stage_revision: int
) -> None:
    snapshot = valid_snapshot(**assessment_updates)

    assert not options_are_complete(
        snapshot,
        session_id=session_id,
        stage_revision=stage_revision,
        turn_ledger=valid_ledger(),
    )


def test_options_completion_rejects_missing_or_non_coachee_source() -> None:
    missing = valid_snapshot(candidate_source_turn_id="fabricated-turn")
    coach_source = valid_ledger(source_actor="coach")

    assert not aggregate_complete(missing)
    assert not aggregate_complete(valid_snapshot(), coach_source)


def test_options_completion_rejects_fabricated_or_negated_candidate_content() -> None:
    fabricated = valid_ledger(source_content="Tôi sẽ học thêm một chứng chỉ")
    negated = valid_ledger(
        source_content="Tôi không muốn xây portfolio để đổi vai trò"
    )

    assert not aggregate_complete(valid_snapshot(), fabricated)
    assert not aggregate_complete(valid_snapshot(), negated)


def test_options_completion_requires_separate_explicit_confirmation_evidence() -> None:
    with pytest.raises(ValidationError, match="separate turns"):
        valid_assessment(confirmation_turn_id="candidate-turn")

    missing = valid_snapshot(confirmation_turn_id="fabricated-turn")
    coach_confirmation = valid_ledger(confirmation_actor="coach")
    negated_confirmation = valid_ledger(
        confirmation_content="Không, đây không phải là một cơ chế khác"
    )
    vague_confirmation = valid_ledger(
        confirmation_content="Tôi xác nhận sẽ thực hiện mỗi tuần"
    )

    assert not aggregate_complete(missing)
    assert not aggregate_complete(valid_snapshot(), coach_confirmation)
    assert not aggregate_complete(valid_snapshot(), negated_confirmation)
    assert not aggregate_complete(valid_snapshot(), vague_confirmation)


def test_options_completion_requires_exact_canonical_baseline() -> None:
    noncanonical = valid_snapshot(
        baseline=(OptionIdea(text="Học chứng chỉ", mechanism="học chứng chỉ"),)
    )
    duplicate_baseline = OptionsSnapshot(
        canonical_baseline=BASELINE + BASELINE,
        assessments=(valid_assessment(baseline=BASELINE + BASELINE),),
    )

    assert not aggregate_complete(noncanonical)
    assert not aggregate_complete(duplicate_baseline)


def test_options_completion_rechecks_novelty_against_canonical_baseline() -> None:
    same_mechanism = OptionIdea(
        text="Đề nghị điều chỉnh lương bằng cách tiếp tục đàm phán lương",
        mechanism="tiếp tục đàm phán lương",
        coachee_generated=True,
        material_difference_confirmed=True,
    )
    ledger = valid_ledger(
        source_content="Đề nghị điều chỉnh lương bằng cách tiếp tục đàm phán lương"
    )

    assert not aggregate_complete(valid_snapshot(candidate=same_mechanism), ledger)


def test_legacy_global_booleans_are_rejected_instead_of_migrated() -> None:
    with pytest.raises(ValidationError):
        OptionsSnapshot.model_validate(
            {
                "baseline_mechanisms": ("đàm phán lương",),
                "materially_new_mechanisms": ("xây portfolio",),
                "coachee_generated_new": True,
                "material_difference_confirmed": True,
            }
        )


def test_stuck_recovery_and_decomposition_follow_canonical_order() -> None:
    assert STUCK_RECOVERY_SEQUENCE[:2] == (
        RecoveryMove.RECHECK_GOAL,
        RecoveryMove.RECHECK_REALITY,
    )
    assert next_recovery_move(()) is RecoveryMove.RECHECK_GOAL
    assert next_recovery_move(STUCK_RECOVERY_SEQUENCE[:5]) is STUCK_RECOVERY_SEQUENCE[5]
    assert DECOMPOSITION_SEQUENCE[0] is DecompositionLayer.NAME_TANGLE
    assert DECOMPOSITION_SEQUENCE[-1] is DecompositionLayer.ACTION_ELEMENT
    assert next_decomposition_layer(DECOMPOSITION_SEQUENCE[:-1]) is DecompositionLayer.ACTION_ELEMENT
