-- Internal tables for retention and permanent purge.
-- Technical logs and notification history are temporary data on the same
-- 90-day clock as transcript. The purge audit is evidence that a deletion
-- happened and holds no deleted content.

CREATE TABLE internal_technical_log (
    id TEXT PRIMARY KEY,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX index_technical_log_age ON internal_technical_log (created_at);

CREATE TABLE internal_notification_history (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    delivered_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX index_notification_history_age
    ON internal_notification_history (created_at);

-- Payload-free: entity identity, why it went and when. Never the content.
CREATE TABLE internal_purge_audit (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('user_confirmed', 'retention')),
    control_id TEXT,
    dependents_removed INTEGER NOT NULL DEFAULT 0,
    purged_at TEXT NOT NULL
);

CREATE INDEX index_purge_audit_entity
    ON internal_purge_audit (entity_type, entity_id);
