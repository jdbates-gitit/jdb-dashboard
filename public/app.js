const SECTION_ORDER = [
  "ai_expansion",
  "ai_technology",
  "expansion_signal",
  "project_vote",
  "disc_golf_outdoors",
  "gaming_entertainment",
  "health_wellness",
  "business_financial_freedom",
  "residential_mortgage",
  "world_watch",
];

const state = {
  briefing: null,
  briefings: [],
  ideas: [],
  canEdit: false,
  view: "today",
  ledgerFilter: "active",
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  "'": "&#39;",
  '"': "&quot;",
})[character]);

function safeUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch {
    return "#";
  }
}

function formatDate(value, options = {}) {
  if (!value) return "";
  const date = new Date(`${value}T12:00:00`);
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    ...options,
  }).format(date);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("show"), 2800);
}

function emptyState(title, body, symbol = "○") {
  return `<div class="empty-state"><span class="empty-symbol">${symbol}</span><h2>${escapeHtml(title)}</h2><p>${escapeHtml(body)}</p></div>`;
}

function renderBriefing(briefing) {
  const hero = $("#briefing-hero");
  const content = $("#today-content");
  hero.classList.remove("skeleton-block");

  if (!briefing) {
    hero.innerHTML = `<p class="eyebrow">READY FOR FIRST RUN</p><h1 id="briefing-title">Your signal room is ready.</h1><p class="briefing-subtitle">The structure is built. Generate the first daily briefing to fill it with current signals, creative connections, and project ideas.</p>`;
    content.innerHTML = state.canEdit
      ? emptyState("No briefing yet", "Use Refresh briefing above to create the first edition.", "+")
      : emptyState("No briefing yet", "The first edition has not been published.");
    return;
  }

  hero.innerHTML = `
    <p class="eyebrow"><span class="briefing-date">${escapeHtml(formatDate(briefing.date))}</span> · MORNING EDITION</p>
    <h1 id="briefing-title">${escapeHtml(briefing.title || "Daily Personal Briefing")}</h1>
    <p class="briefing-subtitle">${escapeHtml(briefing.subtitle || "")}</p>
    <div class="signal-line"><span>ONE-LINE SIGNAL</span><p>${escapeHtml(briefing.oneLineSignal || "")}</p></div>`;

  const sections = [...(briefing.sections || [])].sort(
    (a, b) => SECTION_ORDER.indexOf(a.key) - SECTION_ORDER.indexOf(b.key),
  );
  content.innerHTML = sections.map((section, index) => {
    const feature = ["ai_expansion", "expansion_signal"].includes(section.key) ? " feature" : "";
    const sources = (section.sources || []).filter((source) => safeUrl(source.url) !== "#").map((source) =>
      `<a class="source-link" href="${escapeHtml(safeUrl(source.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a>`,
    ).join("");
    return `<article class="briefing-card${feature}">
      <div class="card-index">${String(index + 1).padStart(2, "0")} · ${escapeHtml(section.title)}</div>
      <h2>${escapeHtml(section.headline)}</h2>
      <h3>${escapeHtml(section.why_it_matters)}</h3>
      <p class="body">${escapeHtml(section.body)}</p>
      <div class="takeaway"><b>THE TAKEAWAY</b><br>${escapeHtml(section.takeaway)}</div>
      ${sources ? `<div class="source-row">${sources}</div>` : ""}
    </article>`;
  }).join("");
}

function ideaCard(idea, context = "inbox") {
  const tags = (idea.tags || []).slice(0, 4).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
  const editorActions = !state.canEdit ? "" : context === "inbox" ? `
    <div class="idea-actions">
      <button class="action primary" data-action="keep" data-id="${idea.id}" type="button">Keep</button>
      <button class="action" data-action="build" data-id="${idea.id}" type="button">Build next</button>
      <button class="action" data-action="hold" data-id="${idea.id}" type="button">Hold</button>
      <button class="action icon" data-action="archive" data-id="${idea.id}" title="Archive" type="button">×</button>
    </div>` : `
    <div class="idea-actions">
      <button class="action" data-action="pin" data-id="${idea.id}" type="button">${idea.pinned ? "Unstar" : "★ Best idea"}</button>
      <button class="action" data-action="build" data-id="${idea.id}" type="button">Build next</button>
      <button class="action icon" data-action="open" data-id="${idea.id}" aria-label="Open details" type="button">→</button>
    </div>`;
  return `<article class="idea-card ${idea.pinned ? "pinned" : ""}" data-idea-id="${idea.id}">
    <div class="idea-meta"><span class="idea-kind">${idea.kind === "project_edit" ? "Project edit" : "New project"}</span>${idea.relatedProject ? `<span>· ${escapeHtml(idea.relatedProject)}</span>` : ""}</div>
    <h3>${escapeHtml(idea.title)}</h3>
    <p>${escapeHtml(idea.summary)}</p>
    ${tags ? `<div class="tag-row">${tags}</div>` : ""}
    ${editorActions || `<div class="idea-actions"><button class="action" data-action="open" data-id="${idea.id}" type="button">View details</button></div>`}
  </article>`;
}

