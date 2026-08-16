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
import json
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
    "AI & Technology": [
        ("The Rundown AI",       "https://rss.beehiiv.com/feeds/2R3C6Bt5wj.xml"),
        ("OpenAI News",          "https://openai.com/news/rss.xml"),
        ("Hugging Face Blog",    "https://huggingface.co/blog/feed.xml"),
    ],
    "Disc Golf": [
        ("PDGA News",            "https://www.pdga.com/rss.xml"),
        ("Ultiworld Disc Golf",  "https://discgolf.ultiworld.com/feed/"),
        ("Disc Golf Pro Tour",   "https://www.dgpt.com/feed/"),
    ],
    "Gaming": [
        ("IGN",                  "https://feeds.ign.com/ign/games-all"),
        ("Polygon",              "https://www.polygon.com/rss/index.xml"),
        ("Kotaku",                "https://kotaku.com/rss"),
    ],
}

# Each category gets its own funnel depth. AI & Technology is the flagship
# section and gets the full 5-step deep dive; Disc Golf and Gaming stay
# light on purpose -- a uniform depth across every card would turn the
# "launchpad" feeling back into a newspaper.
CATEGORY_STEPS = {
    "AI & Technology": [
        ("NEW",       "What's new"),
        ("UNLOCKS",   "What it unlocks"),
        ("MATTERS",   "Why it matters"),
        ("TRY",       "How to try it"),
        ("LEADS",     "Where it could lead"),
    ],
    "Disc Golf": [
        ("EVENT",     "Event / news"),
        ("MATTERS",   "Why it matters"),
        ("TAKEAWAY",  "One skill takeaway"),
    ],
    "Gaming": [
        ("RELEASE",   "Releases / updates"),
        ("MATTERS",   "What matters"),
        ("WATCH",     "What to watch"),
    ],
}

CATEGORY_ICONS = {
    "AI & Technology":  "\u2b21",  # hexagon
    "Expansion Signal": "\u25c8",  # diamond
    "Project Vote":     "\u25b3",  # triangle
    "Disc Golf":        "\u25ce",  # bullseye
    "Gaming":           "\u25a6",  # squares
}

# Fixed tag vocabulary for Project Vote -- keeps the tag row visually
# consistent instead of Claude inventing new emoji/labels every run.
PROJECT_VOTE_TAGS = {
    "MONEY":    ("\U0001F4B0", "Money"),
    "PORTFOLIO":("\U0001F3AF", "Portfolio"),
    "FUN":      ("\U0001F389", "Fun"),
    "PROTECTS": ("\U0001F6E1\uFE0F", "Protects"),
    "ADVENTURE":("\U0001F680", "Adventure"),
    "HELPS":    ("\U0001F91D", "Helps Others"),
}

PROJECT_VOTE_LOG = DASHBOARD_DIR / "project_vote_log.json"
MAX_VOTE_LOG_ENTRIES = 20   # stored history, a bit more than what's shown
MAX_VOTE_TRAIL_SHOWN = 12   # entries shown in the card's Recent Votes trail

MAX_ITEMS_PER_FEED  = 8     # fetched per source

