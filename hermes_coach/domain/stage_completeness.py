"""What a step still needs before it can honestly be called finished.

Requirement families: `HC-PROCESS`; sources `SRC-030…057`.

`stage_is_complete` has existed in `domain.session_state` since the beginning
and has never been consulted, because the snapshots it reads were never
populated by anything: every field defaulted to empty, so every stage read as
incomplete, and wiring it in would have meant no step could ever close.

That left the six-step structure resting entirely on the closing gate — an
explicit yes to a well-formed question — with no check that the step had any
content. A live run showed exactly what that costs: the Coach moved to Reality
and immediately asked an Options question, and nothing objected.

This module is the missing half, in the smallest honest form: given a stage and
whatever the model extracted for it, say which required pieces are still
missing. It names them rather than returning a bare boolean, because "Bước Will
chưa đủ" helps nobody and "chưa có mốc thời gian và chưa có mức cam kết" is
something a Coachee and a Coach can both act on.

Deliberately not the enforcer. Whether a missing piece blocks a gate is a
decision for the caller, and one this codebase is not yet ready to make: the
model has never been asked for these fields, and a rule that fails closed on
data nobody has ever produced would take the whole product down. Naming the
gaps comes first; refusing on them comes when the gaps are known to be real.
"""

from __future__ import annotations

from collections.abc import Mapping

from hermes_coach.contracts.runtime_contract import CoachingStage


# What each step must have said something about, and what to call it in the
# Coachee's own language. Kept as data so the list can be read against the
# framework rather than reconstructed out of validation code.
REQUIRED_FIELDS: dict[CoachingStage, tuple[tuple[str, str], ...]] = {
    CoachingStage.PRE_COACHING: (
        ("ready", "sự sẵn sàng của bạn"),
        ("coaching_understood", "hiểu coaching là gì"),
        ("roles_agreed", "vai của mỗi bên"),
        ("boundaries_agreed", "ranh giới của phiên"),
    ),
    CoachingStage.GOAL: (
        ("title", "mục tiêu"),
        ("why_it_matters", "vì sao nó quan trọng với bạn"),
        ("success_evidence", "dấu hiệu nào cho biết đã đạt"),
        ("target_date", "mốc thời gian"),
    ),
    CoachingStage.REALITY: (
        ("facts", "sự việc đang diễn ra"),
        ("present_state", "tình hình hiện tại"),
        ("gap", "khoảng cách tới mục tiêu"),
    ),
    CoachingStage.OPTIONS: (
        ("options", "các lựa chọn bạn tự nghĩ ra"),
        ("chosen", "lựa chọn bạn chọn"),
    ),
    CoachingStage.WILL: (
        ("chosen_action", "hành động cụ thể"),
        ("due_at", "mốc thời gian"),
        ("commitment_score", "mức cam kết 1–10"),
    ),
    CoachingStage.REVIEW: (
        ("takeaway", "điều bạn mang theo"),
    ),
}

# Options needs at least two genuinely different ideas before a choice between
# them means anything — a single option is not a choice, and the framework says
# so. Kept here beside the field list so the rule and the fields stay together.
MINIMUM_OPTIONS = 2


def _is_present(value: object) -> bool:
    """Present means the Coachee actually said something, not that a key exists.

    A model asked to fill a form will fill it — with "", with 0, with an empty
    list. Treating those as answers is how a step passes a completeness check
    without ever having been worked through.
    """
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def missing_for(stage: CoachingStage, snapshot: Mapping[str, object] | None) -> tuple[str, ...]:
    """The human-readable names of what this step still lacks.

    An empty tuple means nothing required is missing. It does not mean the step
    was done well — no structural check can say that.
    """
    required = REQUIRED_FIELDS.get(stage, ())
    if not snapshot:
        return tuple(label for _, label in required)

    missing = [
        label for key, label in required if not _is_present(snapshot.get(key))
    ]

    # The scale is 1–10, and 0 is what a model reaches for when it must fill a
    # required integer without having asked. It passes a generic presence check
    # — it is not None, not False, not empty — while meaning "no answer".
    if stage is CoachingStage.WILL:
        score = snapshot.get("commitment_score")
        in_range = isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 10
        label = "mức cam kết 1–10"
        if not in_range and label not in missing:
            missing.append(label)

    if stage is CoachingStage.OPTIONS:
        options = snapshot.get("options")
        enough = isinstance(options, (list, tuple)) and len(options) >= MINIMUM_OPTIONS
        label = f"ít nhất {MINIMUM_OPTIONS} lựa chọn khác nhau"
        if not enough and "các lựa chọn bạn tự nghĩ ra" not in missing:
            missing.append(label)
        elif not enough:
            missing = [label if m == "các lựa chọn bạn tự nghĩ ra" else m for m in missing]

    return tuple(missing)


def describe_missing(missing: tuple[str, ...]) -> str:
    """One sentence a Coachee can act on, or an empty string."""
    if not missing:
        return ""
    if len(missing) == 1:
        return f"Bước này chưa nói tới {missing[0]}."
    return "Bước này chưa nói tới " + ", ".join(missing[:-1]) + f" và {missing[-1]}."
