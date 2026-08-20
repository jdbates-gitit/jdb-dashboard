import { generateBriefing } from "./briefing";
import {
  finishGenerationRun,
  getBriefingByDate,
  getLatestBriefing,
  getRecentContext,
  listBriefings,
  listIdeas,
  saveGeneratedBriefing,
  startGenerationRun,
  updateIdea,
  type IdeaDestination,
  type IdeaStatus,
} from "./db";

const VALID_STATUSES = new Set<IdeaStatus>([
  "inbox",
  "kept",
  "build_next",
  "building",
  "shipped",
  "hold",
  "archived",
]);

const VALID_DESTINATIONS = new Set<IdeaDestination>([
  "undecided",
  "architecture_chat",
  "codex",
  "hold",
]);

function json(data: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json; charset=utf-8");
  headers.set("Cache-Control", "no-store");
  headers.set("X-Content-Type-Options", "nosniff");
  return Response.json(data, { ...init, headers });
}

function localDate(timeZone: string, date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const map = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${map.year}-${map.month}-${map.day}`;
}

function localHour(timeZone: string, date = new Date()): number {
  return Number(
    new Intl.DateTimeFormat("en-US", { timeZone, hour: "2-digit", hourCycle: "h23" }).format(date),
  );
}

function isLocalRequest(request: Request): boolean {
  const host = new URL(request.url).hostname;
  return host === "127.0.0.1" || host === "localhost";
}

function editorIdentity(request: Request, env: Env): { canEdit: boolean; email: string } {
  const email = request.headers.get("Cf-Access-Authenticated-User-Email")?.trim().toLowerCase() ?? "";
  const allowed = env.ADMIN_EMAIL.trim().toLowerCase();
  return {
    canEdit: isLocalRequest(request) || Boolean(email && allowed && email === allowed),
    email,
  };
}

async function runGeneration(env: Env, requestedBy: string, force: boolean): Promise<Record<string, unknown>> {
  const briefingDate = localDate(env.TIME_ZONE);
  const existing = await getBriefingByDate(env.DB, briefingDate);
  if (existing && !force) return { skipped: true, briefing: existing };

  const runId = await startGenerationRun(env.DB, requestedBy, briefingDate, env.OPENAI_MODEL);
  try {
    const recentContext = await getRecentContext(env.DB);
    const generated = await generateBriefing(env, briefingDate, recentContext);
    await saveGeneratedBriefing(env.DB, briefingDate, generated, env.OPENAI_MODEL);
    await finishGenerationRun(env.DB, runId, "completed");
    return { skipped: false, briefing: await getBriefingByDate(env.DB, briefingDate) };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await finishGenerationRun(env.DB, runId, "failed", message);
    console.error(JSON.stringify({ event: "briefing_generation_failed", runId, briefingDate, message }));
    throw error;
  }
}

async function handleApi(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const identity = editorIdentity(request, env);

  if (request.method === "GET" && url.pathname === "/api/session") {
    return json({ canEdit: identity.canEdit, email: identity.canEdit ? identity.email : "" });
  }

  if (request.method === "GET" && url.pathname === "/api/briefings/latest") {
    return json({ briefing: await getLatestBriefing(env.DB) });
  }

  if (request.method === "GET" && url.pathname === "/api/briefings") {
    const limit = Math.min(Math.max(Number(url.searchParams.get("limit") ?? 14), 1), 60);
    return json({ briefings: await listBriefings(env.DB, limit) });
  }

  if (request.method === "GET" && url.pathname === "/api/ideas") {
    const rawStatus = url.searchParams.get("status");
    const status = rawStatus && VALID_STATUSES.has(rawStatus as IdeaStatus) ? (rawStatus as IdeaStatus) : undefined;
    return json({ ideas: await listIdeas(env.DB, status) });
  }

  if (request.method === "POST" && url.pathname === "/api/generate") {
    if (!identity.canEdit) return json({ error: "Editor access required." }, { status: 403 });
    const body = (await request.json().catch(() => ({}))) as { force?: boolean };
    return json(await runGeneration(env, identity.email || "local-editor", Boolean(body.force)));
  }

  const ideaMatch = url.pathname.match(/^\/api\/ideas\/([0-9a-f-]+)$/i);
  if (request.method === "PATCH" && ideaMatch) {
    if (!identity.canEdit) return json({ error: "Editor access required." }, { status: 403 });
    const body = (await request.json()) as {
      status?: IdeaStatus;
      destination?: IdeaDestination;
      pinned?: boolean;
    };
    if (body.status && !VALID_STATUSES.has(body.status)) {
      return json({ error: "Invalid idea status." }, { status: 400 });
    }
    if (body.destination && !VALID_DESTINATIONS.has(body.destination)) {
      return json({ error: "Invalid destination." }, { status: 400 });
    }
    const idea = await updateIdea(env.DB, ideaMatch[1], body);
    return idea ? json({ idea }) : json({ error: "Idea not found." }, { status: 404 });
  }

  return json({ error: "Not found." }, { status: 404 });
}

export default {
  async fetch(request, env): Promise<Response> {
    try {
      const url = new URL(request.url);
      if (url.pathname.startsWith("/api/")) return await handleApi(request, env);
      return await env.ASSETS.fetch(request);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error(JSON.stringify({ event: "request_failed", message }));
      return json({ error: "Something went wrong. Please try again." }, { status: 500 });
    }
  },

  async scheduled(controller, env): Promise<void> {
    if (localHour(env.TIME_ZONE, new Date(controller.scheduledTime)) !== 8) {
      console.log(JSON.stringify({ event: "briefing_schedule_skipped", reason: "dst_guard" }));
      return;
    }
    await runGeneration(env, "cloudflare-cron", false);
  },
} satisfies ExportedHandler<Env>;

export { localDate, localHour };
