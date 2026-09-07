"""What the turn tells the model about records, and whether it is followable.

Requirement families: `HC-RECORDS`; sources `SRC-070…075`, `SRC-079`.

`CoachOutput` has carried four candidate arrays since Phase 1 and
`CoachingTurnService` has written them to `candidate_record` since Phase 3 — but
the turn message never mentioned them, so a live model emitted none, ever. A
whole session could reach Review having produced a coaching conversation and no
record of it: `coach.today` answers `goals: []`, Journey and Check-in have
nothing to stand on. Nothing failed. Nothing logged.

So these tests hold two things at once: that the instruction is *sent*, and that
an output shaped exactly as the instruction describes actually *validates*. The
second is the one that matters — an instruction the schema then rejects would
spend every regeneration and still deliver nothing.
"""

from __future__ import annotations

import json

import pytest

from hermes_coach.contracts.runtime_contract import CoachOutput, RecordKind
from hermes_coach.infrastructure.hermes_runtime_adapter import (
    CANDIDATE_EXAMPLE,
    OUTPUT_CONTRACT,
)


# Spelled out rather than derived from the array name: "candidate_memories"
# does not depluralise to "memory", and a helper that got that wrong is how this
# pairing would go untested.
KIND_FOR_ARRAY = {
    "candidate_goals": "goal",
    "candidate_insights": "insight",
    "candidate_commitments": "commitment",
    "candidate_memories": "memory",
}

CANDIDATE_ARRAYS = tuple(KIND_FOR_ARRAY)


def output_with(array: str, element: str) -> str:
    return (
        '{"question": "Điều gì quan trọng với bạn?", '
        f'"coaching_stage": "goal", "{array}": [{element}]}}'
    )


def test_the_example_the_contract_shows_actually_validates() -> None:
    """The instruction has to be followable, not merely present."""
    parsed = CoachOutput.model_validate_json(
        output_with("candidate_goals", CANDIDATE_EXAMPLE)
    )
    assert parsed.candidate_goals[0].kind is RecordKind.GOAL


def test_the_example_carries_every_field_the_schema_requires() -> None:
    """A missing required field is a regeneration spent on nothing."""
    element = json.loads(CANDIDATE_EXAMPLE)
    assert set(element) == {"candidate_id", "kind", "value", "source_turn_id"}


def test_the_example_omits_provenance_the_server_supplies_itself() -> None:
    """`coaching_stage`/`stage_revision` must be both present or both absent.

    The server files a candidate under the turn and session it arrived on, so
    asking the model for provenance would only add a pair it can get half right.
    """
    element = json.loads(CANDIDATE_EXAMPLE)
    assert "coaching_stage" not in element
    assert "stage_revision" not in element


@pytest.mark.parametrize("array", CANDIDATE_ARRAYS)
def test_the_turn_names_every_candidate_array(array: str) -> None:
    assert array in OUTPUT_CONTRACT


@pytest.mark.parametrize(("array", "kind"), sorted(KIND_FOR_ARRAY.items()))
def test_each_array_accepts_the_documented_element_with_its_own_kind(
    array: str, kind: str
) -> None:
    """`kind` must match the array it sits in, and the contract says so."""
    element = json.loads(CANDIDATE_EXAMPLE)
    element["kind"] = kind
    parsed = CoachOutput.model_validate_json(
        output_with(array, json.dumps(element, ensure_ascii=False))
    )
    assert getattr(parsed, array)[0].kind.value == kind


def test_a_kind_that_does_not_match_its_array_is_refused() -> None:
    """Which is why the contract spends a sentence on it."""
    element = json.loads(CANDIDATE_EXAMPLE)
    element["kind"] = "insight"
    with pytest.raises(ValueError, match="mismatched record kind"):
        CoachOutput.model_validate_json(
            output_with("candidate_goals", json.dumps(element, ensure_ascii=False))
        )


def test_an_output_with_no_records_is_still_valid() -> None:
    """Most turns produce nothing to keep, and must not be forced to invent one."""
    parsed = CoachOutput.model_validate_json(
        '{"question": "Điều gì quan trọng với bạn?", "coaching_stage": "goal"}'
    )
    assert parsed.candidate_goals == ()


def test_the_contract_says_a_candidate_is_a_proposal_not_a_record() -> None:
    """The Coachee confirms records; the model only ever offers them."""
    assert "xac nhan" in OUTPUT_CONTRACT
