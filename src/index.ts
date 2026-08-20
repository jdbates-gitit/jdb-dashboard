import { generateBriefing } from "./briefing";
import {
  finishGenerationRun,
  getBriefingByDate,
  getLatestBriefing,
  getLatestPublicBriefing,
  getPublicationStatus,
  getRecentContext,
  listBriefings,
  listIdeas,
  publishLatestBriefing,
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

function publicJson(data: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json; charset=utf-8");
  headers.set("Cache-Control", "public, max-age=60");
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("Access-Control-Allow-Origin", `https://${PUBLIC_HOSTNAME}`);
  return Response.json(data, { ...init, headers });
}

const PUBLIC_HOSTNAME = "briefing.jdb-builds.com";
const PRIVATE_HOSTNAME = "dashboard.jdb-builds.com";
const PUBLIC_ASSET_PATHS = new Map([
  ["/", "/edition.html"],
  ["/edition.css", "/edition.css"],
  ["/edition.js", "/edition.js"],
  ["/favicon.svg", "/favicon.svg"],
]);

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

export function classifyHostname(
  hostname: string,
  privateHostname = PRIVATE_HOSTNAME,
  publicHostname = PUBLIC_HOSTNAME,
): "private" | "public" | "unknown" {
  const normalized = hostname.trim().toLowerCase();
  if (normalized === publicHostname.toLowerCase()) return "public";
  if (
    normalized === privateHostname.toLowerCase() ||
    normalized === "127.0.0.1" ||
    normalized === "localhost"
  ) {
    return "private";
  }
  return "unknown";
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

  if (!identity.canEdit) {
    return json({ error: "Editor access required." }, { status: 403 });
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

  if (request.method === "GET" && url.pathname === "/api/publication") {
    return json({
      publication: {
        ...(await getPublicationStatus(env.DB)),
        publicUrl: `https://${PUBLIC_HOSTNAME}/`,
      },
    });
  }

  if (request.method === "POST" && url.pathname === "/api/publish") {
    const briefing = await publishLatestBriefing(env.DB);
    if (!briefing) return json({ error: "Generate a briefing before publishing." }, { status: 409 });
    return json({
      briefing,
      publication: {
        ...(await getPublicationStatus(env.DB)),
        publicUrl: `https://${PUBLIC_HOSTNAME}/`,
      },
    });
  }

  if (request.method === "POST" && url.pathname === "/api/generate") {
    const body = (await request.json().catch(() => ({}))) as { force?: boolean };
    return json(await runGeneration(env, identity.email || "local-editor", Boolean(body.force)));
  }

  const ideaMatch = url.pathname.match(/^\/api\/ideas\/([0-9a-f-]+)$/i);
  if (request.method === "PATCH" && ideaMatch) {
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

function securePublicResponse(response: Response, pathname: string): Response {
  const headers = new Headers(response.headers);
  headers.set("Cache-Control", pathname === "/" ? "public, max-age=60" : "public, max-age=300");
  headers.set(
    "Content-Security-Policy",
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  );
  headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()");
  headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function handlePublicRequest(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  if (request.method === "GET" && url.pathname === "/api/public/briefing") {
    return publicJson({ briefing: await getLatestPublicBriefing(env.DB) });
  }

  if (request.method !== "GET" && request.method !== "HEAD") {
    return publicJson({ error: "Method not allowed." }, { status: 405, headers: { Allow: "GET, HEAD" } });
  }

  const assetPath = PUBLIC_ASSET_PATHS.get(url.pathname);
  if (!assetPath) return publicJson({ error: "Not found." }, { status: 404 });

  const assetUrl = new URL(request.url);
  assetUrl.pathname = assetPath;
  assetUrl.search = "";
  const assetRequest = new Request(assetUrl, request);
  return securePublicResponse(await env.ASSETS.fetch(assetRequest), url.pathname);
}

const worker = {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      const url = new URL(request.url);
      const surface = classifyHostname(url.hostname);
      if (surface === "public") return await handlePublicRequest(request, env);
      if (surface === "unknown") return json({ error: "Not found." }, { status: 404 });
      if (url.pathname.startsWith("/api/")) return await handleApi(request, env);
      return await env.ASSETS.fetch(request);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error(JSON.stringify({ event: "request_failed", message }));
      return json({ error: "Something went wrong. Please try again." }, { status: 500 });
    }
  },

  async scheduled(controller: ScheduledController, env: Env): Promise<void> {
    if (localHour(env.TIME_ZONE, new Date(controller.scheduledTime)) !== 8) {
      console.log(JSON.stringify({ event: "briefing_schedule_skipped", reason: "dst_guard" }));
      return;
    }
    await runGeneration(env, "cloudflare-cron", false);
  },
} satisfies ExportedHandler<Env>;

export default worker;

export { localDate, localHour };
