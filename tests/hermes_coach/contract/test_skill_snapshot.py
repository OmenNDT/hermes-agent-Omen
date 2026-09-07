"""The Coach prompt asset cannot be extended, replaced or supplemented.

Requirement families: `HC-COMPANION`, `HC-GOV`; sources `SRC-073…075`,
`SRC-096`, `SRC-107`, `SRC-108`.

Byte stability and the load-bearing invariants are covered by
`test_prompt_byte_stability.py`; this file does not repeat them. What it pins is
the skill dimension: the prompt has exactly one definition site, Coach loads no
skill file at all, and nothing in the adapter's construction could let a user or
global skill, a tool, or a second coaching framework in.

There is deliberately no pinned hash literal here. A hash constant is a change
detector, not a behaviour test, and the byte-stability contract plus the
adapter's `system_prompt_hash` check already fail closed on drift.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from hermes_coach.prompt import system_prompt as prompt_module
from hermes_coach.prompt.system_prompt import COACH_SYSTEM_PROMPT, coach_system_prompt


COACH_PACKAGE = Path(__file__).parents[3] / "hermes_coach"

# Names that would mean Coach had started resolving prompt material at runtime.
SKILL_MACHINERY = (
    "skill.md",
    "load_skill",
    "load_skills",
    "skills_dir",
    "external_skills",
    "skill_registry",
    "slash_command",
    "user_skills",
    "global_skills",
)


def coach_sources() -> list[Path]:
    return sorted(COACH_PACKAGE.rglob("*.py"))


def test_the_prompt_has_exactly_one_definition_site() -> None:
    """One constant, one accessor. Assembly from parts is how drift starts."""
    tree = ast.parse(
        Path(prompt_module.__file__).read_text(encoding="utf-8"),
        filename=prompt_module.__file__,
    )
    assigned = [
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    ]
    assert assigned == ["COACH_SYSTEM_PROMPT"]
    assert coach_system_prompt() is COACH_SYSTEM_PROMPT


def test_the_prompt_is_a_literal_not_a_computed_value() -> None:
    """Nothing interpolated: no path, no config, no environment can reach it."""
    tree = ast.parse(
        Path(prompt_module.__file__).read_text(encoding="utf-8"),
        filename=prompt_module.__file__,
    )
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign))
    assert isinstance(assignment.value, ast.Constant)
    assert isinstance(assignment.value.value, str)


@pytest.mark.parametrize("marker", SKILL_MACHINERY)
def test_no_coach_module_touches_skill_machinery(marker: str) -> None:
    """Coach ships one prompt in code; it resolves nothing at runtime.

    A bundled skill asset was considered and left out: with no loader there is
    no path for an arbitrary user or global skill to arrive, which is the
    property the phase actually needs.
    """
    for path in coach_sources():
        content = path.read_text(encoding="utf-8").lower()
        assert marker not in content, f"{path.name} references {marker}"


def test_coach_ships_no_skill_directory() -> None:
    """Adding one must be a deliberate act, not an accident."""
    assert not (COACH_PACKAGE / "skills").exists()
    assert not list(COACH_PACKAGE.rglob("SKILL.md"))


def test_the_prompt_forbids_research_and_advice_mode() -> None:
    assert "không có Research/Advice mode" in COACH_SYSTEM_PROMPT


def test_the_prompt_declares_a_single_framework() -> None:
    """Not just that GROW is present — that it is stated to be the only one."""
    assert "Framework duy nhất" in COACH_SYSTEM_PROMPT


def test_the_prompt_forbids_mid_session_mutation() -> None:
    assert "không sửa system prompt giữa phiên" in COACH_SYSTEM_PROMPT


def test_the_adapter_sends_the_constant_and_nothing_else() -> None:
    """No second prompt source, no skill kwarg, no context injection."""
    from hermes_coach.infrastructure.hermes_runtime_adapter import (
        AdapterConfiguration,
        CoachRuntimeAdapter,
    )

    captured: list[dict] = []

    class RecordingAgent:
        def __init__(self, **kwargs: object) -> None:
            captured.append(kwargs)
            self.tools: list[str] = []

        def run(self, message: str) -> str:
            return '{"question": "Bạn muốn điều gì?", "coaching_stage": "goal"}'

    from hermes_coach.contracts.runtime_contract import (
        CoachingStage,
        RuntimeRequest,
        stable_prompt_fingerprint,
    )

    adapter = CoachRuntimeAdapter(
        AdapterConfiguration(prompt_version="coach-1", provider="fake", model="m"),
        agent_factory=RecordingAgent,
    )
    adapter.generate(
        RuntimeRequest(
            session_id="session-1",
            turn_id="turn-1",
            prompt_version="coach-1",
            system_prompt_hash=stable_prompt_fingerprint(COACH_SYSTEM_PROMPT),
            current_stage=CoachingStage.GOAL,
            user_message="Xin chào",
        )
    )

    kwargs = captured[0]
    assert kwargs["ephemeral_system_prompt"] == COACH_SYSTEM_PROMPT
    # The three doors an outside framework could come through.
    assert kwargs["skip_context_files"] is True
    assert kwargs["skip_memory"] is True
    assert kwargs["enabled_toolsets"] == []
    assert kwargs["load_soul_identity"] is False
    # Nothing else may carry prompt-shaped material.
    prompt_shaped = {
        key
        for key, value in kwargs.items()
        if key != "ephemeral_system_prompt"
        and isinstance(value, str)
        and len(value) > 200
    }
    assert prompt_shaped == set()
