from __future__ import annotations

import json
from typing import Any

from hermes_coach.domain.session_state import CoachingSessionState, stage_is_complete


def build_structured_context(state: CoachingSessionState) -> dict[str, Any]:
    current = state.current_step
    snapshot = getattr(state, current.value)
    if snapshot is None:
        stage_data: dict[str, Any] | None = None
    else:
        stage_data = snapshot.model_dump(mode="json")
    return {
        "session_id": state.session_id,
        "current_step": current.value,
        "current_revision": state.revision_for(current),
        "funnel_stage": state.funnel_stage.value,
        "stage_complete": stage_is_complete(state),
        "confirmed_steps": [stage.value for stage in state.confirmed_steps],
        "safety_state": state.safety_state.value,
        "current_stage_data": stage_data,
        "pending_candidate_ids": [item.candidate_id for item in state.candidate_records],
    }


def structured_context_json(state: CoachingSessionState) -> str:
    return json.dumps(
        build_structured_context(state),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
