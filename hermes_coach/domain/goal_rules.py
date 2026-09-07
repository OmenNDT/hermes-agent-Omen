from __future__ import annotations

from pydantic import ConfigDict

from hermes_coach.domain.models import GoalSnapshot, ImmutableModel


SMART_FIELDS = ("specific", "measurable", "achievable", "relevant", "time_bound")


class GoalAssessmentReport(ImmutableModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    complete: bool
    missing: tuple[str, ...]


def assess_goal(goal: GoalSnapshot) -> GoalAssessmentReport:
    missing = [f"smart_{name}" for name in SMART_FIELDS if not getattr(goal.smart, name)]
    if not goal.belongs_to_coachee:
        missing.append("ownership")
    if not goal.aligned_with_values_or_needs:
        missing.append("fit")
    if not goal.within_influence:
        missing.append("influence")
    if not _has_text(goal.benefit) and not _has_text(goal.loss_avoided):
        missing.append("benefit_or_loss")
    if not _has_text(goal.success_evidence):
        missing.append("success_evidence")
    return GoalAssessmentReport(complete=not missing, missing=tuple(missing))


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip())

