PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS briefings (
  id TEXT PRIMARY KEY,
  briefing_date TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  subtitle TEXT NOT NULL DEFAULT '',
  one_line_signal TEXT NOT NULL DEFAULT '',
  content_json TEXT NOT NULL,
  model TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE TABLE IF NOT EXISTS ideas (
  id TEXT PRIMARY KEY,
  source_briefing_id TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('new_project', 'project_edit')),
  related_project TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  why_now TEXT NOT NULL DEFAULT '',
  smallest_version TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'inbox'
    CHECK (status IN ('inbox', 'kept', 'build_next', 'building', 'shipped', 'hold', 'archived')),
  destination TEXT NOT NULL DEFAULT 'undecided'
    CHECK (destination IN ('undecided', 'architecture_chat', 'codex', 'hold')),
  pinned INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
  tags_json TEXT NOT NULL DEFAULT '[]',
  handoff_prompt TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (source_briefing_id) REFERENCES briefings(id) ON DELETE SET NULL
) STRICT;

CREATE INDEX IF NOT EXISTS ideas_status_idx ON ideas(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS ideas_pinned_idx ON ideas(pinned DESC, updated_at DESC);

CREATE TABLE IF NOT EXISTS generation_runs (
  id TEXT PRIMARY KEY,
  requested_by TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
  briefing_date TEXT NOT NULL,
  model TEXT NOT NULL,
  error_message TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL,
  completed_at TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
) STRICT;

INSERT OR IGNORE INTO settings (key, value, updated_at)
VALUES
  ('briefing_name', 'Daily Personal Briefing', CURRENT_TIMESTAMP),
  ('briefing_time', '08:00', CURRENT_TIMESTAMP),
  ('briefing_timezone', 'America/Chicago', CURRENT_TIMESTAMP);
