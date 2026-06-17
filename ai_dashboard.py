"""
AI News Dashboard Generator
Fetches RSS feeds, live rates, and local weather; summarizes news with the Claude API,
and writes a styled local HTML dashboard.
Usage: python ai_dashboard.py

The Anthropic API key is read from the ANTHROPIC_API_KEY environment variable.
Set it once with:  setx ANTHROPIC_API_KEY "sk-ant-..."   (then reopen your terminal)
"""

import os
import re
import csv
import io
import html
import time
import random
import logging
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import feedparser
import anthropic

# ── CONFIG ────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()

# Locate everything relative to this script, so the folder can be moved freely.
DASHBOARD_DIR   = Path(__file__).resolve().parent
LOG_PATH        = DASHBOARD_DIR / "dashboard.log"
import os
if os.getenv("GITHUB_ACTIONS"):
    OUTPUT_FILE = DASHBOARD_DIR / "index.html"
else:
    OUTPUT_FILE = Path.home() / "OneDrive" / "AI Dashboard" / "ai_dashboard.html"

FEEDS = {
    "🤖 AI & Technology": [
        ("The Rundown AI",       "https://rss.beehiiv.com/feeds/2R3C6Bt5wj.xml"),
        ("OpenAI News",          "https://openai.com/news/rss.xml"),
        ("Hugging Face Blog",    "https://huggingface.co/blog/feed.xml"),
    ],
    "🏦 Mortgage & Fintech": [
        ("HousingWire",          "https://www.housingwire.com/feed/"),
        ("Mortgage News Daily",  "https://www.mortgagenewsdaily.com/rss/news"),
        ("The Mortgage Reports", "https://themortgagereports.com/feed"),
        ("Calculated Risk",      "https://www.calculatedriskblog.com/feeds/posts/default"),
    ],
    "🥏 Disc Golf": [
        ("PDGA News",            "https://www.pdga.com/rss.xml"),
        ("Ultiworld Disc Golf",  "https://discgolf.ultiworld.com/feed/"),
        ("Disc Golf Pro Tour",   "https://www.dgpt.com/feed/"),
    ],
}

MAX_ITEMS_PER_FEED  = 8     # fetched per source
MAX_HEADLINES_SHOWN = 12    # shown per category after merge+sort
MAX_SUMMARY_LINES   = 30
NEW_THRESHOLD_HOURS = 8     # stories newer than this get a "new" accent
MODEL               = "claude-haiku-4-5-20251001"
HEADERS             = {"User-Agent": "Mozilla/5.0"}

# Local disc golf tournaments (Disc Golf Scene — includes sanctioned AND unsanctioned)
DGSCENE_TX_URL      = "https://www.discgolfscene.com/tournaments/Texas"
MAX_TOURNEYS        = 10
HOUSTON_METRO = {
    "houston", "katy", "cypress", "spring", "tomball", "conroe", "the woodlands",
    "woodlands", "sugar land", "pearland", "pasadena", "humble", "kingwood",
    "atascocita", "richmond", "rosenberg", "missouri city", "league city",
    "friendswood", "webster", "baytown", "channelview", "crosby", "magnolia",
    "montgomery", "hockley", "waller", "brookshire", "fulshear", "stafford",
    "dickinson", "texas city", "galveston", "la porte", "deer park", "seabrook",
    "alvin", "santa fe", "angleton", "lake jackson", "clute", "sealy", "bellville",
    "hempstead", "navasota", "brenham", "porter", "new caney", "splendora", "willis",
    "manvel", "rosharon", "needville", "bellaire", "jersey village", "klein",
    "cinco ranch", "cleveland", "dayton", "liberty", "mont belvieu", "prairie view",
    "huntsville",
}

