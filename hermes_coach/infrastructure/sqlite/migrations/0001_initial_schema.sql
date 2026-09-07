-- Canonical Coach schema, version 1.
-- Transcribed from the proposal Data Model section. Column sets are exact:
-- storage convenience must not add a field to a canonical product entity.
-- Enum columns carry CHECK constraints only where the proposal closes the set.
-- Timestamps are ISO-8601 UTC strings.

CREATE TABLE coachee_profile (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    timezone TEXT,
    preferred_language TEXT,
    challenge_level TEXT,
    quiet_hours TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

-- Append-only, so change over time stays visible.
CREATE TABLE career_snapshot (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES coachee_profile(id),
    current_role TEXT,
    industry TEXT,
    experience_summary TEXT,
    strengths TEXT,
    constraints TEXT,
    career_vision TEXT,
    clarity_score INTEGER,
    satisfaction_score INTEGER,
    energy_score INTEGER,
    confidence_score INTEGER,
    balance_score INTEGER,
    follow_through_score INTEGER,
    captured_at TEXT NOT NULL
);

CREATE TABLE coaching_session (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    intention TEXT,
    success_definition TEXT,
    coaching_stage TEXT NOT NULL CHECK (
        coaching_stage IN ('pre_coaching', 'goal', 'reality', 'options', 'will', 'review')
    ),
    coachee_takeaway TEXT,
    summary TEXT,
    safety_state TEXT CHECK (
        safety_state IN ('normal', 'sensitive', 'possible_crisis', 'urgent')
    )
);

CREATE TABLE coachee_value (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES coachee_profile(id),
    name TEXT NOT NULL,
    description TEXT,
    priority INTEGER,
    source_session_id TEXT REFERENCES coaching_session(id),
    confirmed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE goal (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES coachee_profile(id),
    title TEXT NOT NULL,
    why_it_matters TEXT,
    desired_outcome TEXT,
    success_evidence TEXT,
    target_date TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('draft', 'active', 'paused', 'achieved', 'abandoned')
    ),
    priority INTEGER,
    source_session_id TEXT REFERENCES coaching_session(id),
    confirmed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

-- Commitment score is 1–10 by decision 2026-08-01.
CREATE TABLE commitment (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goal(id),
    action_text TEXT NOT NULL,
    due_at TEXT,
    evidence_definition TEXT,
    confidence_score INTEGER CHECK (
        confidence_score IS NULL OR confidence_score BETWEEN 1 AND 10
    ),
    status TEXT NOT NULL,
    source_session_id TEXT REFERENCES coaching_session(id),
    confirmed_at TEXT
);

CREATE TABLE evidence (
    id TEXT PRIMARY KEY,
    commitment_id TEXT NOT NULL REFERENCES commitment(id),
    kind TEXT NOT NULL,
    content_or_path TEXT,
    captured_at TEXT NOT NULL,
    user_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (user_confirmed IN (0, 1))
);

CREATE TABLE check_in (
    id TEXT PRIMARY KEY,
    commitment_id TEXT NOT NULL REFERENCES commitment(id),
    scheduled_at TEXT NOT NULL,
    completed_at TEXT,
    result TEXT,
    blockers TEXT,
    still_relevant INTEGER CHECK (still_relevant IS NULL OR still_relevant IN (0, 1)),
    rescheduled_to TEXT,
    review TEXT
);

-- Transcript layer: temporary data, purged at 90 days from created_at.
CREATE TABLE session_message (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES coaching_session(id),
    sequence_no INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (
        role IN ('coach', 'coachee', 'product_ui', 'safety_system')
    ),
    content TEXT NOT NULL,
    modality TEXT NOT NULL DEFAULT 'text' CHECK (modality IN ('text')),
    coaching_stage TEXT CHECK (
        coaching_stage IS NULL OR coaching_stage IN
        ('pre_coaching', 'goal', 'reality', 'options', 'will', 'review')
    ),
    question_kind TEXT,
    safety_state TEXT CHECK (
        safety_state IS NULL OR safety_state IN
        ('normal', 'sensitive', 'possible_crisis', 'urgent')
    ),
    created_at TEXT NOT NULL,
    expires_at TEXT,
    deleted_at TEXT
);

-- Pending candidates are temporary data; confirming one creates the official
-- record elsewhere. This table is never the structured truth.
CREATE TABLE candidate_record (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES coaching_session(id),
    record_type TEXT NOT NULL CHECK (
        record_type IN ('goal', 'insight', 'commitment', 'memory')
    ),
    payload_json TEXT NOT NULL,
    source_message_id TEXT REFERENCES session_message(id),
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'confirmed', 'edited', 'discarded')
    ),
    created_at TEXT NOT NULL,
    expires_at TEXT,
    resolved_at TEXT
);

