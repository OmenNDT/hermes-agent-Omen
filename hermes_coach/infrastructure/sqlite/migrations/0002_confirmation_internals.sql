-- Internal tables backing durable confirmation.
-- These are Coach machinery, not canonical product entities: they hold ids,
-- digests and timestamps, never record content.

-- A backend-issued, short-lived, single-use confirmation challenge.
-- Only the SHA-256 digest is stored: the raw token lives in the UI for the
-- couple of minutes it is valid, and a database copy would let anyone who can
-- read the file replay a confirmation.
CREATE TABLE internal_confirmation_intent (
    token_digest TEXT PRIMARY KEY,
    local_user_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES coaching_session(id),
    candidate_id TEXT NOT NULL REFERENCES candidate_record(id),
    action TEXT NOT NULL CHECK (action IN ('accept', 'edit', 'discard')),
    edited_payload_digest TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
);

-- At most one usable intent per candidate: re-rendering the confirmation UI
-- supersedes the previous token instead of leaving two that both work.
CREATE UNIQUE INDEX index_confirmation_intent_live_candidate
    ON internal_confirmation_intent (candidate_id)
    WHERE consumed_at IS NULL;

CREATE INDEX index_confirmation_intent_expiry
    ON internal_confirmation_intent (expires_at);

-- One row per applied confirmation command. The UNIQUE command_id is the
-- durable replay guard; revision makes re-confirmation additive rather than a
-- silent rewrite of the earlier provenance.
CREATE TABLE internal_confirmation_audit (
    id TEXT PRIMARY KEY,
    command_id TEXT NOT NULL UNIQUE,
    candidate_id TEXT NOT NULL REFERENCES candidate_record(id),
    revision INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('accept', 'edit', 'discard')),
    official_record_type TEXT,
    official_record_id TEXT,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX index_confirmation_audit_revision
    ON internal_confirmation_audit (candidate_id, revision);