# A new one is chosen each time the briefing is generated (avoids repeating the last).
QUOTE_STATE = DASHBOARD_DIR / "quote_state.txt"
QUOTES = [
    # — Tao Te Ching / Lao Tzu —
    ("The journey of a thousand miles begins with a single step.", "Lao Tzu, Tao Te Ching"),
    ("Nature does not hurry, yet everything is accomplished.", "Lao Tzu"),
    ("He who knows others is wise; he who knows himself is enlightened.", "Lao Tzu, Tao Te Ching"),
    ("When I let go of what I am, I become what I might be.", "Lao Tzu"),
    ("A good traveler has no fixed plans and is not intent upon arriving.", "Lao Tzu, Tao Te Ching"),
    # — Confucius —
    ("It does not matter how slowly you go as long as you do not stop.", "Confucius"),
    ("The man who moves a mountain begins by carrying away small stones.", "Confucius"),
    ("Our greatest glory is not in never falling, but in rising every time we fall.", "Confucius"),
    ("Real knowledge is to know the extent of one's ignorance.", "Confucius"),
    # — Sun Tzu —
    ("In the midst of chaos, there is also opportunity.", "Sun Tzu, The Art of War"),
    ("Victorious warriors win first and then go to war.", "Sun Tzu, The Art of War"),
    ("Know yourself and you will win all battles.", "Sun Tzu, The Art of War"),
    ("Opportunities multiply as they are seized.", "Sun Tzu, The Art of War"),
    # — Buddhism —
    ("What we think, we become.", "The Buddha"),
    ("Holding on to anger is like grasping a hot coal — you are the one who gets burned.", "The Buddha"),
    ("Peace comes from within. Do not seek it without.", "The Buddha"),
    ("No one saves us but ourselves. We ourselves must walk the path.", "The Buddha, Dhammapada"),
    ("Three things cannot long be hidden: the sun, the moon, and the truth.", "The Buddha"),
    # — Stoics & classical —
    ("You have power over your mind — not outside events. Realize this, and you will find strength.", "Marcus Aurelius, Meditations"),
    ("We suffer more often in imagination than in reality.", "Seneca"),
    ("It is not that we have a short time to live, but that we waste much of it.", "Seneca, On the Shortness of Life"),
    ("No man is free who is not master of himself.", "Epictetus"),
    ("Waste no more time arguing about what a good man should be. Be one.", "Marcus Aurelius, Meditations"),
    ("Difficulties strengthen the mind, as labor does the body.", "Seneca"),
    ("The only true wisdom is in knowing you know nothing.", "Socrates"),
    ("We are what we repeatedly do. Excellence, then, is not an act, but a habit.", "Will Durant, on Aristotle"),
    # — Facing fear —
    ("Courage is resistance to fear, mastery of fear — not absence of fear.", "Mark Twain"),
    ("He who is not every day conquering some fear has not learned the secret of life.", "Ralph Waldo Emerson"),
    ("Everything you want is on the other side of fear.", "Jack Canfield"),
    ("Courage is being scared to death, but saddling up anyway.", "John Wayne"),
    ("I have learned over the years that when one's mind is made up, this diminishes fear.", "Rosa Parks"),
    # — Uplifting & resilience —
    ("What lies behind us and what lies before us are tiny matters compared to what lies within us.", "Ralph Waldo Emerson"),
    ("The best way out is always through.", "Robert Frost"),
    ("Hope is the thing with feathers that perches in the soul.", "Emily Dickinson"),
    ("Go confidently in the direction of your dreams. Live the life you have imagined.", "Henry David Thoreau"),
    ("The wound is the place where the Light enters you.", "Rumi"),
    ("What you seek is seeking you.", "Rumi"),
    ("In the depth of winter, I finally learned that within me there lay an invincible summer.", "Albert Camus"),
    ("Tough times never last, but tough people do.", "Robert H. Schuller"),
    # — Viktor Frankl & meaning —
    ("Between stimulus and response there is a space. In that space is our power to choose our response.", "Viktor Frankl"),
    ("When we are no longer able to change a situation, we are challenged to change ourselves.", "Viktor Frankl, Man's Search for Meaning"),
    ("He who has a why to live can bear almost any how.", "Friedrich Nietzsche"),
    # — AA / The Big Book —
    ("God, grant me the serenity to accept the things I cannot change, courage to change the things I can, and wisdom to know the difference.", "The Serenity Prayer (Reinhold Niebuhr)"),
    ("One day at a time.", "Alcoholics Anonymous"),
    ("Progress, not perfection.", "Alcoholics Anonymous"),
    ("We are not saints. The point is that we are willing to grow along spiritual lines.", "The Big Book of Alcoholics Anonymous"),
    ("Acceptance is the answer to all my problems today.", "The Big Book of Alcoholics Anonymous"),
    ("Half measures availed us nothing.", "The Big Book of Alcoholics Anonymous"),
    # — Civilization-shaping voices —
    ("Darkness cannot drive out darkness; only light can do that. Hate cannot drive out hate; only love can do that.", "Martin Luther King Jr."),
    ("The arc of the moral universe is long, but it bends toward justice.", "Martin Luther King Jr."),
    ("Injustice anywhere is a threat to justice everywhere.", "Martin Luther King Jr."),
    ("An eye for an eye only ends up making the whole world blind.", "Mahatma Gandhi"),
    ("Be the change that you wish to see in the world.", "Mahatma Gandhi"),
    ("To every thing there is a season, and a time to every purpose under heaven.", "Ecclesiastes 3:1"),
    ("As iron sharpens iron, so one person sharpens another.", "Proverbs 27:17"),
    ("This too shall pass.", "Persian adage"),
]


