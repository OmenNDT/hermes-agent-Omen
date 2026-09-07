-- Internal state for the RPC envelope: optimistic concurrency and replay.
-- Neither is a product entity, so neither touches the canonical tables.

-- A monotonic counter per session. It lives here rather than as a column on
-- coaching_session because the canonical entity has an exact field set and a
-- concurrency token is not one of its fields.
CREATE TABLE internal_session_revision (
    session_id TEXT PRIMARY KEY REFERENCES coaching_session(id),
    revision INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

-- One row per applied mutating command. The PRIMARY KEY is the replay guard:
-- a retried command finds its own earlier result instead of running twice.
CREATE TABLE internal_rpc_command (
    idempotency_key TEXT PRIMARY KEY,
    method TEXT NOT NULL,
    session_id TEXT,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX index_rpc_command_session ON internal_rpc_command (session_id);
