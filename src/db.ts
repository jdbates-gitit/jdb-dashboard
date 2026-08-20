export type IdeaStatus =
  | "inbox"
  | "kept"
  | "build_next"
  | "building"
  | "shipped"
  | "hold"
  | "archived";

export type IdeaDestination = "undecided" | "architecture_chat" | "codex" | "hold";

export interface StoredBriefingRow {
  id: string;
  briefing_date: string;
  title: string;
  subtitle: string;
  one_line_signal: string;
  content_json: string;
  model: string;
  generated_at: string;
}

export interface StoredIdeaRow {
  id: string;
  source_briefing_id: string | null;
  kind: "new_project" | "project_edit";
  related_project: string;
  title: string;
  summary: string;
  why_now: string;
  smallest_version: string;
  status: IdeaStatus;
  destination: IdeaDestination;
  pinned: number;
  tags_json: string;
  handoff_prompt: string;
  created_at: string;
  updated_at: string;
}

export interface GeneratedBriefing {
  title: string;
  subtitle: string;
  one_line_signal: string;
  sections: Array<{
    key: string;
    title: string;
    headline: string;
    body: string;
    why_it_matters: string;
    takeaway: string;
    sources: Array<{ title: string; url: string }>;
  }>;
  ideas: Array<{
    kind: "new_project" | "project_edit";
    related_project: string;
    title: string;
    summary: string;
    why_now: string;
    smallest_version: string;
    tags: string[];
    destination: IdeaDestination;
  }>;
}

function parseBriefing(row: StoredBriefingRow | null): Record<string, unknown> | null {
  if (!row) return null;
  return {
    id: row.id,
    date: row.briefing_date,
    title: row.title,
    subtitle: row.subtitle,
    oneLineSignal: row.one_line_signal,
    model: row.model,
    generatedAt: row.generated_at,
    ...JSON.parse(row.content_json),
  };
}

