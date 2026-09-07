from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Protocol

from hermes_coach.domain.enums import DecompositionLayer, NoveltyStatus, RecoveryMove
from hermes_coach.domain.models import ImmutableModel, OptionIdea, OptionsSnapshot


STUCK_RECOVERY_SEQUENCE = (
    RecoveryMove.RECHECK_GOAL,
    RecoveryMove.RECHECK_REALITY,
    RecoveryMove.REFRAME_QUESTION,
    RecoveryMove.CHANGE_PERSPECTIVE,
    RecoveryMove.ASK_WHAT_ELSE,
    RecoveryMove.EVOKE_EXPERIENCE,
    RecoveryMove.ALLOW_SILENCE,
    RecoveryMove.DECOMPOSE,
    RecoveryMove.CREATE_OPEN_SPACE,
    RecoveryMove.RETURN_TO_REALITY,
    RecoveryMove.ADD_INGREDIENTS,
    RecoveryMove.HOLD_COACH_ROLE,
)

DECOMPOSITION_SEQUENCE = tuple(DecompositionLayer)


class NoveltyAssessment(ImmutableModel):
    status: NoveltyStatus
    materially_new: bool = False


class OptionTurnEvidence(Protocol):
    """Read-only view of a session turn.

    Members are properties, not mutable attributes: a mutable attribute makes the
    protocol invariant, which frozen turn snapshots cannot satisfy structurally.
    """

    @property
    def turn_id(self) -> str: ...

    @property
    def sequence(self) -> int: ...

    @property
    def actor(self) -> str: ...

    @property
    def content(self) -> str: ...


def assess_option_novelty(
    baseline: tuple[OptionIdea, ...], candidate: OptionIdea
) -> NoveltyAssessment:
    normalized_text = _normalize(candidate.text)
    if any(_normalize(item.text) == normalized_text for item in baseline):
        return NoveltyAssessment(status=NoveltyStatus.DUPLICATE)
    if any(
        mechanisms_equivalent(item.mechanism, candidate.mechanism)
        for item in baseline
    ):
        return NoveltyAssessment(status=NoveltyStatus.SAME_MECHANISM)
    if not candidate.coachee_generated:
        return NoveltyAssessment(status=NoveltyStatus.NOT_COACHEE_OWNED)
    if not candidate.material_difference_confirmed:
        return NoveltyAssessment(status=NoveltyStatus.NEEDS_CLARIFICATION)
    return NoveltyAssessment(status=NoveltyStatus.MATERIALLY_NEW, materially_new=True)


def options_are_complete(
    snapshot: OptionsSnapshot,
    *,
    session_id: str,
    stage_revision: int,
    turn_ledger: Sequence[OptionTurnEvidence],
) -> bool:
    """Verify Options evidence against the owning session aggregate."""
    if not session_id.strip() or stage_revision < 1:
        return False
    if not _canonical_baseline_is_valid(snapshot.canonical_baseline):
        return False

    turns_by_id = {
        turn.turn_id: (index, turn) for index, turn in enumerate(turn_ledger)
    }
    if len(turns_by_id) != len(turn_ledger):
        return False

    for assessment in snapshot.assessments:
        if (
            assessment.session_id != session_id
            or assessment.stage_revision != stage_revision
            or assessment.baseline != snapshot.canonical_baseline
        ):
            continue
        source_entry = turns_by_id.get(assessment.candidate_source_turn_id)
        confirmation_entry = turns_by_id.get(assessment.confirmation_turn_id)
        if source_entry is None or confirmation_entry is None:
            continue
        source_index, source_turn = source_entry
        confirmation_index, confirmation_turn = confirmation_entry
        if source_turn.actor != "coachee" or confirmation_turn.actor != "coachee":
            continue
        if (
            source_index >= confirmation_index
            or source_turn.sequence >= confirmation_turn.sequence
        ):
            continue
        if not _candidate_is_grounded(assessment.candidate, source_turn.content):
            continue
        if not _explicitly_confirms_material_difference(confirmation_turn.content):
            continue
        if assess_option_novelty(
            snapshot.canonical_baseline, assessment.candidate
        ).materially_new:
            return True
    return False


def next_recovery_move(attempted: tuple[RecoveryMove, ...]) -> RecoveryMove | None:
    return next((move for move in STUCK_RECOVERY_SEQUENCE if move not in attempted), None)


def next_decomposition_layer(
    completed: tuple[DecompositionLayer, ...],
) -> DecompositionLayer | None:
    return next((layer for layer in DECOMPOSITION_SEQUENCE if layer not in completed), None)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize(
        "NFD", value.casefold().translate(str.maketrans("đĐ", "dD"))
    )
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()


def _canonical_baseline_is_valid(baseline: tuple[OptionIdea, ...]) -> bool:
    if not baseline:
        return False
    fingerprints = tuple(
        (_normalize(item.text), mechanism_fingerprint(item.mechanism))
        for item in baseline
    )
    return all(text and mechanism for text, mechanism in fingerprints) and len(
        set(fingerprints)
    ) == len(fingerprints)


def _candidate_is_grounded(candidate: OptionIdea, source_content: str) -> bool:
    normalized_source = _normalize(source_content)
    normalized_text = _normalize(candidate.text)
    normalized_mechanism = _normalize(candidate.mechanism)
    if _contains_negation(normalized_source):
        return False
    return normalized_text == normalized_source and _normalized_phrase_is_grounded(
        normalized_mechanism, normalized_source
    )


def _normalized_phrase_is_grounded(phrase: str, content: str) -> bool:
    return bool(phrase and content and f" {phrase} " in f" {content} ")


def _explicitly_confirms_material_difference(content: str) -> bool:
    normalized = _normalize(content)
    if _contains_negation(normalized):
        return False
    tokens = set(normalized.split())
    affirmative = bool(
        tokens & {"correct", "confirm", "dung", "yes"}
        or "dong y" in normalized
        or "xac nhan" in normalized
    )
    difference = bool(
        tokens & {"different", "distinct", "khac"}
        or "material difference" in normalized
    )
    return affirmative and difference


def _contains_negation(normalized: str) -> bool:
    return bool(
        set(normalized.split())
        & {"cha", "chang", "chua", "khong", "never", "no", "not"}
    )


def mechanism_fingerprint(value: str) -> tuple[str, ...]:
    stop_words = {
        "a",
        "an",
        "cac",
        "cho",
        "for",
        "hang",
        "moi",
        "mot",
        "nhung",
        "the",
        "to",
    }
    return tuple(sorted(word for word in _normalize(value).split() if word not in stop_words))


def mechanisms_equivalent(left: str, right: str) -> bool:
    return _fingerprints_equivalent(
        mechanism_fingerprint(left),
        mechanism_fingerprint(right),
    )


def mechanisms_materially_different(
    baseline: tuple[str, ...], candidates: tuple[str, ...]
) -> bool:
    baseline_fingerprints = [
        mechanism_fingerprint(item) for item in baseline if item.strip()
    ]
    candidate_fingerprints = [
        mechanism_fingerprint(item) for item in candidates if item.strip()
    ]
    return bool(
        baseline_fingerprints
        and candidate_fingerprints
        and any(
            fingerprint
            and all(
                not _fingerprints_equivalent(fingerprint, baseline_fingerprint)
                for baseline_fingerprint in baseline_fingerprints
            )
            for fingerprint in candidate_fingerprints
        )
    )


def _fingerprints_equivalent(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    left_tokens = set(left)
    right_tokens = set(right)
    return bool(
        left_tokens
        and right_tokens
        and (left_tokens <= right_tokens or right_tokens <= left_tokens)
    )
