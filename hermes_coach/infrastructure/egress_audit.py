"""Persistence for the Phase 1 egress manifest.

Requirement families: `HC-PRIVACY`; sources `SRC-026`, `SRC-091`.

`EgressManifest` already defines what an audit entry is; this only stores and
reads it. There is no content column, so "the audit holds no payload" is a
property of the schema rather than a rule someone has to remember.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from hermes_coach.contracts.egress_contract import (
    EgressCategory,
    EgressItemRef,
    EgressManifest,
    EgressRequirement,
    ProviderRetentionDisclosure,
    ProviderRetentionStatus,
)
from hermes_coach.domain.clock import parse, render
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


EgressDecision = Literal["allowed", "blocked"]

_CATEGORY_SEPARATOR = ","


class EgressAuditRepository:
    def __init__(self, database: CoachDatabase) -> None:
        self._database = database

    def record(self, manifest: EgressManifest, *, decision: EgressDecision) -> None:
        retention = manifest.provider_retention
        with self._database.transaction():
            self._database.connection.execute(
                "INSERT INTO internal_egress_audit "
                "(manifest_id, profile_id, session_id, turn_id, created_at, provider, "
                "model, purpose, requirement, categories, consent_scope, "
                "consent_version, decision, retention_status, retention_label, "
                "retention_source_url, retention_source_checked_at, retention_version) "
                "VALUES (:manifest_id, :profile_id, :session_id, :turn_id, :created_at, "
                ":provider, :model, :purpose, :requirement, :categories, "
                ":consent_scope, :consent_version, :decision, :retention_status, "
                ":retention_label, :retention_source_url, "
                ":retention_source_checked_at, :retention_version)",
                {
                    "manifest_id": manifest.manifest_id,
                    "profile_id": manifest.profile_id,
                    "session_id": manifest.session_id,
                    "turn_id": manifest.turn_id,
                    "created_at": render(manifest.created_at),
                    "provider": manifest.provider,
                    "model": manifest.model,
                    "purpose": manifest.purpose,
                    "requirement": manifest.requirement.value,
                    "categories": _CATEGORY_SEPARATOR.join(
                        category.value for category in manifest.categories
                    ),
                    "consent_scope": manifest.consent_scope,
                    "consent_version": manifest.consent_version,
                    "decision": decision,
                    "retention_status": retention.status.value,
                    "retention_label": retention.label,
                    "retention_source_url": retention.source_url,
                    "retention_source_checked_at": (
                        render(retention.source_checked_at)
                        if retention.source_checked_at
                        else None
                    ),
                    "retention_version": retention.version,
                },
            )
            for position, ref in enumerate(manifest.item_refs):
                self._database.connection.execute(
                    "INSERT INTO internal_egress_item "
                    "(id, manifest_id, local_id, category, requirement, position) "
                    "VALUES (:id, :manifest_id, :local_id, :category, :requirement, "
                    ":position)",
                    {
                        "id": str(uuid.uuid4()),
                        "manifest_id": manifest.manifest_id,
                        "local_id": ref.local_id,
                        "category": ref.category.value,
                        "requirement": ref.requirement.value,
                        "position": position,
                    },
                )

    def for_session(self, session_id: str) -> tuple[EgressManifest, ...]:
        rows = self._database.connection.execute(
            "SELECT * FROM internal_egress_audit WHERE session_id = :session_id "
            "ORDER BY created_at, manifest_id",
            {"session_id": session_id},
        ).fetchall()
        return tuple(self._to_manifest(dict(row)) for row in rows)

    def _to_manifest(self, row: dict) -> EgressManifest:
        items = self._database.connection.execute(
            "SELECT * FROM internal_egress_item WHERE manifest_id = :manifest_id "
            "ORDER BY position",
            {"manifest_id": row["manifest_id"]},
        ).fetchall()
        return EgressManifest(
            manifest_id=row["manifest_id"],
            profile_id=row["profile_id"],
            session_id=row["session_id"],
            turn_id=row["turn_id"],
            created_at=parse(row["created_at"]),
            provider=row["provider"],
            model=row["model"],
            purpose=row["purpose"],
            requirement=EgressRequirement(row["requirement"]),
            categories=tuple(
                EgressCategory(value)
                for value in row["categories"].split(_CATEGORY_SEPARATOR)
                if value
            ),
            item_refs=tuple(
                EgressItemRef(
                    local_id=item["local_id"],
                    category=EgressCategory(item["category"]),
                    requirement=EgressRequirement(item["requirement"]),
                )
                for item in items
            ),
            consent_scope=row["consent_scope"],
            consent_version=row["consent_version"],
            provider_retention=ProviderRetentionDisclosure(
                status=ProviderRetentionStatus(row["retention_status"]),
                label=row["retention_label"],
                source_url=row["retention_source_url"],
                source_checked_at=_optional_moment(
                    row["retention_source_checked_at"]
                ),
                version=row["retention_version"],
            ),
        )


def _optional_moment(value: str | None) -> datetime | None:
    return parse(value) if value else None
