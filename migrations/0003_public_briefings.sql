PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS public_briefings (
  id TEXT PRIMARY KEY,
  source_briefing_id TEXT NOT NULL,
  briefing_date TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  subtitle TEXT NOT NULL DEFAULT '',
  one_line_signal TEXT NOT NULL DEFAULT '',
  content_json TEXT NOT NULL,
  source_generated_at TEXT NOT NULL,
  published_at TEXT NOT NULL,
  FOREIGN KEY (source_briefing_id) REFERENCES briefings(id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX IF NOT EXISTS public_briefings_published_idx
  ON public_briefings(briefing_date DESC, published_at DESC);
