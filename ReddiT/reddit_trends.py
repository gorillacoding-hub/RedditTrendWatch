#!/usr/bin/env python3
"""
Reddit Political Trends 3.0
Read-only research tool: collects public Reddit RSS feeds, finds emerging
discussion topics, and shows them in a local web dashboard.

Standard library only. Works in Termux.

Quick start:
    python reddit_trends.py serve          # open http://127.0.0.1:8765
    python reddit_trends.py add            # type subreddits, 'done' to save
    python reddit_trends.py run --country morocco
    python reddit_trends.py --help
"""
import argparse
import collections
import csv
import email.utils
import html
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

APP_VERSION = "3.0"
BASE = Path(os.environ.get("RPT_HOME", Path.home() / "RedditPoliticalTrends"))
DB = BASE / "trends.db"
EXPORTS = BASE / "exports"
SCRIPT = Path(__file__).resolve()
SCHEMA_VERSION = 3
SUB_RE = re.compile(r"^[A-Za-z0-9_]{2,21}$")
LIST_NAME_RE = re.compile(r"^[\w .\-]{1,40}$", re.UNICODE)

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
# Country entries are "Name|sub1,sub2". An empty sub list means "no curated
# community known": the country name is tried as the subreddit and flagged
# as a guess in the interface. Use Verify (GUI) to check any subreddit.
_COUNTRY_DATA = """
Afghanistan|Afghanistan
Albania|Shqiperia,albania
Algeria|algeria
Andorra|Andorra
Angola|angola
Antigua and Barbuda|
Argentina|argentina,RepublicaArgentina
Armenia|armenia
Australia|australia,AustralianPolitics
Austria|Austria,oesterreich
Azerbaijan|azerbaijan
Bahamas|Bahamas
Bahrain|Bahrain
Bangladesh|bangladesh
Barbados|Barbados
Belarus|belarus
Belgium|belgium
Belize|belize
Benin|
Bhutan|Bhutan
Bolivia|Bolivia
Bosnia and Herzegovina|bih
Botswana|Botswana
Brazil|brasil,brasilivre
Brunei|Brunei
Bulgaria|bulgaria
Burkina Faso|burkinafaso
Burundi|Burundi
Cabo Verde|CapeVerde
Cambodia|cambodia
Cameroon|Cameroon
Canada|CanadaPolitics,canada,onguardforthee
Central African Republic|
Chad|Chad
Chile|chile
China|China,sino
Colombia|Colombia
Comoros|
Costa Rica|costarica
Croatia|croatia
Cuba|Cuba
Cyprus|cyprus
Czechia|czech
Democratic Republic of the Congo|Congo
Denmark|Denmark
Djibouti|Djibouti
Dominica|
Dominican Republic|DominicanRepublic
Ecuador|ecuador
Egypt|Egypt
El Salvador|ElSalvador
Equatorial Guinea|
Eritrea|Eritrea
Estonia|Eesti
Eswatini|Eswatini
Ethiopia|Ethiopia
Fiji|Fiji
Finland|Suomi,finland
France|france,europe
Gabon|
Gambia|Gambia
Georgia|Sakartvelo
Germany|germany,de
Ghana|ghana
Greece|greece
Grenada|
Guatemala|guatemala
Guinea|
Guinea-Bissau|
Guyana|Guyana
Haiti|Haiti
Honduras|Honduras
Hungary|hungary
Iceland|Iceland
India|india,IndiaSpeaks,IndianPolitics
Indonesia|indonesia
Iran|iran,NewIran
Iraq|Iraq
Ireland|ireland,irishpolitics
Israel|Israel
Italy|italy
Ivory Coast|CoteDIvoire
Jamaica|jamaica
Japan|japan
Jordan|jordan
Kazakhstan|Kazakhstan
Kenya|Kenya
Kiribati|
Kosovo|kosovo
Kuwait|Kuwait
Kyrgyzstan|Kyrgyzstan
Laos|Laos
Latvia|latvia
Lebanon|lebanon
Lesotho|
Liberia|Liberia
Libya|Libya
Liechtenstein|
Lithuania|lithuania
Luxembourg|luxembourg
Madagascar|madagascar
Malawi|Malawi
Malaysia|malaysia
Maldives|Maldives
Mali|Mali
Malta|malta
Marshall Islands|
Mauritania|Mauritania
Mauritius|Mauritius
Mexico|mexico
Micronesia|
Moldova|moldova
Monaco|
Mongolia|mongolia
Montenegro|montenegro
Morocco|Morocco,Casablanca,MoroccoPolitics
Mozambique|Mozambique
Myanmar|Burma
Namibia|namibia
Nauru|
Nepal|nepal
Netherlands|thenetherlands,nederlands
New Zealand|newzealand
Nicaragua|nicaragua
Niger|
Nigeria|Nigeria
North Korea|northkorea
North Macedonia|Macedonia
Norway|norway
Oman|Oman
Pakistan|pakistan
Palau|
Palestine|Palestine
Panama|Panama
Papua New Guinea|PapuaNewGuinea
Paraguay|Paraguay
Peru|PERU
Philippines|Philippines,PHPolitics
Poland|poland,Polska
Portugal|portugal
Qatar|qatar
Romania|Romania
Russia|russia
Rwanda|Rwanda
Saint Kitts and Nevis|
Saint Lucia|
Saint Vincent and the Grenadines|
Samoa|
San Marino|
Sao Tome and Principe|
Saudi Arabia|saudiarabia
Senegal|Senegal
Serbia|serbia
Seychelles|Seychelles
Sierra Leone|SierraLeone
Singapore|singapore
Slovakia|Slovakia
Slovenia|slovenia
Solomon Islands|
Somalia|Somalia
South Africa|southafrica
South Korea|korea
South Sudan|southsudan
Spain|spain,es
Sri Lanka|srilanka
Sudan|Sudan
Suriname|Suriname
Sweden|sweden
Switzerland|switzerland
Syria|syria
Taiwan|taiwan
Tajikistan|Tajikistan
Tanzania|tanzania
Thailand|thailand
Timor-Leste|
Togo|Togo
Tonga|
Trinidad and Tobago|TrinidadandTobago
Tunisia|Tunisia
Turkey|turkey
Turkmenistan|Turkmenistan
Tuvalu|
Uganda|Uganda
Ukraine|ukraine,ukraina
United Arab Emirates|UAE
United Kingdom|unitedkingdom,ukpolitics,uknews
United States|politics,PoliticalDiscussion,neutralpolitics,moderatepolitics,conservative,liberal,Libertarian
Uruguay|uruguay
Uzbekistan|Uzbekistan
Vanuatu|
Vatican City|
Venezuela|vzla
Vietnam|vietnam
Yemen|Yemen
Zambia|zambia
Zimbabwe|zimbabwe
"""

# Older versions used these short keys.
ALIASES = {"usa": "united_states", "uk": "united_kingdom"}

GLOBAL_SUBS = [
    "politics", "PoliticalDiscussion", "neutralpolitics", "moderatepolitics",
    "geopolitics", "worldnews", "news", "conservative", "liberal",
    "libertarian", "socialism", "europe", "CanadaPolitics", "india",
    "Morocco", "unitedkingdom", "france",
]

# Ready-made pools users can mix and match.
GROUPS = {
    "General politics": ["politics", "worldpolitics", "inthenews", "PoliticalDiscussion"],
    "Balanced discussion": ["neutralpolitics", "moderatepolitics", "centrist", "PoliticalDiscussion"],
    "World news": ["worldnews", "news", "geopolitics", "worldpolitics"],
    "Left-leaning": ["liberal", "democrats", "progressive", "socialism", "AskALiberal"],
    "Right-leaning": ["conservative", "Republican", "AskConservatives", "Libertarian"],
    "Economy and business": ["economics", "economy", "finance", "business"],
    "Technology and privacy": ["technology", "privacy", "Futurology", "artificial"],
    "Environment and energy": ["environment", "climate", "energy"],
    "Conflicts and security": ["ukraine", "CredibleDefense", "geopolitics", "NonCredibleDefense"],
    "Regional hubs": ["europe", "asia", "africa", "latinamerica", "middleeast"],
}