function renderIdeas() {
  const inbox = state.ideas.filter((idea) => idea.status === "inbox");
  $("#inbox-badge").textContent = String(inbox.length);
  $("#inbox-content").innerHTML = inbox.length
    ? inbox.map((idea) => ideaCard(idea, "inbox")).join("")
    : emptyState("Inbox clear", "New ideas from future briefings will appear here for a quick decision.", "✓");

  const ledgerIdeas = state.ideas.filter((idea) => !["inbox", "archived"].includes(idea.status));
  const pinned = ledgerIdeas.filter((idea) => idea.pinned).slice(0, 3);
  $("#pinned-content").innerHTML = pinned.length
    ? pinned.map((idea) => ideaCard(idea, "ledger")).join("")
    : emptyState("Your highlight reel starts here", "Star a kept idea and it will stay at the top of the ledger.", "★");

  const count = (statuses) => ledgerIdeas.filter((idea) => statuses.includes(idea.status)).length;
  $("#ledger-counts").innerHTML = `
    <div class="ledger-count"><b>${count(["kept", "build_next", "building"])}</b><span>Active</span></div>
    <div class="ledger-count"><b>${count(["shipped"])}</b><span>Shipped</span></div>`;

  const filtered = ledgerIdeas.filter((idea) => {
    if (state.ledgerFilter === "all") return true;
    if (state.ledgerFilter === "active") return ["kept", "build_next", "building"].includes(idea.status);
    return idea.status === state.ledgerFilter;
  });
  $("#ledger-content").innerHTML = filtered.length ? filtered.map((idea) => `
    <article class="ledger-row">
      <span class="status-pill">${escapeHtml(idea.status.replace("_", " "))}</span>
      <span class="ledger-title">${escapeHtml(idea.title)}</span>
      <span class="ledger-summary">${escapeHtml(idea.summary)}</span>
      <span class="destination">${escapeHtml(idea.destination.replaceAll("_", " "))}</span>
      <button class="row-open" data-action="open" data-id="${idea.id}" type="button" aria-label="Open ${escapeHtml(idea.title)}">→</button>
    </article>`).join("") : emptyState("Nothing in this lane", "Choose another filter or send an idea here from the inbox.");
}

function renderArchive() {
  $("#archive-content").innerHTML = state.briefings.length ? state.briefings.map((briefing) => `
    <button class="archive-row" data-briefing-id="${briefing.id}" type="button">
      <span class="archive-date">${escapeHtml(formatDate(briefing.date, { weekday: undefined, year: undefined }))}</span>
      <span class="archive-title">${escapeHtml(briefing.title)}</span>
      <span class="archive-signal">${escapeHtml(briefing.oneLineSignal)}</span>
    </button>`).join("") : emptyState("No past editions yet", "Each daily briefing will be preserved here automatically.");
}

