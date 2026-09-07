"""What a step still needs, named rather than assumed.

Requirement families: `HC-PROCESS`; sources `SRC-030…057`.

`stage_is_complete` was written at the start of this project and never once
consulted, because nothing populated the snapshots it reads: every field
defaulted to empty, so every stage read as incomplete and switching it on would
have meant no step could ever close. The six-step structure therefore rested
entirely on the closing gate — an explicit yes to a well-formed question — with
no check that the step had any content in it.

A live session showed the cost: the Coach moved to Reality and immediately
asked an Options question, and nothing objected.

These tests cover the missing half. They are about *naming* the gaps, not
refusing on them — see the note in `CoachingTurnService` for why enforcement
waits for evidence that the fields are actually being filled.
"""

from __future__ import annotations

import pytest

from hermes_coach.contracts.runtime_contract import CoachingStage
from hermes_coach.domain.stage_completeness import (
    MINIMUM_OPTIONS,
    REQUIRED_FIELDS,
    describe_missing,
    missing_for,
)


class TestNothingSaidYet:
    @pytest.mark.parametrize("stage", list(CoachingStage))
    def test_an_absent_snapshot_is_missing_everything(
        self, stage: CoachingStage
    ) -> None:
        """The state every session starts in, and the state that used to be
        indistinguishable from a finished step."""
        assert missing_for(stage, None) == tuple(
            label for _, label in REQUIRED_FIELDS[stage]
        )

    @pytest.mark.parametrize("stage", list(CoachingStage))
    def test_an_empty_snapshot_is_the_same_as_none(
        self, stage: CoachingStage
    ) -> None:
        assert missing_for(stage, {}) == missing_for(stage, None)


class TestAFilledFormIsNotAnAnsweredQuestion:
    """A model asked to fill a form will fill it.

    Blank strings, zeros and empty lists are what a step looks like when it was
    never worked through, and treating them as answers is how a completeness
    check passes on a step nobody did.
    """

    @pytest.mark.parametrize("empty", ["", "   ", None, False, [], {}])
    def test_a_hollow_value_does_not_count_as_said(self, empty) -> None:
        assert "điều bạn mang theo" in missing_for(
            CoachingStage.REVIEW, {"takeaway": empty}
        )

    def test_real_words_do_count(self) -> None:
        assert missing_for(CoachingStage.REVIEW, {"takeaway": "tôi hay so sánh"}) == ()

    def test_a_commitment_score_of_zero_is_not_a_score(self) -> None:
        """0 is outside the 1–10 scale, and a model filling a required int
        reaches for it."""
        missing = missing_for(
            CoachingStage.WILL,
            {"chosen_action": "chạy", "due_at": "thứ Năm", "commitment_score": 0},
        )
        assert "mức cam kết 1–10" in missing

    @pytest.mark.parametrize("score", [0, 11, -1, True, "8", 8.5])
    def test_a_score_outside_the_scale_is_not_a_score(self, score) -> None:
        """`True` is an int in Python, and "8" is what a model returns when it
        is filling text fields. Neither is a commitment."""
        assert "mức cam kết 1–10" in missing_for(
            CoachingStage.WILL,
            {"chosen_action": "chạy", "due_at": "thứ Năm", "commitment_score": score},
        )

    @pytest.mark.parametrize("score", [1, 8, 10])
    def test_a_score_on_the_scale_counts(self, score) -> None:
        assert missing_for(
            CoachingStage.WILL,
            {"chosen_action": "chạy", "due_at": "thứ Năm", "commitment_score": score},
        ) == ()

    def test_a_real_score_counts(self) -> None:
        assert missing_for(
            CoachingStage.WILL,
            {"chosen_action": "chạy", "due_at": "thứ Năm", "commitment_score": 8},
        ) == ()


class TestOptionsNeedsMoreThanOne:
    def test_one_option_is_not_a_choice(self) -> None:
        """The framework says a Coachee must generate a genuine alternative.
        Choosing between one thing and nothing is not choosing."""
        missing = missing_for(
            CoachingStage.OPTIONS, {"options": ["để giày cạnh giường"], "chosen": "a"}
        )
        assert missing == (f"ít nhất {MINIMUM_OPTIONS} lựa chọn khác nhau",)

    def test_two_options_and_a_choice_is_enough(self) -> None:
        assert (
            missing_for(
                CoachingStage.OPTIONS,
                {"options": ["giày cạnh giường", "chỉ tính phút"], "chosen": "cả hai"},
            )
            == ()
        )

    def test_options_without_a_choice_is_still_unfinished(self) -> None:
        missing = missing_for(
            CoachingStage.OPTIONS,
            {"options": ["giày cạnh giường", "chỉ tính phút"]},
        )
        assert missing == ("lựa chọn bạn chọn",)


class TestPartlyDone:
    def test_only_what_is_actually_missing_is_named(self) -> None:
        missing = missing_for(
            CoachingStage.GOAL,
            {
                "title": "chạy 3 buổi/tuần",
                "why_it_matters": "tôi muốn khoẻ lại",
                "success_evidence": "",
            },
        )
        assert missing == ("dấu hiệu nào cho biết đã đạt", "mốc thời gian")

    def test_extra_keys_the_model_invents_are_ignored(self) -> None:
        """The snapshot is free-shaped; only the named keys decide anything."""
        assert (
            missing_for(
                CoachingStage.REVIEW,
                {"takeaway": "tôi hay so sánh", "mood": "nhẹ nhõm"},
            )
            == ()
        )


class TestSayingItToAPerson:
    def test_nothing_missing_says_nothing(self) -> None:
        assert describe_missing(()) == ""

    def test_one_gap_reads_as_a_sentence(self) -> None:
        assert describe_missing(("mốc thời gian",)) == (
            "Bước này chưa nói tới mốc thời gian."
        )

    def test_several_gaps_read_as_a_sentence(self) -> None:
        """"Bước Will chưa đủ" helps nobody; naming them is the whole point."""
        assert describe_missing(("hành động cụ thể", "mốc thời gian", "mức cam kết")) == (
            "Bước này chưa nói tới hành động cụ thể, mốc thời gian và mức cam kết."
        )


class TestTheMergeRuleMatchesTheCompletenessRule:
    """Two functions decide what "said" means, and they must agree.

    `CoachingTurnService._is_worth_keeping` decides whether a value survives
    into the stored snapshot; `stage_completeness._is_present` decides whether
    it counts as answered. If they ever disagree, a value is either stored and
    ignored or dropped and demanded — both of which look like the snapshot
    silently losing things.
    """

    @pytest.mark.parametrize(
        "value", ["", "   ", None, False, [], {}, "x", 0, 8, True, ["a"]]
    )
    def test_they_agree_on_every_shape(self, value) -> None:
        from hermes_coach.application.coaching_turn_service import _is_worth_keeping
        from hermes_coach.domain.stage_completeness import _is_present

        assert _is_worth_keeping(value) is _is_present(value)