CATEGORIES = {
    "Elections": ["election", "electoral", "ballot", "voting", "vote",
                  "candidate", "campaign", "poll", "parliamentary election"],
    "Government and policy": ["government", "minister", "president", "parliament",
                              "congress", "legislation", "policy", "law", "bill",
                              "cabinet", "administration"],
    "Geopolitics and conflicts": ["war", "conflict", "military", "troops", "invasion",
                                  "ceasefire", "sanctions", "nato", "diplomacy",
                                  "iran", "ukraine", "russia", "israel", "palestine"],
    "Economy and trade": ["economy", "inflation", "tax", "trade", "tariff",
                          "unemployment", "budget", "debt", "recession",
                          "interest rates", "cost of living"],
    "Immigration": ["immigration", "immigrant", "migration", "migrant",
                    "asylum", "border", "deportation", "refugee"],
    "Civil liberties and privacy": ["privacy", "surveillance", "censorship",
                                    "free speech", "protest", "rights", "freedom",
                                    "police", "security"],
    "Technology and regulation": ["artificial intelligence", " AI ", "technology",
                                  "regulation", "social media", "data protection",
                                  "platform", "encryption"],
    "Public services": ["healthcare", "health care", "education", "housing",
                        "transport", "energy", "public services"],
}

STOP = set("""
a an the and or but if then else of to in on at by for from
with without about into over after before between under through
is are was were be been being it its this that these those
i you he she we they them their our your as not no yes do does
did have has had can could would should will may might must
what when where why who how which while than too very more most
some any all each other same just also only now new latest
news update breaking report reports says said people country
countries government political politics president minister
official officials today yesterday tomorrow
""".split())


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