function setView(view) {
  state.view = view;
  $$(".view").forEach((element) => element.classList.toggle("active", element.id === `${view}-view`));
  $$(".nav-item").forEach((element) => element.classList.toggle("active", element.dataset.view === view));
  history.replaceState(null, "", `#${view}`);
  $("#main-content").focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function openIdea(id) {
  const idea = state.ideas.find((item) => item.id === id);
  if (!idea) return;
  const actions = state.canEdit ? `
    <div class="dialog-actions">
      <button class="action primary" data-action="copy" data-id="${idea.id}" type="button">Copy Codex brief</button>
      <button class="action" data-action="destination_codex" data-id="${idea.id}" type="button">Destination: Codex</button>
      <button class="action" data-action="destination_architecture" data-id="${idea.id}" type="button">Architecture chat</button>
      <button class="action" data-action="hold" data-id="${idea.id}" type="button">Hold</button>
    </div>` : "";
  $("#dialog-content").innerHTML = `<div class="dialog-inner">
    <div class="idea-meta"><span class="idea-kind">${idea.kind === "project_edit" ? "Project edit" : "New project"}</span><span>· ${escapeHtml(idea.status.replace("_", " "))}</span></div>
    <h2>${escapeHtml(idea.title)}</h2>
    <div class="detail-block"><label>The idea</label><p>${escapeHtml(idea.summary)}</p></div>
    <div class="detail-block"><label>Why now</label><p>${escapeHtml(idea.whyNow)}</p></div>
    <div class="detail-block"><label>Smallest useful version</label><p>${escapeHtml(idea.smallestVersion)}</p></div>
    <div class="detail-block"><label>Ready-to-use handoff</label><div class="handoff">${escapeHtml(idea.handoffPrompt)}</div></div>
    ${actions}
  </div>`;
  if (!$("#idea-dialog").open) $("#idea-dialog").showModal();
}

async function updateIdea(id, update, successMessage) {
  const { idea } = await api(`/api/ideas/${id}`, { method: "PATCH", body: JSON.stringify(update) });
  state.ideas = state.ideas.map((item) => item.id === id ? idea : item);
  renderIdeas();
  if ($("#idea-dialog").open) openIdea(id);
  toast(successMessage);
}

async function handleAction(button) {
  const { action, id } = button.dataset;
  const idea = state.ideas.find((item) => item.id === id);
  if (!idea) return;
  button.disabled = true;
  try {
    if (action === "open") return openIdea(id);
    if (action === "keep") await updateIdea(id, { status: "kept" }, "Added to your Project Ledger.");
    if (action === "build") await updateIdea(id, { status: "build_next", destination: "codex" }, "Marked Build Next and routed to Codex.");
    if (action === "hold") await updateIdea(id, { status: "hold", destination: "hold" }, "Moved to Hold.");
    if (action === "archive") await updateIdea(id, { status: "archived" }, "Idea archived.");
    if (action === "pin") await updateIdea(id, { pinned: !idea.pinned }, idea.pinned ? "Removed from Best New Ideas." : "Added to Best New Ideas.");
    if (action === "destination_codex") await updateIdea(id, { destination: "codex" }, "Destination set to Codex.");
    if (action === "destination_architecture") await updateIdea(id, { destination: "architecture_chat" }, "Destination set to Architecture Chat.");
    if (action === "copy") {
      await navigator.clipboard.writeText(idea.handoffPrompt);
      toast("Codex brief copied. Paste it into the right project when ready.");
    }
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
}

async function generateBriefing() {
  const button = $("#generate-button");
  button.disabled = true;
  button.textContent = "Researching…";
  toast("Building today’s briefing. This may take a minute.");
  try {
    const data = await api("/api/generate", { method: "POST", body: JSON.stringify({ force: true }) });
    state.briefing = data.briefing;
    const all = await Promise.all([api("/api/briefings"), api("/api/ideas")]);
    state.briefings = all[0].briefings || [];
    state.ideas = all[1].ideas || [];
    renderBriefing(state.briefing);
    renderIdeas();
    renderArchive();
    setView("today");
    toast("Today’s briefing is ready.");
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Refresh briefing";
  }
}

async function init() {
  $("#current-date").textContent = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "short", day: "numeric" }).format(new Date());
  try {
    const [sessionData, briefingData, briefingsData, ideasData] = await Promise.all([
      api("/api/session"),
      api("/api/briefings/latest"),
      api("/api/briefings"),
      api("/api/ideas"),
    ]);
    state.canEdit = Boolean(sessionData.canEdit);
    state.briefing = briefingData.briefing;
    state.briefings = briefingsData.briefings || [];
    state.ideas = ideasData.ideas || [];
    $$(".editor-only").forEach((element) => { element.hidden = !state.canEdit; });
    $("#access-label").textContent = state.canEdit ? "Editor controls active" : "Viewing dashboard";
    renderBriefing(state.briefing);
    renderIdeas();
    renderArchive();
  } catch (error) {
    $("#briefing-hero").classList.remove("skeleton-block");
    $("#briefing-hero").innerHTML = `<p class="eyebrow">CONNECTION ERROR</p><h1 id="briefing-title">The signal went quiet.</h1><p class="briefing-subtitle">${escapeHtml(error.message)}</p>`;
    toast("Could not load the dashboard.");
  }

  const initialView = ["today", "inbox", "ledger", "archive"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "today";
  setView(initialView);
}

document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-view]");
  if (nav) setView(nav.dataset.view);
  const filter = event.target.closest("[data-filter]");
  if (filter) {
    state.ledgerFilter = filter.dataset.filter;
    $$(".filter").forEach((item) => item.classList.toggle("active", item === filter));
    renderIdeas();
  }
  const action = event.target.closest("[data-action]");
  if (action) handleAction(action);
  const archive = event.target.closest("[data-briefing-id]");
  if (archive) {
    const briefing = state.briefings.find((item) => item.id === archive.dataset.briefingId);
    if (briefing) { state.briefing = briefing; renderBriefing(briefing); setView("today"); }
  }
});

$("#generate-button").addEventListener("click", generateBriefing);
$("#idea-dialog .dialog-close").addEventListener("click", () => $("#idea-dialog").close());
$("#idea-dialog").addEventListener("click", (event) => {
  if (event.target === $("#idea-dialog")) $("#idea-dialog").close();
});

init();