function parseIdea(row: StoredIdeaRow): Record<string, unknown> {
  return {
    id: row.id,
    sourceBriefingId: row.source_briefing_id,
    kind: row.kind,
    relatedProject: row.related_project,
    title: row.title,
    summary: row.summary,
    whyNow: row.why_now,
    smallestVersion: row.smallest_version,
    status: row.status,
    destination: row.destination,
    pinned: Boolean(row.pinned),
    tags: JSON.parse(row.tags_json),
    handoffPrompt: row.handoff_prompt,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export async function getLatestBriefing(db: D1Database): Promise<Record<string, unknown> | null> {
  const row = await db
    .prepare("SELECT * FROM briefings ORDER BY briefing_date DESC, generated_at DESC LIMIT 1")
    .first<StoredBriefingRow>();
  return parseBriefing(row);
}

export async function getBriefingByDate(
  db: D1Database,
  briefingDate: string,
): Promise<Record<string, unknown> | null> {
  const row = await db
    .prepare("SELECT * FROM briefings WHERE briefing_date = ? LIMIT 1")
    .bind(briefingDate)
    .first<StoredBriefingRow>();
  return parseBriefing(row);
}

export async function listBriefings(db: D1Database, limit: number): Promise<Record<string, unknown>[]> {
  const result = await db
    .prepare("SELECT * FROM briefings ORDER BY briefing_date DESC, generated_at DESC LIMIT ?")
    .bind(limit)
    .all<StoredBriefingRow>();
  return result.results.map((row) => parseBriefing(row)!).filter(Boolean);
}

export async function listIdeas(
  db: D1Database,
  status?: IdeaStatus,
): Promise<Record<string, unknown>[]> {
  const query = status
    ? db
        .prepare(
          "SELECT * FROM ideas WHERE status = ? ORDER BY pinned DESC, updated_at DESC, created_at DESC",
        )
        .bind(status)
    : db.prepare("SELECT * FROM ideas ORDER BY pinned DESC, updated_at DESC, created_at DESC");
  const result = await query.all<StoredIdeaRow>();
  return result.results.map(parseIdea);
}

export async function getRecentContext(db: D1Database): Promise<{
  ideaTitles: string[];
  signals: string[];
}> {
  const [ideas, briefings] = await Promise.all([
    db.prepare("SELECT title FROM ideas ORDER BY created_at DESC LIMIT 30").all<{ title: string }>(),
    db
      .prepare("SELECT one_line_signal FROM briefings ORDER BY briefing_date DESC LIMIT 7")
      .all<{ one_line_signal: string }>(),
  ]);
  return {
    ideaTitles: ideas.results.map((row) => row.title),
    signals: briefings.results.map((row) => row.one_line_signal),
  };
}

function buildHandoffPrompt(idea: GeneratedBriefing["ideas"][number]): string {
  const destination = idea.destination === "codex" ? "Codex implementation" : "architecture review";
  return [
    `Prepare this idea for ${destination}: ${idea.title}.`,
    idea.related_project ? `Related project: ${idea.related_project}.` : "",
    `Concept: ${idea.summary}`,
    `Why now: ${idea.why_now}`,
    `Smallest useful version: ${idea.smallest_version}`,
    "Preserve existing decisions, keep the scope narrow, and identify any security or maintenance risks before implementation.",
  ]
    .filter(Boolean)
    .join("\n\n");
}

export async function saveGeneratedBriefing(
  db: D1Database,
  briefingDate: string,
  generated: GeneratedBriefing,
  model: string,
): Promise<string> {
  const briefingId = crypto.randomUUID();
  const now = new Date().toISOString();
  const statements = [
    db
      .prepare(
        `INSERT INTO briefings
          (id, briefing_date, title, subtitle, one_line_signal, content_json, model, generated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(briefing_date) DO UPDATE SET
          title = excluded.title,
          subtitle = excluded.subtitle,
          one_line_signal = excluded.one_line_signal,
          content_json = excluded.content_json,
          model = excluded.model,
          generated_at = excluded.generated_at`,
      )
      .bind(
        briefingId,
        briefingDate,
        generated.title,
        generated.subtitle,
        generated.one_line_signal,
        JSON.stringify({ sections: generated.sections }),
        model,
        now,
      ),
    db
      .prepare(
        `DELETE FROM ideas
         WHERE source_briefing_id = (SELECT id FROM briefings WHERE briefing_date = ?)
           AND status = 'inbox'`,
      )
      .bind(briefingDate),
  ];

  for (const idea of generated.ideas) {
    statements.push(
      db
        .prepare(
          `INSERT INTO ideas
            (id, source_briefing_id, kind, related_project, title, summary, why_now,
             smallest_version, status, destination, pinned, tags_json, handoff_prompt,
             created_at, updated_at)
           VALUES (?, (SELECT id FROM briefings WHERE briefing_date = ?), ?, ?, ?, ?, ?, ?,
                   'inbox', ?, 0, ?, ?, ?, ?)`,
        )
        .bind(
          crypto.randomUUID(),
          briefingDate,
          idea.kind,
          idea.related_project,
          idea.title,
          idea.summary,
          idea.why_now,
          idea.smallest_version,
          idea.destination,
          JSON.stringify(idea.tags),
          buildHandoffPrompt(idea),
          now,
          now,
        ),
    );
  }

  await db.batch(statements);
  return briefingId;
}

export async function updateIdea(
  db: D1Database,
  id: string,
  update: { status?: IdeaStatus; destination?: IdeaDestination; pinned?: boolean },
): Promise<Record<string, unknown> | null> {
  const existing = await db.prepare("SELECT * FROM ideas WHERE id = ?").bind(id).first<StoredIdeaRow>();
  if (!existing) return null;

  const status = update.status ?? existing.status;
  const destination = update.destination ?? existing.destination;
  const pinned = update.pinned === undefined ? existing.pinned : Number(update.pinned);
  const now = new Date().toISOString();

  await db
    .prepare(
      "UPDATE ideas SET status = ?, destination = ?, pinned = ?, updated_at = ? WHERE id = ?",
    )
    .bind(status, destination, pinned, now, id)
    .run();

  const row = await db.prepare("SELECT * FROM ideas WHERE id = ?").bind(id).first<StoredIdeaRow>();
  return row ? parseIdea(row) : null;
}

export async function startGenerationRun(
  db: D1Database,
  requestedBy: string,
  briefingDate: string,
  model: string,
): Promise<string> {
  const id = crypto.randomUUID();
  await db
    .prepare(
      `INSERT INTO generation_runs
        (id, requested_by, status, briefing_date, model, started_at)
       VALUES (?, ?, 'running', ?, ?, ?)`,
    )
    .bind(id, requestedBy, briefingDate, model, new Date().toISOString())
    .run();
  return id;
}

export async function finishGenerationRun(
  db: D1Database,
  id: string,
  status: "completed" | "failed" | "skipped",
  errorMessage = "",
): Promise<void> {
  await db
    .prepare(
      "UPDATE generation_runs SET status = ?, error_message = ?, completed_at = ? WHERE id = ?",
    )
    .bind(status, errorMessage.slice(0, 1000), new Date().toISOString(), id)
    .run();
}