COUNTRIES = {}
for _line in _COUNTRY_DATA.strip().splitlines():
    _name, _, _subs = _line.partition("|")
    _list = [s for s in _subs.split(",") if s]
    COUNTRIES[slug(_name)] = {
        "name": _name,
        "subs": _list or [re.sub(r"[^A-Za-z0-9]", "", _name)],
        "curated": bool(_list),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now():
    return datetime.now(timezone.utc)


def ts(dt):
    return dt.astimezone(timezone.utc).timestamp()


def say(*parts):
    print(*parts, flush=True)


def normalize_sub(raw):
    """Accepts 'name', 'r/name', '/r/name' or a reddit URL. Returns name or ''."""
    text = (raw or "").strip()
    match = re.search(r"(?:^|/)r/([A-Za-z0-9_]{2,21})", text)
    if match:
        return match.group(1)
    text = text.strip("/ ")
    return text if SUB_RE.match(text) else ""


def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return ts(dt)
    except Exception:
        try:
            dt = email.utils.parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return ts(dt)
        except Exception:
            return ts(now())


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    country TEXT NOT NULL,
    subreddit TEXT NOT NULL,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    published REAL NOT NULL,
    collected REAL NOT NULL DEFAULT 0,
    first_seen REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS post_time ON posts(published);
CREATE INDEX IF NOT EXISTS post_scope ON posts(country, published);
CREATE TABLE IF NOT EXISTS alerts (
    phrase TEXT NOT NULL,
    day TEXT NOT NULL,
    PRIMARY KEY (phrase, day)
);
CREATE TABLE IF NOT EXISTS lists (
    name TEXT PRIMARY KEY,
    subs TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    kind TEXT NOT NULL,
    started REAL NOT NULL,
    finished REAL,
    communities INTEGER NOT NULL DEFAULT 0,
    fetched INTEGER NOT NULL DEFAULT 0,
    new_posts INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
);
CREATE TABLE IF NOT EXISTS fetch_log (
    run_id INTEGER NOT NULL,
    subreddit TEXT NOT NULL,
    fetched INTEGER NOT NULL DEFAULT 0,
    added INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS fetch_run ON fetch_log(run_id);
CREATE TABLE IF NOT EXISTS snapshots (
    run_id INTEGER NOT NULL,
    scope TEXT NOT NULL,
    generated REAL NOT NULL,
    rank INTEGER NOT NULL,
    phrase TEXT NOT NULL,
    status TEXT NOT NULL,
    mentions INTEGER NOT NULL,
    communities INTEGER NOT NULL,
    growth REAL NOT NULL,
    score REAL NOT NULL,
    top_title TEXT,
    top_link TEXT,
    top_sub TEXT
);
CREATE INDEX IF NOT EXISTS snap_run ON snapshots(run_id);
CREATE INDEX IF NOT EXISTS snap_scope ON snapshots(scope, generated);
"""


def connect():
    BASE.mkdir(parents=True, exist_ok=True)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if version < SCHEMA_VERSION:
        has_posts = con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='posts'").fetchone()
        if has_posts and DB.exists():
            backup = BASE / f"trends.db.backup.pre{SCHEMA_VERSION}_{now():%Y%m%d_%H%M%S}"
            shutil.copy2(DB, backup)
    con.executescript(SCHEMA)
    con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    con.commit()
    return con


def post_columns(con):
    return {r[1] for r in con.execute("PRAGMA table_info(posts)")}


# ---------------------------------------------------------------------------
# Scopes: a scope is "global", a country key, or "list:<name>"
# ---------------------------------------------------------------------------
def get_list(con, name):
    row = con.execute("SELECT subs FROM lists WHERE name=?", (name,)).fetchone()
    return json.loads(row["subs"]) if row else None


def save_list(con, name, subs):
    name = name.strip()
    if not LIST_NAME_RE.match(name):
        raise ValueError("List name must be 1-40 letters, numbers, spaces, - or _.")
    cleaned = []
    for raw in subs:
        sub = normalize_sub(raw)
        if sub and sub.lower() not in [c.lower() for c in cleaned]:
            cleaned.append(sub)
    if not cleaned:
        raise ValueError("Add at least one valid subreddit.")
    if len(cleaned) > 200:
        raise ValueError("A list can hold up to 200 subreddits.")
    con.execute(
        "INSERT INTO lists(name,subs,created) VALUES (?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET subs=excluded.subs",
        (name, json.dumps(cleaned), ts(now())))
    con.commit()
    return cleaned


def resolve(con, scope):
    """Returns (scope_key, label, subreddits). Raises ValueError if unknown."""
    scope = ALIASES.get(scope, scope)
    if scope == "global":
        return "global", "Worldwide", GLOBAL_SUBS
    if scope.startswith("list:"):
        name = scope[5:]
        subs = get_list(con, name)
        if subs is None:
            raise ValueError(f"No saved list named '{name}'.")
        return scope, name, subs
    if scope in COUNTRIES:
        c = COUNTRIES[scope]
        return scope, c["name"], c["subs"]
    raise ValueError(f"Unknown region '{scope}'.")


def scope_label(scope):
    scope = ALIASES.get(scope, scope)
    if scope == "global":
        return "Worldwide"
    if scope.startswith("list:"):
        return scope[5:]
    return COUNTRIES.get(scope, {}).get("name", scope)


def scope_args(scope):
    scope = ALIASES.get(scope, scope)
    return ["--list", scope[5:]] if scope.startswith("list:") else ["--country", scope]


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------
def fetch(subreddit, limit=100):
    """Returns (status, posts). status is 'ok' or a short error message."""
    url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit={limit}"
    req = urllib.request.Request(url, headers={
        "User-Agent": f"RedditPoliticalTrends/{APP_VERSION} (read-only research)",
        "Accept": "application/atom+xml, application/xml",
    })
    last = "error"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                root = ET.fromstring(response.read())
            ns = "{http://www.w3.org/2005/Atom}"
            results = []
            for entry in root.findall(f".//{ns}entry"):
                def get(tag):
                    node = entry.find(f"{ns}{tag}")
                    return node.text.strip() if node is not None and node.text else ""
                title = clean(get("title"))
                post_id = get("id")
                published = parse_date(get("published"))
                node = entry.find(f"{ns}link")
                link = node.attrib.get("href", "") if node is not None else ""
                if title and link and post_id:
                    results.append((post_id, title, link, published))
            return "ok", results
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code == 404:
                return "not found, private or banned", []
            if exc.code == 429 or exc.code >= 500:
                time.sleep((attempt + 1) * 8)
                continue
            return last, []
        except Exception as exc:
            last = f"network error: {str(exc)[:60]}"
            time.sleep(4)
    return last, []


def collect(con, scope, keep_days=30):
    key, label, subs = resolve(con, scope)
    started = ts(now())
    run_id = con.execute(
        "INSERT INTO runs(scope,kind,started,communities) VALUES (?,?,?,?)",
        (key, "collect", started, len(subs))).lastrowid
    con.commit()
    cols = post_columns(con)
    say(f"\nCollecting: {label} ({len(subs)} communities)")
    total_new = total_fetched = 0
    status_final = "done"
    try:
        for i, sub in enumerate(subs, 1):
            status, posts = fetch(sub)
            added = 0
            stamp = ts(now())
            for post_id, title, link, published in posts:
                names = ["id", "country", "subreddit", "title", "link", "published", "collected"]
                vals = [post_id, key, sub, title, link, published, stamp]
                if "first_seen" in cols:
                    names.append("first_seen")
                    vals.append(stamp)
                cur = con.execute(
                    f"INSERT OR IGNORE INTO posts({','.join(names)}) "
                    f"VALUES ({','.join('?' * len(names))})", vals)
                added += cur.rowcount
            con.execute(
                "INSERT INTO fetch_log VALUES (?,?,?,?,?)",
                (run_id, sub, len(posts), added, status))
            con.commit()
            total_new += added
            total_fetched += len(posts)
            note = f"{len(posts)} fetched, {added} new" if status == "ok" else f"skipped ({status})"
            say(f"  [{i}/{len(subs)}] r/{sub}: {note}")
            if i < len(subs):
                time.sleep(2.5)
        cutoff = ts(now() - timedelta(days=keep_days))
        con.execute("DELETE FROM posts WHERE published < ?", (cutoff,))
    except KeyboardInterrupt:
        status_final = "stopped"
        say("\nStopped before finishing.")
        raise
    finally:
        con.execute(
            "UPDATE runs SET finished=?, fetched=?, new_posts=?, status=? WHERE id=?",
            (ts(now()), total_fetched, total_new, status_final, run_id))
        con.commit()
    say(f"New posts stored: {total_new}")
    return run_id


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def category(title):
    text = " " + title.lower() + " "
    matches = [n for n, terms in CATEGORIES.items()
               if any(t.lower() in text for t in terms)]
    return matches or ["Other"]


def phrases(title):
    words = re.findall(r"[^\W\d_][\w'-]{2,}", title.lower(), re.UNICODE)
    words = [w for w in words if w not in STOP and len(w) > 2]
    found = set(words)
    for size in (2, 3):
        for i in range(len(words) - size + 1):
            group = words[i:i + size]
            if not any(w in STOP for w in group):
                phrase = " ".join(group)
                if len(phrase) >= 7:
                    found.add(phrase)
    return found


def analyze(con, scope, threshold=2.5, send_alerts=True, save=False):
    key, label, _ = resolve(con, scope)
    current = ts(now())
    recent_start = current - 86400
    baseline_start = current - 8 * 86400

    rows = con.execute(
        "SELECT subreddit,title,link,published FROM posts "
        "WHERE country=? AND published>=? ORDER BY published DESC",
        (key, baseline_start)).fetchall()

    recent = collections.defaultdict(lambda: {"count": 0, "subs": set(), "links": []})
    baseline = collections.Counter()
    category_counts = collections.Counter()
    community_counts = collections.Counter()
    daily = collections.Counter()
    last24 = 0

    for row in rows:
        title = row["title"]
        found = phrases(title)
        published = row["published"]
        if published >= recent_start:
            last24 += 1
            community_counts[row["subreddit"]] += 1
            for cat in category(title):
                category_counts[cat] += 1
            for phrase in found:
                item = recent[phrase]
                item["count"] += 1
                item["subs"].add(row["subreddit"])
                if len(item["links"]) < 3:
                    item["links"].append({"title": title, "link": row["link"],
                                          "subreddit": row["subreddit"]})
        else:
            for phrase in found:
                baseline[phrase] += 1
        day = datetime.fromtimestamp(published, timezone.utc).strftime("%Y-%m-%d")
        daily[day] += 1

    ranked = []
    for phrase, item in recent.items():
        count = item["count"]
        if count < 2:
            continue
        old_rate = baseline[phrase] / 7
        growth = (count + 0.5) / (old_rate + 0.5)
        spread = len(item["subs"])
        score = count * min(growth, 10) * (1 + 0.25 * (spread - 1))
        ranked.append({
            "phrase": phrase, "mentions": count, "subreddits": spread,
            "growth": round(growth, 2), "score": round(score, 2),
            "links": item["links"],
            "status": ("STRONG GROWTH" if growth >= 3 else
                       "RISING" if growth >= 1.5 else "STEADY"),
        })
    ranked.sort(key=lambda x: x["score"], reverse=True)

    alerts = []
    if send_alerts:
        day = now().strftime("%Y-%m-%d")
        for item in ranked:
            if item["growth"] < threshold or item["mentions"] < 3:
                continue
            cur = con.execute("INSERT OR IGNORE INTO alerts VALUES (?,?)",
                              (item["phrase"], day))
            if cur.rowcount:
                alerts.append(item)
                say(f"\n*** TREND ALERT: {item['phrase']} ({item['growth']}x growth) ***")
        con.commit()

    data = {
        "scope": key,
        "label": label,
        "generated": now().strftime("%Y-%m-%d %H:%M UTC"),
        "generated_ts": current,
        "posts_analyzed": len(rows),
        "posts_24h": last24,
        "topics": ranked[:30],
        "categories": category_counts.most_common(),
        "communities": community_counts.most_common(),
        "daily": sorted(daily.items())[-8:],
        "baseline_ready": any(r["published"] < recent_start for r in rows),
        "alerts": [a["phrase"] for a in alerts],
    }
    if save:
        save_snapshot(con, data)
    return data


def save_snapshot(con, data, run_id=None):
    if run_id is None:
        run_id = con.execute(
            "INSERT INTO runs(scope,kind,started,finished,status) VALUES (?,?,?,?,?)",
            (data["scope"], "analyze", data["generated_ts"], ts(now()), "done")).lastrowid
    con.execute("DELETE FROM snapshots WHERE run_id=?", (run_id,))
    for rank, item in enumerate(data["topics"], 1):
        top = item["links"][0] if item["links"] else {}
        con.execute(
            "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, data["scope"], data["generated_ts"], rank, item["phrase"],
             item["status"], item["mentions"], item["subreddits"], item["growth"],
             item["score"], top.get("title"), top.get("link"), top.get("subreddit")))
    con.commit()
    return run_id


def report(data):
    say("\n" + "=" * 65)
    say(f" REDDIT POLITICAL TRENDS {APP_VERSION}")
    say("=" * 65)
    say("Region:", data["label"])
    say("Generated:", data["generated"])
    say("Posts in analysis window:", data["posts_analyzed"])
    say("Comparison: last 24 hours vs preceding 7 days")
    if not data["baseline_ready"]:
        say("\nBuilding historical baseline. Keep collecting daily.")
    say("\nTOPIC CATEGORIES")
    for name, count in data["categories"]:
        say(f"  {name}: {count}")
    say("\nTOP EMERGING TOPICS")
    for i, item in enumerate(data["topics"][:20], 1):
        say(f"\n{i}. {item['phrase'].upper()} - {item['status']}")
        say(f"   Mentions: {item['mentions']} | Communities: "
            f"{item['subreddits']} | Growth: {item['growth']}x")
        for src in item["links"][:2]:
            say(f"   r/{src['subreddit']}: {src['title'][:100]}")
            say(f"   {src['link']}")
    say("\nGrowth is a discussion signal, not a measure of public opinion.")
    say("Reddit communities are not representative samples of populations.")
    say("=" * 65)


def export_csv(data):
    EXPORTS.mkdir(parents=True, exist_ok=True)
    name = f"trends_{slug(data['label'])}_{now():%Y%m%d_%H%M%S}.csv"
    path = EXPORTS / name
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["region", "generated", "rank", "topic", "status",
                         "mentions", "communities", "growth", "score",
                         "source_title", "source_url", "source_subreddit"])
        for rank, item in enumerate(data["topics"], 1):
            for src in item["links"] or [{}]:
                writer.writerow([data["label"], data["generated"], rank,
                                 item["phrase"], item["status"], item["mentions"],
                                 item["subreddits"], item["growth"], item["score"],
                                 src.get("title", ""), src.get("link", ""),
                                 src.get("subreddit", "")])
    say("\nCSV exported:", path)
    return path


# ---------------------------------------------------------------------------
# Interactive subreddit entry
# ---------------------------------------------------------------------------
def interactive_add(con):
    say("\nAdd your own subreddits")
    say("Type a name (news, r/worldnews or a Reddit link) and press Enter.")
    say("Type 'done' when you have finished to save.\n")
    entered = []
    while True:
        try:
            raw = input(f"[{len(entered)} entered] Subreddit (or 'done' to save): ").strip()
        except (EOFError, KeyboardInterrupt):
            say()
            break
        if raw.lower() in ("done", "d"):
            break
        if not raw:
            continue
        sub = normalize_sub(raw)
        if not sub:
            say("  That is not a valid subreddit name. Use letters, numbers and _ (2-21 characters).")
        elif sub.lower() in [e.lower() for e in entered]:
            say(f"  r/{sub} is already in your list.")
        else:
            entered.append(sub)
            say(f"  Added r/{sub}")
    if not entered:
        say("Nothing to save.")
        return None
    say(f"\nYou entered {len(entered)}: " + ", ".join("r/" + e for e in entered))
    while True:
        try:
            name = input("Name for this list: ").strip()
        except (EOFError, KeyboardInterrupt):
            say("\nNot saved.")
            return None
        try:
            save_list(con, name, entered)
            break
        except ValueError as exc:
            say(" ", exc)
    say(f"Saved list '{name}'. Fetch it with:  python reddit_trends.py run --list \"{name}\"")
    try:
        if input("Fetch it now? [y/N]: ").strip().lower() == "y":
            run_once(con, f"list:{name}", 2.5, False)
    except (EOFError, KeyboardInterrupt):
        pass
    return name


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------
def run_once(con, scope, alert_growth, export, keep_days=30):
    run_id = collect(con, scope, keep_days)
    data = analyze(con, scope, alert_growth)
    save_snapshot(con, data, run_id)
    report(data)
    if export:
        export_csv(data)


def scope_from_args(args, con):
    if getattr(args, "subs", None):
        subs = [normalize_sub(s) for s in args.subs.split(",")]
        subs = [s for s in subs if s]
        if not subs:
            raise SystemExit("No valid subreddits in --subs.")
        name = args.name or f"Quick {now():%Y-%m-%d %H%M}"
        save_list(con, name, subs)
        return f"list:{name}"
    if getattr(args, "list", None):
        return f"list:{args.list}"
    return args.country


# ---------------------------------------------------------------------------
# Background jobs (GUI buttons run real Termux commands)
# ---------------------------------------------------------------------------
class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.log = []
        self.cmd = ""
        self.kind = ""
        self.started = None
        self.ended = None
        self.code = None

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, args, kind):
        with self.lock:
            if self.running():
                raise RuntimeError("A job is already running. Stop it or wait for it to finish.")
            cmd = [sys.executable, "-u", str(SCRIPT)] + args
            self.log = []
            self.cmd = "python reddit_trends.py " + " ".join(shlex.quote(a) for a in args)
            self.kind = kind
            self.started = time.time()
            self.ended = None
            self.code = None
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=str(BASE))
            threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def _read(self, proc):
        for line in proc.stdout:
            self.log.append(line.rstrip("\n"))
            if len(self.log) > 2000:
                del self.log[:500]
        proc.wait()
        self.code = proc.returncode
        self.ended = time.time()

    def stop(self):
        if self.running():
            self.proc.terminate()
            return True
        return False

    def info(self, since=0):
        return {
            "running": self.running(), "cmd": self.cmd, "kind": self.kind,
            "started": self.started, "ended": self.ended, "code": self.code,
            "log": self.log[since:], "next": len(self.log),
        }


JOB = Job()


# ---------------------------------------------------------------------------
# Web server
# ---------------------------------------------------------------------------
def scopes_overview(con):
    counts = {r["country"]: (r["n"], r["last"]) for r in con.execute(
        "SELECT country, COUNT(*) n, MAX(collected) last FROM posts GROUP BY country")}
    out = [{"id": "global", "label": "Worldwide", "kind": "global",
            "subs": len(GLOBAL_SUBS), "posts": counts.get("global", (0, 0))[0]}]
    for r in con.execute("SELECT name, subs FROM lists ORDER BY name COLLATE NOCASE"):
        sid = "list:" + r["name"]
        out.append({"id": sid, "label": r["name"], "kind": "list",
                    "subs": len(json.loads(r["subs"])), "posts": counts.get(sid, (0, 0))[0]})
    for k, c in sorted(COUNTRIES.items(), key=lambda kv: kv[1]["name"]):
        out.append({"id": k, "label": c["name"], "kind": "country",
                    "subs": len(c["subs"]), "posts": counts.get(k, (0, 0))[0]})
    return out


class Handler(BaseHTTPRequestHandler):
    token = ""
    port = 8765

    def log_message(self, fmt, *args):
        pass

    # -- plumbing ---------------------------------------------------------
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj))

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    # -- GET --------------------------------------------------------------
    def do_GET(self):
        if not self._host_ok():
            return self._json({"error": "Forbidden host"}, 403)
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        con = connect()
        try:
            if url.path == "/":
                page = PAGE.replace("__TOKEN__", self.token).replace("__VERSION__", APP_VERSION)
                return self._send(200, page, "text/html; charset=utf-8")
            if url.path == "/api/state":
                return self._json({
                    "scopes": scopes_overview(con),
                    "groups": GROUPS,
                    "countries": [{"id": k, "name": c["name"], "subs": c["subs"],
                                   "curated": c["curated"]} for k, c in COUNTRIES.items()],
                    "lists": [{"name": r["name"], "subs": json.loads(r["subs"])}
                              for r in con.execute("SELECT * FROM lists ORDER BY name COLLATE NOCASE")],
                })
            if url.path == "/api/report":
                data = analyze(con, q.get("scope", "global"), send_alerts=False)
                return self._json(data)
            if url.path == "/api/job":
                return self._json(JOB.info(int(q.get("since", 0) or 0)))
            if url.path == "/api/runs":
                rows = con.execute(
                    "SELECT * FROM runs ORDER BY id DESC LIMIT 40").fetchall()
                return self._json([dict(r, label=scope_label(r["scope"])) for r in rows])
            if url.path == "/api/run":
                rid = int(q.get("id", 0))
                run = con.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
                if not run:
                    return self._json({"error": "Run not found"}, 404)
                return self._json({
                    "run": dict(run, label=scope_label(run["scope"])),
                    "topics": [dict(r) for r in con.execute(
                        "SELECT * FROM snapshots WHERE run_id=? ORDER BY rank", (rid,))],
                    "sources": [dict(r) for r in con.execute(
                        "SELECT * FROM fetch_log WHERE run_id=? ORDER BY rowid", (rid,))],
                })
            if url.path == "/api/posts":
                key, _, _ = resolve(con, q.get("scope", "global"))
                term = "%" + q.get("q", "").strip() + "%"
                rows = con.execute(
                    "SELECT subreddit,title,link,published FROM posts "
                    "WHERE country=? AND title LIKE ? ORDER BY published DESC LIMIT 60",
                    (key, term)).fetchall()
                return self._json([dict(r) for r in rows])
            if url.path == "/api/export":
                data = analyze(con, q.get("scope", "global"), send_alerts=False)
                path = export_csv(data)
                return self._send(200, path.read_bytes(), "text/csv; charset=utf-8",
                                  {"Content-Disposition": f'attachment; filename="{path.name}"'})
            return self._json({"error": "Not found"}, 404)
        except ValueError as exc:
            return self._json({"error": str(exc)}, 400)
        except Exception as exc:
            return self._json({"error": f"Server error: {exc}"}, 500)
        finally:
            con.close()

    # -- POST -------------------------------------------------------------
    def do_POST(self):
        if not self._host_ok():
            return self._json({"error": "Forbidden host"}, 403)
        if self.headers.get("X-Token") != self.token:
            return self._json({"error": "Session expired. Reload the page."}, 403)
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 100_000)
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json({"error": "Invalid request"}, 400)
        path = urlparse(self.path).path
        con = connect()
        try:
            if path == "/api/run":
                action = body.get("action")
                commands = {"fetch": "collect", "analyze": "analyze", "run": "run",
                            "export": "export", "watch": "watch"}
                if action not in commands:
                    return self._json({"error": "Unknown action"}, 400)
                key, _, _ = resolve(con, str(body.get("scope", "global")))
                args = [commands[action]] + scope_args(key)
                if action == "watch":
                    hours = max(1.0, min(float(body.get("interval", 6)), 168.0))
                    args += ["--interval", str(hours)]
                JOB.start(args, action)
                return self._json({"ok": True})
            if path == "/api/stop":
                return self._json({"ok": JOB.stop()})
            if path == "/api/list/save":
                subs = save_list(con, str(body.get("name", "")), body.get("subs") or [])
                return self._json({"ok": True, "subs": subs})
            if path == "/api/list/delete":
                con.execute("DELETE FROM lists WHERE name=?", (str(body.get("name", "")),))
                con.commit()
                return self._json({"ok": True})
            if path == "/api/verify":
                sub = normalize_sub(str(body.get("sub", "")))
                if not sub:
                    return self._json({"error": "Not a valid subreddit name."}, 400)
                status, posts = fetch(sub, limit=5)
                return self._json({"sub": sub, "ok": status == "ok",
                                   "status": status, "found": len(posts)})
            return self._json({"error": "Not found"}, 404)
        except (ValueError, RuntimeError) as exc:
            return self._json({"error": str(exc)}, 400)
        except Exception as exc:
            return self._json({"error": f"Server error: {exc}"}, 500)
        finally:
            con.close()


def serve(port, open_browser):
    con = connect()
    con.execute("UPDATE runs SET status='interrupted', finished=? WHERE status='running'",
                (ts(now()),))
    con.commit()
    con.close()
    Handler.token = secrets.token_urlsafe(24)
    Handler.port = port
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        raise SystemExit(f"Cannot use port {port}: {exc}. Try --port {port + 1}.")
    url = f"http://127.0.0.1:{port}"
    say(f"\nReddit Political Trends {APP_VERSION}")
    say(f"Dashboard: {url}")
    say("Keep Termux open (run 'termux-wake-lock' so Android does not pause it).")
    say("Press CTRL+C to stop.")
    if open_browser and shutil.which("termux-open-url"):
        subprocess.Popen(["termux-open-url", url])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        say("\nStopped.")
    finally:
        JOB.stop()
        server.server_close()


# ---------------------------------------------------------------------------
# Web interface
# ---------------------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reddit Political Trends</title>
<style>
:root{--bg:#eef1f4;--panel:#fff;--panel2:#f4f6f8;--line:#d9dfe6;--text:#1c2430;--muted:#5d6978;
--accent:#1b7f6e;--on-accent:#fff;--warn:#9a6508;--hot:#b8402f;--ok:#1b7f6e;--radius:12px}
@media (prefers-color-scheme:dark){:root{--bg:#141a21;--panel:#1c242e;--panel2:#222c38;--line:#303b49;
--text:#e8e5dd;--muted:#9aa5b3;--accent:#6cc4b0;--on-accent:#0f1a17;--warn:#e6b566;--hot:#ef8a7a;--ok:#6cc4b0}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
h1,h2,h3{font-family:Georgia,"Iowan Old Style",serif;font-weight:600;line-height:1.25;margin:0}
h2{font-size:1.25rem;margin-bottom:.6rem}h3{font-size:1.05rem}
a{color:var(--accent)}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:.7rem 1rem}
.bar{max-width:980px;margin:auto;display:flex;flex-wrap:wrap;gap:.6rem 1rem;align-items:center;justify-content:space-between}
.brand{font-family:Georgia,serif;font-size:1.2rem;font-weight:600}
.tools{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}
select,input[type=text],input[type=number]{font:inherit;color:var(--text);background:var(--panel);border:1px solid var(--line);
border-radius:10px;padding:.55rem .7rem;min-height:44px;max-width:100%}
select{min-width:200px}
nav{max-width:980px;margin:.5rem auto 0;display:flex;gap:.3rem;overflow-x:auto}
nav button{background:none;border:0;color:var(--muted);font:inherit;padding:.6rem .9rem;min-height:44px;border-bottom:3px solid transparent;cursor:pointer;white-space:nowrap}
nav button[aria-selected=true]{color:var(--text);border-bottom-color:var(--accent);font-weight:600}
main{max-width:980px;margin:auto;padding:1rem}
section[hidden]{display:none}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:1rem 1.1rem;margin-bottom:1rem}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.8rem;margin-bottom:1rem}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:.8rem 1rem}
.stat b{display:block;font-size:1.6rem;font-family:Georgia,serif}
.muted{color:var(--muted)}.small{font-size:.9rem}
button.btn{font:inherit;min-height:44px;padding:.55rem 1rem;border-radius:10px;border:1px solid var(--line);background:var(--panel2);color:var(--text);cursor:pointer}
button.btn:hover{border-color:var(--accent)}
button.primary{background:var(--accent);color:var(--on-accent);border-color:var(--accent);font-weight:600}
button.danger{color:var(--hot)}
button:disabled{opacity:.5;cursor:not-allowed}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.row{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center}
.pill{display:inline-block;padding:.15rem .6rem;border-radius:99px;font-size:.85rem;border:1px solid var(--line);background:var(--panel2)}
.pill.run{border-color:var(--accent);color:var(--accent)}
.s-strong{color:var(--hot);border-color:var(--hot)}.s-rising{color:var(--warn);border-color:var(--warn)}.s-steady{color:var(--muted)}
.bar-row{display:grid;grid-template-columns:minmax(110px,190px) 1fr 40px;gap:.6rem;align-items:center;margin:.45rem 0}
.track{height:12px;background:var(--panel2);border-radius:8px;overflow:hidden}
.track i{display:block;height:100%;background:var(--accent);border-radius:8px}
.topic{border-top:1px solid var(--line);padding:.6rem 0}
.topic summary{cursor:pointer;display:flex;flex-wrap:wrap;gap:.4rem .8rem;align-items:center;min-height:44px}
.topic summary b{font-size:1.05rem}
.topic ul{margin:.3rem 0 .3rem 1.1rem;padding:0}.topic li{margin:.35rem 0}
.chips{display:flex;flex-wrap:wrap;gap:.45rem}
.chip{font:inherit;padding:.35rem .75rem;border-radius:99px;border:1px solid var(--line);background:var(--panel2);color:var(--text);cursor:pointer;min-height:38px}
.chip[aria-pressed=true]{background:var(--accent);color:var(--on-accent);border-color:var(--accent)}
.chip.rm::after{content:" \00d7";opacity:.7}
pre.log{background:#0e1319;color:#d7dde4;border-radius:10px;padding:.9rem;max-height:340px;overflow:auto;font:13px/1.5 ui-monospace,Menlo,Consolas,monospace;white-space:pre-wrap;margin:.6rem 0 0}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.88rem;background:var(--panel2);padding:.1rem .4rem;border-radius:6px;word-break:break-all}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:.5rem .4rem;border-top:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:.9rem;border-top:0}
.scroll{overflow-x:auto}
.empty{padding:1.4rem 0;text-align:center;color:var(--muted)}
.list{max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:10px}
.item{display:flex;justify-content:space-between;gap:.6rem;align-items:center;padding:.5rem .8rem;border-top:1px solid var(--line)}
.item:first-child{border-top:0}
.msg{margin:.5rem 0;font-size:.95rem}.msg.err{color:var(--hot)}.msg.ok{color:var(--ok)}
#toast{position:fixed;left:50%;bottom:1.2rem;transform:translateX(-50%);background:var(--text);color:var(--bg);padding:.7rem 1.1rem;border-radius:10px;opacity:0;pointer-events:none;transition:opacity .2s;max-width:90vw;z-index:9}
#toast.show{opacity:1}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body>
<header><div class="bar">
  <div class="brand">Reddit Political Trends</div>
  <div class="tools">
    <label class="small muted" for="scope">Region</label>
    <select id="scope" aria-label="Region or list"></select>
    <span id="jobpill" class="pill">Idle</span>
  </div>
</div>
<nav role="tablist" id="tabs">
  <button role="tab" data-tab="overview" aria-selected="true">Overview</button>
  <button role="tab" data-tab="fetch" aria-selected="false">Fetch</button>
  <button role="tab" data-tab="sources" aria-selected="false">Sources</button>
  <button role="tab" data-tab="results" aria-selected="false">Results</button>
</nav></header>
<main>

<section id="t-overview">
  <div id="ov"></div>
</section>

<section id="t-fetch" hidden>
  <div class="panel">
    <h2>Fetch and track</h2>
    <p class="muted">These buttons run the same commands you would type in Termux, for the region chosen at the top.</p>
    <div class="row">
      <button class="btn primary" data-act="run">Fetch and analyze</button>
      <button class="btn" data-act="fetch">Fetch only</button>
      <button class="btn" data-act="analyze">Analyze saved posts</button>
      <button class="btn" data-act="export">Export CSV</button>
    </div>
    <div class="row" style="margin-top:.8rem">
      <label for="hours">Track every</label>
      <input id="hours" type="number" min="1" max="168" value="6" style="width:90px"> <span>hours</span>
      <button class="btn" data-act="watch">Start tracking</button>
      <button class="btn danger" id="stop" disabled>Stop</button>
    </div>
    <p class="small muted" style="margin:.8rem 0 0">Command: <code id="cmd">none yet</code></p>
    <pre class="log" id="log" aria-live="polite">Output appears here when a job runs.</pre>
  </div>
</section>

<section id="t-sources" hidden>
  <div class="panel">
    <h2>Your selection</h2>
    <p class="muted small">Type subreddits one at a time, or tap suggestions below. Press Enter after each one.</p>
    <div class="row">
      <input id="subin" type="text" placeholder="worldnews, r/europe or a Reddit link" autocapitalize="off" autocomplete="off" style="flex:1;min-width:200px">
      <button class="btn" id="subadd">Add</button>
    </div>
    <p class="msg" id="submsg"></p>
    <p><b id="count">0 entered</b> <span class="muted small">Tap a chip to remove it.</span></p>
    <div class="chips" id="basket"></div>
    <div class="row" style="margin-top:.9rem">
      <input id="listname" type="text" placeholder="List name" maxlength="40" style="flex:1;min-width:160px">
      <button class="btn primary" id="savelist">Done, save list</button>
      <button class="btn" id="savefetch">Save and fetch</button>
      <button class="btn" id="clearbasket">Clear</button>
    </div>
  </div>
  <div class="panel"><h2>Saved lists</h2><div id="lists"></div></div>
  <div class="panel"><h2>Suggested groups</h2><div id="groups"></div></div>
  <div class="panel">
    <h2>Countries</h2>
    <p class="muted small">Every country has a starting set of communities. Countries marked "guess" use the country name as the subreddit; check it before relying on it.</p>
    <input id="csearch" type="text" placeholder="Search countries" style="width:100%;margin-bottom:.6rem">
    <div class="list" id="countries"></div>
  </div>
  <div class="panel">
    <h2>Check a subreddit</h2>
    <div class="row"><input id="vsub" type="text" placeholder="subreddit name" style="flex:1;min-width:160px" autocapitalize="off">
    <button class="btn" id="vbtn">Check</button></div>
    <p class="msg" id="vmsg"></p>
  </div>
</section>

<section id="t-results" hidden>
  <div class="panel"><h2>Saved runs</h2><div id="runs" class="scroll"></div></div>
  <div class="panel" id="rundetail" hidden></div>
  <div class="panel">
    <h2>Search saved posts</h2>
    <div class="row"><input id="pq" type="text" placeholder="Search titles in this region" style="flex:1;min-width:180px">
    <button class="btn" id="pgo">Search</button>
    <button class="btn" id="csv">Download CSV</button></div>
    <div id="posts"></div>
  </div>
</section>
</main>
<div id="toast" role="status"></div>
<script>
const TOKEN="__TOKEN__";
const $=s=>document.querySelector(s);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=t=>t?new Date(t*1000).toLocaleString([], {dateStyle:"medium",timeStyle:"short"}):"";
const api=async(p,b)=>{const o=b?{method:"POST",headers:{"Content-Type":"application/json","X-Token":TOKEN},body:JSON.stringify(b)}:{};
  const r=await fetch(p,o);let j={};try{j=await r.json()}catch(e){}if(!r.ok)throw new Error(j.error||r.statusText);return j};
let toastT;const toast=m=>{const t=$("#toast");t.textContent=m;t.classList.add("show");clearTimeout(toastT);toastT=setTimeout(()=>t.classList.remove("show"),3200)};
let S={scopes:[],groups:{},countries:[],lists:[]},scope=localStorage.getItem("rpt-scope")||"global",basket=[],cursor=0,wasRunning=false;

function tab(name){document.querySelectorAll("#tabs button").forEach(b=>b.setAttribute("aria-selected",b.dataset.tab===name));
  ["overview","fetch","sources","results"].forEach(n=>$("#t-"+n).hidden=n!==name);
  if(name==="overview")loadOverview();if(name==="results")loadRuns();window.scrollTo(0,0)}
$("#tabs").onclick=e=>{const b=e.target.closest("button");if(b)tab(b.dataset.tab)};

function buildScope(){const g=(k,l)=>{const it=S.scopes.filter(s=>s.kind===k);return it.length?`<optgroup label="${l}">`+it.map(s=>`<option value="${esc(s.id)}">${esc(s.label)}${s.posts?` (${s.posts} posts)`:""}</option>`).join("")+"</optgroup>":""};
  $("#scope").innerHTML=g("global","Worldwide")+g("list","My lists")+g("country","Countries");
  if(!S.scopes.some(s=>s.id===scope))scope="global";$("#scope").value=scope}
$("#scope").onchange=e=>{scope=e.target.value;localStorage.setItem("rpt-scope",scope);loadOverview();loadRuns();$("#posts").innerHTML=""};

async function refreshState(){S=await api("/api/state");buildScope();renderLists();renderCountries()}

async function loadOverview(){
  const box=$("#ov");box.innerHTML='<p class="muted">Loading</p>';
  try{const d=await api("/api/report?scope="+encodeURIComponent(scope));
    if(!d.posts_analyzed){box.innerHTML=`<div class="panel empty"><h2>No posts yet for ${esc(d.label)}</h2><p>Open the Fetch tab and press Fetch and analyze.</p><button class="btn primary" onclick="tab('fetch')">Go to Fetch</button></div>`;return}
    const max=Math.max(1,...d.daily.map(x=>x[1])),cmax=Math.max(1,...d.categories.map(x=>x[1])),smax=Math.max(1,...d.communities.map(x=>x[1]));
    const bars=(rows,m,l=x=>x)=>rows.map(([k,v])=>`<div class="bar-row"><span>${esc(l(k))}</span><div class="track"><i style="width:${Math.max(3,v/m*100)}%"></i></div><b>${v}</b></div>`).join("");
    const topics=d.topics.map(t=>{const c=t.status==="STRONG GROWTH"?"s-strong":t.status==="RISING"?"s-rising":"s-steady";
      return `<details class="topic"><summary><b>${esc(t.phrase)}</b><span class="pill ${c}">${t.status==="STRONG GROWTH"?"Strong growth":t.status==="RISING"?"Rising":"Steady"}</span><span class="muted small">${t.mentions} mentions, ${t.subreddits} communities, ${t.growth}x</span></summary><ul>${t.links.map(l=>`<li><a href="${esc(l.link)}" target="_blank" rel="noopener noreferrer">${esc(l.title)}</a> <span class="muted small">r/${esc(l.subreddit)}</span></li>`).join("")}</ul></details>`}).join("");
    box.innerHTML=`<div class="stats"><div class="stat"><span class="muted small">Region</span><b>${esc(d.label)}</b></div><div class="stat"><span class="muted small">Posts, last 24 hours</span><b>${d.posts_24h}</b></div><div class="stat"><span class="muted small">Posts analyzed</span><b>${d.posts_analyzed}</b></div><div class="stat"><span class="muted small">Updated</span><b style="font-size:1rem">${esc(d.generated)}</b></div></div>
    ${d.baseline_ready?"":'<div class="panel"><b>Building baseline.</b> <span class="muted">Keep collecting for a few days so growth comparisons become reliable.</span></div>'}
    <div class="panel"><h2>Emerging topics</h2>${topics||'<p class="muted">Not enough repeated phrases yet.</p>'}</div>
    <div class="panel"><h2>Posts per day</h2>${bars(d.daily,max)}</div>
    <div class="panel"><h2>Topic categories, last 24 hours</h2>${bars(d.categories,cmax)}</div>
    <div class="panel"><h2>Most active communities</h2>${bars(d.communities.slice(0,10),smax,x=>"r/"+x)}</div>
    <p class="muted small">Growth compares the last 24 hours with the previous 7 days. It shows what people discuss on Reddit, not public opinion.</p>`;
  }catch(e){box.innerHTML=`<div class="panel msg err">${esc(e.message)}</div>`}}

/* jobs */
document.querySelectorAll("[data-act]").forEach(b=>b.onclick=async()=>{
  try{await api("/api/run",{action:b.dataset.act,scope,interval:+$("#hours").value||6});cursor=0;$("#log").textContent="";poll()}catch(e){toast(e.message)}});
$("#stop").onclick=async()=>{await api("/api/stop",{});toast("Stopping")};
async function poll(){
  try{const j=await api("/api/job?since="+cursor);cursor=j.next;
    if(j.log.length){const l=$("#log");const stick=l.scrollTop+l.clientHeight>=l.scrollHeight-30;l.textContent+=(l.textContent?"\n":"")+j.log.join("\n");if(stick)l.scrollTop=l.scrollHeight}
    if(j.cmd)$("#cmd").textContent=j.cmd;
    const p=$("#jobpill");p.textContent=j.running?"Running: "+({run:"fetch and analyze",fetch:"fetching",analyze:"analyzing",export:"exporting",watch:"tracking"}[j.kind]||j.kind):"Idle";p.className="pill"+(j.running?" run":"");
    $("#stop").disabled=!j.running;document.querySelectorAll("[data-act]").forEach(b=>b.disabled=j.running);
    if(wasRunning&&!j.running){toast(j.code===0||j.code===null?"Job finished":"Job stopped");refreshState();if(!$("#t-overview").hidden)loadOverview();if(!$("#t-results").hidden)loadRuns()}
    wasRunning=j.running}catch(e){}
  setTimeout(poll,wasRunning?1200:3000)}

/* sources */
const normSub=r=>{r=(r||"").trim();let m=r.match(/(?:^|\/)r\/([A-Za-z0-9_]{2,21})/);if(m)return m[1];r=r.replace(/^\/+|\/+$/g,"");return /^[A-Za-z0-9_]{2,21}$/.test(r)?r:""};
function renderBasket(){$("#count").textContent=basket.length+(basket.length===1?" entered":" entered");
  $("#basket").innerHTML=basket.length?basket.map((s,i)=>`<button class="chip rm" data-i="${i}">r/${esc(s)}</button>`).join(""):'<span class="muted small">Nothing selected yet.</span>'}
$("#basket").onclick=e=>{const b=e.target.closest("[data-i]");if(b){basket.splice(+b.dataset.i,1);renderBasket();renderGroups()}};
function addSub(raw,quiet){const s=normSub(raw),m=$("#submsg");
  if(!s){if(!quiet){m.textContent="That is not a valid subreddit name. Use letters, numbers and _ (2-21 characters).";m.className="msg err"}return false}
  if(basket.some(b=>b.toLowerCase()===s.toLowerCase())){if(!quiet){m.textContent="r/"+s+" is already in your selection.";m.className="msg err"}return false}
  basket.push(s);if(!quiet){m.textContent="Added r/"+s+". Add another, or press Done, save list.";m.className="msg ok"}renderBasket();renderGroups();return true}
$("#subadd").onclick=()=>{if(addSub($("#subin").value))$("#subin").value="";$("#subin").focus()};
$("#subin").onkeydown=e=>{if(e.key==="Enter")$("#subadd").click()};
$("#clearbasket").onclick=()=>{basket=[];renderBasket();renderGroups()};
async function saveBasket(fetchAfter){const name=$("#listname").value.trim(),m=$("#submsg");
  if(!basket.length){m.textContent="Add at least one subreddit first.";m.className="msg err";return}
  if(!name){m.textContent="Give the list a name.";m.className="msg err";$("#listname").focus();return}
  try{await api("/api/list/save",{name,subs:basket});basket=[];$("#listname").value="";renderBasket();renderGroups();await refreshState();
    scope="list:"+name;localStorage.setItem("rpt-scope",scope);$("#scope").value=scope;m.textContent=`Saved list "${name}".`;m.className="msg ok";
    if(fetchAfter){await api("/api/run",{action:"run",scope});cursor=0;$("#log").textContent="";tab("fetch");poll()}}catch(e){m.textContent=e.message;m.className="msg err"}}
$("#savelist").onclick=()=>saveBasket(false);$("#savefetch").onclick=()=>saveBasket(true);
function renderGroups(){$("#groups").innerHTML=Object.entries(S.groups).map(([g,subs])=>`<h3 style="margin:.8rem 0 .4rem">${esc(g)}</h3><div class="chips">${subs.map(s=>`<button class="chip" data-g="${esc(s)}" aria-pressed="${basket.some(b=>b.toLowerCase()===s.toLowerCase())}">r/${esc(s)}</button>`).join("")}</div>`).join("")}
$("#groups").onclick=e=>{const b=e.target.closest("[data-g]");if(!b)return;const s=b.dataset.g,i=basket.findIndex(x=>x.toLowerCase()===s.toLowerCase());if(i>=0)basket.splice(i,1);else basket.push(s);renderBasket();renderGroups()};
function renderLists(){$("#lists").innerHTML=S.lists.length?S.lists.map(l=>`<div class="item"><div><b>${esc(l.name)}</b> <span class="muted small">${l.subs.length} communities</span><div class="small muted">${l.subs.slice(0,6).map(s=>"r/"+esc(s)).join(", ")}${l.subs.length>6?", ...":""}</div></div><div class="row"><button class="btn" data-use="${esc(l.name)}">Use</button><button class="btn" data-edit="${esc(l.name)}">Edit</button><button class="btn danger" data-del="${esc(l.name)}">Delete</button></div></div>`).join(""):'<p class="empty">No saved lists yet. Add subreddits above and press Done, save list.</p>'}
$("#lists").onclick=async e=>{const b=e.target.closest("button");if(!b)return;
  if(b.dataset.use){scope="list:"+b.dataset.use;localStorage.setItem("rpt-scope",scope);$("#scope").value=scope;toast("Using "+b.dataset.use);tab("fetch")}
  if(b.dataset.edit){const l=S.lists.find(x=>x.name===b.dataset.edit);basket=[...l.subs];$("#listname").value=l.name;renderBasket();renderGroups();window.scrollTo(0,0)}
  if(b.dataset.del&&confirm(`Delete list "${b.dataset.del}"? Saved posts stay in the database.`)){await api("/api/list/delete",{name:b.dataset.del});await refreshState()}};
function renderCountries(){const q=$("#csearch").value.toLowerCase();
  $("#countries").innerHTML=S.countries.filter(c=>c.name.toLowerCase().includes(q)).map(c=>`<div class="item"><div><b>${esc(c.name)}</b>${c.curated?"":' <span class="pill s-rising">guess</span>'}<div class="small muted">${c.subs.map(s=>"r/"+esc(s)).join(", ")}</div></div><div class="row"><button class="btn" data-cuse="${esc(c.id)}">Use</button><button class="btn" data-cadd="${esc(c.id)}">Add to selection</button></div></div>`).join("")||'<p class="empty">No country matches.</p>'}
$("#csearch").oninput=renderCountries;
$("#countries").onclick=e=>{const b=e.target.closest("button");if(!b)return;
  if(b.dataset.cuse){scope=b.dataset.cuse;localStorage.setItem("rpt-scope",scope);$("#scope").value=scope;toast("Region set");tab("fetch")}
  if(b.dataset.cadd){const c=S.countries.find(x=>x.id===b.dataset.cadd);c.subs.forEach(s=>addSub(s,true));toast(c.name+" communities added");window.scrollTo(0,0)}};
$("#vbtn").onclick=async()=>{const m=$("#vmsg");m.textContent="Checking";m.className="msg";
  try{const r=await api("/api/verify",{sub:$("#vsub").value});m.textContent=r.ok?`r/${r.sub} works (${r.found} recent posts).`:`r/${r.sub}: ${r.status}`;m.className="msg "+(r.ok?"ok":"err")}catch(e){m.textContent=e.message;m.className="msg err"}};

/* results */
async function loadRuns(){try{const r=await api("/api/runs");
  $("#runs").innerHTML=r.length?`<table><thead><tr><th>When</th><th>Region</th><th>Type</th><th>New posts</th><th>Status</th></tr></thead><tbody>`+r.map(x=>`<tr data-run="${x.id}" style="cursor:pointer"><td>${fmt(x.started)}</td><td><a href="#" data-run="${x.id}">${esc(x.label)}</a></td><td>${esc(x.kind)}</td><td>${x.new_posts}</td><td>${esc(x.status)}</td></tr>`).join("")+"</tbody></table>":'<p class="empty">No runs yet. Fetch some data first.</p>'}catch(e){}}
$("#runs").onclick=async e=>{const t=e.target.closest("[data-run]");if(!t)return;e.preventDefault();
  const d=await api("/api/run?id="+t.dataset.run),b=$("#rundetail");b.hidden=false;
  b.innerHTML=`<h2>${esc(d.run.label)}, ${fmt(d.run.started)}</h2><p class="muted small">${d.run.communities} communities, ${d.run.fetched} posts fetched, ${d.run.new_posts} new. Status: ${esc(d.run.status)}.</p>
  ${d.topics.length?`<h3>Saved topics</h3><div class="scroll"><table><thead><tr><th>#</th><th>Topic</th><th>Status</th><th>Mentions</th><th>Growth</th></tr></thead><tbody>${d.topics.map(x=>`<tr><td>${x.rank}</td><td>${x.top_link?`<a href="${esc(x.top_link)}" target="_blank" rel="noopener noreferrer">${esc(x.phrase)}</a>`:esc(x.phrase)}</td><td>${esc(x.status.toLowerCase())}</td><td>${x.mentions}</td><td>${x.growth}x</td></tr>`).join("")}</tbody></table></div>`:""}
  ${d.sources.length?`<h3 style="margin-top:1rem">Communities</h3><div class="scroll"><table><thead><tr><th>Subreddit</th><th>Fetched</th><th>New</th><th>Result</th></tr></thead><tbody>${d.sources.map(x=>`<tr><td>r/${esc(x.subreddit)}</td><td>${x.fetched}</td><td>${x.added}</td><td>${x.status==="ok"?"ok":'<span class="s-strong">'+esc(x.status)+"</span>"}</td></tr>`).join("")}</tbody></table></div>`:""}`;
  b.scrollIntoView({behavior:"smooth"})};
async function searchPosts(){try{const r=await api(`/api/posts?scope=${encodeURIComponent(scope)}&q=${encodeURIComponent($("#pq").value)}`);
  $("#posts").innerHTML=r.length?r.map(p=>`<div class="item"><div><a href="${esc(p.link)}" target="_blank" rel="noopener noreferrer">${esc(p.title)}</a><div class="small muted">r/${esc(p.subreddit)}, ${fmt(p.published)}</div></div></div>`).join(""):'<p class="empty">No posts found.</p>'}catch(e){toast(e.message)}}
$("#pgo").onclick=searchPosts;$("#pq").onkeydown=e=>{if(e.key==="Enter")searchPosts()};
$("#csv").onclick=()=>{location.href="/api/export?scope="+encodeURIComponent(scope)};

(async()=>{renderBasket();await refreshState();renderGroups();loadOverview();poll()})();
</script></body></html>
"""


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def build_parser():
    scope = argparse.ArgumentParser(add_help=False)
    scope.add_argument("--country", default="global",
                       help="'global' or a country key such as morocco, united_states")
    scope.add_argument("--list", help="name of a saved subreddit list")
    scope.add_argument("--subs", help="comma-separated subreddits (saved as a list)")
    scope.add_argument("--name", help="list name to use with --subs")
    scope.add_argument("--alert-growth", type=float, default=2.5)
    scope.add_argument("--keep-days", type=int, default=30)
    scope.add_argument("--export", action="store_true")
    scope.add_argument("--interval", type=float, default=6, help="hours between scans")

    parser = argparse.ArgumentParser(
        prog="reddit_trends.py",
        description="Aggregate Reddit political trend research.")
    sub = parser.add_subparsers(dest="cmd", metavar="command")
    sub.add_parser("serve", help="start the local dashboard").add_argument(
        "--port", type=int, default=8765)
    sub.choices["serve"].add_argument("--open", action="store_true",
                                      help="open the dashboard in the phone browser")
    sub.add_parser("run", parents=[scope], help="fetch, analyze and save results")
    sub.add_parser("collect", parents=[scope], help="fetch posts only")
    sub.add_parser("analyze", parents=[scope], help="analyze saved posts")
    sub.add_parser("watch", parents=[scope], help="repeat run every --interval hours")
    sub.add_parser("export", parents=[scope], help="write a CSV of current topics")
    sub.add_parser("add", help="type subreddits one by one and save a list")
    sub.add_parser("lists", help="show saved lists")
    p = sub.add_parser("countries", help="show every country and its communities")
    p.add_argument("search", nargs="?", default="")
    return parser


def translate_legacy(argv):
    """Old style flags (--dashboard, --watch) still work."""
    if not argv or not argv[0].startswith("-") or argv[0] in ("-h", "--help"):
        return argv
    rest = list(argv)
    if "--dashboard" in rest:
        rest.remove("--dashboard")
        keep = []
        skip = False
        for a in rest:
            if skip:
                keep.append(a)
                skip = False
            elif a == "--port":
                keep.append(a)
                skip = True
        return ["serve"] + keep
    if "--watch" in rest:
        rest.remove("--watch")
        return ["watch"] + rest
    return ["run"] + rest


def main():
    parser = build_parser()
    args = parser.parse_args(translate_legacy(sys.argv[1:]))
    if not args.cmd:
        parser.print_help()
        return
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    if args.cmd == "serve":
        return serve(args.port, args.open)
    if args.cmd == "countries":
        term = args.search.lower()
        for k, c in sorted(COUNTRIES.items(), key=lambda kv: kv[1]["name"]):
            if term in c["name"].lower() or term in k:
                tag = "" if c["curated"] else "  (guess)"
                say(f"{k:34} {', '.join('r/' + s for s in c['subs'])}{tag}")
        return

    con = connect()
    try:
        if args.cmd == "add":
            interactive_add(con)
            return
        if args.cmd == "lists":
            rows = con.execute("SELECT name,subs FROM lists ORDER BY name").fetchall()
            if not rows:
                say("No saved lists. Create one with: python reddit_trends.py add")
            for r in rows:
                subs = json.loads(r["subs"])
                say(f"{r['name']} ({len(subs)}): " + ", ".join("r/" + s for s in subs))
            return

        if args.alert_growth < 1:
            parser.error("--alert-growth must be at least 1.")
        if args.interval < 1:
            parser.error("--interval must be at least 1 hour.")
        scope = scope_from_args(args, con)
        resolve(con, scope)

        if args.cmd == "collect":
            collect(con, scope, args.keep_days)
        elif args.cmd == "analyze":
            data = analyze(con, scope, args.alert_growth, save=True)
            report(data)
            if args.export:
                export_csv(data)
        elif args.cmd == "export":
            export_csv(analyze(con, scope, send_alerts=False))
        elif args.cmd == "run":
            run_once(con, scope, args.alert_growth, args.export, args.keep_days)
        elif args.cmd == "watch":
            while True:
                run_once(con, scope, args.alert_growth, args.export, args.keep_days)
                say(f"\nNext scan in {args.interval:g} hours.")
                time.sleep(args.interval * 3600)
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}")
    except KeyboardInterrupt:
        say("\nStopped.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
