PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chat_threads (
    thread_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    last_focus_entity_id TEXT,
    contract_version TEXT NOT NULL DEFAULT '2.0',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES chat_threads(thread_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    run_id TEXT,
    status TEXT NOT NULL DEFAULT 'committed',
    structured_json TEXT,
    idempotency_key TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (thread_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS qa_runs (
    run_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES chat_threads(thread_id) ON DELETE CASCADE,
    trace_id TEXT NOT NULL,
    user_message_id TEXT NOT NULL REFERENCES chat_messages(message_id),
    assistant_message_id TEXT REFERENCES chat_messages(message_id),
    status TEXT NOT NULL,
    intent TEXT,
    prompt_versions_json TEXT NOT NULL DEFAULT '{}',
    budget_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT,
    error_json TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    error_code TEXT
);

CREATE TABLE IF NOT EXISTS chat_citations (
    citation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES qa_runs(run_id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL,
    tool_call_id TEXT,
    fact_ids_json TEXT NOT NULL,
    label TEXT NOT NULL,
    locator_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES qa_runs(run_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '2.0',
    title TEXT NOT NULL,
    data_uri TEXT,
    data_hash TEXT NOT NULL,
    data_json TEXT NOT NULL,
    fact_ids_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_events (
    event_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES chat_threads(thread_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES qa_runs(run_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_created ON chat_messages(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_events_thread_event ON chat_events(thread_id, event_id);
CREATE INDEX IF NOT EXISTS idx_chat_events_run_sequence ON chat_events(run_id, sequence);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_events_thread_sequence ON chat_events(thread_id, sequence);
