"""User-initiated export.

Requirement families: `HC-PRIVACY`; sources `SRC-026`, `SRC-072`, `SRC-091`.

Export gives the Coachee their own records with provenance, status and
timestamps. It carries the unencrypted-at-rest disclosure with the file, since
an exported copy outlives the UI that explained it.

No API key or internal secret is written. The database is not supposed to hold
one, but export is the moment data leaves the machine in bulk, so any value that
looks like a credential is redacted here rather than trusted to be absent.
Backup is Phase 7.
"""

from __future__ import annotations

import re
from typing import Any

from hermes_coach.infrastructure.repositories.consent_repository import (
    ConsentRepository,
)
from hermes_coach.infrastructure.repositories.goal_repository import GoalRepository
from hermes_coach.infrastructure.repositories.insight_repository import (
    InsightRepository,
)
from hermes_coach.infrastructure.repositories.memory_repository import MemoryRepository
from hermes_coach.infrastructure.repositories.session_message_repository import (
    SessionMessageRepository,
)
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


DISCLOSURE_VERSION = "2026-01"

REDACTED = "[redacted: looks like a credential]"

# Deliberately broad. A false positive costs the Coachee one line of their own
# text in an export they can regenerate; a false negative leaks a live secret.
_CREDENTIAL_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}", re.IGNORECASE),
    re.compile(r"\bapi[_\-]?key\b", re.IGNORECASE),
    re.compile(r"\bbearer\s+\S+", re.IGNORECASE),
    re.compile(r"\bauthorization\b", re.IGNORECASE),
)


class ExportService:
    def __init__(self, database: CoachDatabase, *, profile_id: str) -> None:
        self._database = database
        self._profile_id = profile_id
        self._redactions = 0

    def to_json(self, *, now: str) -> dict[str, Any]:
        self._redactions = 0
        connection = self._database.connection
        memory_repository = MemoryRepository(connection)

        goals = [
            self._clean(goal.model_dump())
            for goal in GoalRepository(connection).list_active(self._profile_id)
        ]
        memory = []
        for item in memory_repository.list_active():
            entry = self._clean(item.model_dump())
            entry["provenance"] = [
                self._clean(row.model_dump())
                for row in memory_repository.provenance_for(item.id)
            ]
            memory.append(entry)
        insights = [
            self._clean(row.model_dump())
            for row in InsightRepository(connection).list_active()
        ]
        consent_events = [
            self._clean(event.model_dump())
            for event in ConsentRepository(connection).all_for_profile(
                self._profile_id
            )
        ]

        return {
            "exported_at": now,
            "profile_id": self._profile_id,
            "disclosure": self._disclosure(),
            "goals": goals,
            "memory": memory,
            "insights": insights,
            "consent_events": consent_events,
            "redacted_count": self._redactions,
        }

    def session_to_json(self, session_id: str, *, now: str) -> dict[str, Any]:
        """One session's transcript, redacted, with the disclosure attached.

        Separate from `to_json`, which exports what the system concluded —
        goals, memory, insights. This exports what was actually said, which is
        the thing a Coachee asks to keep.

        Redacted on the same terms as every other export. The transcript is the
        Coachee's own typed words, so a credential can only get in here by being
        pasted in; that is exactly the case worth catching, because an exported
        copy travels further than the database ever does.

        Reads through `list_active`, so a line the Coachee deleted stays deleted
        and an expired one stays gone — export is not a way around the scope
        every other read obeys.
        """
        self._redactions = 0
        messages = SessionMessageRepository(self._database.connection).list_active(
            session_id, now=now
        )
        return {
            "session_id": session_id,
            "exported_at": now,
            "profile_id": self._profile_id,
            "disclosure": self._disclosure(),
            "turns": [
                {
                    "voice": row.role,
                    "content": self._redact(row.content),
                    "stage": row.coaching_stage,
                    "created_at": row.created_at,
                }
                for row in messages
            ],
            "redacted_count": self._redactions,
        }

    def to_markdown(self, *, now: str) -> str:
        payload = self.to_json(now=now)
        lines = [
            "# Hermes Coach export",
            "",
            f"Xuất lúc: {payload['exported_at']}",
            f"Mã hoá khi lưu: không (phiên bản công bố {DISCLOSURE_VERSION})",
            "",
            "## Mục tiêu",
        ]
        for goal in payload["goals"]:
            lines.append(
                f"- {goal['title']} — trạng thái {goal['status']}, "
                f"xác nhận {goal['confirmed_at']}"
            )
        lines += ["", "## Ghi nhớ đã duyệt"]
        for item in payload["memory"]:
            lines.append(f"- {item['content']}")
            for row in item["provenance"]:
                lines.append(f"  - nguồn {row['source_type']} ({row['relation']})")
        lines += ["", "## Nhận thức"]
        for insight in payload["insights"]:
            lines.append(f"- {insight['content']}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _disclosure() -> dict[str, Any]:
        """Travels with every export, because the file outlives the screen."""
        return {
            "encrypted_at_rest": False,
            "note": (
                "Bản xuất và cơ sở dữ liệu Coach không được mã hoá. "
                "Người hoặc tiến trình có quyền đọc tệp đều đọc được nội dung."
            ),
            "version": DISCLOSURE_VERSION,
        }

    def _clean(self, values: dict[str, Any]) -> dict[str, Any]:
        return {key: self._redact(value) for key, value in values.items()}

    def _redact(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if any(pattern.search(value) for pattern in _CREDENTIAL_PATTERNS):
            self._redactions += 1
            return REDACTED
        return value