def get_quote():
    """Pick a quote at random, avoiding an immediate repeat of the last one shown."""
    last = ""
    try:
        last = QUOTE_STATE.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    pool = [q for q in QUOTES if q[0] != last] or QUOTES
    quote = random.choice(pool)
    try:
        QUOTE_STATE.write_text(quote[0], encoding="utf-8")
    except Exception:
        pass
    return quote

# When launched at logon the network may not be up yet — wait for it.
NETWORK_WAIT_SECONDS = 90
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
# Quiet the noisy per-request HTTP logging from the HTTP client.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("dashboard")


# ── HELPERS ─────────────────────────────────────────────────────────────────
def wait_for_network(timeout=NETWORK_WAIT_SECONDS):
    """Block until we can reach the internet, or give up after `timeout` seconds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.head("https://www.google.com", timeout=5)
            return True
        except Exception:
            log.info("  …waiting for network")
            time.sleep(5)
    log.warning("  network not available after %ss — continuing anyway", timeout)
    return False


def humanize_age(dt):
    """Return a short relative age like '3h' or '2d', or '' if unknown."""
    if not dt:
        return ""
    delta = datetime.now(timezone.utc) - dt
    secs = delta.total_seconds()
    if secs < 0:
        return "now"
    if secs < 3600:
        return f"{int(secs // 60)}m"
    if secs < 86400:
        return f"{int(secs // 3600)}h"
    return f"{int(secs // 86400)}d"


def entry_datetime(entry):
    """Best-effort UTC datetime from a feedparser entry, or None."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


# ── DATA FETCHERS ───────────────────────────────────────────────────────────
def fetch_feed(name, url):
    """Return a list of dicts: {title, link, desc, source, dt}."""
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)

        items = []
        for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
            title = (entry.get("title") or "").strip()
            link  = (entry.get("link")  or "").strip()
            raw   = entry.get("summary") or entry.get("description") or ""
            desc  = re.sub(r"<[^>]+>", "", raw)[:300].strip()
            if title:
                items.append({
                    "title": title, "link": link, "desc": desc,
                    "source": name, "dt": entry_datetime(entry),
                })

        log.info("  OK  %s: %d items", name, len(items))
        return items
    except Exception as e:
        log.warning("  ERR %s: %s", name, e)
        return []


def get_rates():
    """30yr/15yr fixed (Freddie Mac PMMS) + 10yr Treasury yield. All free, no key."""
    out = {}
    # Freddie Mac PMMS weekly survey (30yr / 15yr)
    try:
        r = requests.get("https://www.freddiemac.com/pmms/docs/PMMS_history.csv",
                         timeout=15, headers=HEADERS)
        r.raise_for_status()
        rows = list(csv.reader(io.StringIO(r.text)))
        head = rows[0]
        i30, i15 = head.index("pmms30"), head.index("pmms15")
        for row in reversed(rows[1:]):
            if len(row) > i30 and row[i30].strip():
                out["r30"] = row[i30].strip()
                out["r15"] = row[i15].strip() if len(row) > i15 else ""
                out["rdate"] = row[0].strip()
                break
    except Exception as e:
        log.warning("  ERR rates (Freddie): %s", e)

    # US Treasury daily par yield curve (10yr)
    try:
        ym = datetime.now().strftime("%Y%m")
        u = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
             f"pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month={ym}")
        r = requests.get(u, timeout=15, headers=HEADERS)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
              "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
        props = root.findall(".//m:properties", ns)
        if props:
            last = props[-1]
            out["ten"] = (last.find("d:BC_10YEAR", ns).text or "").strip()
            out["tendate"] = (last.find("d:NEW_DATE", ns).text or "")[:10]
    except Exception as e:
        log.warning("  ERR rates (Treasury): %s", e)

    log.info("  OK  Rates: 30yr=%s 15yr=%s 10yrT=%s",
             out.get("r30"), out.get("r15"), out.get("ten"))
    return out