# --- Feed freshness controls ---
MAX_AGE_HOURS = 48        # Drop feed entries older than this many hours
KEEP_UNDATED = False      # If a feed entry has no parseable date: True=keep, False=drop

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
            dt = entry_datetime(entry)
            # Freshness filter: drop stale or (optionally) undated entries
            if dt is None:
                if not KEEP_UNDATED:
                    continue
            else:
                age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
                if age_hours > MAX_AGE_HOURS:
                    continue
            if title:
                items.append({
                    "title": title, "link": link, "desc": desc,
                    "source": name, "dt": dt,
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
    """Return an OrderedDict of {step_key: step_text} following that
    category's funnel depth (CATEGORY_STEPS), or a single-key dict with an
    explanatory message if there's nothing to summarize."""
    steps = CATEGORY_STEPS[category]
    if not items:
        return {steps[0][0]: "No articles retrieved for this category."}

    lines = [f"- {it['title']}: {it['desc']}" for it in items[:MAX_SUMMARY_LINES]]
    step_instructions = "\n".join(
        f"{key}: {label} \u2014 1-2 sentences, specific (names, numbers, facts), no filler."
        for key, label in steps
    )

    prompt = f"""You are writing one section of Jason's personal daily briefing.
Category: {category}

Headlines:
{chr(10).join(lines)}

Write the following steps IN ORDER, each on its own line, each starting
with the exact label shown (including the colon), plain text only, no
markdown, no bullets, no restating the label in the sentence itself:

{step_instructions}

Ground everything in the actual headlines above. If a step genuinely
doesn't apply to today's headlines, still write one honest sentence for
it rather than skipping it."""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=420,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
    except Exception as e:
        log.warning("  ERR summary (%s): %s", category, e)
        return {steps[0][0]: f"Summary unavailable: {e}"}

    result = {}
    for key, _label in steps:
        m = re.search(rf"^{key}:\s*(.+?)(?=\n[A-Z]+:|\Z)", text, re.MULTILINE | re.DOTALL)
        if m:
            result[key] = re.sub(r"\s+", " ", m.group(1)).strip()
    if not result:
        # Parsing failed entirely (model didn't follow the format) -- fall
        # back to showing the raw text under the first step so nothing is
        # silently lost.
        result = {steps[0][0]: text}
    return result


def generate_expansion_signal(client, ai_items):
    """Second-order synthesis pass over the same AI & Technology headlines:
    connect the dots across them and name one emerging opportunity."""
    if not ai_items:
        return {"SIGNAL": "No AI & Technology headlines to draw a pattern from today."}

    lines = [f"- {it['title']}: {it['desc']}" for it in ai_items[:MAX_SUMMARY_LINES]]
    prompt = f"""You are writing the "Expansion Signal" section of Jason's personal
daily briefing -- a step beyond just reporting AI/tech news.

Today's AI & Technology headlines:
{chr(10).join(lines)}

Write exactly two labeled parts, plain text, no markdown, no bullets:

CONNECT: 1-2 sentences connecting the dots across TWO OR MORE of today's
headlines into a single underlying pattern -- not just describing one
story on its own.

OPPORTUNITY: 1-2 sentences naming the specific emerging opportunity that
pattern points to for Jason -- someone who builds real tools with AI as
a technically capable non-developer. Be concrete, not motivational."""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=260,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
    except Exception as e:
        log.warning("  ERR expansion signal: %s", e)
        return {"SIGNAL": f"Expansion signal unavailable: {e}"}

    result = {}
    for key in ("CONNECT", "OPPORTUNITY"):
        m = re.search(rf"^{key}:\s*(.+?)(?=\n[A-Z]+:|\Z)", text, re.MULTILINE | re.DOTALL)
        if m:
            result[key] = re.sub(r"\s+", " ", m.group(1)).strip()
    if not result:
        result = {"CONNECT": text}
    return result


def load_vote_log():
    try:
        with open(PROJECT_VOTE_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_vote_log(log_entries):
    try:
        with open(PROJECT_VOTE_LOG, "w", encoding="utf-8") as f:
            json.dump(log_entries[-MAX_VOTE_LOG_ENTRIES:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("  ERR saving project vote log: %s", e)


def generate_project_vote(client, ai_items):
    """One concrete build idea drawn from today's AI/tech headlines, tagged
    against Jason's own filter (money/portfolio/fun/etc), and appended to a
    persisted log so patterns across days become visible over time."""
    vote_log = load_vote_log()
    recent_titles = [v["title"] for v in vote_log[-6:]]
    avoid_line = (
        f"Avoid repeating or lightly rewording these recent picks: {'; '.join(recent_titles)}."
        if recent_titles else ""
    )

    if not ai_items:
        result = {"IDEA": "No headlines today to draw a build idea from.", "tags": []}
        return result

    lines = [f"- {it['title']}: {it['desc']}" for it in ai_items[:MAX_SUMMARY_LINES]]
    tag_list = ", ".join(PROJECT_VOTE_TAGS.keys())
    prompt = f"""You are writing the "Project Vote" section of Jason's personal daily
briefing: one concrete thing worth building or testing today, drawn from
today's AI & Technology headlines.

Jason is a technically capable non-developer who builds real tools with AI
assistance (Make.com, Python scripts, Cloudflare Workers, Claude). He wants
ideas that could: make money, help others, be genuinely useful to him, be
fun, be an adventure, or be a portfolio piece -- ideally hitting more than
one of those at once. {avoid_line}

Headlines:
{chr(10).join(lines)}

Write exactly these labeled parts, plain text, no markdown, no bullets:

TITLE: A short project name, a few words.
IDEA: 1 sentence naming the build idea itself.
WHY_NOW: 1 sentence on why this specific headline/moment makes it timely.
SMALLEST: 1 sentence describing the smallest version worth actually building today.
TAGS: 2-3 tags from this exact list, comma-separated, choosing only ones that genuinely apply: {tag_list}"""

    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=320,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
    except Exception as e:
        log.warning("  ERR project vote: %s", e)
        return {"IDEA": f"Project vote unavailable: {e}", "tags": []}

    result = {}
    for key in ("TITLE", "IDEA", "WHY_NOW", "SMALLEST"):
        m = re.search(rf"^{key}:\s*(.+?)(?=\n[A-Z_]+:|\Z)", text, re.MULTILINE | re.DOTALL)
        if m:
            result[key] = re.sub(r"\s+", " ", m.group(1)).strip()

    tags = []
    m = re.search(r"^TAGS:\s*(.+?)(?=\n[A-Z_]+:|\Z)", text, re.MULTILINE | re.DOTALL)
    if m:
        for raw in m.group(1).split(","):
            key = raw.strip().upper()
            if key in PROJECT_VOTE_TAGS:
                tags.append(key)
    result["tags"] = tags

    if "TITLE" in result:
        from datetime import date as _date
        vote_log.append({"date": _date.today().isoformat(), "title": result["TITLE"], "tags": tags, "flagged": False})
        save_vote_log(vote_log)
        result["_recent"] = vote_log[-(MAX_VOTE_TRAIL_SHOWN + 1):-1]  # prior entries, excluding today's

    return result


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


def funnel_html(steps, result):
    blocks = ""
    for key, label in steps:
        text = result.get(key, "")
        if not text:
            continue
        blocks += f"""
            <div class="funnel-step">
                <span class="step-lbl">{html.escape(label).upper()}</span>
                <p>{html.escape(text)}</p>
            </div>"""
    return blocks


def expansion_signal_html(result):
    blocks = ""
    if result.get("CONNECT"):
        blocks += f'<div class="funnel-step"><span class="step-lbl">CONNECT THE DOTS</span><p>{html.escape(result["CONNECT"])}</p></div>'
    if result.get("OPPORTUNITY"):
        blocks += f'<div class="funnel-step"><span class="step-lbl">THE OPPORTUNITY</span><p>{html.escape(result["OPPORTUNITY"])}</p></div>'
    return blocks


def project_vote_html(result):
    tags = result.get("tags", [])
    tag_pills = "".join(
        f'<span class="vote-tag">{PROJECT_VOTE_TAGS[t][0]} {PROJECT_VOTE_TAGS[t][1]}</span>'
        for t in tags if t in PROJECT_VOTE_TAGS
    )
    tag_row = f'<div class="vote-tags">{tag_pills}</div>' if tag_pills else ""

    blocks = ""
    for key, label in (("IDEA", "The idea"), ("WHY_NOW", "Why now"), ("SMALLEST", "Smallest version")):
        if result.get(key):
            blocks += f'<div class="funnel-step"><span class="step-lbl">{label.upper()}</span><p>{html.escape(result[key])}</p></div>'

    recent = result.get("_recent", [])
    recent_html = ""
    if recent:
        rows = ""
        for v in reversed(recent):
            flagged = v.get("flagged", False)
            row_class = " flagged" if flagged else ""
            star = '<span class="vt-star">\u2605</span>' if flagged else ""
            rows += f'<div class="vote-trail-row{row_class}">{star}<span class="vt-date">{v["date"]}</span><span class="vt-title">{html.escape(v["title"])}</span></div>'
        recent_html = f"""
            <div class="vote-trail">
                <div class="articles-label">RECENT VOTES</div>
                {rows}
            </div>"""

    return result.get("TITLE", ""), tag_row, blocks, recent_html


def build_html(cards, weather, tournaments, quote):
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/Chicago")).strftime("%A, %B %d, %Y — %I:%M %p CT")

    cards_html = ""
    for card in cards:
        kind = card["kind"]
        category = card["category"]
        icon = CATEGORY_ICONS.get(category, "\u25c7")
        css_class = card["css_class"]

        if kind == "vote":
            title, tag_row, blocks, recent_html = project_vote_html(card["result"])
            title_html = f'<div class="vote-title">{html.escape(title)}</div>' if title else ""
            cards_html += f"""
        <div class="card {css_class}">
            <div class="card-header">
                <span class="card-icon">{icon}</span>
                <h2>{category}</h2>
            </div>
            {title_html}
            {tag_row}
            {blocks}
            {recent_html}
        </div>"""
            continue

        if kind == "signal":
            blocks = expansion_signal_html(card["result"])
            cards_html += f"""
        <div class="card {css_class}">
            <div class="card-header">
                <span class="card-icon">{icon}</span>
                <h2>{category}</h2>
            </div>
            {blocks}
        </div>"""
            continue

        # kind == "funnel" -- AI & Technology, Disc Golf, Gaming
        items = card["items"]
        blocks = funnel_html(CATEGORY_STEPS[category], card["result"])
        extra_block = tournaments_html(tournaments) if category == "Disc Golf" else ""
        cards_html += f"""
        <div class="card {css_class}">
            <div class="card-header">
                <span class="card-icon">{icon}</span>
                <h2>{category}</h2>
                <span class="count-badge">{len(items)}</span>
            </div>
            {blocks}
            <div class="articles">
                <div class="articles-label">LATEST</div>
                {headlines_html(items)}
            </div>
            {extra_block}
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
    --accent4: #d060f0;
    --accent5: #60f0a8;
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
  .card-signal .card-icon {{ color: var(--accent2); }}
  .card-vote   .card-icon {{ color: var(--accent3); }}
  .card-disc   .card-icon {{ color: var(--accent4); }}
  .card-gaming .card-icon {{ color: var(--accent5); }}

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

  .funnel-step {{
    font-size: 0.88rem;
    line-height: 1.6;
    color: #c8c8c0;
    padding: 0.85rem 1.1rem;
    background: rgba(255,255,255,0.03);
    border-left: 2px solid var(--accent);
    border-radius: 0 4px 4px 0;
  }}
  .funnel-step .step-lbl {{
    display: block;
    font-family: var(--mono);
    font-size: 0.58rem;
    letter-spacing: 0.15em;
    color: var(--accent);
    margin-bottom: 0.35rem;
  }}
  .funnel-step p {{ color: #c8c8c0; }}
  .card-signal .funnel-step {{ border-left-color: var(--accent2); }}
  .card-signal .funnel-step .step-lbl {{ color: var(--accent2); }}
  .card-vote .funnel-step {{ border-left-color: var(--accent3); }}
  .card-vote .funnel-step .step-lbl {{ color: var(--accent3); }}
  .card-disc .funnel-step {{ border-left-color: var(--accent4); }}
  .card-disc .funnel-step .step-lbl {{ color: var(--accent4); }}
  .card-gaming .funnel-step {{ border-left-color: var(--accent5); }}
  .card-gaming .funnel-step .step-lbl {{ color: var(--accent5); }}

  .vote-title {{
    font-family: var(--serif);
    font-size: 1.5rem;
    color: var(--text);
    line-height: 1.2;
  }}

  .vote-tags {{ display: flex; flex-wrap: wrap; gap: 0.5rem; }}
  .vote-tag {{
    font-family: var(--mono);
    font-size: 0.66rem;
    letter-spacing: 0.05em;
    color: var(--accent3);
    background: rgba(240,160,96,0.1);
    border: 1px solid rgba(240,160,96,0.25);
    padding: 0.25rem 0.6rem;
    border-radius: 20px;
    white-space: nowrap;
  }}

  .vote-trail {{ display: flex; flex-direction: column; gap: 0.1rem; }}
  .vote-trail-row {{
    display: flex;
    align-items: baseline;
    gap: 0.7rem;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.8rem;
  }}
  .vote-trail-row:last-child {{ border-bottom: none; }}
  .vt-date {{ font-family: var(--mono); font-size: 0.62rem; color: var(--muted); flex-shrink: 0; }}
  .vt-title {{ color: #b8b8b0; }}
  .vote-trail-row.flagged {{ background: rgba(240,160,96,0.06); border-radius: 4px; padding-left: 0.4rem; }}
  .vote-trail-row.flagged .vt-title {{ color: var(--text); }}
  .vt-star {{ color: var(--accent3); font-size: 0.7rem; flex-shrink: 0; }}

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
<footer>Generated by ai_dashboard.py · Summarized by Claude Haiku · Sources: RSS · Open-Meteo</footer>
</body>
</html>"""


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    # --- Windowed run gate (absorbs GitHub Actions cron lag) -----------------
    # GitHub fires scheduled crons late and imprecisely. Instead of demanding an
    # exact hour, accept a WINDOW and run only the first cron that lands in it:
    #   Morning: 5:00-9:59 AM CT   Midday: 11:00 AM-3:59 PM CT
    # run_state.json remembers which slots ran today so later stragglers exit
    # clean and we never double-run. Manual runs (RUN_NOW=1) bypass the gate.
    import os, sys, json
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI

    if os.environ.get("RUN_NOW") != "1":
        _now = _dt.now(_ZI("America/Chicago"))
        _today = _now.strftime("%Y-%m-%d")
        _hour = _now.hour

        # Which window are we in?
        if 5 <= _hour < 10:
            _slot = "morning"
        elif 11 <= _hour < 16:
            _slot = "midday"
        else:
            _slot = None

        if _slot is None:
            log.info("Outside run windows (CT hour=%s). Exiting cleanly.", _hour)
            sys.exit(0)

        # Load today's run state (reset if it's a new day or file is missing)
        _state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_state.json")
        _state = {"date": _today, "morning": False, "midday": False}
        try:
            with open(_state_path, "r", encoding="utf-8") as _f:
                _loaded = json.load(_f)
            if _loaded.get("date") == _today:
                _state = _loaded
        except Exception:
            pass  # missing/corrupt -> start fresh for today

        if _state.get(_slot):
            log.info("Slot '%s' already ran today (%s). Exiting cleanly.", _slot, _today)
            sys.exit(0)

        # Claim the slot BEFORE heavy work so a near-simultaneous cron sees it taken
        _state["date"] = _today
        _state[_slot] = True
        try:
            with open(_state_path, "w", encoding="utf-8") as _f:
                json.dump(_state, _f)
            log.info("Claimed slot '%s' for %s; proceeding with run.", _slot, _today)
        except Exception as _e:
            log.warning("Could not write run_state.json: %s", _e)
    # ------------------------------------------------------------------------
    log.info("── AI Dashboard Generator ──────────────────")

    if not API_KEY:
        log.error("ANTHROPIC_API_KEY environment variable is not set.")
        log.error('Set it with:  setx ANTHROPIC_API_KEY "sk-ant-..."  then reopen your terminal.')
        return

    wait_for_network()
    client = anthropic.Anthropic(api_key=API_KEY)

    quote = get_quote()
    log.info('Quote: "%s" — %s', quote[0][:50], quote[1])

    log.info("[Weather & Tournaments]")
    weather     = get_weather()
    tournaments = get_tournaments()

    # Fetch every feed category up front -- AI & Technology's items get
    # reused by Expansion Signal and Project Vote, not just its own card.
    items_by_category = {}
    for category, feeds in FEEDS.items():
        log.info("[%s]", category)
        items = []
        for name, url in feeds:
            items.extend(fetch_feed(name, url))
        items.sort(key=lambda it: it["dt"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        items_by_category[category] = items

    ai_items = items_by_category.get("AI & Technology", [])

    cards = []

    log.info("[AI & Technology] -> Summarizing with Claude...")
    ai_result = summarize_news(client, "AI & Technology", ai_items)
    cards.append({"kind": "funnel", "category": "AI & Technology", "css_class": "card-ai",
                  "result": ai_result, "items": ai_items})

    log.info("[Expansion Signal] -> Synthesizing with Claude...")
    signal_result = generate_expansion_signal(client, ai_items)
    cards.append({"kind": "signal", "category": "Expansion Signal", "css_class": "card-signal",
                  "result": signal_result})

    log.info("[Project Vote] -> Generating with Claude...")
    vote_result = generate_project_vote(client, ai_items)
    cards.append({"kind": "vote", "category": "Project Vote", "css_class": "card-vote",
                  "result": vote_result})

    disc_items = items_by_category.get("Disc Golf", [])
    log.info("[Disc Golf] -> Summarizing with Claude...")
    disc_result = summarize_news(client, "Disc Golf", disc_items)
    cards.append({"kind": "funnel", "category": "Disc Golf", "css_class": "card-disc",
                  "result": disc_result, "items": disc_items})

    gaming_items = items_by_category.get("Gaming", [])
    log.info("[Gaming] -> Summarizing with Claude...")
    gaming_result = summarize_news(client, "Gaming", gaming_items)
    cards.append({"kind": "funnel", "category": "Gaming", "css_class": "card-gaming",
                  "result": gaming_result, "items": gaming_items})

    log.info("Building dashboard -> %s", OUTPUT_FILE)
    html = build_html(cards, weather, tournaments, quote)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    # Auto-push to GitHub
    import subprocess
    REPO_DIR = r"C:\Users\jdbat\jdb-dashboard"
    try:
        import shutil
        # In GitHub Actions, the workflow handles the commit/push and REPO_DIR
        # (a local Windows path) does not exist on the runner. Skip the in-script
        # push there; only push from local runs.
        if os.environ.get("GITHUB_ACTIONS") == "true":
            log.info("Running in GitHub Actions; workflow handles push. Skipping in-script push.")
        else:
            shutil.copy(OUTPUT_FILE, REPO_DIR + r"\index.html")
            subprocess.run(["git", "-C", REPO_DIR, "add", "index.html", "project_vote_log.json"], check=True)
            subprocess.run(["git", "-C", REPO_DIR, "commit", "-m", "auto-update dashboard"], check=True)
            subprocess.run(["git", "-C", REPO_DIR, "push"], check=True)
            log.info("Dashboard pushed to GitHub successfully.")
    except Exception as e:
        log.warning("GitHub push failed: %s", e)
    webbrowser.open(OUTPUT_FILE.as_uri())
    log.info("Done. Run again anytime for a fresh briefing.")


if __name__ == "__main__":
    main()
