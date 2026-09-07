"""Coach repositories.

Requirement families: `HC-DATA-*`, `HC-RECORDS`, `HC-MEMORY`, `HC-PRIVACY`.

`ACTIVE_SCOPE_REPOSITORIES` is the registry of repositories whose reads must
exclude Trash, expired and unconfirmed rows. The active-scope test suite is
driven off this mapping, so adding a repository here without adding its case
fails the suite rather than quietly widening what can leak.

`career_snapshot` and `trash_entry` are absent on purpose: snapshots are
append-only history with no active/deleted distinction, and the Trash table is
the exclusion mechanism itself.
"""

from __future__ import annotations

from hermes_coach.infrastructure.repositories.candidate_repository import (
    CandidateRepository,
)
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.memory_repository import MemoryRepository
from hermes_coach.infrastructure.repositories.session_message_repository import (
    SessionMessageRepository,
)


ACTIVE_SCOPE_REPOSITORIES: dict[str, type] = {
    GoalRepository.entity_type: GoalRepository,
    SessionMessageRepository.entity_type: SessionMessageRepository,
    CandidateRepository.entity_type: CandidateRepository,
    MemoryRepository.entity_type: MemoryRepository,
}

__all__ = [
    "ACTIVE_SCOPE_REPOSITORIES",
    "CandidateRepository",
    "GoalRepository",
    "MemoryRepository",
    "SessionMessageRepository",
]