WMO = {  # WMO weather code → (emoji, label)
    0: ("☀️", "Clear"), 1: ("🌤️", "Mostly clear"), 2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"), 45: ("🌫️", "Fog"), 48: ("🌫️", "Fog"),
    51: ("🌦️", "Drizzle"), 53: ("🌦️", "Drizzle"), 55: ("🌦️", "Drizzle"),
    61: ("🌧️", "Rain"), 63: ("🌧️", "Rain"), 65: ("🌧️", "Heavy rain"),
    66: ("🌧️", "Freezing rain"), 67: ("🌧️", "Freezing rain"),
    71: ("🌨️", "Snow"), 73: ("🌨️", "Snow"), 75: ("🌨️", "Heavy snow"),
    77: ("🌨️", "Snow grains"), 80: ("🌦️", "Showers"), 81: ("🌦️", "Showers"),
    82: ("⛈️", "Violent showers"), 95: ("⛈️", "Thunderstorm"),
    96: ("⛈️", "Thunderstorm"), 99: ("⛈️", "Thunderstorm"),
}


def get_weather():
    """IP-geolocate, then pull current conditions + today's hi/lo from Open-Meteo."""
    lat = lon = city = region = None
    for u in ("https://ipwho.is/", "https://get.geojs.io/v1/ip/geo.json",
              "http://ip-api.com/json/"):
        try:
            j = requests.get(u, timeout=10, headers=HEADERS).json()
            lat = j.get("latitude") or j.get("lat")
            lon = j.get("longitude") or j.get("lon")
            city = j.get("city")
            region = j.get("region") or j.get("region_code")
            if lat and lon:
                break
        except Exception:
            continue
    if not (lat and lon):
        log.warning("  ERR weather: could not geolocate")
        return None

    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=10, headers=HEADERS,
                         params={"latitude": lat, "longitude": lon,
                                 "current": "temperature_2m,wind_speed_10m,weather_code",
                                 "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                                 "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
                                 "timezone": "auto", "forecast_days": 1})
        j = r.json()
        cur, day = j["current"], j["daily"]
        emoji, label = WMO.get(cur.get("weather_code"), ("🌡️", ""))
        wx = {
            "city": "Katy", "region": "TX",
            "temp": round(cur["temperature_2m"]),
            "wind": round(cur["wind_speed_10m"]),
            "hi": round(day["temperature_2m_max"][0]),
            "lo": round(day["temperature_2m_min"][0]),
            "precip": day["precipitation_probability_max"][0],
            "emoji": emoji, "label": label,
        }
        log.info("  OK  Weather: %s %s°F %s", city, wx["temp"], label)
        return wx
    except Exception as e:
        log.warning("  ERR weather (Open-Meteo): %s", e)
        return None


def get_tournaments():
    """Upcoming Houston-area disc golf tournaments (sanctioned + unsanctioned) from Disc Golf Scene."""
    try:
        t = requests.get(DGSCENE_TX_URL, timeout=20, headers=HEADERS).text
    except Exception as e:
        log.warning("  ERR tournaments: %s", e)
        return []

    def grab(pat, s):
        m = re.search(pat, s, re.S)
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    out = []
    for rec in re.split(r'<div class="tournament-list list-record', t)[1:]:
        city = grab(r'fa-map-marker-alt count"></i><b>\s*(.*?)\s*</b>', rec)
        if city.split(",")[0].strip().lower() not in HOUSTON_METRO:
            continue
        name = html.unescape(re.sub(r"<[^>]+>", "", grab(r'<span class="name">(.*?)</span>', rec))).strip()
        out.append({
            "name":   name,
            "mon":    grab(r'list-date-range.*?text-muted">\s*([A-Za-z]{3})', rec).upper(),
            "day":    grab(r'list-date-range.*?text-muted">\s*[A-Za-z]{3}\s*</span>\s*<span>\s*(\d{1,2})', rec),
            "course": grab(r'fa-map count"></i><b>\s*(.*?)\s*</b>', rec),
            "city":   city,
            "link":   grab(r'href="(https://www\.discgolfscene\.com/tournaments/[^"]+)"', rec),
        })
        if len(out) >= MAX_TOURNEYS:
            break
    log.info("  OK  Tournaments: %d Houston-area", len(out))
    return out


