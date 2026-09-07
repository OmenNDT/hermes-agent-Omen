from __future__ import annotations

from typing import Any

from hermes_coach.contracts.runtime_contract import CoachOutput


def coach_output_json_schema() -> dict[str, Any]:
    return CoachOutput.model_json_schema()

