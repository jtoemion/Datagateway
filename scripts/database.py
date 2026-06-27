#!/usr/bin/env python3
"""
Datagateway — Database layer
SQLite cache for RSS responses, article dedup, and dashboard queries.
"""

import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "datagateway.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    name        TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    lang        TEXT DEFAULT 'id',
    category    TEXT DEFAULT 'umum',
    last_fetched TEXT,
    etag        TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS articles (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL REFERENCES sources(name),
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    description TEXT DEFAULT '',
    image_url   TEXT DEFAULT '',
    date        TEXT NOT NULL,
    date_wib    TEXT,
    category    TEXT DEFAULT 'umum',
    lang        TEXT DEFAULT 'id',
    filepath    TEXT,
    wikilink    TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(url)
);

CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);

CREATE TABLE IF NOT EXISTS cache (
    cache_key   TEXT PRIMARY KEY,
    body        TEXT,
    status_code INTEGER,
    fetched_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    etag        TEXT
);

CREATE TABLE IF NOT EXISTS fetch_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    article_count INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'ok',
    error_msg   TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS football_events (
    event_id      TEXT PRIMARY KEY,
    sport_id      INTEGER DEFAULT 18,
    event_date    TEXT NOT NULL,
    event_status  TEXT DEFAULT 'STATUS_SCHEDULED',
    status_detail TEXT DEFAULT 'Scheduled',
    team_away_id  INTEGER,
    team_away     TEXT,
    team_away_abbr TEXT,
    team_home_id  INTEGER,
    team_home     TEXT,
    team_home_abbr TEXT,
    score_away    INTEGER DEFAULT 0,
    score_home    INTEGER DEFAULT 0,
    venue_name    TEXT,
    venue_location TEXT,
    broadcast     TEXT,
    season_type   TEXT,
    attendance    TEXT,
    espn_uid      TEXT,
    fetched_at    TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_football_date ON football_events(event_date);

CREATE TABLE IF NOT EXISTS scraped_articles (
    article_id  TEXT PRIMARY KEY REFERENCES articles(id),
    url         TEXT NOT NULL,
    title       TEXT,
    author      TEXT DEFAULT '',
    full_html   TEXT,
    full_text   TEXT,
    images_json TEXT DEFAULT '[]',
    scraped_at  TEXT DEFAULT (datetime('now')),
    fetch_count INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS football_odds (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT NOT NULL REFERENCES football_events(event_id),
    market_id     INTEGER NOT NULL,
    market_name   TEXT,
    affiliate_id  INTEGER,
    affiliate_name TEXT,
    participant_type TEXT,
    participant_name TEXT,
    price_american INTEGER,
    price_decimal  REAL,
    is_main_line   INTEGER DEFAULT 0,
    line_value    REAL,
    updated_at    TEXT,
    UNIQUE(event_id, market_id, affiliate_id, participant_name, line_value)
);

CREATE TABLE IF NOT EXISTS article_metadata (
    article_id TEXT PRIMARY KEY REFERENCES articles(id),
    sections    TEXT DEFAULT '[]',
    keywords    TEXT DEFAULT '[]',
    entities    TEXT DEFAULT '[]',
    word_count  INTEGER DEFAULT 0,
    reading_time INTEGER DEFAULT 0,
    enriched_at  TEXT DEFAULT (datetime('now'))
);"""

# Default sources — sync with config.yaml
DEFAULT_SOURCES = [
    ("CNN Indonesia", "https://www.cnnindonesia.com/rss", "id", "umum"),
    ("Detik", "https://news.detik.com/rss", "id", "umum"),
    ("CNBC Indonesia", "https://www.cnbcindonesia.com/rss", "id", "bisnis"),
    ("Antara", "https://www.antaranews.com/rss/terkini", "id", "umum"),
    ("Republika", "https://www.republika.co.id/rss", "id", "umum"),
    ("BBC Indonesia", "https://feeds.bbci.co.uk/indonesia/rss.xml", "id", "internasional"),
    ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml", "en", "internasional"),
    ("NY Times", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "en", "internasional"),
    # Football news
    ("BBC Football", "https://feeds.bbci.co.uk/sport/football/rss.xml", "en", "football"),
    ("Sky Sports Football", "https://www.skysports.com/rss/12040", "en", "football"),
    ("The Guardian Football", "https://www.theguardian.com/football/rss", "en", "football"),
    ("Fox Sports Soccer", "https://api.foxsports.com/v1/rss?partnerKey=zBaFxRyGKCfxBagJG9b8MjLy&tag=soccer", "en", "football"),
    ("NY Times Soccer", "https://rss.nytimes.com/services/xml/rss/nyt/Soccer.xml", "en", "football"),
]


def get_db() -> sqlite3.Connection:
    """Get SQLite connection with row factory."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    """Initialize schema and seed sources."""
    db = get_db()
    db.executescript(SCHEMA)

    # Seed sources
    for name, url, lang, cat in DEFAULT_SOURCES:
        db.execute(
            """INSERT OR IGNORE INTO sources (name, url, lang, category)
               VALUES (?, ?, ?, ?)""",
            (name, url, lang, cat),
        )
    db.commit()
    db.close()


def cache_get(key: str, ttl_seconds: int = 1800) -> str | None:
    """Get cached response if not expired. ttl defaults to 30 min."""
    db = get_db()
    row = db.execute(
        "SELECT body, fetched_at FROM cache WHERE cache_key = ? AND expires_at > ?",
        (key, time.time()),
    ).fetchone()
    db.close()
    if row:
        return row["body"]
    return None


def cache_set(key: str, body: str, status_code: int = 200, ttl_seconds: int = 1800, etag: str = ""):
    """Store response in cache with TTL."""
    now = time.time()
    db = get_db()
    db.execute(
        """INSERT OR REPLACE INTO cache (cache_key, body, status_code, fetched_at, expires_at, etag)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (key, body, status_code, now, now + ttl_seconds, etag),
    )
    db.commit()
    db.close()


def cache_clear():
    """Clear expired cache entries."""
    db = get_db()
    deleted = db.execute("DELETE FROM cache WHERE expires_at < ?", (time.time(),)).rowcount
    db.commit()
    db.close()
    return deleted


def article_upsert(art: dict) -> bool:
    """Insert or update article. Returns True if new, False if duplicate."""
    db = get_db()
    try:
        db.execute(
            """INSERT OR IGNORE INTO articles
               (id, source, title, url, description, image_url, date, date_wib, category, lang, filepath, wikilink)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                art["id"],
                art["source"],
                art["title"],
                art["url"],
                art.get("description", ""),
                art.get("image_url", ""),
                art["date"],
                art.get("date_wib", ""),
                art.get("category", "umum"),
                art.get("lang", "id"),
                art.get("filepath", ""),
                art.get("wikilink", ""),
            ),
        )
        db.commit()
        is_new = db.total_changes > 0
        db.close()
        return is_new
    except sqlite3.IntegrityError:
        db.close()
        return False


def article_exists(url: str) -> bool:
    """Check if article URL already stored."""
    db = get_db()
    row = db.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone()
    db.close()
    return row is not None


def get_articles(limit: int = 200, offset: int = 0) -> list[dict]:
    """Get articles for dashboard, newest first."""
    db = get_db()
    rows = db.execute(
        """SELECT id, source, title, url, description as excerpt,
                  image_url, date, date_wib, category, lang, filepath, wikilink
           FROM articles
           ORDER BY date DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_article_count() -> int:
    """Total article count."""
    db = get_db()
    row = db.execute("SELECT COUNT(*) as cnt FROM articles").fetchone()
    db.close()
    return row["cnt"] if row else 0


def get_today_count() -> int:
    """Article count for today."""
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM articles WHERE date LIKE ?", (f"{today}%",)
    ).fetchone()
    db.close()
    return row["cnt"] if row else 0


def get_articles_with_meta(limit: int = 500) -> list[dict]:
    """Get articles with enriched metadata (keywords, sections)."""
    db = get_db()
    rows = db.execute(
        """SELECT a.id, a.source, a.title, a.url, a.description as excerpt,
                  a.image_url, a.date, a.date_wib, a.category, a.lang, a.filepath, a.wikilink,
                  m.keywords, m.sections, m.word_count
           FROM articles a
           LEFT JOIN article_metadata m ON a.id = m.article_id
           ORDER BY a.date DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        import json
        if isinstance(d.get("keywords"), str):
            d["keywords"] = json.loads(d["keywords"]) if d["keywords"] else []
        if isinstance(d.get("sections"), str):
            d["sections"] = json.loads(d["sections"]) if d["sections"] else []
        result.append(d)
    db.close()
    return result


def get_source_stats() -> list[dict]:
    """Article count per source."""
    db = get_db()
    rows = db.execute(
        """SELECT source, COUNT(*) as count FROM articles
           GROUP BY source ORDER BY count DESC"""
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_category_stats() -> list[dict]:
    """Article count per category."""
    db = get_db()
    rows = db.execute(
        """SELECT category, COUNT(*) as count FROM articles
           GROUP BY category ORDER BY count DESC"""
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def log_fetch(source: str, count: int, status: str = "ok", error: str = ""):
    """Log a fetch event."""
    db = get_db()
    db.execute(
        "INSERT INTO fetch_log (source, fetched_at, article_count, status, error_msg) VALUES (?, ?, ?, ?, ?)",
        (source, datetime.now(WIB).isoformat(), count, status, error),
    )
    db.commit()
    db.close()


def get_last_fetch_times() -> dict:
    """Get last fetch time per source."""
    db = get_db()
    rows = db.execute(
        """SELECT source, MAX(fetched_at) as last_fetch
           FROM fetch_log WHERE status = 'ok'
           GROUP BY source"""
    ).fetchall()
    db.close()
    return {r["source"]: r["last_fetch"] for r in rows}


def get_latest_date() -> str:
    """Get latest article date."""
    db = get_db()
    row = db.execute("SELECT date FROM articles ORDER BY date DESC LIMIT 1").fetchone()
    db.close()
    return row["date"][:10] if row else "—"


def close():
    """Cleanup expired cache."""
    cache_clear()


def article_scraped_exists(article_id: str) -> bool:
    db = get_db()
    row = db.execute("SELECT 1 FROM scraped_articles WHERE article_id = ?", (article_id,)).fetchone()
    db.close()
    return row is not None


def article_save_scraped(article_id: str, url: str, title: str, author: str, full_html: str, full_text: str, images: list):
    import json
    db = get_db()
    exists = db.execute("SELECT fetch_count FROM scraped_articles WHERE article_id = ?", (article_id,)).fetchone()
    if exists:
        db.execute("""UPDATE scraped_articles
            SET fetch_count = fetch_count + 1,
                scraped_at = datetime('now'),
                full_html = ?, full_text = ?, images_json = ?, title = COALESCE(?, title), author = COALESCE(?, author)
            WHERE article_id = ?""",
            (full_html, full_text, json.dumps(images), title, author, article_id))
    else:
        db.execute("""INSERT INTO scraped_articles (article_id, url, title, author, full_html, full_text, images_json) VALUES (?,?,?,?,?,?,?)""",
            (article_id, url, title, author, full_html, full_text, json.dumps(images)))
    db.commit()
    db.close()


def get_scraped_article(article_id: str) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM scraped_articles WHERE article_id = ?", (article_id,)).fetchone()
    db.close()
    return dict(row) if row else None


# ─── Football helpers ───

def football_upsert_event(e: dict) -> bool:
    """Insert or update a football event."""
    db = get_db()
    try:
        db.execute("""INSERT OR REPLACE INTO football_events
           (event_id, sport_id, event_date, event_status, status_detail,
            team_away_id, team_away, team_away_abbr,
            team_home_id, team_home, team_home_abbr,
            score_away, score_home, venue_name, venue_location,
            broadcast, season_type, attendance, espn_uid)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (e["event_id"], e.get("sport_id", 18), e["event_date"],
             e.get("event_status", "STATUS_SCHEDULED"), e.get("status_detail", ""),
             e.get("team_away_id"), e.get("team_away"), e.get("team_away_abbr"),
             e.get("team_home_id"), e.get("team_home"), e.get("team_home_abbr"),
             e.get("score_away", 0), e.get("score_home", 0),
             e.get("venue_name"), e.get("venue_location"),
             e.get("broadcast"), e.get("season_type"), e.get("attendance"),
             e.get("espn_uid")))
        db.commit()
        db.close()
        return True
    except Exception:
        db.close()
        return False


def football_upsert_odds(odds: dict) -> bool:
    """Insert a single odds row."""
    db = get_db()
    try:
        db.execute("""INSERT OR IGNORE INTO football_odds
           (event_id, market_id, market_name, affiliate_id, affiliate_name,
            participant_type, participant_name, price_american, price_decimal,
            is_main_line, line_value, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (odds["event_id"], odds["market_id"], odds.get("market_name"),
             odds.get("affiliate_id"), odds.get("affiliate_name"),
             odds.get("participant_type"), odds.get("participant_name"),
             odds.get("price_american"), odds.get("price_decimal"),
             odds.get("is_main_line", 0), odds.get("line_value"),
             odds.get("updated_at")))
        db.commit()
        db.close()
        return True
    except Exception:
        db.close()
        return False


def get_football_events(status: str = None) -> list[dict]:
    """Get football events, ordered by date. Optionally filter by status."""
    db = get_db()
    if status:
        rows = db.execute(
            "SELECT * FROM football_events WHERE event_status = ? ORDER BY event_date ASC",
            (status,)).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM football_events ORDER BY event_date ASC").fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_football_odds(event_id: str, market_id: int = None) -> list[dict]:
    """Get odds for an event, optionally filtered by market."""
    db = get_db()
    if market_id:
        rows = db.execute(
            "SELECT * FROM football_odds WHERE event_id = ? AND market_id = ? ORDER BY affiliate_id",
            (event_id, market_id)).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM football_odds WHERE event_id = ? ORDER BY market_id, affiliate_id",
            (event_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_football_count() -> int:
    """Total football events count."""
    db = get_db()
    row = db.execute("SELECT COUNT(*) as cnt FROM football_events").fetchone()
    db.close()
    return row["cnt"] if row else 0


def get_next_football_match() -> dict | None:
    """Get the next upcoming scheduled match."""
    db = get_db()
    row = db.execute(
        """SELECT * FROM football_events
           WHERE event_status = 'STATUS_SCHEDULED'
           ORDER BY event_date ASC LIMIT 1"""
    ).fetchone()
    db.close()
    return dict(row) if row else None


# ─── Article metadata helpers ─────────────────────────────────────────────────

def get_article_metadata(article_id: str) -> dict | None:
    """Get enriched metadata for an article."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM article_metadata WHERE article_id = ?", (article_id,)
    ).fetchone()
    db.close()
    if not row:
        return None
    import json
    return {
        "article_id": row["article_id"],
        "sections": json.loads(row["sections"] or "[]"),
        "keywords": json.loads(row["keywords"] or "[]"),
        "entities": json.loads(row["entities"] or "[]"),
        "word_count": row["word_count"],
        "reading_time": row["reading_time"],
        "enriched_at": row["enriched_at"],
    }


def save_article_metadata(
    article_id: str,
    sections: list,
    keywords: list,
    entities: list,
    word_count: int,
):
    """Save or update enriched metadata for an article."""
    import json
    reading_time = max(1, round(word_count / 200))
    db = get_db()
    db.execute(
        """INSERT OR REPLACE INTO article_metadata
           (article_id, sections, keywords, entities, word_count, reading_time, enriched_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
        (article_id, json.dumps(sections), json.dumps(keywords),
         json.dumps(entities), word_count, reading_time),
    )
    db.commit()
    db.close()


def get_articles_with_metadata(limit: int = 200, offset: int = 0) -> list[dict]:
    """Get articles enriched with metadata for dashboard."""
    import json
    db = get_db()
    rows = db.execute(
        """SELECT a.id, a.source, a.title, a.url,
                  a.description as excerpt, a.image_url, a.date, a.date_wib,
                  a.category, a.lang, a.filepath, a.wikilink,
                  m.sections, m.keywords, m.word_count, m.reading_time
           FROM articles a
           LEFT JOIN article_metadata m ON a.id = m.article_id
           ORDER BY a.date DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()
    db.close()
    result = []
    for r in rows:
        d = dict(r)
        d["sections"] = json.loads(d["sections"] or "[]") if d.get("sections") else []
        d["keywords"] = json.loads(d["keywords"] or "[]") if d.get("keywords") else []
        result.append(d)
    return result

