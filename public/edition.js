const SECTION_ORDER = [
  "ai_expansion",
  "ai_technology",
  "expansion_signal",
  "disc_golf_outdoors",
  "gaming_entertainment",
  "health_wellness",
  "business_financial_freedom",
  "residential_mortgage",
  "world_watch",
];

const $ = (selector, root = document) => root.querySelector(selector);
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

function formatDate(value) {
  if (!value) return "Today";
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
}

function formatPublished(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function renderBriefing(briefing) {
  if (!briefing) {
    $("#lead").innerHTML = `
      <p class="kicker">PUBLIC EDITION</p>
      <h1 id="edition-title">Today’s signal is still being prepared.</h1>
      <p class="dek">Check back after the latest edition has been reviewed and published.</p>`;
    $("#briefing-content").innerHTML = `<article class="empty-edition"><span>NOT YET PUBLISHED</span><p>The next edition is on its way.</p></article>`;
    $("#signal-count").textContent = "0";
    return;
  }

  const sections = [...(briefing.sections || [])].sort(
    (a, b) => SECTION_ORDER.indexOf(a.key) - SECTION_ORDER.indexOf(b.key),
  );

  $("#lead").innerHTML = `
    <p class="kicker">${escapeHtml(formatDate(briefing.date))} · MORNING EDITION</p>
    <h1 id="edition-title">${escapeHtml(briefing.title || "The Daily Signal")}</h1>
    <p class="dek">${escapeHtml(briefing.subtitle || "One thoughtful scan of what is changing—and why it matters.")}</p>
    <div class="one-line-signal"><span>THE SIGNAL</span><p>${escapeHtml(briefing.oneLineSignal || "")}</p></div>`;

  $("#edition-date").textContent = formatDate(briefing.date);
  $("#signal-count").textContent = String(sections.length);
  $("#published-time").textContent = formatPublished(briefing.publishedAt);
  $("#briefing-content").innerHTML = sections.map((section, index) => {
    const sources = (section.sources || [])
      .filter((source) => safeUrl(source.url) !== "#")
      .map((source) => `<a href="${escapeHtml(safeUrl(source.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a>`)
      .join("");
    return `<article class="signal-card">
      <span class="card-number">${String(index + 1).padStart(2, "0")} / ${escapeHtml(section.title)}</span>
      <h2>${escapeHtml(section.headline)}</h2>
      <h3>${escapeHtml(section.why_it_matters)}</h3>
      <p class="body">${escapeHtml(section.body)}</p>
      <div class="takeaway"><b>THE TAKEAWAY</b>${escapeHtml(section.takeaway)}</div>
      ${sources ? `<div class="sources">${sources}</div>` : ""}
    </article>`;
  }).join("");
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2400);
}

async function init() {
  try {
    const response = await fetch("/api/public/briefing", { headers: { Accept: "application/json" } });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The public edition could not be loaded.");
    renderBriefing(data.briefing);
  } catch {
    $("#lead").innerHTML = `<p class="kicker">CONNECTION ERROR</p><h1 id="edition-title">The signal went quiet.</h1><p class="dek">Please try again in a moment.</p>`;
    $("#briefing-content").innerHTML = `<article class="empty-edition"><span>OFFLINE</span><p>The latest edition could not be reached.</p></article>`;
  }
}

$("#copy-link").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(location.href);
    showToast("Today’s link copied.");
  } catch {
    showToast("Copy the address from your browser bar.");
  }
});

init();
