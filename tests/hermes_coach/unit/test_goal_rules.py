from __future__ import annotations

import pytest

from hermes_coach.contracts.runtime_contract import GoalSmartAssessment
from hermes_coach.domain.goal_rules import assess_goal
from hermes_coach.domain.models import GoalSnapshot


def valid_goal(**changes: object) -> GoalSnapshot:
    values: dict[str, object] = {
        "wording": "Hoàn thành portfolio gồm ba case study trước 30/11/2026",
        "smart": GoalSmartAssessment(
            specific=True,
            measurable=True,
            achievable=True,
            relevant=True,
            time_bound=True,
        ),
        "belongs_to_coachee": True,
        "aligned_with_values_or_needs": True,
        "within_influence": True,
        "benefit": "Tăng khả năng chuyển sang vai trò phù hợp",
        "success_evidence": "Ba case study được xuất bản",
    }
    values.update(changes)
    return GoalSnapshot.model_validate(values)


@pytest.mark.parametrize(
    ("changes", "missing"),
    [
        ({"smart": GoalSmartAssessment()}, "smart_specific"),
        ({"belongs_to_coachee": False}, "ownership"),
        ({"aligned_with_values_or_needs": False}, "fit"),
        ({"within_influence": False}, "influence"),
        ({"benefit": None, "loss_avoided": None}, "benefit_or_loss"),
        ({"success_evidence": None}, "success_evidence"),
    ],
)
def test_goal_hard_gate_reports_every_missing_predicate(
    changes: dict[str, object], missing: str
) -> None:
    report = assess_goal(valid_goal(**changes))

    assert not report.complete
    assert missing in report.missing


def test_goal_is_complete_with_benefit_or_loss_and_all_other_predicates() -> None:
    with_benefit = assess_goal(valid_goal())
    with_loss = assess_goal(valid_goal(benefit=None, loss_avoided="Mất cơ hội ứng tuyển quý IV"))

    assert with_benefit.complete
    assert with_loss.complete
    assert with_benefit.missing == ()