def summarize_news(client, category, items):
    """Return (summary_body, takeaway)."""
    if not items:
        return "No articles retrieved for this category.", ""

    lines = [f"- {it['title']}: {it['desc']}" for it in items[:MAX_SUMMARY_LINES]]
    prompt = f"""You are a sharp analyst writing a quick daily briefing.
Category: {category}

Headlines:
{chr(10).join(lines)}

Write 3-4 punchy sentences covering the most significant stories.
Be specific with names, numbers, facts. No filler.
Then, on a new final line, write: TAKEAWAY: <one bold insight in 10 words or less>
Plain text only, no markdown, no bullets."""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=240,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
    except Exception as e:
        log.warning("  ERR summary (%s): %s", category, e)
        return f"Summary unavailable: {e}", ""

    takeaway = ""
    m = re.search(r"TAKEAWAY:\s*(.+)$", text, re.IGNORECASE | re.DOTALL)
    if m:
        takeaway = m.group(1).strip()
        text = text[:m.start()].strip()
    return text, takeaway


# ── HTML ─────────────────────────────────────────────────────────────────────
def weather_html(wx):
    if not wx:
        return ""
    loc = ", ".join(p for p in (wx["city"], wx["region"]) if p)
    rain = f" · {wx['precip']}% rain" if wx.get("precip") else ""
    return f"""
  <div class="weather">
    <span class="wx-emoji">{wx['emoji']}</span>
    <span class="wx-temp">{wx['temp']}°</span>
    <div class="wx-meta">
      <div class="wx-loc">{loc}</div>
      <div class="wx-detail">H {wx['hi']}° · L {wx['lo']}° · 💨 {wx['wind']} mph{rain}</div>
    </div>
  </div>"""


def rates_html(rates):
    if not rates:
        return ""
    cells = []
    if rates.get("r30"):
        cells.append((f"{rates['r30']}%", "30-YR FIXED"))
    if rates.get("r15"):
        cells.append((f"{rates['r15']}%", "15-YR FIXED"))
    if rates.get("ten"):
        cells.append((f"{rates['ten']}%", "10-YR TREASURY"))
    if not cells:
        return ""
    inner = "".join(
        f'<div class="rate"><div class="rate-val">{v}</div><div class="rate-lbl">{l}</div></div>'
        for v, l in cells
    )
    asof = rates.get("rdate") or rates.get("tendate") or ""
    return f'<div class="rates">{inner}</div><div class="rates-asof">Rates as of {asof}</div>'


def headlines_html(items):
    rows = ""
    for it in items[:MAX_HEADLINES_SHOWN]:
        href = f'href="{it["link"]}"' if it["link"] else ""
        age = humanize_age(it["dt"])
        is_new = it["dt"] and (datetime.now(timezone.utc) - it["dt"]) < timedelta(hours=NEW_THRESHOLD_HOURS)
        new_dot = '<span class="new-dot"></span>' if is_new else ""
        age_html = f'<span class="art-age">{age} ago</span>' if age else ""
        rows += f"""
                <a {href} target="_blank" class="article-link">
                    <span class="art-title">{new_dot}{it['title']}</span>
                    <span class="art-meta"><span class="src">{it['source']}</span>{age_html}</span>
                </a>"""
    return rows


def tournaments_html(tournaments):
    if not tournaments:
        return ""
    rows = ""
    for tn in tournaments:
        href = f'href="{tn["link"]}"' if tn["link"] else ""
        loc = " · ".join(p for p in (tn["course"], tn["city"]) if p)
        rows += f"""
                <a {href} target="_blank" class="tourney">
                    <span class="t-date"><b>{tn['day']}</b><span>{tn['mon']}</span></span>
                    <span class="t-body">
                        <span class="t-name">{tn['name']}</span>
                        <span class="t-loc">{loc}</span>
                    </span>
                </a>"""
    return f"""
            <div class="articles tournaments">
                <div class="articles-label">🏆 UPCOMING TOURNAMENTS · HOUSTON</div>
                {rows}
            </div>"""


