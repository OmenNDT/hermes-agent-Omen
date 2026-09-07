from __future__ import annotations

from enum import StrEnum


class FunnelStage(StrEnum):
    OPEN = "open"
    DISCOVER = "discover_5w1h"
    CLARIFY = "clarify"
    CLOSE = "close_yes_no"


class NoveltyStatus(StrEnum):
    DUPLICATE = "duplicate"
    SAME_MECHANISM = "same_mechanism"
    NEEDS_CLARIFICATION = "needs_clarification"
    NOT_COACHEE_OWNED = "not_coachee_owned"
    MATERIALLY_NEW = "materially_new"


class RecoveryMove(StrEnum):
    RECHECK_GOAL = "recheck_goal"
    RECHECK_REALITY = "recheck_reality"
    REFRAME_QUESTION = "reframe_question"
    CHANGE_PERSPECTIVE = "change_perspective"
    ASK_WHAT_ELSE = "ask_what_else"
    EVOKE_EXPERIENCE = "evoke_experience"
    ALLOW_SILENCE = "allow_silence"
    DECOMPOSE = "decompose"
    CREATE_OPEN_SPACE = "create_open_space"
    RETURN_TO_REALITY = "return_to_reality"
    ADD_INGREDIENTS = "add_values_resources_support"
    HOLD_COACH_ROLE = "hold_coach_role"


class DecompositionLayer(StrEnum):
    NAME_TANGLE = "name_tangle"
    SEPARATE_PARTS = "separate_parts"
    CHOOSE_PART = "choose_part"
    SEPARATE_FACTS = "separate_facts"
    EMOTION_AND_NEED = "emotion_and_need"
    INFLUENCE = "influence"
    TIME = "time"
    ACTION_ELEMENT = "action_element"


class SafetyState(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    POSSIBLE_CRISIS = "possible_crisis"
    URGENT = "urgent"


class SafetyOutputMode(StrEnum):
    COACHING_QUESTION = "coaching_question"
    PERMISSION_QUESTION = "permission_question"
    SAFETY_CHECK = "safety_check"
    BLOCKED = "blocked"
    DIRECT_SAFETY_GUIDANCE = "direct_safety_guidance"