-- Only a 'yes' immediately after a step's closing question opens a gate.
-- 'no' and 'unclear' are audit events. Rollback writes 'invalidated'.
CREATE TABLE gate_confirmation (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES coaching_session(id),
    step TEXT NOT NULL CHECK (
        step IN ('pre_coaching', 'goal', 'reality', 'options', 'will', 'review')
    ),
    revision INTEGER NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('yes', 'no', 'unclear', 'invalidated')),
    closing_question_message_id TEXT REFERENCES session_message(id),
    response_message_id TEXT REFERENCES session_message(id),
    confirmed_at TEXT,
    invalidated_at TEXT,
    invalidated_by_step TEXT CHECK (
        invalidated_by_step IS NULL OR invalidated_by_step IN
        ('pre_coaching', 'goal', 'reality', 'options', 'will', 'review')
    )
);

CREATE TABLE insight (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    topic TEXT,
    sensitivity TEXT,
    source_session_id TEXT REFERENCES coaching_session(id),
    goal_id TEXT REFERENCES goal(id),
    confirmed_at TEXT
);

-- A confirmed memory item never auto-expires: expires_at stays NULL and no
-- sentinel date is permitted. Deletion goes through the Trash lifecycle.
CREATE TABLE memory_item (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT,
    sensitivity TEXT,
    user_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (user_confirmed IN (0, 1)),
    expires_at TEXT CHECK (user_confirmed = 0 OR expires_at IS NULL),
    last_used_at TEXT
);

-- Only a manually entered memory may lack a source id.
CREATE TABLE memory_provenance (
    id TEXT PRIMARY KEY,
    memory_item_id TEXT NOT NULL REFERENCES memory_item(id),
    source_type TEXT NOT NULL CHECK (
        source_type IN ('session', 'message', 'goal', 'insight', 'manual')
    ),
    source_id TEXT CHECK (source_type = 'manual' OR source_id IS NOT NULL),
    source_session_id TEXT REFERENCES coaching_session(id),
    source_message_id TEXT REFERENCES session_message(id),
    relation TEXT NOT NULL CHECK (
        relation IN ('derived_from', 'confirmed_from', 'manually_entered')
    ),
    created_at TEXT NOT NULL
);

-- Append-only. Only a trusted UI control may write a row; effective consent is
-- the latest event for a normalized type/scope.
CREATE TABLE consent_event (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES coachee_profile(id),
    session_id TEXT REFERENCES coaching_session(id),
    consent_type TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('granted', 'declined', 'withdrawn')),
    scope_json TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'ui' CHECK (source IN ('ui')),
    ui_action TEXT NOT NULL CHECK (ui_action IN ('confirm', 'decline', 'withdraw')),
    control_id TEXT NOT NULL,
    evidence_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

-- The canonical deletion marker. An open entry hides its entity from every
-- active query, coaching context, egress, check-in and notification.
CREATE TABLE trash_entry (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES coachee_profile(id),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    deleted_at TEXT NOT NULL,
    purge_after TEXT NOT NULL,
    restored_at TEXT,
    purged_at TEXT,
    deletion_source TEXT NOT NULL CHECK (
        deletion_source IN ('item', 'session', 'goal', 'transcript', 'all_data')
    )
);

CREATE UNIQUE INDEX index_session_message_sequence
    ON session_message (session_id, sequence_no);

CREATE UNIQUE INDEX index_gate_confirmation_step_revision
    ON gate_confirmation (session_id, step, revision);

CREATE UNIQUE INDEX index_trash_entry_open_entity
    ON trash_entry (entity_type, entity_id)
    WHERE restored_at IS NULL AND purged_at IS NULL;

CREATE INDEX index_session_message_expiry ON session_message (expires_at);

CREATE INDEX index_candidate_record_active ON candidate_record (session_id, status);

CREATE INDEX index_candidate_record_expiry ON candidate_record (expires_at, status);

CREATE INDEX index_trash_entry_purge_due ON trash_entry (purge_after);

CREATE INDEX index_goal_active ON goal (profile_id, status);

CREATE INDEX index_commitment_goal ON commitment (goal_id, status);

CREATE INDEX index_check_in_due ON check_in (scheduled_at);

CREATE INDEX index_memory_provenance_item ON memory_provenance (memory_item_id);

CREATE INDEX index_consent_event_latest ON consent_event (profile_id, consent_type, created_at);
