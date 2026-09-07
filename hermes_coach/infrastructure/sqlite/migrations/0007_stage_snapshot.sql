-- Where a step's own content lives.
--
-- `stage_is_complete` has existed since the first commit and has never been
-- consulted: the snapshots it reads were populated by nothing, so every stage
-- read as empty and enforcing it would have meant no step could ever close.
-- The six-step structure has therefore rested entirely on the closing gate,
-- with no check that the step had anything in it.
--
-- One row per session and step, replaced as the step develops. Not append-only:
-- this is the current understanding of a step, not evidence of what was said —
-- `session_message` and `gate_confirmation` already hold that, and they are the
-- records an audit reads.
CREATE TABLE stage_snapshot (
    session_id TEXT NOT NULL REFERENCES coaching_session(id),
    stage TEXT NOT NULL CHECK (
        stage IN ('pre_coaching', 'goal', 'reality', 'options', 'will', 'review')
    ),
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (session_id, stage)
);
