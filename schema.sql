CREATE TABLE IF NOT EXISTS zs_event (
    id INTEGER PRIMARY KEY CHECK (id=1),
    registration_open INTEGER NOT NULL DEFAULT 0 CHECK (registration_open IN (0,1)),
    generation INTEGER NOT NULL DEFAULT 1
);
INSERT INTO zs_event(id,registration_open,generation) VALUES(1,0,1) ON CONFLICT(id) DO NOTHING;
CREATE TABLE IF NOT EXISTS zs_entries (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('solo','team')),
    name TEXT NOT NULL,
    started DOUBLE PRECISION NOT NULL,
    last_seen DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS zs_members (
    admission TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES zs_entries(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    class_name TEXT NOT NULL,
    section TEXT NOT NULL,
    password_hash TEXT,
    is_creator INTEGER NOT NULL DEFAULT 0,
    last_seen DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS zs_members_entry ON zs_members(entry_id);
CREATE TABLE IF NOT EXISTS zs_sessions (
    token_hash TEXT PRIMARY KEY,
    admission TEXT NOT NULL REFERENCES zs_members(admission) ON DELETE CASCADE,
    expires DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS zs_sessions_member ON zs_sessions(admission);
CREATE TABLE IF NOT EXISTS zs_tokens (
    token_hash TEXT PRIMARY KEY,
    admission TEXT NOT NULL REFERENCES zs_members(admission) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('activate','reset')),
    expires DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS zs_completions (
    entry_id TEXT NOT NULL REFERENCES zs_entries(id) ON DELETE CASCADE,
    level_id INTEGER NOT NULL CHECK(level_id BETWEEN 1 AND 4),
    completed_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY(entry_id,level_id)
);
CREATE TABLE IF NOT EXISTS zs_notes (
    entry_id TEXT PRIMARY KEY REFERENCES zs_entries(id) ON DELETE CASCADE,
    body TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 0,
    updated_at DOUBLE PRECISION NOT NULL,
    updated_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS zs_limits (
    bucket_key TEXT PRIMARY KEY,
    window_started DOUBLE PRECISION NOT NULL,
    attempts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS zs_audit (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    subject TEXT NOT NULL,
    at DOUBLE PRECISION NOT NULL
);

-- Additive: preserves existing accounts, original completions and notes.
-- Run during a submission maintenance window before switching app versions.
CREATE TABLE IF NOT EXISTS zs_finishes (
    entry_id TEXT PRIMARY KEY REFERENCES zs_entries(id) ON DELETE CASCADE,
    finished_at DOUBLE PRECISION NOT NULL,
    finish_order INTEGER NOT NULL UNIQUE CHECK (finish_order > 0)
);
-- Import any already-completed four-level entries, once, oldest finish first.
-- Previously assigned places are never changed when this is run again.
INSERT INTO zs_finishes(entry_id,finished_at,finish_order)
SELECT c.entry_id,MAX(c.completed_at),
    (SELECT COALESCE(MAX(finish_order),0) FROM zs_finishes) +
    ROW_NUMBER() OVER (ORDER BY MAX(c.completed_at),e.started,e.id)
FROM zs_completions c JOIN zs_entries e ON e.id=c.entry_id
WHERE c.entry_id NOT IN (SELECT entry_id FROM zs_finishes)
GROUP BY c.entry_id,e.started,e.id
HAVING COUNT(DISTINCT c.level_id)=4
ON CONFLICT(entry_id) DO NOTHING;