def quote_band_html(quote):
    text, author = quote
    n = len(text)
    size = "q-lg" if n <= 70 else ("q-md" if n <= 120 else "q-sm")
    return f"""
  <div class="quote-band">
    <div class="quote-text {size}">“{html.escape(text)}”</div>
    <div class="quote-author">— {html.escape(author)}</div>
  </div>"""


def build_html(sections, weather, rates, tournaments, quote):
    from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("America/Chicago")).strftime("%A, %B %d, %Y — %I:%M %p CT")

    cards_html = ""
    for category, summary, takeaway, items in sections:
        if "Mortgage" in category:
            icon = "◈"
        elif "Disc" in category:
            icon = "◎"
        else:
            icon = "⬡"

        rate_block = rates_html(rates) if "Mortgage" in category else ""
        tourney_block = tournaments_html(tournaments) if "Disc" in category else ""
        takeaway_block = (
            f'<div class="takeaway"><span class="takeaway-lbl">TAKEAWAY</span>{takeaway}</div>'
            if takeaway else ""
        )

        cards_html += f"""
        <div class="card">
            <div class="card-header">
                <span class="card-icon">{icon}</span>
                <h2>{category}</h2>
                <span class="count-badge">{len(items)}</span>
            </div>
            {rate_block}
            <div class="summary">{summary}</div>
            {takeaway_block}
            <div class="articles">
                <div class="articles-label">LATEST</div>
                {headlines_html(items)}
            </div>
            {tourney_block}
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Launch Briefing</title>
<link rel="icon" href="data:image/svg+xml,&lt;svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'&gt;&lt;circle cx='16' cy='16' r='13' fill='%23c8f060'/&gt;&lt;/svg&gt;">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&family=DM+Mono&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg:      #0e0e10;
    --surface: #17171a;
    --border:  #2a2a30;
    --accent:  #c8f060;
    --accent2: #60c8f0;
    --accent3: #f0a060;
    --text:    #e8e8e0;
    --muted:   #888880;
    --serif:   'DM Serif Display', Georgia, serif;
    --sans:    'DM Sans', system-ui, sans-serif;
    --mono:    'DM Mono', monospace;
  }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-weight: 300;
    min-height: 100vh;
  }}

  header {{
    padding: 2.25rem 4rem 1.5rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 1.5rem;
  }}

  .logo {{
    font-family: var(--mono);
    font-size: 0.7rem;
    color: var(--accent);
    letter-spacing: 0.2em;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
  }}

  h1 {{
    font-family: var(--serif);
    font-size: clamp(1.8rem, 4vw, 2.8rem);
    font-weight: 400;
    line-height: 1.1;
    letter-spacing: -0.02em;
  }}

  .header-right {{
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.6rem;
  }}

  .weather {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    background: rgba(96,200,240,0.06);
    border: 1px solid rgba(96,200,240,0.18);
    padding: 0.5rem 0.9rem;
    border-radius: 12px;
  }}
  .wx-emoji {{ font-size: 1.5rem; line-height: 1; }}
  .wx-temp  {{ font-family: var(--serif); font-size: 1.6rem; color: var(--text); }}
  .wx-meta  {{ display: flex; flex-direction: column; gap: 0.1rem; }}
  .wx-loc   {{ font-family: var(--mono); font-size: 0.7rem; color: var(--accent2); letter-spacing: 0.04em; }}
  .wx-detail{{ font-family: var(--mono); font-size: 0.66rem; color: var(--muted); }}

  .timestamp {{
    font-family: var(--mono);
    font-size: 0.72rem;
    color: var(--muted);
    letter-spacing: 0.05em;
    text-align: right;
  }}

  .quote-band {{
    text-align: center;
    padding: 1.4rem 2rem 1.5rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    align-items: center;
  }}
  .quote-text {{
    font-family: var(--serif);
    font-style: italic;
    color: var(--text);
    line-height: 1.4;
    max-width: 760px;
    letter-spacing: -0.01em;
  }}
  .q-lg {{ font-size: clamp(1.1rem, 2.6vw, 1.6rem); }}
  .q-md {{ font-size: clamp(1rem, 2.2vw, 1.35rem); }}
  .q-sm {{ font-size: clamp(0.9rem, 1.9vw, 1.15rem); }}
  .quote-author {{
    font-family: var(--mono);
    font-size: 0.66rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent);
  }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
    gap: 1.5px;
    background: var(--border);
    border-top: 1.5px solid var(--border);
  }}

  .card {{
    background: var(--surface);
    padding: 1.75rem 2rem;
    display: flex;
    flex-direction: column;
    gap: 1.1rem;
  }}

  .card-header {{ display: flex; align-items: center; gap: 0.75rem; }}
  .card-icon   {{ font-size: 1.3rem; color: var(--accent); line-height: 1; }}
  .card:nth-child(2) .card-icon {{ color: var(--accent2); }}
  .card:nth-child(3) .card-icon {{ color: var(--accent3); }}

  h2 {{
    font-family: var(--serif);
    font-size: 1.3rem;
    font-weight: 400;
    letter-spacing: -0.01em;
  }}

  .count-badge {{
    margin-left: auto;
    font-family: var(--mono);
    font-size: 0.66rem;
    color: var(--muted);
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
    padding: 0.15rem 0.5rem;
    border-radius: 20px;
  }}

  /* Rates ticker */
  .rates {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }}
  .rate {{ background: rgba(96,200,240,0.05); padding: 0.7rem 0.5rem; text-align: center; }}
  .rate-val {{ font-family: var(--serif); font-size: 1.5rem; color: var(--accent2); line-height: 1; }}
  .rate-lbl {{ font-family: var(--mono); font-size: 0.55rem; letter-spacing: 0.1em; color: var(--muted); margin-top: 0.35rem; }}
  .rates-asof {{ font-family: var(--mono); font-size: 0.6rem; color: var(--muted); text-align: right; margin-top: -0.5rem; }}

  .summary {{
    font-size: 0.88rem;
    line-height: 1.65;
    color: #c8c8c0;
    padding: 1rem 1.1rem;
    background: rgba(255,255,255,0.03);
    border-left: 2px solid var(--accent);
    border-radius: 0 4px 4px 0;
  }}
  .card:nth-child(2) .summary {{ border-left-color: var(--accent2); }}
  .card:nth-child(3) .summary {{ border-left-color: var(--accent3); }}

  .takeaway {{
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text);
    padding: 0.2rem 0.1rem;
  }}
  .takeaway-lbl {{
    font-family: var(--mono);
    font-size: 0.55rem;
    letter-spacing: 0.15em;
    color: var(--accent);
    background: rgba(200,240,96,0.1);
    border: 1px solid rgba(200,240,96,0.25);
    padding: 0.15rem 0.45rem;
    border-radius: 4px;
    flex-shrink: 0;
  }}
  .card:nth-child(2) .takeaway-lbl {{ color: var(--accent2); background: rgba(96,200,240,0.1); border-color: rgba(96,200,240,0.25); }}
  .card:nth-child(3) .takeaway-lbl {{ color: var(--accent3); background: rgba(240,160,96,0.1); border-color: rgba(240,160,96,0.25); }}

  .articles {{ display: flex; flex-direction: column; gap: 0.1rem; }}
  .articles-label {{
    font-family: var(--mono);
    font-size: 0.62rem;
    letter-spacing: 0.18em;
    color: var(--muted);
    margin-bottom: 0.4rem;
  }}

  .article-link {{
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    text-decoration: none;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border);
    transition: background 0.15s;
  }}
  .article-link:last-child {{ border-bottom: none; }}
  .article-link:hover {{ background: rgba(255,255,255,0.02); }}

  .art-title {{
    font-size: 0.84rem;
    color: #c2c2ba;
    line-height: 1.35;
    transition: color 0.15s;
  }}
  .article-link:hover .art-title {{ color: var(--text); }}

  .art-meta {{ display: flex; align-items: center; gap: 0.5rem; }}
  .src {{
    font-family: var(--mono);
    font-size: 0.58rem;
    letter-spacing: 0.04em;
    color: var(--muted);
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
    padding: 0.05rem 0.4rem;
    border-radius: 4px;
  }}
  .art-age {{ font-family: var(--mono); font-size: 0.6rem; color: var(--muted); }}

  .new-dot {{
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--accent);
    margin-right: 0.4rem;
    vertical-align: middle;
    box-shadow: 0 0 6px var(--accent);
  }}

  /* Tournaments */
  .tournaments {{ margin-top: 0.5rem; }}
  .tourney {{
    display: flex;
    align-items: center;
    gap: 0.8rem;
    text-decoration: none;
    padding: 0.45rem 0;
    border-bottom: 1px solid var(--border);
  }}
  .tourney:last-child {{ border-bottom: none; }}
  .t-date {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-width: 2.6rem;
    font-family: var(--mono);
    line-height: 1.1;
    border-right: 1px solid var(--border);
    padding-right: 0.6rem;
  }}
  .t-date b {{ font-size: 1.1rem; color: var(--accent3); font-weight: 500; }}
  .t-date span {{ font-size: 0.55rem; letter-spacing: 0.12em; color: var(--muted); }}
  .t-body {{ display: flex; flex-direction: column; gap: 0.15rem; }}
  .t-name {{ font-size: 0.82rem; color: #c2c2ba; line-height: 1.3; transition: color 0.15s; }}
  .tourney:hover .t-name {{ color: var(--text); }}
  .t-loc {{ font-family: var(--mono); font-size: 0.62rem; color: var(--muted); }}

  footer {{
    padding: 1.5rem 4rem;
    font-family: var(--mono);
    font-size: 0.68rem;
    color: var(--muted);
    letter-spacing: 0.05em;
    border-top: 1px solid var(--border);
  }}

  @media (max-width: 640px) {{
    header, footer {{ padding-left: 1.5rem; padding-right: 1.5rem; }}
    .card {{ padding: 1.5rem; }}
  }}
</style>
</head>
<body>
<header>
  <div>
    <div class="logo">Jason · Personal Intelligence</div>
    <h1>Launch Briefing</h1>
  </div>
  <div class="header-right">
    {weather_html(weather)}
    <div class="timestamp">{now}<br>Powered by Claude + local stack</div>
  </div>
</header>
{quote_band_html(quote)}
<div class="grid">
{cards_html}
</div>
<footer>Generated by ai_dashboard.py · Summarized by Claude Haiku · Sources: RSS · Freddie Mac · US Treasury · Open-Meteo</footer>
</body>
</html>"""


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    log.info("── AI Dashboard Generator ──────────────────")

    if not API_KEY:
        log.error("ANTHROPIC_API_KEY environment variable is not set.")
        log.error('Set it with:  setx ANTHROPIC_API_KEY "sk-ant-..."  then reopen your terminal.')
        return

    wait_for_network()
    client = anthropic.Anthropic(api_key=API_KEY)

    quote = get_quote()
    log.info('Quote: "%s" — %s', quote[0][:50], quote[1])

    log.info("[Rates, Weather & Tournaments]")
    rates       = get_rates()
    weather     = get_weather()
    tournaments = get_tournaments()

    sections = []
    for category, feeds in FEEDS.items():
        log.info("[%s]", category.encode("ascii", "ignore").decode().strip() or category)
        items = []
        for name, url in feeds:
            items.extend(fetch_feed(name, url))
        # newest first; undated items sink to the bottom
        items.sort(key=lambda it: it["dt"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        log.info("  -> Summarizing with Claude...")
        summary, takeaway = summarize_news(client, category, items)
        sections.append((category, summary, takeaway, items))

    log.info("Building dashboard -> %s", OUTPUT_FILE)
    html = build_html(sections, weather, rates, tournaments, quote)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    # Auto-push to GitHub
    import subprocess
    REPO_DIR = r"C:\Users\jdbat\jdb-dashboard"
    try:
        import shutil
        shutil.copy(OUTPUT_FILE, REPO_DIR + r"\index.html")
        subprocess.run(["git", "-C", REPO_DIR, "add", "index.html"], check=True)
        subprocess.run(["git", "-C", REPO_DIR, "commit", "-m", "auto-update dashboard"], check=True)
        subprocess.run(["git", "-C", REPO_DIR, "push"], check=True)
        log.info("Dashboard pushed to GitHub successfully.")
    except Exception as e:
        log.warning("GitHub push failed: %s", e)
    webbrowser.open(OUTPUT_FILE.as_uri())
    log.info("Done. Run again anytime for a fresh briefing.")


if __name__ == "__main__":
    main()
