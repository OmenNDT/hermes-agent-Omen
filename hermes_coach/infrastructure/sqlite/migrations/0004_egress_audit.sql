-- Egress audit: evidence that data left, and which items it named.
-- Payload-free by construction — there is no content column to fill.

CREATE TABLE internal_egress_audit (
    manifest_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES coachee_profile(id),
    session_id TEXT NOT NULL REFERENCES coaching_session(id),
    turn_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    purpose TEXT NOT NULL,
    requirement TEXT NOT NULL CHECK (requirement IN ('required', 'optional')),
    categories TEXT NOT NULL,
    consent_scope TEXT NOT NULL,
    consent_version TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('allowed', 'blocked')),
    -- Provider retention is display metadata with its own version, so a later
    -- policy check can supersede it without rewriting the manifest.
    retention_status TEXT NOT NULL CHECK (
        retention_status IN ('documented', 'unknown', 'not_applicable')
    ),
    retention_label TEXT NOT NULL,
    retention_source_url TEXT,
    retention_source_checked_at TEXT,
    retention_version TEXT NOT NULL
);

CREATE INDEX index_egress_audit_session
    ON internal_egress_audit (session_id, created_at);

-- One row per item named in the manifest: local id and category only.
CREATE TABLE internal_egress_item (
    id TEXT PRIMARY KEY,
    manifest_id TEXT NOT NULL REFERENCES internal_egress_audit(manifest_id),
    local_id TEXT NOT NULL,
    category TEXT NOT NULL CHECK (
        category IN ('current_turn', 'selected_profile', 'selected_memory',
                     'coaching_state', 'candidate_record')
    ),
    requirement TEXT NOT NULL CHECK (requirement IN ('required', 'optional')),
    position INTEGER NOT NULL
);

CREATE UNIQUE INDEX index_egress_item_order
    ON internal_egress_item (manifest_id, position);
