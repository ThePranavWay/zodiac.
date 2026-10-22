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
